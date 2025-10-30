#!/usr/bin/env python3
"""
Unified Worker - Optimiert für Smart Interpolation
=================================================

Einheitlicher Worker für Precompute, On-Demand und RPC Tasks
mit Integration in die Smart Interpolation Architektur.

Features:
- ✅ Shared Skyfield Resources (Memory-Effizienz)
- ✅ Integration mit Smart Interpolation
- ✅ Adaptive Task-Verarbeitung
- ✅ Performance-Monitoring
- ✅ Health Checks und Metrics
- ✅ Graceful Shutdown
"""

import os
import sys
import time
import json
import socket
import logging
import signal
import asyncio
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import psutil
import pika

# ASCII Sky Imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bright_asteroids
import comets
from cache_utils import normalize_location, location_key, time_bucket_utc
from db_utils import store_asteroid_positions, store_comet_positions
from api.on_demand_computation import OnDemandComputationService
from api.astronomical_corrections import AstronomicalCorrector
from config.interpolation_config import get_interpolation_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Typen von Tasks die der Worker verarbeiten kann"""
    PRECOMPUTE = "precompute"
    ON_DEMAND = "on_demand"
    RPC = "rpc"


@dataclass
class WorkerMetrics:
    """Performance-Metriken für den Worker"""
    tasks_processed: int = 0
    tasks_failed: int = 0
    total_processing_time: float = 0.0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    last_task_time: Optional[float] = None
    start_time: float = 0.0


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
                self.asteroid_df = bright_asteroids.load_asteroid_dataframe()
                self.comet_df = comets.load_comet_dataframe()
                logger.info(f"Pre-loaded {len(self.asteroid_df)} asteroids, {len(self.comet_df)} comets")
            except Exception as e:
                logger.warning(f"Could not pre-load dataframes: {e}")
                self.asteroid_df = None
                self.comet_df = None
            
            # Memory-Usage logging
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


class UnifiedWorker:
    """
    Unified Worker für alle Task-Typen mit Smart Interpolation Integration
    """
    
    def __init__(self, worker_id: str, rabbitmq_url: str):
        self.worker_id = worker_id
        self.rabbitmq_url = rabbitmq_url
        self.connection = None
        self.channel = None
        self.running = False
        
        # Shared Resources
        self.shared_resources = SharedSkyfieldResources()
        loader, ts, eph, asteroid_df, comet_df = self.shared_resources.get_resources()
        self.loader = loader
        self.ts = ts
        self.eph = eph
        self.asteroid_df = asteroid_df
        self.comet_df = comet_df
        
        # Smart Interpolation Integration
        self.config = get_interpolation_config()
        self.on_demand_service = OnDemandComputationService()
        self.astronomical_corrector = AstronomicalCorrector()
        
        # Metrics
        self.metrics = WorkerMetrics()
        self.metrics.start_time = time.time()
        
        # Graceful Shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        logger.info(f"Unified Worker {worker_id} initialized")
    
    def _signal_handler(self, signum, frame):
        """Handler für graceful shutdown"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def connect(self):
        """Verbinde zu RabbitMQ mit optimierten Einstellungen"""
        try:
            params = pika.URLParameters(self.rabbitmq_url)
            params.heartbeat = 600  # 10 Minuten Heartbeat
            params.blocked_connection_timeout = 300
            params.connection_attempts = 3
            params.retry_delay = 5
            
            self.connection = pika.BlockingConnection(params)
            self.channel = self.connection.channel()
            
            # QoS konfigurierbar
            prefetch_count = int(os.getenv('RABBITMQ_PREFETCH_COUNT', '1'))
            self.channel.basic_qos(prefetch_count=prefetch_count)
            
            # Queues deklarieren
            self._declare_queues()
            
            logger.info(f"Worker {self.worker_id} connected to RabbitMQ")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            return False
    
    def _declare_queues(self):
        """Deklariere alle notwendigen Queues"""
        # Precompute Queue
        self.channel.queue_declare(
            queue='precompute.tasks',
            durable=True,
            arguments={'x-max-priority': 10}
        )
        
        # On-Demand Queues (Smart Interpolation)
        self.channel.queue_declare(
            queue='asteroid.compute',
            durable=True
        )
        
        self.channel.queue_declare(
            queue='comet.compute',
            durable=True
        )
        
        # Status Queue
        self.channel.queue_declare(
            queue='computation.status',
            durable=True
        )
        
        # Exchange für On-Demand Computation
        self.channel.exchange_declare(
            exchange='computation.direct',
            exchange_type='direct',
            durable=True
        )
        
        # Bindings
        self.channel.queue_bind(
            exchange='computation.direct',
            queue='asteroid.compute',
            routing_key='compute.asteroid'
        )
        
        self.channel.queue_bind(
            exchange='computation.direct',
            queue='comet.compute',
            routing_key='compute.comet'
        )
        
        logger.info("All queues and exchanges declared successfully")
    
    def process_task(self, task: Dict[str, Any]) -> bool:
        """
        Verarbeite einen Task mit Smart Interpolation Integration
        """
        start_time = time.time()
        task_type = task.get('type', 'precompute')
        
        try:
            if task_type == 'precompute':
                success = self._process_precompute_task(task)
            elif task_type == 'on_demand':
                success = self._process_on_demand_task(task)
            elif task_type == 'rpc':
                success = self._process_rpc_task(task)
            else:
                logger.error(f"Unknown task type: {task_type}")
                return False
            
            # Update Metrics
            processing_time = time.time() - start_time
            self._update_metrics(success, processing_time)
            
            return success
            
        except Exception as e:
            logger.error(f"Task processing failed: {e}", exc_info=True)
            processing_time = time.time() - start_time
            self._update_metrics(False, processing_time)
            return False
    
    def _process_precompute_task(self, task: Dict[str, Any]) -> bool:
        """Verarbeite Precompute Task (optimiert)"""
        # Validiere Task-Struktur
        if 'kind' not in task:
            logger.error(f"Invalid precompute task: missing 'kind' field. Task: {task}")
            return False
        
        kind = task['kind']
        location = task.get('location', {})
        time_bucket_str = task.get('time_bucket', '')
        magnitude = task.get('magnitude', 20.0)
        
        if not location or not time_bucket_str:
            logger.error(f"Invalid precompute task: missing required fields. Task: {task}")
            return False
        
        lat, lon, elevation = location['latitude'], location['longitude'], location['elevation']
        dt_utc = datetime.fromisoformat(time_bucket_str.replace('Z', '+00:00'))
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        
        logger.info(f"Processing precompute {kind} for {location.get('name', 'Unknown')}")
        
        # Normalisiere Location
        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        observer_loc = {
            'latitude': lat_norm,
            'longitude': lon_norm,
            'elevation': elev_norm
        }
        
        if kind == 'asteroids':
            # Nutze shared resources und konfigurierbare Limits
            max_mag = min(magnitude, self.config.max_magnitude_asteroids)
            
            asteroids_data = bright_asteroids.load_bright_asteroids(
                self.loader, self.ts, self.eph, observer_loc,
                max_magnitude=max_mag,
                current_dt=dt_utc
            )
            
            if asteroids_data:
                loc_key = location_key(lat_norm, lon_norm, elev_norm)
                tb = time_bucket_utc(dt_utc)
                store_asteroid_positions(0, loc_key, tb, lat_norm, lon_norm, elev_norm, asteroids_data)
                count = len(asteroids_data)
            else:
                count = 0
        
        elif kind == 'comets':
            # Nutze konfigurierbare Limits
            max_comets = min(1000, self.config.max_comets)
            
            comets_data = comets.load_comets(
                self.ts, self.eph, observer_loc,
                max_comets=max_comets,
                current_dt=dt_utc
            )
            
            if comets_data:
                loc_key = location_key(lat_norm, lon_norm, elev_norm)
                tb = time_bucket_utc(dt_utc)
                store_comet_positions(0, loc_key, tb, lat_norm, lon_norm, elev_norm, comets_data)
                count = len(comets_data)
            else:
                count = 0
        
        else:
            logger.error(f"Unknown kind: {kind}")
            return False
        
        logger.info(f"✅ Precompute {kind} completed: {count} objects")
        return True
    
    def _process_on_demand_task(self, task: Dict[str, Any]) -> bool:
        """Verarbeite On-Demand Task mit Smart Interpolation"""
        object_type = task['object_type']  # 'asteroids' or 'comets'
        location = task['location']
        time_bucket_str = task['time_bucket']
        task_id = task.get('task_id', 'unknown')
        
        dt_utc = datetime.fromisoformat(time_bucket_str.replace('Z', '+00:00'))
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        
        logger.info(f"Processing on-demand {object_type} task {task_id}")
        
        # Nutze On-Demand Service
        if object_type == 'asteroids':
            result = self.on_demand_service.compute_asteroid_bucket(
                location['latitude'], location['longitude'], location['elevation'], dt_utc
            )
        else:
            result = self.on_demand_service.compute_comet_bucket(
                location['latitude'], location['longitude'], location['elevation'], dt_utc
            )
        
        success = result.status.value == 'success'
        
        # Veröffentliche Status
        self._publish_status(task_id, result.status.value, 100 if success else 0)
        
        logger.info(f"✅ On-demand {object_type} task {task_id} completed: {result.status.value}")
        return success
    
    def _process_rpc_task(self, task: Dict[str, Any]) -> bool:
        """Verarbeite RPC Task (kompatibel mit bestehenden asteroid/comet workers)"""
        # Implementierung für bestehende RPC-Kompatibilität
        return self._process_on_demand_task(task)
    
    def _publish_status(self, task_id: str, status: str, progress: int):
        """Veröffentliche Task-Status"""
        try:
            status_msg = {
                'task_id': task_id,
                'status': status,
                'progress': progress,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'worker_id': self.worker_id,
                'worker_type': 'unified'
            }
            
            props = pika.BasicProperties(
                delivery_mode=1,
                content_type='application/json'
            )
            
            self.channel.basic_publish(
                exchange='',
                routing_key='computation.status',
                properties=props,
                body=json.dumps(status_msg)
            )
            
        except Exception as e:
            logger.error(f"Error publishing status: {e}")
    
    def _update_metrics(self, success: bool, processing_time: float):
        """Aktualisiere Worker-Metriken"""
        self.metrics.tasks_processed += 1
        if not success:
            self.metrics.tasks_failed += 1
        
        self.metrics.total_processing_time += processing_time
        self.metrics.last_task_time = time.time()
        
        # System-Metriken
        try:
            process = psutil.Process()
            self.metrics.memory_usage_mb = process.memory_info().rss / 1024 / 1024
            self.metrics.cpu_usage_percent = process.cpu_percent()
        except Exception:
            pass
    
    def get_health_status(self) -> Dict[str, Any]:
        """Gibt Health-Status zurück"""
        uptime = time.time() - self.metrics.start_time
        success_rate = (self.metrics.tasks_processed - self.metrics.tasks_failed) / max(self.metrics.tasks_processed, 1)
        
        return {
            'worker_id': self.worker_id,
            'status': 'healthy' if self.running else 'stopped',
            'uptime_seconds': uptime,
            'tasks_processed': self.metrics.tasks_processed,
            'tasks_failed': self.metrics.tasks_failed,
            'success_rate': success_rate,
            'avg_processing_time': self.metrics.total_processing_time / max(self.metrics.tasks_processed, 1),
            'memory_usage_mb': self.metrics.memory_usage_mb,
            'cpu_usage_percent': self.metrics.cpu_usage_percent,
            'last_task_time': self.metrics.last_task_time
        }
    
    def callback(self, ch, method, properties, body):
        """RabbitMQ Callback mit optimierter Fehlerbehandlung"""
        try:
            task = json.loads(body)
            success = self.process_task(task)
            
            if success:
                ch.basic_ack(delivery_tag=method.delivery_tag)
            else:
                # Intelligent Retry mit exponential backoff
                if hasattr(method, 'redelivered') and method.redelivered:
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                    logger.error("Task failed after retry, moved to DLQ")
                else:
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                    logger.warning("Task failed, requeued for retry")
        
        except Exception as e:
            logger.error(f"Callback error: {e}", exc_info=True)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    def start(self):
        """Starte den Worker"""
        logger.info(f"Starting Unified Worker {self.worker_id}")
        
        if not self.connect():
            logger.error("Failed to connect, exiting...")
            return
        
        self.running = True
        
        # Starte Heartbeat-Thread
        heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        heartbeat_thread.start()
        
        # Starte Consumer für alle Queues
        self.channel.basic_consume(
            queue='precompute.tasks',
            on_message_callback=self.callback,
            auto_ack=False
        )
        
        self.channel.basic_consume(
            queue='asteroid.compute',
            on_message_callback=self.callback,
            auto_ack=False
        )
        
        self.channel.basic_consume(
            queue='comet.compute',
            on_message_callback=self.callback,
            auto_ack=False
        )
        
        logger.info(f"Worker {self.worker_id} started, consuming from all queues...")
        
        # Sende initialen Heartbeat
        self._log_health_status()
        
        try:
            # Blocking consume
            self.channel.start_consuming()
        
        except KeyboardInterrupt:
            logger.info("Worker stopped by user")
        finally:
            self.stop()
    
    def _heartbeat_loop(self):
        """Separater Thread für regelmäßige Heartbeats"""
        while self.running:
            try:
                time.sleep(30)  # Alle 30 Sekunden
                if self.running:
                    self._log_health_status()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    def _log_health_status(self):
        """Logge und sende Health-Status"""
        health = self.get_health_status()
        logger.info(f"Health Status: {health['tasks_processed']} tasks, "
                   f"{health['success_rate']:.2%} success rate, "
                   f"{health['memory_usage_mb']:.1f}MB memory")
        
        # Sende Heartbeat an worker.health Queue
        try:
            heartbeat_msg = {
                'worker_id': self.worker_id,
                'worker_type': 'unified',
                'status': health['status'],
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'tasks_processed': health['tasks_processed'],
                'tasks_failed': health['tasks_failed'],
                'success_rate': health['success_rate'],
                'memory_usage_mb': health['memory_usage_mb'],
                'cpu_usage_percent': health['cpu_usage_percent'],
                'uptime_seconds': health['uptime_seconds']
            }
            
            props = pika.BasicProperties(
                delivery_mode=1,  # Non-persistent (Heartbeats müssen nicht persistent sein)
                content_type='application/json'
            )
            
            # Sende an beide Queues
            self.channel.basic_publish(
                exchange='',
                routing_key='worker.health',
                properties=props,
                body=json.dumps(heartbeat_msg)
            )
            
            self.channel.basic_publish(
                exchange='',
                routing_key='computation.status',
                properties=props,
                body=json.dumps(heartbeat_msg)
            )
            
        except Exception as e:
            logger.error(f"Error sending heartbeat: {e}")
    
    def stop(self):
        """Stoppe den Worker gracefully"""
        logger.info(f"Stopping Unified Worker {self.worker_id}")
        self.running = False
        
        try:
            if self.channel:
                self.channel.stop_consuming()
            if self.connection and not self.connection.is_closed:
                self.connection.close()
        except Exception as e:
            logger.error(f"Error stopping worker: {e}")
        
        # Logge finale Metriken
        health = self.get_health_status()
        logger.info(f"Worker {self.worker_id} stopped. Final stats: {health}")


def wait_for_database(worker_id: str):
    """Warte bis Datenbank bereit ist (optimiert)"""
    from db_utils import get_asteroid_dataframe, get_comet_dataframe
    
    logger.info(f"[{worker_id}] Checking database readiness...")
    
    max_wait = 600
    check_interval = 30
    waited = 0
    
    while waited < max_wait:
        try:
            asteroid_df = get_asteroid_dataframe()
            comet_df = get_comet_dataframe()
            
            if asteroid_df is not None and comet_df is not None:
                logger.info(f"[{worker_id}] ✅ Database ready")
                return True
            else:
                if waited == 0:
                    logger.info(f"[{worker_id}] ⏳ Waiting for database...")
                waited += check_interval
                time.sleep(check_interval)
        except Exception as e:
            if waited == 0:
                logger.warning(f"[{worker_id}] Database not ready: {e}")
            waited += check_interval
            time.sleep(check_interval)
    
    logger.error(f"[{worker_id}] ❌ Database timeout after {max_wait}s")
    return False


def main():
    """Hauptfunktion"""
    worker_id = os.getenv('WORKER_ID')
    if not worker_id or worker_id == 'unified-worker-${HOSTNAME:-unknown}':
        # Fallback: Verwende tatsächlichen Hostname
        hostname = socket.gethostname()
        worker_id = f'unified-worker-{hostname}'
    
    rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://admin:changeme@localhost:5672/')
    
    logger.info("=" * 60)
    logger.info(f"Unified Worker [{worker_id}] - Starting")
    logger.info("=" * 60)
    
    # Warte auf Datenbank
    if not wait_for_database(worker_id):
        sys.exit(1)
    
    # Starte Worker
    worker = UnifiedWorker(worker_id, rabbitmq_url)
    worker.start()


if __name__ == '__main__':
    main()
