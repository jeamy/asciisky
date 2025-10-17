"""
Constellation Worker für RabbitMQ
Lädt Sternbild-Daten aus Stellarium
"""
import pika
import json
import time
import os
import sys
import logging
from datetime import datetime, timezone

# Pfad anpassen für Imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.computation import load_constellations

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConstellationWorker:
    """
    RabbitMQ Worker für Constellation-Daten
    """
    
    def __init__(self, rabbitmq_url: str, worker_id: str = "constellation-worker-1"):
        """
        Initialisiert Constellation Worker
        
        Args:
            rabbitmq_url: RabbitMQ Connection URL
            worker_id: Eindeutige Worker-ID
        """
        self.rabbitmq_url = rabbitmq_url
        self.worker_id = worker_id
        self.connection = None
        self.channel = None
        
        logger.info(f"Initializing {worker_id}")
        self._connect()
    
    def _connect(self):
        """Stellt Verbindung zu RabbitMQ her"""
        try:
            self.params = pika.URLParameters(self.rabbitmq_url)
            self.connection = pika.BlockingConnection(self.params)
            self.channel = self.connection.channel()
            
            # QoS: Nur 1 Message gleichzeitig verarbeiten
            self.channel.basic_qos(prefetch_count=1)
            
            # Queue deklarieren (idempotent)
            self.channel.queue_declare(
                queue='constellation.compute',
                durable=True,
                arguments={
                    'x-queue-type': 'quorum',
                    'x-max-priority': 10,
                    'x-message-ttl': 3600000  # 1 Stunde
                }
            )
            
            # Exchange deklarieren
            self.channel.exchange_declare(
                exchange='computation.direct',
                exchange_type='direct',
                durable=True
            )
            
            # Binding
            self.channel.queue_bind(
                exchange='computation.direct',
                queue='constellation.compute',
                routing_key='compute.constellation'
            )
            
            logger.info(f"{self.worker_id} connected to RabbitMQ")
            
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise
    
    def compute_constellations(self):
        """
        Lädt Constellation-Daten aus Stellarium
        
        Returns:
            Dict von Constellation-Daten
        """
        try:
            # Constellations laden (statisch, keine Location/Zeit nötig)
            constellation_data = load_constellations()
            
            logger.info(f"Loaded {len(constellation_data)} constellations")
            return constellation_data
            
        except Exception as e:
            logger.error(f"Error loading constellations: {e}")
            raise
    
    def callback(self, ch, method, properties, body):
        """
        Callback für eingehende Messages
        
        Args:
            ch: Channel
            method: Delivery method
            properties: Message properties
            body: Message body
        """
        start_time = time.time()
        
        try:
            # Request parsen
            request = json.loads(body)
            task_id = request.get('task_id', 'unknown')
            
            logger.info(f"Processing task {task_id}")
            
            # Status: Started
            self.publish_status(task_id, 'started', 0, properties.correlation_id)
            
            # Berechnung (Constellations sind statisch)
            results = self.compute_constellations()
            
            # Status: Completed
            self.publish_status(task_id, 'completed', 100, properties.correlation_id)
            
            # Result erstellen
            result = {
                'task_id': task_id,
                'constellations': results,
                'computed_at': datetime.now(timezone.utc).isoformat(),
                'worker_id': self.worker_id,
                'duration': time.time() - start_time
            }
            
            # Reply mit correlation_id
            reply_to = properties.reply_to or 'computation.results'
            ch.basic_publish(
                exchange='',
                routing_key=reply_to,
                properties=pika.BasicProperties(
                    correlation_id=properties.correlation_id,
                    delivery_mode=2,
                    content_type='application/json'
                ),
                body=json.dumps(result)
            )
            
            # ACK
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
            duration = time.time() - start_time
            logger.info(f"Task {task_id} completed in {duration:.2f}s")
            
        except Exception as e:
            logger.error(f"Error processing task: {e}", exc_info=True)
            
            # NACK mit Requeue (max 3x)
            if hasattr(method, 'redelivered') and method.redelivered:
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                logger.error("Task failed after retry, moved to DLQ")
            else:
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                logger.warning("Task failed, requeued for retry")
    
    def publish_status(self, task_id, status, progress, correlation_id):
        """
        Publiziert Status-Update
        
        Args:
            task_id: Task-ID
            status: Status ('started', 'progress', 'completed', 'failed')
            progress: Fortschritt (0-100)
            correlation_id: Correlation-ID
        """
        try:
            status_msg = {
                'task_id': task_id,
                'status': status,
                'progress': progress,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'worker_id': self.worker_id
            }
            
            self.channel.basic_publish(
                exchange='',
                routing_key='computation.status',
                properties=pika.BasicProperties(
                    correlation_id=correlation_id,
                    delivery_mode=1,
                    content_type='application/json'
                ),
                body=json.dumps(status_msg)
            )
            
        except Exception as e:
            logger.error(f"Error publishing status: {e}")
    
    def start(self):
        """Startet Worker"""
        logger.info(f"{self.worker_id} started. Waiting for messages...")
        
        self.channel.basic_consume(
            queue='constellation.compute',
            on_message_callback=self.callback,
            auto_ack=False
        )
        
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("Stopping worker...")
            self.stop()
    
    def stop(self):
        """Stoppt Worker"""
        try:
            if self.channel:
                self.channel.stop_consuming()
            if self.connection and not self.connection.is_closed:
                self.connection.close()
            logger.info(f"{self.worker_id} stopped")
        except Exception as e:
            logger.error(f"Error stopping worker: {e}")


if __name__ == '__main__':
    # Konfiguration aus ENV
    rabbitmq_url = os.environ.get('RABBITMQ_URL', 'amqp://admin:password@localhost:5672/')
    worker_id = os.environ.get('WORKER_ID', 'constellation-worker-1')
    
    # Worker starten
    worker = ConstellationWorker(rabbitmq_url, worker_id)
    
    try:
        worker.start()
    except KeyboardInterrupt:
        worker.stop()
