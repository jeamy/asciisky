#!/usr/bin/env python3
"""
Unified worker for precompute tasks.

Consumes the precompute queues (coordinator and API cache misses), computes
asteroid, comet and sunpath buckets with shared Skyfield resources and stores
them in PostgreSQL.  A failed task is retried once and then routed to the
dead-letter queue ``computation.dead``.
"""

import json
import logging
import os
import signal
import socket
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pika
import psutil

# ASCII Sky Imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bright_asteroids
import comets
import settings
from api.computation import compute_sunpath_year
from cache_utils import location_key, normalize_location
from db_utils import (
    computation_lock,
    database_identity,
    database_target,
    get_asteroid_positions,
    get_comet_positions,
    get_sunpath_year,
    store_asteroid_positions,
    store_comet_positions,
    store_sunpath_year,
)

# Worker Utils (same directory)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import worker_utils
from worker_utils import SharedSkyfieldResources

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class WorkerMetrics:
    """Performance-Metriken für den Worker"""
    tasks_processed: int = 0
    tasks_failed: int = 0
    total_processing_time: float = 0.0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    last_task_time: float | None = None
    start_time: float = 0.0


class UnifiedWorker:
    """Worker for precompute tasks (asteroids, comets, sunpath)."""

    def __init__(self, worker_id: str, rabbitmq_url: str):
        self.worker_id = worker_id
        self.rabbitmq_url = rabbitmq_url
        self.connection = None
        self.channel = None
        self.running = False
        self.shutdown_requested = False

        # Shared Resources
        self.shared_resources = SharedSkyfieldResources()
        loader, ts, eph, _, _ = self.shared_resources.get_resources()
        self.loader = loader
        self.ts = ts
        self.eph = eph

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

    def _signal_handler(self, signum, _frame):
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

    def process_task(self, task: dict[str, Any]) -> bool:
        """Process one task and record its outcome in the metrics."""
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
    def _describe_task(task: dict[str, Any]) -> dict[str, Any]:
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

    def _process_precompute_task(self, task: dict[str, Any]) -> bool:
        """Verarbeite Precompute Task (optimiert)"""
        # Validiere Task-Struktur
        if 'kind' not in task:
            logger.error(f"Invalid precompute task: missing 'kind' field. Task: {task}")
            return False

        kind = task['kind']
        if kind not in ('asteroids', 'comets', 'sunpath'):
            # Never acknowledge a task nobody can compute.
            logger.error("Unknown precompute kind: %s", kind)
            return False
        location = task.get('location', {})
        time_bucket_str = task.get('time_bucket', '')

        if not location or not time_bucket_str:
            logger.error(f"Invalid precompute task: missing required fields. Task: {task}")
            return False

        # Debug: Zeige komplette Task-Struktur
        logger.debug(f"Task structure: {json.dumps(task, indent=2)}")

        lat, lon, elevation = location['latitude'], location['longitude'], location.get('elevation', 0)
        location_name = location.get('name', f"Lat {lat:.2f}, Lon {lon:.2f}")

        dt_utc = datetime.fromisoformat(time_bucket_str.replace('Z', '+00:00'))
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        bucket_hours = int(task.get('bucket_hours', 1))

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
        calculation_seconds = None

        # Use Advisory Locks for database operations (Hybrid approach)
        # RabbitMQ handles task deduplication, Advisory Locks protect DB operations
        try:
            with computation_lock(computation_key):
                logger.debug(f"Acquired Advisory Lock for: {computation_key}")

                tb = worker_utils.position_time_bucket(dt_utc, bucket_hours)
                existing = (
                    get_asteroid_positions(loc_key, tb) if kind == 'asteroids'
                    else get_comet_positions(loc_key, tb) if kind == 'comets'
                    else get_sunpath_year(loc_key, str(dt_utc.year)) if kind == 'sunpath'
                    else None
                )
                cache_complete = (
                    existing is not None if kind == 'sunpath'
                    else isinstance(existing, list)
                )
                if cache_complete:
                    logger.info("Skipping duplicate cached task %s", computation_key)
                    return True

                if kind == 'asteroids':
                    # A bucket is shared by every user, so it always covers
                    # the faintest filter; the API narrows it per request.
                    _, _, _, asteroid_df, _ = self.shared_resources.get_resources()

                    calculation_started = time.perf_counter()
                    asteroids_data = bright_asteroids.load_bright_asteroids(
                        self.loader, self.ts, self.eph, observer_loc,
                        max_magnitude=bright_asteroids.CACHE_MAX_MAGNITUDE,
                        use_cache=False,  # stored once below
                        current_dt=dt_utc,
                        dataframe=asteroid_df
                    )
                    calculation_seconds = time.perf_counter() - calculation_started

                    if asteroids_data is None:
                        logger.error("Asteroid computation failed for %s", computation_key)
                        return False
                    store_asteroid_positions(0, loc_key, tb, lat_norm, lon_norm, elev_norm, asteroids_data)
                    count = len(asteroids_data)

                elif kind == 'comets':
                    _, _, _, _, comet_df = self.shared_resources.get_resources()

                    calculation_started = time.perf_counter()
                    comets_data = comets.load_comets(
                        self.ts, self.eph, observer_loc,
                        max_comets=comets.MAX_COMETS_DEFAULT,
                        use_cache=False,  # stored once below
                        current_dt=dt_utc,
                        dataframe=comet_df
                    )
                    calculation_seconds = time.perf_counter() - calculation_started

                    if comets_data is None:
                        logger.error("Comet computation failed for %s", computation_key)
                        return False
                    store_comet_positions(0, loc_key, tb, lat_norm, lon_norm, elev_norm, comets_data)
                    count = len(comets_data)

                else:  # sunpath: the yearly curve for this location
                    # Normalized like the API's own computation, so both store the same curve.
                    year = dt_utc.year
                    result = compute_sunpath_year(lat_norm, lon_norm, elev_norm, year)
                    try:
                        store_sunpath_year(loc_key, str(year), lat_norm, lon_norm, elev_norm, result)
                    except Exception as e:
                        logger.error(f"Failed to store sunpath year in DB: {e}")
                        return False

                    count = len(result.get('points', []))

        except Exception as e:
            logger.error(f"Precompute task {computation_key} failed: {e}", exc_info=True)
            return False

        with self._task_state_lock:
            if self._current_task is not None:
                self._current_task['objects'] = count
        if calculation_seconds is None:
            logger.info(f"✅ Precompute {kind} completed: {count} objects")
        else:
            logger.info(
                "✅ Precompute %s completed: %d objects in %.2fs",
                kind,
                count,
                calculation_seconds,
            )
        return True

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

    def get_health_status(self) -> dict[str, Any]:
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

    # Task types that go through a persistent publication claim.
    _CLAIMED_TASK_TYPES = frozenset({'precompute'})

    def _release_claim(self, task: dict[str, Any], context: str) -> None:
        if task.get('type', 'precompute') not in self._CLAIMED_TASK_TYPES:
            return
        try:
            from db_utils import release_precompute_task
            release_precompute_task(worker_utils.precompute_task_key(task))
        except Exception:
            logger.exception("Could not release %s claim", context)

    def callback(self, ch, method, _properties, body):
        """Ack a processed task; retry a failed one once, then dead-letter it."""
        try:
            task = json.loads(body)
        except (TypeError, ValueError) as exc:
            # A message that is not JSON can never succeed: dead-letter it
            # instead of requeueing it forever.
            logger.error("Undecodable task message: %s", exc)
            if self._publish_dead_task(ch, {'raw': body.decode('utf-8', 'replace') if isinstance(body, bytes) else str(body)}, "undecodable message"):
                self._safe_ack(ch, method.delivery_tag)
            else:
                self._safe_nack(ch, method.delivery_tag, requeue=True)
            return
        try:
            success = self.process_task(task)

            if success:
                self._release_claim(task, "completed")
                self._safe_ack(ch, method.delivery_tag)
            else:
                # One immediate retry.  A second failure is routed to the
                # configured DLQ; the publication claim is released only once
                # the task is truly finished (DLQ delivery confirmed) so a
                # message stuck retrying because the DLQ itself is down does
                # not leave its bucket unclaimed and open to a duplicate
                # concurrent publish.
                if hasattr(method, 'redelivered') and method.redelivered:
                    if self._publish_dead_task(ch, task, "failed after retry"):
                        self._release_claim(task, "failed")
                        self._safe_ack(ch, method.delivery_tag)
                        logger.error("Task failed after retry and was routed to the DLQ")
                    else:
                        self._safe_nack(ch, method.delivery_tag, requeue=True)
                else:
                    self._safe_nack(ch, method.delivery_tag, requeue=True)
                    logger.warning("Task failed, requeued for retry")

        except Exception as e:
            # Same retry policy as a failed task: one redelivery, then the DLQ.
            logger.error(f"Callback error: {e}", exc_info=True)
            if getattr(method, 'redelivered', False) and self._publish_dead_task(ch, task, f"callback error: {e}"):
                self._release_claim(task, "failed")
                self._safe_ack(ch, method.delivery_tag)
            else:
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

    @staticmethod
    def _publish_dead_task(ch, task: dict[str, Any], reason: str) -> bool:
        """Persist a failed task in the DLQ without changing existing queue arguments."""
        try:
            ch.basic_publish(
                exchange='',
                routing_key='computation.dead',
                properties=pika.BasicProperties(delivery_mode=2, content_type='application/json'),
                body=json.dumps({
                    'failed_at': datetime.now(timezone.utc).isoformat(),
                    'reason': reason,
                    'task': task,
                }),
            )
            return True
        except Exception:
            logger.exception("Could not publish failed task to DLQ")
            return False

    def start(self):
        """Starte den Worker mit automatischer Wiederverbindung"""
        logger.info(f"Starting Unified Worker {self.worker_id}")

        self.running = True

        # Health is logged from its own thread so long tasks cannot delay it.
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
        """Log the worker's health every 30 seconds."""
        while self.running:
            time.sleep(30)
            if not self.running:
                break
            try:
                health = self.get_health_status()
                task = health['current_task'] or health['last_task']
                task_label = self._format_task_for_log(task, current=health['current_task'] is not None)
                logger.info(
                    f"Health: {health['tasks_processed']} tasks, "
                    f"{health['success_rate']:.2%} success, "
                    f"{health['memory_usage_mb']:.1f}MB mem, "
                    f"{task_label}"
                )
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
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

    rabbitmq_url = settings.RABBITMQ_URL

    logger.info("=" * 60)
    logger.info(f"Unified Worker [{worker_id}] - Starting")
    logger.info("PostgreSQL target: %s", database_target())
    logger.info("=" * 60)

    # Warte auf Datenbank
    if not wait_for_database(worker_id):
        sys.exit(1)
    try:
        logger.info("Actual PostgreSQL server: %s", database_identity())
    except Exception as exc:
        logger.warning("Could not read PostgreSQL server identity: %s", exc)

    # Starte Worker
    worker = UnifiedWorker(worker_id, rabbitmq_url)
    worker.start()


if __name__ == '__main__':
    main()
