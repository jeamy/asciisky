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
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import psutil
import pika
import hashlib

# ASCII Sky Imports
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
from api.on_demand_computation import OnDemandComputationService
from api.astronomical_corrections import AstronomicalCorrector
from config.interpolation_config import get_interpolation_config
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


class TaskType(Enum):
    """Typen von Tasks die der Worker verarbeiten kann"""
    PRECOMPUTE = "precompute"
    ON_DEMAND = "on_demand"
    RPC = "rpc"


def generate_computation_message_id(task_type: str, location_key: str, time_bucket: str, **kwargs) -> str:
    """Generate unique message ID for computation deduplication"""
    # Create deterministic hash from computation parameters
    components = [task_type, location_key, time_bucket]

    # Add optional parameters sorted by key
    for key in sorted(kwargs.keys()):
        components.append(f"{key}:{kwargs[key]}")

    computation_string = "|".join(components)
    return hashlib.sha256(computation_string.encode()).hexdigest()


def generate_precompute_message_id(lat: float, lon: float, elevation: float, time_bucket: str, object_type: str) -> str:
    """Generate message ID for precompute tasks"""
    loc_key = location_key(lat, lon, elevation)
    return generate_computation_message_id(
        task_type=f"precompute_{object_type}",
        location_key=loc_key,
        time_bucket=time_bucket,
        object_type=object_type
    )


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
        self.shutdown_requested = False

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
        self._task_state_lock = threading.Lock()
        self._current_task = None
        self._last_task = None

        # Graceful Shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        logger.info(f"Unified Worker {worker_id} initialized")

    def _signal_handler(self, signum, frame):
        """Handler für graceful shutdown"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.shutdown_requested = True
        self.running = False
        try:
            if self.connection and self.connection.is_open and self.channel and self.channel.is_open:
                self.connection.add_callback_threadsafe(self.channel.stop_consuming)
        except Exception as e:
            logger.debug(f"Could not schedule consumer shutdown: {e}")

    def connect(self):
        """Verbinde zu RabbitMQ mit optimierten Einstellungen"""
        try:
            params = pika.URLParameters(self.rabbitmq_url)
            params.heartbeat = 1800  # 30 Minuten – lang genug für lange Tasks
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

    def disconnect(self):
        """Gracefully close RabbitMQ connection and channel"""
        try:
            if self.channel and self.channel.is_open:
                self.channel.close()
        except Exception as e:
            logger.debug(f"Error closing channel: {e}")
        finally:
            self.channel = None

        try:
            if self.connection and self.connection.is_open:
                self.connection.close()
        except Exception as e:
            logger.debug(f"Error closing connection: {e}")
        finally:
            self.connection = None

    def _declare_queues(self):
        """Deklariere alle notwendigen Queues für PostgreSQL Advisory Locks"""
        # Nutze zentrale Queue-Definition aus worker_utils, damit alle Worker
        # konsistent dieselben Queue-Argumente verwenden (insbesondere keine
        # TTL-Differenzen bei bereits existierenden Queues in RabbitMQ).
        worker_utils.declare_computation_queues(self.channel)
        logger.info("All queues and exchanges declared successfully")

    def send_task_with_deduplication(self, queue_name: str, task_data: Dict[str, Any],
                                    message_id: str, priority: int = 0) -> bool:
        """Send task with RabbitMQ deduplication"""
        try:
            self.channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=json.dumps(task_data),
                properties=pika.BasicProperties(
                    message_id=message_id,
                    delivery_mode=2,  # Persistent
                    priority=priority,
                    expiration='300000'  # 5 minutes
                )
            )
            logger.debug(f"Sent task to {queue_name} with deduplication ID: {message_id[:16]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to send task to {queue_name}: {e}")
            return False

    def process_task(self, task: Dict[str, Any]) -> bool:
        """
        Verarbeite einen Task mit Smart Interpolation Integration
        """
        start_time = time.time()
        task_type = task.get('type', 'precompute')
        task_summary = self._describe_task(task)
        task_summary['started_at'] = datetime.now(timezone.utc).isoformat()
        task_summary['started_monotonic'] = start_time
        with self._task_state_lock:
            self._current_task = task_summary

        try:
            if task_type == 'precompute':
                success = self._process_precompute_task(task)
            elif task_type == 'on_demand':
                success = self._process_on_demand_task(task)
            elif task_type == 'rpc':
                success = self._process_rpc_task(task)
            else:
                logger.error(f"Unknown task type: {task_type}")
                success = False

            # Update Metrics
            processing_time = time.time() - start_time
            self._update_metrics(success, processing_time)
            self._finish_task_summary(task_summary, success, processing_time)

            return success

        except Exception as e:
            logger.error(f"Task processing failed: {e}", exc_info=True)
            processing_time = time.time() - start_time
            self._update_metrics(False, processing_time)
            task_summary['error'] = str(e)
            self._finish_task_summary(task_summary, False, processing_time)
            return False

    @staticmethod
    def _describe_task(task: Dict[str, Any]) -> Dict[str, Any]:
        """Extract compact, stable fields for logs and health messages."""
        location = task.get('location') or {}
        lat = location.get('latitude')
        lon = location.get('longitude')
        if lat is not None and lon is not None:
            try:
                coordinates = f"{float(lat):.4f},{float(lon):.4f}"
            except (TypeError, ValueError):
                coordinates = f"{lat},{lon}"
        else:
            coordinates = None
        return {
            'type': task.get('type', 'precompute'),
            'kind': task.get('kind') or task.get('object_type') or 'unknown',
            'location': location.get('name') or coordinates or 'unknown',
            'coordinates': coordinates,
            'time_bucket': task.get('time_bucket') or 'unknown',
            'task_id': task.get('task_id'),
            'magnitude': task.get('magnitude'),
        }

    def _finish_task_summary(self, summary, success, processing_time):
        summary['status'] = 'success' if success else 'failed'
        summary['duration_seconds'] = processing_time
        summary['finished_at'] = datetime.now(timezone.utc).isoformat()
        summary.pop('started_monotonic', None)
        with self._task_state_lock:
            self._last_task = dict(summary)
            self._current_task = None

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

        # Debug: Zeige komplette Task-Struktur
        logger.debug(f"Task structure: {json.dumps(task, indent=2)}")

        lat, lon, elevation = location['latitude'], location['longitude'], location['elevation']
        location_name = location.get('name', f"Lat {lat:.2f}, Lon {lon:.2f}")

        dt_utc = datetime.fromisoformat(time_bucket_str.replace('Z', '+00:00'))
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)

        logger.info(f"Processing precompute {kind} for {location_name} at {dt_utc.strftime('%Y-%m-%d %H:%M UTC')}")

        # Normalisiere Location
        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        observer_loc = {
            'latitude': lat_norm,
            'longitude': lon_norm,
            'elevation': elev_norm
        }

        # Create computation key for Advisory Locks
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        computation_key = f"precompute_{kind}:{loc_key}:{time_bucket_str}"

        # Use Advisory Locks for database operations (Hybrid approach)
        # RabbitMQ handles task deduplication, Advisory Locks protect DB operations
        try:
            with computation_lock(computation_key, ttl_seconds=300):
                logger.debug(f"Acquired Advisory Lock for: {computation_key}")

                if kind == 'asteroids':
                    # Nutze shared resources und globale Magnituden-Limits
                    max_mag = min(magnitude, bright_asteroids.MAX_APPARENT_MAGNITUDE)

                    asteroids_data = bright_asteroids.load_bright_asteroids(
                        self.loader, self.ts, self.eph, observer_loc,
                        max_magnitude=max_mag,
                        current_dt=dt_utc,
                        dataframe=self.asteroid_df  # Pass pre-loaded dataframe
                    )

                    if asteroids_data:
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
                        current_dt=dt_utc,
                        dataframe=self.comet_df  # Pass pre-loaded dataframe
                    )

                    if comets_data:
                        tb = time_bucket_utc(dt_utc)
                        store_comet_positions(0, loc_key, tb, lat_norm, lon_norm, elev_norm, comets_data)
                        count = len(comets_data)
                    else:
                        count = 0

                elif kind == 'sunpath':
                    # Precompute yearly sunpath curve for this location
                    year = dt_utc.year
                    result = compute_sunpath_year(lat, lon, elevation, year)

                    loc_key = location_key(lat_norm, lon_norm, elev_norm)
                    year_bucket = str(year)
                    try:
                        store_sunpath_year(loc_key, year_bucket, lat, lon, elevation, result)
                    except Exception as e:
                        logger.error(f"Failed to store sunpath year in DB: {e}")
                        return False

                    count = len(result.get('points', []))

                else:
                    logger.error(f"Unknown kind: {kind}")
                    count = 0

        except Exception as e:
            logger.error(f"Failed to acquire Advisory Lock for {computation_key}: {e}", exc_info=True)
            return False

        with self._task_state_lock:
            if self._current_task is not None:
                self._current_task['objects'] = count
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

        with self._task_state_lock:
            current_task = dict(self._current_task) if self._current_task else None
            last_task = dict(self._last_task) if self._last_task else None
        if current_task:
            started = current_task.pop('started_monotonic', None)
            current_task['running_seconds'] = time.time() - started if started else None

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
            'last_task_time': self.metrics.last_task_time,
            'current_task': current_task,
            'last_task': last_task,
        }

    def callback(self, ch, method, properties, body):
        """RabbitMQ Callback mit optimierter Fehlerbehandlung"""
        try:
            task = json.loads(body)
            success = self.process_task(task)

            if success:
                self._safe_ack(ch, method.delivery_tag)
            else:
                # Intelligent Retry mit exponential backoff
                if hasattr(method, 'redelivered') and method.redelivered:
                    self._safe_nack(ch, method.delivery_tag, requeue=False)
                    logger.error("Task failed after retry, moved to DLQ")
                else:
                    self._safe_nack(ch, method.delivery_tag, requeue=True)
                    logger.warning("Task failed, requeued for retry")

        except Exception as e:
            logger.error(f"Callback error: {e}", exc_info=True)
            self._safe_nack(ch, method.delivery_tag, requeue=True)

    def _safe_ack(self, ch, delivery_tag):
        """basic_ack mit Fehlerbehandlung für geschlossene Channels"""
        try:
            if ch.is_open:
                ch.basic_ack(delivery_tag=delivery_tag)
            else:
                logger.warning("Channel closed, cannot ack – message will be redelivered")
        except Exception as e:
            logger.warning(f"Failed to ack: {e} – message will be redelivered")

    def _safe_nack(self, ch, delivery_tag, requeue=True):
        """basic_nack mit Fehlerbehandlung für geschlossene Channels"""
        try:
            if ch.is_open:
                ch.basic_nack(delivery_tag=delivery_tag, requeue=requeue)
            else:
                logger.warning("Channel closed, cannot nack – message will be redelivered")
        except Exception as e:
            logger.warning(f"Failed to nack: {e} – message will be redelivered")

    def start(self):
        """Starte den Worker mit automatischer Wiederverbindung"""
        logger.info(f"Starting Unified Worker {self.worker_id}")

        self.running = True

        # Health publishing owns a separate RabbitMQ connection so long-running
        # task callbacks cannot delay monitor heartbeats.
        heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        heartbeat_thread.start()

        while not self.shutdown_requested:
            if not self.connect():
                logger.error("Failed to connect, retrying in 10s...")
                self._wait_for_shutdown(10)
                continue

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
            self._publish_health_status()

            try:
                # Blocking consume
                self.channel.start_consuming()

            except KeyboardInterrupt:
                logger.info("Worker stopped by user")
                break
            except Exception as e:
                logger.error(f"Consumer error: {e}")

            if self.shutdown_requested:
                logger.info("Worker stopping...")
                break

            logger.warning("Connection lost, attempting reconnect in 5s...")
            self.disconnect()
            self._wait_for_shutdown(5)

        self.stop()

    def _heartbeat_loop(self):
        """Publish health over a connection owned exclusively by this thread."""
        connection = None
        channel = None
        while self.running:
            try:
                time.sleep(30)
                if self.running:
                    health = self.get_health_status()
                    task = health['current_task'] or health['last_task']
                    task_label = self._format_task_for_log(
                        task,
                        current=health['current_task'] is not None,
                    )
                    logger.info(
                        f"Health: {health['tasks_processed']} tasks, "
                        f"{health['success_rate']:.2%} success, "
                        f"{health['memory_usage_mb']:.1f}MB mem, "
                        f"{task_label}"
                    )
                    if not connection or connection.is_closed:
                        params = pika.URLParameters(self.rabbitmq_url)
                        params.heartbeat = 60
                        params.blocked_connection_timeout = 30
                        connection = pika.BlockingConnection(params)
                        channel = connection.channel()
                    self._publish_health_status(channel)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                try:
                    if connection and connection.is_open:
                        connection.close()
                except Exception:
                    pass
                connection = None
                channel = None
        try:
            if connection and connection.is_open:
                connection.close()
        except Exception:
            pass
        logger.info("Heartbeat thread exiting")

    @staticmethod
    def _format_task_for_log(task, current=False):
        if not task:
            return "task=idle (nothing processed yet)"
        state = "running" if current else task.get('status', 'unknown')
        elapsed = task.get('running_seconds') if current else task.get('duration_seconds')
        elapsed_text = f", elapsed={elapsed:.1f}s" if elapsed is not None else ""
        objects = task.get('objects')
        objects_text = f", objects={objects}" if objects is not None else ""
        magnitude = task.get('magnitude')
        magnitude_text = f", max_mag={magnitude}" if magnitude is not None else ""
        location = task.get('location')
        coordinates = task.get('coordinates')
        if coordinates and coordinates != location:
            location = f"{location} ({coordinates})"
        return (
            f"task={state} {task.get('type')}/{task.get('kind')}, "
            f"location={location}, bucket={task.get('time_bucket')}"
            f"{magnitude_text}{objects_text}{elapsed_text}"
        )

    def _wait_for_shutdown(self, seconds):
        """Interruptible reconnect delay."""
        deadline = time.monotonic() + seconds
        while not self.shutdown_requested and time.monotonic() < deadline:
            time.sleep(max(0.0, min(0.25, deadline - time.monotonic())))

    def _publish_health_status(self, channel=None):
        """Publish health on the supplied thread-owned channel."""
        health = self.get_health_status()

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
                'uptime_seconds': health['uptime_seconds'],
                'current_task': health['current_task'],
                'last_task': health['last_task'],
            }

            props = pika.BasicProperties(
                delivery_mode=1,
                content_type='application/json'
            )

            publish_channel = channel or self.channel
            if publish_channel and publish_channel.is_open:
                publish_channel.basic_publish(
                    exchange='',
                    routing_key='worker.health',
                    properties=props,
                    body=json.dumps(heartbeat_msg)
                )

                publish_channel.basic_publish(
                    exchange='',
                    routing_key='computation.status',
                    properties=props,
                    body=json.dumps(heartbeat_msg)
                )

        except Exception as e:
            logger.error(f"Error publishing health status: {e}")

    def send_precompute_task_with_deduplication(self, kind: str, location: Dict[str, Any],
                                            time_bucket: str, magnitude: float = 20.0) -> bool:
        """Send precompute task with RabbitMQ deduplication"""
        task_data = {
            'type': 'precompute',
            'kind': kind,
            'location': location,
            'time_bucket': time_bucket,
            'magnitude': magnitude,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        # Generate deduplication message ID
        message_id = generate_precompute_message_id(
            location['latitude'],
            location['longitude'],
            location['elevation'],
            time_bucket,
            kind
        )

        return self.send_task_with_deduplication('precompute.tasks', task_data, message_id, priority=5)

    def stop(self):
        """Stoppe den Worker gracefully"""
        logger.info(f"Stopping Unified Worker {self.worker_id}")
        self.running = False

        try:
            if self.channel:
                self.channel.stop_consuming()
            if self.connection and self.connection.is_open:
                self.connection.close()
        except Exception as e:
            logger.error(f"Error stopping worker: {e}")

        # Logge finale Metriken
        health = self.get_health_status()
        logger.info(f"Worker {self.worker_id} stopped. Final stats: {health}")


# Removed: wait_for_database() - now using worker_utils.wait_for_database()

def wait_for_database(worker_id: str):
    """Wrapper for backward compatibility with start_unified_worker.py"""
    return worker_utils.wait_for_database(worker_id, check_both=True)


def main():
    """Hauptfunktion"""
    worker_id = os.getenv('WORKER_ID', '')
    # Fallback wenn nicht gesetzt, Docker Swarm Template oder Shell-Variable nicht aufgelöst
    if not worker_id or '{{' in worker_id or '${' in worker_id:
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
