"""
RabbitMQ Task Publisher für asynchrone Precompute-Tasks

Sendet Tasks an Worker-Queues ohne auf Antwort zu warten.
Worker speichern Ergebnisse in Cache/DB.
"""
import pika
import json
import logging
import uuid
import time
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import settings

logger = logging.getLogger(__name__)

# Thread-local storage für Connections
_thread_local = threading.local()


class TaskPublisher:
    """
    Publisher für asynchrone Background-Tasks
    
    Sendet Tasks an RabbitMQ Queues ohne auf Reply zu warten.
    Worker verarbeiten Tasks und speichern in Cache/DB.
    """
    
    def __init__(self, rabbitmq_url: str):
        """
        Initialisiert Task Publisher
        
        Args:
            rabbitmq_url: RabbitMQ Connection URL
        """
        self.rabbitmq_url = rabbitmq_url
        # Keine globale Connection - wird pro Thread erstellt
    
    def _get_connection(self):
        """Holt oder erstellt thread-local Connection"""
        if not hasattr(_thread_local, 'connection') or _thread_local.connection is None or _thread_local.connection.is_closed:
            try:
                params = pika.URLParameters(self.rabbitmq_url)
                params.heartbeat = 600
                params.blocked_connection_timeout = 300
                
                _thread_local.connection = pika.BlockingConnection(params)
                _thread_local.channel = _thread_local.connection.channel()
                
                # Exchange deklarieren
                _thread_local.channel.exchange_declare(
                    exchange='computation.direct',
                    exchange_type='direct',
                    durable=True
                )
                
                # Queues deklarieren (RabbitMQ 4.x kompatibel)
                # Idempotent: Wenn Queue existiert, passiert nichts
                _thread_local.channel.queue_declare(
                    queue='asteroid.compute',
                    durable=True,
                    arguments={
                        'x-queue-type': 'quorum',
                        'x-max-priority': 10,
                        'x-message-ttl': 3600000
                    }
                )
                
                _thread_local.channel.queue_declare(
                    queue='comet.compute',
                    durable=True,
                    arguments={
                        'x-queue-type': 'quorum',
                        'x-max-priority': 10,
                        'x-message-ttl': 3600000
                    }
                )
                
                _thread_local.channel.queue_declare(
                    queue='precompute.tasks',
                    durable=True,
                    arguments={'x-max-priority': 10}
                )
                
                # Bindings
                _thread_local.channel.queue_bind(
                    exchange='computation.direct',
                    queue='asteroid.compute',
                    routing_key='compute.asteroid'
                )
                
                _thread_local.channel.queue_bind(
                    exchange='computation.direct',
                    queue='comet.compute',
                    routing_key='compute.comet'
                )
                
                logger.info(f"TaskPublisher connected to RabbitMQ (thread {threading.current_thread().name})")
            except Exception as e:
                logger.error(f"Failed to connect to RabbitMQ: {e}")
                raise
        
        return _thread_local.connection, _thread_local.channel
    
    def publish_precompute_task(
        self,
        kind: str,
        location: Dict[str, float],
        time_bucket: str,
        magnitude: Optional[float] = None,
        priority: int = 5
    ) -> str:
        """
        Publiziert einen Precompute-Task
        
        Args:
            kind: 'asteroids', 'comets', 'celestial', 'constellations'
            location: {'latitude': float, 'longitude': float, 'elevation': float}
            time_bucket: ISO-Format Zeitstempel
            magnitude: Optional max magnitude
            priority: Task-Priorität (0-10, höher = wichtiger)
            
        Returns:
            Task-ID
        """
        task_id = f"{kind}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        
        task_data = {
            'task_id': task_id,
            'type': 'precompute',  # Task-Typ für unified_worker
            'kind': kind,
            'location': location,
            'time_bucket': time_bucket,
            'magnitude': magnitude,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'priority': priority
        }
        
        # Routing Key basierend auf Kind (singular!)
        kind_singular = {
            'asteroids': 'asteroid',
            'comets': 'comet',
            'celestial': 'celestial',
            'constellations': 'constellation'
        }.get(kind, kind)
        routing_key = f'compute.{kind_singular}'
        
        try:
            # Hole thread-local Connection
            connection, channel = self._get_connection()
            
            channel.basic_publish(
                exchange='computation.direct',
                routing_key=routing_key,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent
                    content_type='application/json'
                ),
                body=json.dumps(task_data)
            )
            
            logger.debug(f"Published task {task_id} to {routing_key}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to publish task: {e}")
            # Cleanup thread-local bei Fehler
            if hasattr(_thread_local, 'connection'):
                try:
                    _thread_local.connection.close()
                except:
                    pass
                _thread_local.connection = None
                _thread_local.channel = None
            raise
    
    def publish_batch(self, tasks: list) -> list:
        """
        Publiziert mehrere Tasks als Batch
        
        Args:
            tasks: Liste von Task-Dicts
            
        Returns:
            Liste von Task-IDs
        """
        task_ids = []
        
        for task in tasks:
            try:
                task_id = self.publish_precompute_task(
                    kind=task['kind'],
                    location=task['location'],
                    time_bucket=task['time_bucket'],
                    magnitude=task.get('magnitude'),
                    priority=task.get('priority', 5)
                )
                task_ids.append(task_id)
            except Exception as e:
                logger.error(f"Failed to publish task in batch: {e}")
        
        return task_ids
    
    def close(self):
        """Schließt thread-local Verbindung"""
        try:
            if hasattr(_thread_local, 'connection') and _thread_local.connection and not _thread_local.connection.is_closed:
                _thread_local.connection.close()
                logger.info("TaskPublisher connection closed")
                _thread_local.connection = None
                _thread_local.channel = None
        except Exception as e:
            logger.error(f"Error closing connection: {e}")


# Singleton Instance
_publisher = None

def get_task_publisher() -> Optional[TaskPublisher]:
    """
    Lazy initialization von Task Publisher
    
    Returns:
        TaskPublisher instance oder None
    """
    global _publisher
    
    if _publisher is None and settings.RABBITMQ_ENABLED:
        try:
            _publisher = TaskPublisher(settings.RABBITMQ_URL)
        except Exception as e:
            logger.error(f"Failed to initialize TaskPublisher: {e}")
            _publisher = None
    
    return _publisher
