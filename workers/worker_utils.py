"""
Worker Utilities - Gemeinsame Funktionen für alle Worker
=========================================================

Zentrale Sammlung von wiederverwendbaren Funktionen für:
- Database Readiness Checks
- Lock Management
- RabbitMQ Status Publishing
- Time Bucket Handling
- Error Handling
"""

import time
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import pika

logger = logging.getLogger(__name__)


def wait_for_database(worker_id: str, check_both: bool = True) -> bool:
    """
    Warte bis Daten in PostgreSQL vorhanden sind.

    Args:
        worker_id: Worker-ID für Logging
        check_both: Wenn True, prüfe Asteroid UND Comet DataFrames
                   Wenn False, prüfe nur was verfügbar ist

    Returns:
        True wenn Datenbank bereit, False bei Timeout
    """
    from db_utils import get_asteroid_dataframe, get_comet_dataframe

    logger.info(f"[{worker_id}] Checking if database has data...")

    max_wait = 600  # 10 Minuten
    check_interval = 30  # Alle 30 Sekunden prüfen
    waited = 0

    while waited < max_wait:
        try:
            asteroid_df = get_asteroid_dataframe()
            comet_df = get_comet_dataframe()

            if check_both:
                # Beide DataFrames müssen vorhanden sein
                if asteroid_df is not None and comet_df is not None:
                    logger.info(f"[{worker_id}] ✅ Database has data - starting worker")
                    return True
            else:
                # Mindestens einer muss vorhanden sein
                if asteroid_df is not None or comet_df is not None:
                    logger.info(f"[{worker_id}] ✅ Database has data - starting worker")
                    return True

            if waited == 0:
                logger.info(f"[{worker_id}] ⏳ Waiting for data_updater to populate database...")
            waited += check_interval
            time.sleep(check_interval)

        except Exception as e:
            if waited == 0:
                logger.warning(f"[{worker_id}] Database not ready: {e}")
                logger.info(f"[{worker_id}] ⏳ Waiting for database...")
            waited += check_interval
            time.sleep(check_interval)

    logger.error(f"[{worker_id}] ❌ Timeout waiting for database data after {max_wait}s")
    return False


def compute_lock_key(object_type: str, location: Dict[str, float], time_bucket_str: str) -> str:
    """
    Berechne Lock-Key für Computation Lock.

    Args:
        object_type: 'asteroid' oder 'comet'
        location: Dict mit latitude, longitude, elevation
        time_bucket_str: ISO-Format Zeitstempel

    Returns:
        Lock-Key String im Format: "computing:{type}:{location_key}:{bucket_key}"
    """
    from cache_utils import normalize_location, location_key, time_bucket_utc

    # Parse und runde Zeit auf Bucket-Boundary
    bucket_dt = datetime.fromisoformat(time_bucket_str.replace('Z', '+00:00'))
    bucket_dt = bucket_dt.replace(minute=0, second=0, microsecond=0)

    # Normalisiere Location
    lat_norm, lon_norm, elev_norm = normalize_location(
        location['latitude'],
        location['longitude'],
        location.get('elevation', 0)
    )

    # Erstelle Keys
    loc_key = location_key(lat_norm, lon_norm, elev_norm)
    bucket_key = time_bucket_utc(bucket_dt, 1)

    return f"computing:{object_type}:{loc_key}:{bucket_key}"


def round_to_bucket_boundary(time_bucket_str: str) -> datetime:
    """
    Runde Zeitstempel auf Stunden-Boundary.

    Args:
        time_bucket_str: ISO-Format Zeitstempel (z.B. "2024-10-31T20:15:00Z")

    Returns:
        datetime gerundet auf volle Stunde (z.B. 20:15 → 20:00)
    """
    # Parse Zeit
    time_bucket_dt = datetime.fromisoformat(time_bucket_str.replace('Z', '+00:00'))

    # Runde auf Stunden-Boundary
    time_bucket_dt = time_bucket_dt.replace(minute=0, second=0, microsecond=0)

    return time_bucket_dt


def publish_worker_status(
    channel: pika.channel.Channel,
    worker_id: str,
    task_id: str,
    status: str,
    progress: int,
    correlation_id: Optional[str] = None
) -> None:
    """
    Publiziere Worker-Status zu RabbitMQ.

    Args:
        channel: RabbitMQ Channel
        worker_id: Worker-ID
        task_id: Task-ID
        status: Status ('started', 'progress', 'completed', 'failed')
        progress: Fortschritt (0-100)
        correlation_id: Optional Correlation-ID
    """
    try:
        status_msg = {
            'task_id': task_id,
            'status': status,
            'progress': progress,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'worker_id': worker_id
        }

        props = pika.BasicProperties(
            delivery_mode=1,  # non-persistent
            content_type='application/json'
        )
        if correlation_id:
            props.correlation_id = correlation_id

        channel.basic_publish(
            exchange='',
            routing_key='computation.status',
            properties=props,
            body=json.dumps(status_msg)
        )

    except Exception as e:
        logger.error(f"Error publishing status: {e}")


def setup_rabbitmq_connection(rabbitmq_url: str, heartbeat: int = 0) -> Optional[pika.BlockingConnection]:
    """
    Erstelle RabbitMQ-Verbindung mit optimierten Einstellungen.

    Args:
        rabbitmq_url: RabbitMQ Connection URL
        heartbeat: Heartbeat Interval (0 = disabled für lange Berechnungen)

    Returns:
        RabbitMQ Connection oder None bei Fehler
    """
    try:
        params = pika.URLParameters(rabbitmq_url)
        params.heartbeat = heartbeat
        params.blocked_connection_timeout = 0

        connection = pika.BlockingConnection(params)
        return connection

    except Exception as e:
        logger.error(f"Failed to connect to RabbitMQ: {e}")
        return None


def declare_computation_queues(channel: pika.channel.Channel) -> None:
    """
    Deklariere alle Standard-Queues für Computation Workers.

    Args:
        channel: RabbitMQ Channel
    """
    # Precompute Queue
    channel.queue_declare(
        queue='precompute.tasks',
        durable=True,
        arguments={'x-max-priority': 10}
    )

    # On-Demand Queues (Classic mit Priorität + TTL)
    channel.queue_declare(
        queue='asteroid.compute',
        durable=True,
        arguments={
            'x-queue-type': 'classic',
            'x-max-priority': 10,
            'x-message-ttl': 3600000
        }
    )

    channel.queue_declare(
        queue='comet.compute',
        durable=True,
        arguments={
            'x-queue-type': 'classic',
            'x-max-priority': 10,
            'x-message-ttl': 3600000
        }
    )

    # Status Queue
    channel.queue_declare(
        queue='computation.status',
        durable=True
    )

    # Exchange für On-Demand Computation
    channel.exchange_declare(
        exchange='computation.direct',
        exchange_type='direct',
        durable=True
    )

    # Bindings
    channel.queue_bind(
        exchange='computation.direct',
        queue='asteroid.compute',
        routing_key='compute.asteroid'
    )

    channel.queue_bind(
        exchange='computation.direct',
        queue='comet.compute',
        routing_key='compute.comet'
    )

    logger.info("✅ All computation queues and exchanges declared")


def handle_task_error(
    channel: pika.channel.Channel,
    method: pika.spec.Basic.Deliver,
    error: Exception,
    task_id: str = "unknown"
) -> None:
    """
    Standardisierte Fehlerbehandlung für Worker Tasks.

    Args:
        channel: RabbitMQ Channel
        method: Delivery Method
        error: Exception die aufgetreten ist
        task_id: Task-ID für Logging
    """
    logger.error(f"❌ Task {task_id} failed: {error}", exc_info=True)

    # NACK mit Requeue-Logik
    if hasattr(method, 'redelivered') and method.redelivered:
        # Bereits redelivered -> nicht mehr requeuen
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        logger.error(f"Task {task_id} failed after retry, moved to DLQ")
    else:
        # Ersten Fehler -> requeuen
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        logger.warning(f"Task {task_id} failed, requeued for retry")


class SharedSkyfieldResources:
    """Shared Skyfield Resources für alle Worker-Instanzen (Singleton)"""

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
            with SharedSkyfieldResources._lock:
                if not self._initialized:
                    self._initialize_resources()
                    SharedSkyfieldResources._initialized = True

    def _initialize_resources(self):
        """Initialisiere Skyfield Resources einmalig mit Memory-Optimierung"""
        try:
            from data_paths import DATA_DIR, ensure_data_dirs
            from skyfield.api import Loader

            logger.info("Initializing shared Skyfield resources...")
            start_time = time.time()

            ensure_data_dirs()
            self.loader = Loader(str(DATA_DIR))
            self.loader.verbose = False

            self.ts = self.loader.timescale()
            self.eph = self.loader('de421.bsp')

            load_time = time.time() - start_time
            logger.info(f"Skyfield resources loaded in {load_time:.2f}s")

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

            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            logger.info(f"Shared resources initialized - Memory usage: {memory_mb:.1f}MB")

        except Exception as e:
            logger.error(f"Failed to initialize shared resources: {e}")
            raise

    def get_resources(self):
        """Gibt die shared Resources zurück"""
        return self.loader, self.ts, self.eph, self.asteroid_df, self.comet_df

    def get_memory_usage(self) -> float:
        """Gibt Memory-Usage der shared Resources zurück"""
        try:
            import psutil
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0
