"""
RabbitMQ RPC Client für ASCII Sky
Ermöglicht Request/Reply Pattern mit Timeout
"""
import pika
import json
import uuid
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class RabbitMQRPCClient:
    """
    RabbitMQ RPC Client mit Request/Reply Pattern
    """
    
    def __init__(self, rabbitmq_url: str):
        """
        Initialisiert RabbitMQ RPC Client
        
        Args:
            rabbitmq_url: RabbitMQ Connection URL (amqp://user:pass@host:port/)
        """
        self.rabbitmq_url = rabbitmq_url
        self.connection = None
        self.channel = None
        self.callback_queue = None
        self.response = None
        self.corr_id = None
        
        self._connect()
    
    def _connect(self):
        """Stellt Verbindung zu RabbitMQ her"""
        try:
            self.params = pika.URLParameters(self.rabbitmq_url)
            self.connection = pika.BlockingConnection(self.params)
            self.channel = self.connection.channel()
            
            # Callback Queue für RPC Responses
            result = self.channel.queue_declare(queue='', exclusive=True)
            self.callback_queue = result.method.queue
            
            self.channel.basic_consume(
                queue=self.callback_queue,
                on_message_callback=self._on_response,
                auto_ack=True
            )
            
            logger.info(f"RabbitMQ RPC Client connected to {self.rabbitmq_url}")
            
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise
    
    def _on_response(self, ch, method, props, body):
        """Callback für RPC Response"""
        if self.corr_id == props.correlation_id:
            self.response = json.loads(body)
    
    def call(
        self,
        queue: str,
        request: Dict[str, Any],
        priority: int = 5,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Führt RPC Call aus (synchron mit Timeout)
        
        Args:
            queue: Queue-Name ('asteroid', 'comet', 'celestial', 'constellation')
            request: Request-Daten als Dict
            priority: Priorität (0-10, höher = wichtiger)
            timeout: Timeout in Sekunden
            
        Returns:
            Response-Daten als Dict
            
        Raises:
            TimeoutError: Wenn Timeout überschritten
            ConnectionError: Wenn Verbindung fehlschlägt
        """
        self.response = None
        self.corr_id = str(uuid.uuid4())
        
        try:
            # Request publishen
            self.channel.basic_publish(
                exchange='computation.direct',
                routing_key=f'compute.{queue}',
                properties=pika.BasicProperties(
                    reply_to=self.callback_queue,
                    correlation_id=self.corr_id,
                    priority=priority,
                    delivery_mode=2,  # persistent
                    content_type='application/json'
                ),
                body=json.dumps(request)
            )
            
            logger.debug(f"RPC request sent: queue={queue}, corr_id={self.corr_id}")
            
            # Warten auf Response
            start_time = time.time()
            while self.response is None:
                self.connection.process_data_events(time_limit=1)
                
                if time.time() - start_time > timeout:
                    logger.error(f"RPC call timeout after {timeout}s: queue={queue}")
                    raise TimeoutError(f"RPC call timeout after {timeout}s")
            
            logger.debug(f"RPC response received: corr_id={self.corr_id}")
            return self.response
            
        except Exception as e:
            logger.error(f"RPC call failed: {e}")
            raise
    
    def publish_async(
        self,
        queue: str,
        request: Dict[str, Any],
        priority: int = 5
    ):
        """
        Publiziert Request asynchron (Fire & Forget)
        
        Args:
            queue: Queue-Name
            request: Request-Daten
            priority: Priorität (0-10)
        """
        try:
            self.channel.basic_publish(
                exchange='computation.direct',
                routing_key=f'compute.{queue}',
                properties=pika.BasicProperties(
                    priority=priority,
                    delivery_mode=2,
                    content_type='application/json'
                ),
                body=json.dumps(request)
            )
            
            logger.debug(f"Async request published: queue={queue}")
            
        except Exception as e:
            logger.error(f"Async publish failed: {e}")
            raise
    
    def close(self):
        """Schließt Verbindung"""
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
                logger.info("RabbitMQ connection closed")
        except Exception as e:
            logger.error(f"Error closing connection: {e}")
    
    def __enter__(self):
        """Context Manager Support"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context Manager Support"""
        self.close()
