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
import signal
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

# RabbitMQ
import pika

# Settings
import settings
from cache_utils import normalize_location, location_key, time_bucket_utc
from db_utils import get_asteroid_positions, get_comet_positions, get_sunpath_year, get_all_user_locations

# Worker Utils
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workers'))
import worker_utils

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Graceful shutdown flag
_shutdown_requested = False
_queued_task_keys = set()


def _signal_handler(signum, frame):
    """Handler für graceful shutdown bei SIGTERM/SIGINT"""
    global _shutdown_requested
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    _shutdown_requested = True


def _wait_for_shutdown(seconds):
    """Interruptible scheduler delay."""
    deadline = time.monotonic() + seconds
    while not _shutdown_requested and time.monotonic() < deadline:
        time.sleep(max(0.0, min(0.25, deadline - time.monotonic())))


def get_rabbitmq_connection():
    """Erstelle RabbitMQ-Verbindung"""
    rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://admin:changeme@127.0.0.1:5672/')
    heartbeat = int(os.getenv('RABBITMQ_HEARTBEAT', '60'))
    return worker_utils.setup_rabbitmq_connection(rabbitmq_url, heartbeat=heartbeat)


def get_queue_status() -> int:
    """
    Prüfe die Anzahl der Nachrichten in der Queue.
    Returns: Anzahl der Messages oder -1 bei Fehler
    """
    connection = get_rabbitmq_connection()
    if not connection:
        return -1

    try:
        channel = connection.channel()
        # Passive=True prüft nur Existenz und Metadaten, erstellt nicht neu
        queue = channel.queue_declare(queue='precompute.tasks', passive=True)
        count = queue.method.message_count
        return count
    except Exception as e:
        # Queue existiert vielleicht noch nicht
        logger.debug(f"Queue check failed: {e}")
        return 0  # Annahme: Leer wenn nicht existent
    finally:
        try:
            if connection and connection.is_open:
                connection.close()
        except Exception:
            pass


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

    # 2b. User-Locations aus der Datenbank (user_settings)
    try:
        db_locations = get_all_user_locations()
        if db_locations:
            locations.extend(db_locations)
            logger.info(f"Added {len(db_locations)} locations from user_settings in database")
    except Exception as e:
        logger.warning(f"Could not load user locations from database: {e}")

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


def get_existing_queue_tasks() -> set:
    """
    Hole alle Tasks, die bereits in der precompute.tasks Queue sind.

    Tracks tasks published by this coordinator process. Completed tasks are
    removed from this set when their database cache is observed.

    Returns:
        Snapshot der von diesem Prozess bereits publizierten Tasks.
    """
    return set(_queued_task_keys)


def task_key(task: Dict[str, Any]) -> str:
    """Return the same deterministic key used while creating tasks."""
    location = task['location']
    lat, lon, elevation = normalize_location(
        location['latitude'], location['longitude'], location['elevation']
    )
    loc = f"{lat:.4f}_{lon:.4f}_{elevation:.0f}"
    kind = task['kind']
    dt = datetime.fromisoformat(task['time_bucket'].replace('Z', '+00:00'))
    bucket = dt.isoformat() if kind == 'sunpath' else time_bucket_utc(dt, 1)
    return f"{kind}_{loc}_{bucket}"


def create_precompute_tasks(locations: List[Dict], start_offset: int, end_offset: int, include_yearly: bool = True) -> List[Dict]:
    """
    Erstelle Precompute-Tasks für alle Locations und Zeitfenster.

    Args:
        locations: Liste von Location-Dicts
        start_offset: Start-Stunde (relativ zu jetzt)
        end_offset: End-Stunde (relativ zu jetzt)
        include_yearly: Ob Sunpath-Tasks (jährlich) erstellt werden sollen

    Returns:
        Liste von Task-Dicts für RabbitMQ
    """
    # DB-Cache-Prüfung reicht für Deduplication; Queue-Drain wurde entfernt
    # (zerstörte Message-Reihenfolge und verursachte Race-Conditions mit Workern)
    existing_tasks = get_existing_queue_tasks()

    tasks = []
    skipped = 0
    skipped_queue = 0  # Bereits in Queue
    total_possible = 0
    now = datetime.now(timezone.utc)

    # Runde auf volle Stunde
    current_hour = now.replace(minute=0, second=0, microsecond=0)

    # Welche Jahre decken wir mit dem Zeithorizont ab?
    covered_years = set()
    if include_yearly:
        covered_years = {
            (current_hour + timedelta(hours=h)).year
            for h in range(start_offset, end_offset)
        }
        if not covered_years:
            covered_years = {current_hour.year}

    for location in locations:
        lat = location['latitude']
        lon = location['longitude']
        elevation = location['elevation']
        name = location.get('name', 'Unknown')

        # Normalisiere Location für Cache-Lookup
        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        loc_key_dup = f"{lat_norm:.4f}_{lon_norm:.4f}_{elev_norm:.0f}"

        # Erstelle Sunpath-Tasks pro Jahr (nur wenn angefordert)
        if include_yearly:
            for target_year in sorted(covered_years):
                year_start = datetime(target_year, 1, 1, tzinfo=timezone.utc)
                task_key = f"sunpath_{loc_key_dup}_{year_start.isoformat()}"
                sunpath_cached = False
                try:
                    cached = get_sunpath_year(loc_key, str(target_year))
                    sunpath_cached = cached is not None
                except Exception:
                    pass

                if not sunpath_cached:
                    total_possible += 1
                    if task_key not in existing_tasks:
                        tasks.append({
                            'kind': 'sunpath',
                            'location': {
                                'latitude': lat,
                                'longitude': lon,
                                'elevation': elevation,
                                'name': name
                            },
                            'time_bucket': year_start.isoformat(),
                            'priority': 10
                        })
                    else:
                        skipped_queue += 1
                else:
                    _queued_task_keys.discard(task_key)
                    skipped += 1

        # Erstelle Tasks für jede Stunde im Fenster
        for hour_offset in range(start_offset, end_offset):
            target_time = current_hour + timedelta(hours=hour_offset)
            bucket = time_bucket_utc(target_time, 1)  # 1-hour buckets
            asteroid_task_key = f"asteroids_{loc_key_dup}_{bucket}"
            comet_task_key = f"comets_{loc_key_dup}_{bucket}"

            # Priorität: Nächste 24h = HIGH (10), danach NORMAL (5)
            priority = 10 if hour_offset < 24 else 5

            # Prüfe ob Asteroiden-Daten schon vorhanden
            asteroid_cached = False
            try:
                cached = get_asteroid_positions(loc_key, bucket)
                asteroid_cached = cached is not None and len(cached) > 0
            except Exception:
                pass

            # Task für Asteroiden nur wenn nicht gecached UND nicht in Queue
            if not asteroid_cached:
                total_possible += 1
                if asteroid_task_key not in existing_tasks:
                    tasks.append({
                        'kind': 'asteroids',
                        'location': {
                            'latitude': lat,
                            'longitude': lon,
                            'elevation': elevation,
                            'name': name
                        },
                        'time_bucket': target_time.isoformat(),
                        'magnitude': 20.0,  # Default max magnitude
                        'priority': priority
                    })
                else:
                    skipped_queue += 1
            else:
                _queued_task_keys.discard(asteroid_task_key)
                skipped += 1

            # Prüfe ob Kometen-Daten schon vorhanden
            comet_cached = False
            try:
                cached = get_comet_positions(loc_key, bucket)
                comet_cached = cached is not None and len(cached) > 0
            except Exception:
                pass

            # Task für Kometen nur wenn nicht gecached UND nicht in Queue
            if not comet_cached:
                total_possible += 1
                if comet_task_key not in existing_tasks:
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
                    skipped_queue += 1
            else:
                _queued_task_keys.discard(comet_task_key)
                skipped += 1

    logger.info(f"Created {len(tasks)} tasks for window +{start_offset}h to +{end_offset}h (skipped {skipped} cached, {skipped_queue} in queue)")
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
                'x-max-priority': 10              # Priority Queue
            }
        )

        # Publiziere Tasks
        published = 0
        for i, task in enumerate(tasks):
            try:
                key = task_key(task)
                channel.basic_publish(
                    exchange='',
                    routing_key='precompute.tasks',
                    body=json.dumps(task),
                    properties=pika.BasicProperties(
                        message_id=hashlib.sha256(key.encode('utf-8')).hexdigest(),
                        delivery_mode=2,  # Persistent
                        priority=task.get('priority', 5)
                    )
                )
                _queued_task_keys.add(key)
                published += 1

                # Progress-Logging
                if (i + 1) % batch_size == 0:
                    logger.info(f"Published {i + 1}/{len(tasks)} tasks...")

            except Exception as e:
                logger.error(f"Failed to publish task {i}: {e}")

        logger.info(f"✅ Published {published}/{len(tasks)} tasks to RabbitMQ")
        return published == len(tasks)

    except Exception as e:
        logger.error(f"Failed to publish tasks: {e}")
        return False

    finally:
        try:
            if connection and connection.is_open:
                connection.close()
        except Exception:
            pass


def main():
    """Hauptfunktion - läuft stündlich"""
    # Signal Handler für graceful shutdown
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

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

    # Smart Scheduling State
    current_horizon = 0
    BATCH_SIZE_HOURS = 24  # Immer 24h Blöcke nachschieben
    QUEUE_THRESHOLD = 50   # Wenn weniger als 50 Tasks, nachschieben

    while not _shutdown_requested:
        try:
            # 1. Hole Locations
            locations = get_target_locations()

            if not locations:
                logger.warning("No locations configured - skipping this run")
                _wait_for_shutdown(retry_interval)
                continue

            # 2. Prüfe Queue-Status
            queue_count = get_queue_status()
            logger.info(f"Current Queue Size: {queue_count} (Horizon: {current_horizon}/{hours_ahead}h)")

            # 3. Entscheidung: Nachschieben oder Warten?
            should_produce = False

            # Fall Fehler: RabbitMQ nicht erreichbar
            if queue_count < 0:
                logger.error("Could not get queue status (RabbitMQ down?) - retrying...")
                _wait_for_shutdown(retry_interval)
                continue

            # Fall A: Queue fast leer UND Horizon noch nicht erreicht -> Nachschieben
            elif queue_count < QUEUE_THRESHOLD and current_horizon < hours_ahead:
                should_produce = True
                logger.info("Queue low - producing next batch...")

            # Fall B: Horizon erreicht -> Warten auf Reset (stündlich)
            elif current_horizon >= hours_ahead:
                logger.info(f"Max horizon ({hours_ahead}h) reached. Waiting for next full cycle.")
                _wait_for_shutdown(run_interval)
                current_horizon = 0  # Reset für nächsten Zyklus
                continue

            # Fall C: Queue noch voll -> Warten
            else:
                logger.info("Queue busy - waiting...")
                _wait_for_shutdown(300)  # 5 Minuten Polling
                continue

            if should_produce:
                start_offset = current_horizon
                end_offset = min(current_horizon + BATCH_SIZE_HOURS, hours_ahead)

                # Sunpath nur im ersten Batch (Stunde 0-24) mitberechnen
                include_yearly = (start_offset == 0)

                tasks = create_precompute_tasks(
                    locations,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    include_yearly=include_yearly
                )

                if tasks:
                    success = publish_tasks_to_rabbitmq(tasks)
                    if success:
                        current_horizon = end_offset
                        # Kurze Pause um RabbitMQ nicht zu fluten
                        _wait_for_shutdown(1)
                    else:
                        logger.error("Failed to publish batch - retrying later")
                        _wait_for_shutdown(retry_interval)
                else:
                    # Keine Tasks (alles gecached), Horizon trotzdem erhöhen
                    current_horizon = end_offset
                    logger.info("Batch skipped (all cached)")

        except KeyboardInterrupt:
            logger.info("Coordinator stopped by user")
            break

        except Exception as e:
            if _shutdown_requested:
                break
            logger.error(f"Coordinator error: {e}", exc_info=True)
            _wait_for_shutdown(retry_interval)

    logger.info("Precompute Coordinator stopped")


if __name__ == '__main__':
    main()
