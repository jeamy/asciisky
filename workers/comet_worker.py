"""
Comet Worker für RabbitMQ
Berechnet Kometen-Positionen mit Skyfield
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

import comets
from api.computation import LOADER, ts, eph
from skyfield.api import wgs84

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CometWorker:
    """
    RabbitMQ Worker für Kometen-Berechnungen
    """
    
    def __init__(self, rabbitmq_url: str, worker_id: str = "comet-worker-1"):
        """
        Initialisiert Comet Worker
        
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
                queue='comet.compute',
                durable=True,
                arguments={
                    'x-queue-type': 'quorum',
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
                queue='comet.compute',
                routing_key='compute.comet'
            )
            
            logger.info(f"{self.worker_id} connected to RabbitMQ")
            
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise
    
    def compute_comets(self, location_dict, time_bucket_str, magnitude):
        """
        Berechnet Kometen-Positionen mit Skyfield
        
        Args:
            location_dict: {'latitude': float, 'longitude': float, 'elevation': float}
            time_bucket_str: ISO-Format Zeitstempel
            magnitude: Max Magnitude
            
        Returns:
            Liste von Kometen-Daten
        """
        try:
            # Location erstellen
            location = wgs84.latlon(
                location_dict['latitude'],
                location_dict['longitude'],
                elevation_m=location_dict.get('elevation', 0)
            )
            
            # Zeit parsen
            time_bucket_dt = datetime.fromisoformat(time_bucket_str.replace('Z', '+00:00'))
            
            # Kometen berechnen UND in Cache speichern
            comet_list = comets.load_comets(
                ts, eph, location_dict,
                max_comets=1000,
                current_dt=time_bucket_dt
            )
            
            logger.info(f"Computed {len(comet_list)} comets for {location_dict}")
            return comet_list
            
        except Exception as e:
            logger.error(f"Error computing comets: {e}")
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
            location = request['location']
            time_bucket = request.get('time_bucket') or request['time_range']['start']
            magnitude = request.get('magnitude', 14.0)
            
            logger.info(f"Processing task {task_id}")
            
            # Status: Started
            self.publish_status(task_id, 'started', 0, None)
            
            # Berechnung - Ergebnisse werden automatisch in Cache/DB gespeichert
            results = self.compute_comets(location, time_bucket, magnitude)
            
            # Status: Completed
            self.publish_status(task_id, 'completed', 100, None)
            
            # ACK - Task erfolgreich verarbeitet und in Cache gespeichert
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
    
    def publish_status(self, task_id, status, progress, correlation_id=None):
        """
        Publiziert Status-Update
        
        Args:
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
                'worker_id': self.worker_id
            }
            
            props = pika.BasicProperties(
                delivery_mode=1,
                content_type='application/json'
            )
            if correlation_id:
                props.correlation_id = correlation_id
            
            self.channel.basic_publish(
                exchange='',
                routing_key='computation.status',
                properties=props,
                body=json.dumps(status_msg)
            )
            
        except Exception as e:
            logger.error(f"Error publishing status: {e}")
    
    def start(self):
        """Startet Worker"""
        logger.info(f"{self.worker_id} started. Waiting for messages...")
        
        self.channel.basic_consume(
            queue='comet.compute',
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
    rabbitmq_url = os.environ.get('RABBITMQ_URL', 'amqp://admin:changeme@localhost:5672/')
    worker_id = os.environ.get('WORKER_ID', 'comet-worker-1')
    
    # Worker starten
    worker = CometWorker(rabbitmq_url, worker_id)
    
    try:
        worker.start()
    except KeyboardInterrupt:
        worker.stop()
