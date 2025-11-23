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
    store_asteroid_positions,
    store_comet_positions,
    store_sunpath_year,
    computation_lock,
)
from api.computation import compute_sunpath_year

# Worker Utils (same directory)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import worker_utils

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


# Removed: get_rabbitmq_connection() - now using worker_utils.setup_rabbitmq_connection()

import threading

class SharedSkyfieldResources:
    """Shared Skyfield Resources für alle Worker-Instanzen"""
    
    _instance = None
    _initialized = False
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self._initialize_resources()
                    SharedSkyfieldResources._initialized = True
    
    def _initialize_resources(self):
        """Initialisiere Skyfield Resources einmalig mit Memory-Optimierung"""
        try:
            from data_paths import DATA_DIR
            from skyfield.api import Loader
            
            logger.info("Initializing shared Skyfield resources...")
            start_time = time.time()
            
            # Memory-optimierte Loader Konfiguration
            self.loader = Loader(str(DATA_DIR))
            self.loader.verbose = False  # Reduziere Logging Overhead
            
            # Timescale mit optimierter Konfiguration
            self.ts = self.loader.timescale()
            
            # Ephemeriden mit Caching
            self.eph = self.loader('de421.bsp')
            
            load_time = time.time() - start_time
            logger.info(f"Skyfield resources loaded in {load_time:.2f}s")
            
            # Pre-load asteroid/comet dataframes mit Error Handling
            try:
                import pickle
                from db_utils import get_asteroid_dataframe, get_comet_dataframe
                
                asteroid_pickle = get_asteroid_dataframe()
                comet_pickle = get_comet_dataframe()
                
                self.asteroid_df = pickle.loads(asteroid_pickle) if asteroid_pickle else None
                self.comet_df = pickle.loads(comet_pickle) if comet_pickle else None
                
                if self.asteroid_df is not None and self.comet_df is not None:
                    logger.info(f"Pre-loaded {len(self.asteroid_df)} asteroids, {len(self.comet_df)} comets")
                else:
                    logger.warning("Could not pre-load dataframes from database")
            except Exception as e:
                logger.warning(f"Could not pre-load dataframes: {e}")
                self.asteroid_df = None
                self.comet_df = None
            
        except Exception as e:
            logger.error(f"Failed to initialize shared resources: {e}")
            raise
    
    def get_resources(self):
        """Gibt die shared Resources zurück"""
        return self.loader, self.ts, self.eph, self.asteroid_df, self.comet_df

# Global resources instance
shared_resources = None



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
                        tb = time_bucket_utc(dt_utc)
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
                        count = 0

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
                        tb = time_bucket_utc(dt_utc)
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
                        count = 0

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
    
    # Initialize Shared Resources
    global shared_resources
    shared_resources = SharedSkyfieldResources()
    
    rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://admin:changeme@localhost:5672/')
    
    while True:
        try:
            # Verbinde zu RabbitMQ
            connection = worker_utils.setup_rabbitmq_connection(rabbitmq_url, heartbeat=0)
            if not connection:
                logger.error("Cannot connect to RabbitMQ - retrying in 10s...")
                time.sleep(10)
                continue
            
            channel = connection.channel()
            
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
        
        except KeyboardInterrupt:
            logger.info(f"[{WORKER_ID}] Worker stopped by user")
            break
        
        except Exception as e:
            logger.error(f"[{WORKER_ID}] Worker error: {e}", exc_info=True)
            logger.info("Reconnecting in 10 seconds...")
            time.sleep(10)


# Removed: wait_for_database() - now using worker_utils.wait_for_database()


if __name__ == '__main__':
    # Warte bis Daten vorhanden sind
    if not worker_utils.wait_for_database(WORKER_ID, check_both=True):
        sys.exit(1)
    
    # Starte Worker
    main()
