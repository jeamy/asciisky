#!/usr/bin/env python3
"""
Precompute Coordinator - RabbitMQ-basierte Lösung
==================================================

Statt manueller Location-Aufteilung:
- Coordinator erstellt Tasks für alle Locations/Zeiten
- Publiziert Tasks in RabbitMQ Queue
- Beliebig viele Worker holen sich Tasks (Fair Dispatch)
- Automatische Lastverteilung durch RabbitMQ

Vorteile:
- ✅ Keine Duplikate (jeder Task wird nur 1x bearbeitet)
- ✅ Automatische Lastverteilung
- ✅ Einfach skalierbar (mehr Worker = schneller)
- ✅ Failover (Worker fällt aus → anderer übernimmt)
"""

import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

# RabbitMQ
import pika

# Settings
import settings
from cache_utils import normalize_location

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_rabbitmq_connection():
    """Erstelle RabbitMQ-Verbindung"""
    rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://admin:changeme@localhost:5672/')
    
    try:
        params = pika.URLParameters(rabbitmq_url)
        params.heartbeat = int(os.getenv('RABBITMQ_HEARTBEAT', '60'))
        connection = pika.BlockingConnection(params)
        return connection
    except Exception as e:
        logger.error(f"Failed to connect to RabbitMQ: {e}")
        return None


def get_target_locations() -> List[Dict[str, Any]]:
    """
    Hole alle Locations die vorberechnet werden sollen.
    
    Quellen (in Reihenfolge):
    1. user_settings.json (persönliche Location)
    2. precompute_locations.json (konfigurierte Locations)
    3. Environment Variable ASCII_SKY_PRECOMPUTE_LOCATIONS
    """
    locations = []
    
    # 1. User Location
    try:
        user_loc = settings.get_location()
        if user_loc and 'latitude' in user_loc and 'longitude' in user_loc:
            locations.append({
                'latitude': float(user_loc['latitude']),
                'longitude': float(user_loc['longitude']),
                'elevation': float(user_loc.get('elevation', 0)),
                'name': user_loc.get('name', 'User Location')
            })
            logger.info(f"Added user location: {user_loc.get('name', 'Unknown')}")
    except Exception as e:
        logger.warning(f"Could not load user location: {e}")
    
    # 2. precompute_locations.json
    try:
        locations_file = os.path.join(os.getcwd(), 'precompute_locations.json')
        if os.path.exists(locations_file):
            with open(locations_file, 'r') as f:
                file_locs = json.load(f)
                for loc in file_locs:
                    locations.append({
                        'latitude': float(loc['latitude']),
                        'longitude': float(loc['longitude']),
                        'elevation': float(loc.get('elevation', 0)),
                        'name': loc.get('name', 'Unknown')
                    })
                logger.info(f"Added {len(file_locs)} locations from precompute_locations.json")
    except Exception as e:
        logger.warning(f"Could not load precompute_locations.json: {e}")
    
    # 3. Environment Variable
    try:
        env_locs = os.getenv('ASCII_SKY_PRECOMPUTE_LOCATIONS')
        if env_locs:
            env_locs_parsed = json.loads(env_locs)
            for loc in env_locs_parsed:
                locations.append({
                    'latitude': float(loc['latitude']),
                    'longitude': float(loc['longitude']),
                    'elevation': float(loc.get('elevation', 0)),
                    'name': loc.get('name', 'Unknown')
                })
            logger.info(f"Added {len(env_locs_parsed)} locations from environment")
    except Exception as e:
        logger.warning(f"Could not parse ASCII_SKY_PRECOMPUTE_LOCATIONS: {e}")
    
    # Dedupliziere Locations (gleiche Koordinaten)
    unique_locations = []
    seen = set()
    for loc in locations:
        # Normalisiere auf 3 Dezimalstellen (~111m Genauigkeit)
        # Ausreichend für astronomische Zwecke, vermeidet GPS-Ungenauigkeiten
        key = (round(loc['latitude'], 3), round(loc['longitude'], 3))
        if key not in seen:
            seen.add(key)
            unique_locations.append(loc)
    
    logger.info(f"Total unique locations: {len(unique_locations)}")
    return unique_locations


def create_precompute_tasks(locations: List[Dict], hours_ahead: int = 720) -> List[Dict]:
    """
    Erstelle Precompute-Tasks für alle Locations und Zeitfenster.
    
    Args:
        locations: Liste von Location-Dicts
        hours_ahead: Wie viele Stunden voraus berechnen (default: 720 = 30 Tage)
    
    Returns:
        Liste von Task-Dicts für RabbitMQ
    """
    from cache_utils import normalize_location, location_key, time_bucket_utc
    from db_utils import get_asteroid_positions, get_comet_positions
    
    tasks = []
    skipped = 0
    now = datetime.now(timezone.utc)
    
    # Runde auf volle Stunde
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    
    for location in locations:
        lat = location['latitude']
        lon = location['longitude']
        elevation = location['elevation']
        name = location.get('name', 'Unknown')
        
        # Normalisiere Location für Cache-Lookup
        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        
        # Erstelle Tasks für jede Stunde
        for hour_offset in range(hours_ahead):
            target_time = current_hour + timedelta(hours=hour_offset)
            bucket = time_bucket_utc(target_time, 1)  # 1-hour buckets
            
            # Priorität: Nächste 24h = HIGH (10), danach NORMAL (5)
            priority = 10 if hour_offset < 24 else 5
            
            # Prüfe ob Asteroiden-Daten schon vorhanden
            asteroid_cached = False
            try:
                cached = get_asteroid_positions(loc_key, bucket, None)
                asteroid_cached = cached is not None and len(cached) > 0
            except Exception:
                pass
            
            # Task für Asteroiden nur wenn nicht gecached
            if not asteroid_cached:
                tasks.append({
                    'kind': 'asteroids',
                    'location': {
                        'latitude': lat,
                        'longitude': lon,
                        'elevation': elevation,
                        'name': name
                    },
                    'time_bucket': target_time.isoformat(),
                    'magnitude': 20.0,  # Asteroid max magnitude
                    'priority': priority
                })
            else:
                skipped += 1
            
            # Prüfe ob Kometen-Daten schon vorhanden
            comet_cached = False
            try:
                cached = get_comet_positions(loc_key, bucket, None)
                comet_cached = cached is not None and len(cached) > 0
            except Exception:
                pass
            
            # Task für Kometen nur wenn nicht gecached
            if not comet_cached:
                tasks.append({
                    'kind': 'comets',
                    'location': {
                        'latitude': lat,
                        'longitude': lon,
                        'elevation': elevation,
                        'name': name
                    },
                    'time_bucket': target_time.isoformat(),
                    'magnitude': 14.0,  # Comet max magnitude
                    'priority': priority
                })
            else:
                skipped += 1
    
    total_possible = len(locations) * hours_ahead * 2
    logger.info(f"Created {len(tasks)} precompute tasks (skipped {skipped} already cached, total {total_possible})")
    return tasks


def publish_tasks_to_rabbitmq(tasks: List[Dict], batch_size: int = 100):
    """
    Publiziere Tasks in RabbitMQ Queue.
    
    Args:
        tasks: Liste von Task-Dicts
        batch_size: Wie viele Tasks pro Batch (für Progress-Logging)
    """
    connection = get_rabbitmq_connection()
    if not connection:
        logger.error("Cannot publish tasks - no RabbitMQ connection")
        return False
    
    try:
        channel = connection.channel()
        
        # Deklariere Queue (falls noch nicht vorhanden)
        channel.queue_declare(
            queue='precompute.tasks',
            durable=True,
            arguments={
                'x-max-priority': 10  # Priority Queue
            }
        )
        
        # Publiziere Tasks
        published = 0
        for i, task in enumerate(tasks):
            try:
                channel.basic_publish(
                    exchange='',
                    routing_key='precompute.tasks',
                    body=json.dumps(task),
                    properties=pika.BasicProperties(
                        delivery_mode=2,  # Persistent
                        priority=task.get('priority', 5)
                    )
                )
                published += 1
                
                # Progress-Logging
                if (i + 1) % batch_size == 0:
                    logger.info(f"Published {i + 1}/{len(tasks)} tasks...")
            
            except Exception as e:
                logger.error(f"Failed to publish task {i}: {e}")
        
        connection.close()
        logger.info(f"✅ Published {published}/{len(tasks)} tasks to RabbitMQ")
        return True
    
    except Exception as e:
        logger.error(f"Failed to publish tasks: {e}")
        if connection:
            connection.close()
        return False


def main():
    """Hauptfunktion - läuft stündlich"""
    logger.info("=" * 60)
    logger.info("Precompute Coordinator - Starting")
    logger.info("=" * 60)
    
    # Konfiguration
    hours_ahead = int(os.getenv('ASCII_SKY_PRECOMPUTE_HOURS', '720'))
    run_interval = int(os.getenv('PRECOMPUTE_COORDINATOR_INTERVAL', '3600'))  # 1 Stunde
    retry_interval = int(os.getenv('PRECOMPUTE_COORDINATOR_RETRY_INTERVAL', '30'))  # 30 Sekunden
    
    logger.info(f"Configuration:")
    logger.info(f"  - Hours ahead: {hours_ahead}")
    logger.info(f"  - Run interval: {run_interval}s")
    logger.info(f"  - Retry interval: {retry_interval}s (on failure)")
    
    first_run = True
    
    while True:
        try:
            # 1. Hole Locations
            locations = get_target_locations()
            
            if not locations:
                logger.warning("No locations configured - skipping this run")
                sleep_time = retry_interval if first_run else run_interval
                logger.info(f"Sleeping for {sleep_time}s...")
                time.sleep(sleep_time)
                continue
            
            # 2. Erstelle Tasks
            tasks = create_precompute_tasks(locations, hours_ahead)
            
            # 3. Publiziere in RabbitMQ
            success = publish_tasks_to_rabbitmq(tasks)
            
            if success:
                logger.info(f"✅ Coordinator run completed successfully")
                first_run = False
                # Bei Erfolg: Normales Intervall
                logger.info(f"Sleeping for {run_interval}s until next run...")
                time.sleep(run_interval)
            else:
                logger.error(f"❌ Coordinator run failed")
                # Bei Fehler: Kurzes Retry-Intervall (besonders beim ersten Start)
                sleep_time = retry_interval if first_run else 300  # 30s beim Start, 5min später
                logger.info(f"Retrying in {sleep_time}s...")
                time.sleep(sleep_time)
        
        except KeyboardInterrupt:
            logger.info("Coordinator stopped by user")
            break
        
        except Exception as e:
            logger.error(f"Coordinator error: {e}", exc_info=True)
            sleep_time = retry_interval if first_run else 60
            logger.info(f"Retrying in {sleep_time}s...")
            time.sleep(sleep_time)


if __name__ == '__main__':
    main()
