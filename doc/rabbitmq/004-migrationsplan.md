# ASCII Sky - RabbitMQ Migrationsplan (Kompakt)

## Übersicht

Dieser Plan beschreibt die Migration zu RabbitMQ 4.1. **Schneller und einfacher als Kafka** (10-14 Wochen vs. 12-18 Wochen).

## Phasen

```
Phase 0: Vorbereitung (2 Wochen)
Phase 1: RabbitMQ-Infrastruktur (1-2 Wochen)
Phase 2: Erste Worker (Asteroids) (2-3 Wochen)
Phase 3: Weitere Worker (2-3 Wochen)
Phase 4: Web Service Integration (2 Wochen)
Phase 5: Scheduler & Optimierung (1-2 Wochen)

Gesamt: 10-14 Wochen
```

## Phase 0: Vorbereitung

### Aufgaben
- [ ] Requirements definieren
- [ ] RabbitMQ vs. Kafka entscheiden
- [ ] Team schulen (RabbitMQ Basics, pika Library)
- [ ] Lokale Entwicklungsumgebung aufsetzen

### Deliverables
- Entscheidung für RabbitMQ
- Team-Training abgeschlossen
- Lokales RabbitMQ-Cluster läuft

## Phase 1: RabbitMQ-Infrastruktur

### Aufgaben
- [ ] 2-3 RabbitMQ Nodes deployen (siehe `003-rabbitmq-4.1-multi-host-setup.md`)
- [ ] Cluster bilden
- [ ] Queues erstellen
- [ ] Policies setzen (HA, Quorum)
- [ ] Management UI konfigurieren

### Queue-Erstellung

```bash
# Asteroid Compute Queue (Priority Queue)
docker exec rabbitmq-1 rabbitmqadmin declare queue \
  name=asteroid.compute \
  durable=true \
  arguments='{"x-queue-type":"quorum","x-max-priority":10,"x-message-ttl":3600000}'

# Comet Compute Queue
docker exec rabbitmq-1 rabbitmqadmin declare queue \
  name=comet.compute \
  durable=true \
  arguments='{"x-queue-type":"quorum","x-max-priority":10,"x-message-ttl":3600000}'

# Results Queue
docker exec rabbitmq-1 rabbitmqadmin declare queue \
  name=computation.results \
  durable=true \
  arguments='{"x-queue-type":"quorum","x-message-ttl":300000}'

# Status Queue (Classic für Performance)
docker exec rabbitmq-1 rabbitmqadmin declare queue \
  name=computation.status \
  durable=false \
  arguments='{"x-message-ttl":60000}'
```

### Exchange-Erstellung

```bash
# Direct Exchange für Computation Requests
docker exec rabbitmq-1 rabbitmqadmin declare exchange \
  name=computation.direct \
  type=direct \
  durable=true

# Topic Exchange für Results
docker exec rabbitmq-1 rabbitmqadmin declare exchange \
  name=celestial.topic \
  type=topic \
  durable=true

# Bindings
docker exec rabbitmq-1 rabbitmqadmin declare binding \
  source=computation.direct \
  destination=asteroid.compute \
  routing_key=compute.asteroid
```

## Phase 2: Erste Worker (Asteroids)

### Worker-Implementierung

**Datei**: `workers/asteroid_worker.py`

```python
import pika
import json
import time
from datetime import datetime, timezone
import bright_asteroids
from api.computation import LOADER, ts, eph

class AsteroidWorker:
    def __init__(self, rabbitmq_url):
        # Connection
        self.params = pika.URLParameters(rabbitmq_url)
        self.connection = pika.BlockingConnection(self.params)
        self.channel = self.connection.channel()
        
        # QoS: Nur 1 Message gleichzeitig verarbeiten
        self.channel.basic_qos(prefetch_count=1)
        
        # Queue deklarieren (idempotent)
        self.channel.queue_declare(
            queue='asteroid.compute',
            durable=True,
            arguments={
                'x-queue-type': 'quorum',
                'x-max-priority': 10
            }
        )
    
    def compute_asteroids(self, location, time_bucket_dt):
        """Berechnet Asteroiden-Positionen mit Skyfield"""
        asteroids = bright_asteroids.load_bright_asteroids(
            LOADER, ts, eph, location,
            max_magnitude=20.0,
            use_cache=False,
            current_dt=time_bucket_dt
        )
        return asteroids
    
    def callback(self, ch, method, properties, body):
        """Callback für eingehende Messages"""
        try:
            # Request parsen
            request = json.loads(body)
            task_id = request['task_id']
            location = request['location']
            time_range = request['time_range']
            
            print(f"Processing task {task_id}")
            
            # Status: Started
            self.publish_status(task_id, 'started', 0, properties.correlation_id)
            
            # Berechnung
            start_time = datetime.fromisoformat(time_range['start'])
            results = self.compute_asteroids(location, start_time)
            
            # Status: Completed
            self.publish_status(task_id, 'completed', 100, properties.correlation_id)
            
            # Result publishen
            result = {
                'task_id': task_id,
                'location_key': f"lat+{location['latitude']}_lon+{location['longitude']}_el+{location['elevation']:04d}",
                'time_bucket': start_time.strftime('%Y%m%dT%H'),
                'timestamp': start_time.isoformat(),
                'asteroids': results,
                'computed_at': datetime.now(timezone.utc).isoformat(),
                'worker_id': 'asteroid-worker-1'
            }
            
            # Reply mit correlation_id
            self.channel.basic_publish(
                exchange='',
                routing_key=properties.reply_to or 'computation.results',
                properties=pika.BasicProperties(
                    correlation_id=properties.correlation_id,
                    delivery_mode=2
                ),
                body=json.dumps(result)
            )
            
            # ACK
            ch.basic_ack(delivery_tag=method.delivery_tag)
            print(f"Task {task_id} completed")
            
        except Exception as e:
            print(f"Error processing task: {e}")
            # NACK mit Requeue
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    def publish_status(self, task_id, status, progress, correlation_id):
        """Publiziert Status-Update"""
        status_msg = {
            'task_id': task_id,
            'status': status,
            'progress': progress,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'worker_id': 'asteroid-worker-1'
        }
        
        self.channel.basic_publish(
            exchange='',
            routing_key='computation.status',
            properties=pika.BasicProperties(
                correlation_id=correlation_id,
                delivery_mode=1  # non-persistent
            ),
            body=json.dumps(status_msg)
        )
    
    def start(self):
        """Startet Worker"""
        print("Asteroid Worker started. Waiting for messages...")
        self.channel.basic_consume(
            queue='asteroid.compute',
            on_message_callback=self.callback,
            auto_ack=False
        )
        self.channel.start_consuming()
    
    def stop(self):
        """Stoppt Worker"""
        self.channel.stop_consuming()
        self.connection.close()

if __name__ == '__main__':
    import os
    rabbitmq_url = os.environ.get('RABBITMQ_URL', 'amqp://admin:password@192.168.1.10:5672/')
    worker = AsteroidWorker(rabbitmq_url)
    try:
        worker.start()
    except KeyboardInterrupt:
        worker.stop()
```

### Docker Integration

**Datei**: `docker-compose.workers.yml`

```yaml
version: '3.8'

services:
  asteroid-worker-1:
    build:
      context: .
      dockerfile: Dockerfile.worker
    command: ["python", "workers/asteroid_worker.py"]
    environment:
      - RABBITMQ_URL=amqp://admin:password@192.168.1.10:5672/
      - WORKER_ID=asteroid-worker-1
    volumes:
      - .:/app
    restart: unless-stopped
    depends_on:
      - rabbitmq-1

  asteroid-worker-2:
    # Analog zu worker-1 mit WORKER_ID=asteroid-worker-2
```

## Phase 3: Weitere Worker

Analog zu Phase 2:
- Comet Worker
- Celestial Worker
- Constellation Worker

## Phase 4: Web Service Integration

### FastAPI Integration

**Datei**: `api/rabbitmq_client.py`

```python
import pika
import json
import uuid
from typing import Optional

class RabbitMQClient:
    def __init__(self, rabbitmq_url):
        self.params = pika.URLParameters(rabbitmq_url)
        self.connection = pika.BlockingConnection(self.params)
        self.channel = self.connection.channel()
        
        # Callback Queue für RPC
        result = self.channel.queue_declare(queue='', exclusive=True)
        self.callback_queue = result.method.queue
        
        self.response = None
        self.corr_id = None
        
        self.channel.basic_consume(
            queue=self.callback_queue,
            on_message_callback=self.on_response,
            auto_ack=True
        )
    
    def on_response(self, ch, method, props, body):
        if self.corr_id == props.correlation_id:
            self.response = json.loads(body)
    
    def call(self, queue, request, priority=5, timeout=30):
        """RPC Call mit Timeout"""
        self.response = None
        self.corr_id = str(uuid.uuid4())
        
        self.channel.basic_publish(
            exchange='computation.direct',
            routing_key=f'compute.{queue}',
            properties=pika.BasicProperties(
                reply_to=self.callback_queue,
                correlation_id=self.corr_id,
                priority=priority,
                delivery_mode=2
            ),
            body=json.dumps(request)
        )
        
        # Warten auf Response
        start_time = time.time()
        while self.response is None:
            self.connection.process_data_events(time_limit=1)
            if time.time() - start_time > timeout:
                raise TimeoutError(f"RPC call timeout after {timeout}s")
        
        return self.response
    
    def publish_async(self, queue, request, priority=5):
        """Async Publish (Fire & Forget)"""
        self.channel.basic_publish(
            exchange='computation.direct',
            routing_key=f'compute.{queue}',
            properties=pika.BasicProperties(
                priority=priority,
                delivery_mode=2
            ),
            body=json.dumps(request)
        )
```

### API Endpoint

**Datei**: `api/routes/asteroids.py` (anpassen)

```python
from api.rabbitmq_client import RabbitMQClient

rabbitmq_client = RabbitMQClient(os.environ.get('RABBITMQ_URL'))

@router.get("/bright_asteroids")
async def get_bright_asteroids(request: Request, ...):
    # Location und Zeit ermitteln
    location_key_str = ...
    time_bucket = ...
    
    # Cache prüfen (Redis)
    cached = redis_client.get(f"asteroids:{location_key_str}:{time_bucket}")
    if cached:
        return json.loads(cached)
    
    # RPC Call zu Worker
    request_data = {
        'task_id': f"task_{int(time.time())}",
        'type': 'asteroid',
        'location': {'latitude': lat, 'longitude': lon, 'elevation': elev},
        'time_range': {'start': ..., 'end': ...}
    }
    
    try:
        result = rabbitmq_client.call('asteroid', request_data, priority=10, timeout=30)
        
        # Cache Update
        redis_client.setex(
            f"asteroids:{location_key_str}:{time_bucket}",
            3600,  # 1 Stunde
            json.dumps(result['asteroids'])
        )
        
        return result['asteroids']
    except TimeoutError:
        # Fallback: Alte Berechnung
        return old_compute_asteroids(...)
```

## Phase 5: Scheduler & Optimierung

### Scheduler

**Datei**: `scheduler/precompute_scheduler.py`

```python
from apscheduler.schedulers.blocking import BlockingScheduler
import pika
import json
from datetime import datetime, timedelta, timezone

class PrecomputeScheduler:
    def __init__(self, rabbitmq_url):
        self.params = pika.URLParameters(rabbitmq_url)
        self.connection = pika.BlockingConnection(self.params)
        self.channel = self.connection.channel()
        self.scheduler = BlockingScheduler()
    
    def schedule_precompute(self):
        """Generiert Precompute-Tasks"""
        locations = self.get_target_locations()
        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=720)
        
        for location in locations:
            request = {
                'task_id': f"precompute_{location['loc_key']}_{int(now.timestamp())}",
                'type': 'asteroid',
                'location': location,
                'time_range': {'start': now.isoformat(), 'end': end.isoformat()}
            }
            
            # Publish mit niedriger Priorität
            self.channel.basic_publish(
                exchange='computation.direct',
                routing_key='compute.asteroid',
                properties=pika.BasicProperties(
                    priority=2,  # Niedrige Priorität
                    delivery_mode=2
                ),
                body=json.dumps(request)
            )
    
    def start(self):
        self.scheduler.add_job(self.schedule_precompute, 'cron', hour='*')
        self.scheduler.start()
```

## Rollback-Plan

1. **Feature Flag zurücksetzen**: Alte Architektur aktivieren
2. **RabbitMQ-Consumer stoppen**: Keine neuen Messages
3. **Alte Worker starten**: Precompute-Worker reaktivieren
4. **Analyse**: Ursache finden
5. **Retry**: Migration erneut versuchen

## Erfolgskriterien

- [ ] Alle API-Endpoints funktionieren
- [ ] Latenz ≤ alte Architektur
- [ ] Durchsatz ≥ alte Architektur
- [ ] Keine Datenverluste
- [ ] Management UI funktionsfähig
- [ ] Team kann System betreiben

## Zeitvergleich: RabbitMQ vs. Kafka

| Phase | RabbitMQ | Kafka | Unterschied |
|-------|----------|-------|-------------|
| Vorbereitung | 2 Wochen | 2-3 Wochen | -1 Woche |
| Infrastruktur | 1-2 Wochen | 1-2 Wochen | Gleich |
| Erste Worker | 2-3 Wochen | 2-3 Wochen | Gleich |
| Weitere Worker | 2-3 Wochen | 2-3 Wochen | Gleich |
| Integration | 2 Wochen | 2-3 Wochen | -1 Woche |
| Optimierung | 1-2 Wochen | 1-2 Wochen | Gleich |
| **Gesamt** | **10-14 Wochen** | **12-18 Wochen** | **-2-4 Wochen** |

**RabbitMQ ist 15-25% schneller zu implementieren!**
