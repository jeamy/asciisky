#!/usr/bin/env python3
"""
Precompute Worker - Holt Tasks aus RabbitMQ Queue
==================================================

Läuft auf beliebig vielen Servern (Hauptserver oder Worker-Server).
Holt sich automatisch Tasks aus der Queue und berechnet sie.

Features:
- ✅ Fair Dispatch (PREFETCH_COUNT=1)
- ✅ Automatische Lastverteilung
- ✅ Failover (Worker fällt aus → anderer übernimmt)
- ✅ Keine Duplikate (Task wird nur 1x bearbeitet)
"""

import os
import sys
import time
import json
import logging
from datetime import datetime
from typing import Dict, Any

# RabbitMQ
import pika

# ASCII Sky
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bright_asteroids
import comets
from cache_utils import normalize_location, location_key, time_bucket_utc
from db_utils import store_asteroid_positions, store_comet_positions

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Worker ID (für Logging)
WORKER_ID = os.getenv('WORKER_ID', 'precompute-worker-unknown')


def get_rabbitmq_connection():
    """Erstelle RabbitMQ-Verbindung"""
    rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://admin:changeme@localhost:5672/')
    
    try:
        params = pika.URLParameters(rabbitmq_url)
        # Deaktiviere Heartbeat für lange Berechnungen (0 = disabled)
        # Berechnungen können mehrere Minuten dauern
        params.heartbeat = 0
        params.blocked_connection_timeout = 0
        connection = pika.BlockingConnection(params)
        return connection
    except Exception as e:
        logger.error(f"Failed to connect to RabbitMQ: {e}")
        return None


def process_task(task: Dict[str, Any]) -> bool:
    """
    Bearbeite einen Precompute-Task.
    
    Args:
        task: Task-Dict mit kind, location, time_bucket, magnitude
    
    Returns:
        True wenn erfolgreich, False bei Fehler
    """
    try:
        kind = task['kind']
        location = task['location']
        time_bucket_str = task['time_bucket']
        magnitude = task['magnitude']
        
        lat = location['latitude']
        lon = location['longitude']
        elevation = location['elevation']
        name = location.get('name', 'Unknown')
        
        # Parse Zeit
        dt_utc = datetime.fromisoformat(time_bucket_str.replace('Z', '+00:00'))
        
        logger.info(f"[{WORKER_ID}] Processing {kind} for {name} ({lat:.4f}, {lon:.4f}) at {time_bucket_str}")
        
        # Berechne Positionen
        start_time = time.time()
        
        if kind == 'asteroids':
            # Lade und berechne Asteroiden
            from skyfield.api import Loader
            from data_paths import DATA_DIR
            loader = Loader(str(DATA_DIR))
            ts = loader.timescale()
            eph = loader('de421.bsp')  # Nur Dateiname, nicht vollständiger Pfad
            
            # Normalisiere Location (gibt Tuple zurück: (lat, lon, elevation))
            lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
            
            # Erstelle Observer Location Dict für bright_asteroids
            observer_loc = {
                'latitude': lat_norm,
                'longitude': lon_norm,
                'elevation': elev_norm
            }
            
            # Berechne
            asteroids_data = bright_asteroids.load_bright_asteroids(
                loader,
                ts,
                eph,
                observer_loc,
                max_magnitude=magnitude,
                current_dt=dt_utc
            )
            
            # Speichere in DB
            if asteroids_data:
                # Verwende 0 als representative_id (da wir keine asteroid_id haben)
                loc_key = location_key(lat_norm, lon_norm, elev_norm)
                tb = time_bucket_utc(dt_utc)
                store_asteroid_positions(
                    0,  # representative_id
                    loc_key,
                    tb,
                    lat_norm,
                    lon_norm,
                    elev_norm,
                    asteroids_data
                )
                count = len(asteroids_data)
            else:
                count = 0
        
        elif kind == 'comets':
            # Lade und berechne Kometen
            from skyfield.api import Loader
            from data_paths import DATA_DIR
            loader = Loader(str(DATA_DIR))
            ts = loader.timescale()
            eph = loader('de421.bsp')  # Nur Dateiname, nicht vollständiger Pfad
            
            # Normalisiere Location (gibt Tuple zurück: (lat, lon, elevation))
            lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
            
            # Erstelle Observer Location Dict für comets
            observer_loc = {
                'latitude': lat_norm,
                'longitude': lon_norm,
                'elevation': elev_norm
            }
            
            # Berechne
            comets_data = comets.load_comets(
                ts,
                eph,
                observer_loc,
                max_comets=100,  # Limit für Precompute
                current_dt=dt_utc
            )
            
            # Speichere in DB
            if comets_data:
                # Verwende 0 als representative_id (da wir keine comet_id haben)
                loc_key = location_key(lat_norm, lon_norm, elev_norm)
                tb = time_bucket_utc(dt_utc)
                store_comet_positions(
                    0,  # representative_id
                    loc_key,
                    tb,
                    lat_norm,
                    lon_norm,
                    elev_norm,
                    comets_data
                )
                count = len(comets_data)
            else:
                count = 0
        
        else:
            logger.error(f"Unknown kind: {kind}")
            return False
        
        elapsed = time.time() - start_time
        logger.info(f"[{WORKER_ID}] ✅ Completed {kind} for {name}: {count} objects in {elapsed:.2f}s")
        return True
    
    except Exception as e:
        logger.error(f"[{WORKER_ID}] ❌ Task failed: {e}", exc_info=True)
        return False


def callback(ch, method, properties, body):
    """RabbitMQ Callback für eingehende Tasks"""
    try:
        # Parse Task
        task = json.loads(body)
        
        # Bearbeite Task
        success = process_task(task)
        
        if success:
            # ACK (Task erfolgreich)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            # NACK (Task fehlgeschlagen, zurück in Queue)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    except Exception as e:
        logger.error(f"Callback error: {e}", exc_info=True)
        # NACK bei Fehler
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def main():
    """Hauptfunktion - Worker Loop"""
    logger.info("=" * 60)
    logger.info(f"Precompute Worker [{WORKER_ID}] - Starting")
    logger.info("=" * 60)
    
    # Konfiguration
    prefetch_count = int(os.getenv('RABBITMQ_PREFETCH_COUNT', '1'))
    
    logger.info(f"Configuration:")
    logger.info(f"  - Worker ID: {WORKER_ID}")
    logger.info(f"  - Prefetch Count: {prefetch_count}")
    
    while True:
        try:
            # Verbinde zu RabbitMQ
            connection = get_rabbitmq_connection()
            if not connection:
                logger.error("Cannot connect to RabbitMQ - retrying in 10s...")
                time.sleep(10)
                continue
            
            channel = connection.channel()
            
            # Deklariere Queue
            channel.queue_declare(
                queue='precompute.tasks',
                durable=True,
                arguments={
                    'x-max-priority': 10
                }
            )
            
            # Fair Dispatch (nur 1 Task gleichzeitig pro Worker)
            channel.basic_qos(prefetch_count=prefetch_count)
            
            # Starte Consumer
            logger.info(f"[{WORKER_ID}] 🎧 Listening for tasks on queue 'precompute.tasks'...")
            channel.basic_consume(
                queue='precompute.tasks',
                on_message_callback=callback,
                auto_ack=False  # Manuelles ACK
            )
            
            # Blocking Loop
            channel.start_consuming()
        
        except KeyboardInterrupt:
            logger.info(f"[{WORKER_ID}] Worker stopped by user")
            break
        
        except Exception as e:
            logger.error(f"[{WORKER_ID}] Worker error: {e}", exc_info=True)
            logger.info("Reconnecting in 10 seconds...")
            time.sleep(10)


def wait_for_database():
    """Warte bis Daten in PostgreSQL vorhanden sind"""
    from db_utils import get_asteroid_dataframe, get_comet_dataframe
    
    logger.info(f"[{WORKER_ID}] Checking if database has data...")
    
    max_wait = 600  # 10 Minuten
    check_interval = 30  # Alle 30 Sekunden prüfen
    waited = 0
    
    while waited < max_wait:
        try:
            asteroid_df = get_asteroid_dataframe()
            comet_df = get_comet_dataframe()
            
            if asteroid_df and comet_df:
                logger.info(f"[{WORKER_ID}] ✅ Database has data - starting worker")
                return True
            else:
                if waited == 0:
                    logger.info(f"[{WORKER_ID}] ⏳ Waiting for data_updater to populate database...")
                waited += check_interval
                time.sleep(check_interval)
        except Exception as e:
            if waited == 0:
                logger.warning(f"[{WORKER_ID}] Database not ready: {e}")
                logger.info(f"[{WORKER_ID}] ⏳ Waiting for database...")
            waited += check_interval
            time.sleep(check_interval)
    
    logger.error(f"[{WORKER_ID}] ❌ Timeout waiting for database data after {max_wait}s")
    return False


if __name__ == '__main__':
    # Warte bis Daten vorhanden sind
    if not wait_for_database():
        sys.exit(1)
    
    # Starte Worker
    main()
