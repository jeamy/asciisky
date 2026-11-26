"""
RabbitMQ publisher for asynchronous precompute tasks.

Tasks are sent to the worker queues without waiting for an answer; the
workers store their results in PostgreSQL.  A persistent claim per task key
(``precompute_task_claims``) deduplicates publications across processes.
"""
import asyncio
import hashlib
import json
import logging
import threading
from datetime import datetime, timezone

import pika
from pika import exceptions as pika_exceptions

import settings
from db_utils import claim_precompute_task, release_precompute_task
from workers.worker_utils import declare_computation_queues, precompute_task_key

logger = logging.getLogger(__name__)

# One connection per thread: pika's BlockingConnection is not thread-safe.
_thread_local = threading.local()


async def trigger_precompute_task(
    kind: str,
    location: dict[str, float],
    time_bucket: str,
    magnitude: float,
    bucket_hours: int,
    priority: int = 10,
) -> None:
    """Publish a deduplicated minor-body task without blocking an ASGI worker."""
    publisher = TaskPublisher(settings.RABBITMQ_URL)
    await asyncio.to_thread(
        publisher.publish_precompute_task,
        kind,
        location,
        time_bucket,
        magnitude,
        priority,
        bucket_hours,
    )


def _drop_thread_connection() -> None:
    connection = getattr(_thread_local, 'connection', None)
    if connection is not None:
        try:
            connection.close()
        except Exception:
            pass
    _thread_local.connection = None
    _thread_local.channel = None


_ROUTING_NAMES = {'asteroids': 'asteroid', 'comets': 'comet'}


class TaskPublisher:
    """Publishes precompute tasks to the computation exchange with broker confirms."""

    def __init__(self, rabbitmq_url: str):
        self.rabbitmq_url = rabbitmq_url

    def _get_connection(self):
        """Return this thread's connection and channel, opening them when needed."""
        connection = getattr(_thread_local, 'connection', None)
        if connection is None or connection.is_closed:
            params = pika.URLParameters(self.rabbitmq_url)
            params.heartbeat = 600
            params.blocked_connection_timeout = 300
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            # Same queue arguments as the workers, so neither side redeclares
            # a queue with conflicting arguments.
            declare_computation_queues(channel)
            channel.confirm_delivery()
            _thread_local.connection = connection
            _thread_local.channel = channel
            logger.info("TaskPublisher connected to RabbitMQ (thread %s)", threading.current_thread().name)
        else:
            # A BlockingConnection only answers broker heartbeats during I/O.
            # Processing pending events here keeps an idle connection alive
            # and surfaces a connection the broker has already closed.
            connection.process_data_events(0)
        return _thread_local.connection, _thread_local.channel

    def _publish(self, routing_key: str, task_id: str, priority: int, body: str) -> None:
        """Publish with confirm; reconnect once when a stale connection fails."""
        for attempt in (1, 2):
            try:
                _, channel = self._get_connection()
                confirmed = channel.basic_publish(
                    exchange='computation.direct',
                    routing_key=routing_key,
                    properties=pika.BasicProperties(
                        delivery_mode=2,
                        content_type='application/json',
                        message_id=task_id,
                        priority=priority,
                    ),
                    body=body,
                )
                if confirmed is False:
                    raise RuntimeError(f"Broker did not confirm task {task_id}")
                return
            except (pika_exceptions.AMQPConnectionError, pika_exceptions.AMQPChannelError):
                _drop_thread_connection()
                if attempt == 2:
                    raise
                logger.info("RabbitMQ connection was stale, reconnecting once")

    def publish_precompute_task(
        self,
        kind: str,
        location: dict[str, float],
        time_bucket: str,
        magnitude: float | None = None,
        priority: int = 5,
        bucket_hours: int = 1,
    ) -> str:
        """Publish one precompute task ('asteroids' or 'comets') and return its id.

        A task whose key is already claimed is not published again.
        """
        task_data = {
            'type': 'precompute',
            'kind': kind,
            'location': location,
            'time_bucket': time_bucket,
            'magnitude': magnitude,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'priority': priority,
            'bucket_hours': bucket_hours,
        }
        key = precompute_task_key(task_data)
        task_id = f"{kind}_{hashlib.sha256(key.encode()).hexdigest()[:16]}"
        task_data['task_id'] = task_id
        routing_key = f"compute.{_ROUTING_NAMES.get(kind, kind)}"

        if not claim_precompute_task(key):
            logger.debug("Task already queued/active: %s", key)
            return task_id
        try:
            self._publish(routing_key, task_id, priority, json.dumps(task_data))
            logger.debug("Published task %s to %s", task_id, routing_key)
            return task_id
        except Exception as exc:
            try:
                release_precompute_task(key)
            except Exception:
                logger.exception("Could not release failed task claim %s", key)
            logger.error("Failed to publish task: %s", exc)
            _drop_thread_connection()
            raise

    def close(self):
        """Close this thread's connection."""
        _drop_thread_connection()
