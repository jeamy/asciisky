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
import signal
import logging
from datetime import datetime, timezone
from typing import Dict, Any

# RabbitMQ
import pika

# ASCII Sky
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bright_asteroids
import comets
from cache_utils import normalize_location, location_key, time_bucket_utc
from db_utils import (
    database_target,
    database_identity,
    get_asteroid_positions,
    get_comet_positions,
    get_sunpath_year,
    store_asteroid_positions,
    store_comet_positions,
    store_sunpath_year,
    computation_lock,
)
from api.computation import compute_sunpath_year

# Worker Utils (same directory)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import worker_utils
from worker_utils import SharedSkyfieldResources

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Worker ID (für Logging)
import socket
_worker_id_env = os.getenv('WORKER_ID', '')
# Fallback wenn Docker Swarm Template nicht aufgelöst wurde
if '{{' in _worker_id_env or _worker_id_env == '':
    WORKER_ID = f"precompute-worker-{socket.gethostname()}"
else:
    WORKER_ID = _worker_id_env

# Global resources instance
shared_resources = None

# Graceful shutdown flag
_shutdown_requested = False
_active_connection = None
_active_channel = None


def _signal_handler(signum, frame):
    """Handler für graceful shutdown bei SIGTERM/SIGINT"""
    global _shutdown_requested
    logger.info(f"[{WORKER_ID}] Received signal {signum}, shutting down gracefully...")
    _shutdown_requested = True
    try:
        if _active_connection and _active_connection.is_open and _active_channel and _active_channel.is_open:
            _active_connection.add_callback_threadsafe(_active_channel.stop_consuming)
    except Exception as e:
        logger.debug(f"[{WORKER_ID}] Could not schedule consumer shutdown: {e}")



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

        # Magnitude ist optional (Sunpath-Tasks, alte Tasks ohne Feld, etc.)
        mag_raw = task.get('magnitude', None)
        if isinstance(mag_raw, (int, float)):
            magnitude = float(mag_raw)
        else:
            # Default wie im Coordinator für Asteroiden; für Kometen/Sunpath wird es aktuell nicht verwendet
            magnitude = 20.0

        lat = location['latitude']
        lon = location['longitude']
        elevation = location['elevation']
        name = location.get('name', 'Unknown')

        # Parse Zeit (robust für verschiedene Formate)
        time_str = time_bucket_str.replace('Z', '+00:00')
        dt_utc = datetime.fromisoformat(time_str)
        # Stelle sicher dass Timezone gesetzt ist
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)

        logger.info(f"[{WORKER_ID}] Processing {kind} for {name} ({lat:.4f}, {lon:.4f}) at {time_bucket_str}")

        # Berechne Positionen
        start_time = time.time()

        # Normalisierte Location nur einmal berechnen
        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        computation_key = f"precompute_{kind}:{loc_key}:{time_bucket_str}"
        logger.debug(f"[{WORKER_ID}] Computation key: {computation_key}")

        try:
            with computation_lock(computation_key, ttl_seconds=300):
                logger.debug(f"[{WORKER_ID}] Acquired advisory lock for {computation_key}")

                tb = worker_utils.position_time_bucket(dt_utc)
                existing = (
                    get_asteroid_positions(loc_key, tb) if kind == 'asteroids'
                    else get_comet_positions(loc_key, tb) if kind == 'comets'
                    else get_sunpath_year(loc_key, str(dt_utc.year)) if kind == 'sunpath'
                    else None
                )
                cache_complete = (
                    existing is not None if kind == 'sunpath'
                    else isinstance(existing, list) and len(existing) > 0
                )
                if cache_complete:
                    logger.info("[%s] Skipping duplicate cached task %s", WORKER_ID, computation_key)
                    return True

                if kind == 'asteroids':
                    # Use shared resources
                    loader, ts, eph, asteroid_df, _ = shared_resources.get_resources()

                    observer_loc = {
                        'latitude': lat_norm,
                        'longitude': lon_norm,
                        'elevation': elev_norm
                    }

                    max_mag = min(magnitude, bright_asteroids.MAX_APPARENT_MAGNITUDE)
                    asteroids_data = bright_asteroids.load_bright_asteroids(
                        loader,
                        ts,
                        eph,
                        observer_loc,
                        max_magnitude=max_mag,
                        current_dt=dt_utc,
                        dataframe=asteroid_df  # Pass pre-loaded dataframe
                    )

                    if asteroids_data:
                        store_asteroid_positions(
                            0,
                            loc_key,
                            tb,
                            lat_norm,
                            lon_norm,
                            elev_norm,
                            asteroids_data
                        )
                        count = len(asteroids_data)
                    else:
                        logger.error("[%s] Asteroid computation returned no objects for %s", WORKER_ID, computation_key)
                        return False

                elif kind == 'comets':
                    # Use shared resources
                    loader, ts, eph, _, comet_df = shared_resources.get_resources()

                    observer_loc = {
                        'latitude': lat_norm,
                        'longitude': lon_norm,
                        'elevation': elev_norm
                    }

                    comets_data = comets.load_comets(
                        ts,
                        eph,
                        observer_loc,
                        max_comets=100,
                        current_dt=dt_utc,
                        dataframe=comet_df  # Pass pre-loaded dataframe
                    )

                    if comets_data:
                        store_comet_positions(
                            0,
                            loc_key,
                            tb,
                            lat_norm,
                            lon_norm,
                            elev_norm,
                            comets_data
                        )
                        count = len(comets_data)
                    else:
                        logger.error("[%s] Comet computation returned no objects for %s", WORKER_ID, computation_key)
                        return False

                elif kind == 'sunpath':
                    year = dt_utc.year
                    result = compute_sunpath_year(lat, lon, elevation, year)

                    year_bucket = str(year)
                    store_sunpath_year(loc_key, year_bucket, lat, lon, elevation, result)
                    count = len(result.get('points', []))

                else:
                    logger.error(f"Unknown kind: {kind}")
                    return False

        except Exception as e:
            logger.error(f"[{WORKER_ID}] Failed to acquire advisory lock for {computation_key}: {e}")
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
            try:
                from db_utils import release_precompute_task
                release_precompute_task(worker_utils.precompute_task_key(task))
            except Exception:
                logger.exception("Could not release precompute claim")
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
    logger.info("PostgreSQL target: %s", database_target())
    logger.info("=" * 60)

    # Konfiguration
    prefetch_count = int(os.getenv('RABBITMQ_PREFETCH_COUNT', '1'))

    logger.info(f"Configuration:")
    logger.info(f"  - Worker ID: {WORKER_ID}")
    logger.info(f"  - Prefetch Count: {prefetch_count}")
    try:
        logger.info("Actual PostgreSQL server: %s", database_identity())
    except Exception as exc:
        logger.warning("Could not read PostgreSQL server identity: %s", exc)

    # Initialize Shared Resources
    global shared_resources, _active_connection, _active_channel
    shared_resources = SharedSkyfieldResources()

    rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://admin:changeme@localhost:5672/')

    # Signal Handler für graceful shutdown
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    while not _shutdown_requested:
        try:
            # Verbinde zu RabbitMQ
            connection = worker_utils.setup_rabbitmq_connection(rabbitmq_url, heartbeat=0)
            if not connection:
                logger.error("Cannot connect to RabbitMQ - retrying in 10s...")
                _wait_for_shutdown(10)
                continue

            channel = connection.channel()
            _active_connection = connection
            _active_channel = channel

            # Deklariere alle Queues
            logger.info(f"[{WORKER_ID}] Declaring queues...")
            worker_utils.declare_computation_queues(channel)
            logger.info(f"[{WORKER_ID}] ✅ All queues declared")

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

            if _shutdown_requested:
                logger.info(f"[{WORKER_ID}] Shutdown requested, stopping consumer...")
                try:
                    channel.stop_consuming()
                except Exception:
                    pass
                break

        except KeyboardInterrupt:
            logger.info(f"[{WORKER_ID}] Worker stopped by user")
            break

        except Exception as e:
            if _shutdown_requested:
                break
            logger.error(f"[{WORKER_ID}] Worker error: {e}", exc_info=True)
            logger.info("Reconnecting in 10 seconds...")
            _wait_for_shutdown(10)
        finally:
            try:
                if _active_connection and _active_connection.is_open:
                    _active_connection.close()
            except Exception:
                pass
            _active_channel = None
            _active_connection = None

    logger.info(f"[{WORKER_ID}] Worker stopped")


def _wait_for_shutdown(seconds):
    """Interruptible retry delay."""
    deadline = time.monotonic() + seconds
    while not _shutdown_requested and time.monotonic() < deadline:
        time.sleep(max(0.0, min(0.25, deadline - time.monotonic())))


# Removed: wait_for_database() - now using worker_utils.wait_for_database()


if __name__ == '__main__':
    # Warte bis Daten vorhanden sind
    if not worker_utils.wait_for_database(WORKER_ID, check_both=True):
        sys.exit(1)

    # Starte Worker
    main()
