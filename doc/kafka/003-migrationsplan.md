# ASCII Sky - Kafka Migrationsplan

## Übersicht

Dieser Plan beschreibt die schrittweise Migration von der aktuellen monolithischen Architektur zu einer Kafka-basierten Event-Streaming-Architektur.

## Migrationsstrategie

### Ansatz: Strangler Fig Pattern

Wir verwenden das **Strangler Fig Pattern**, um die alte Architektur schrittweise durch die neue zu ersetzen:

1. Neue Funktionalität parallel zur alten implementieren
2. Traffic schrittweise auf neue Komponenten umleiten
3. Alte Komponenten entfernen, wenn nicht mehr benötigt

### Phasen

```
Phase 0: Vorbereitung (2-3 Wochen)
Phase 1: Kafka-Infrastruktur (1-2 Wochen)
Phase 2: Erste Producer (Asteroids) (2-3 Wochen)
Phase 3: Weitere Producer (Comets, Celestial) (2-3 Wochen)
Phase 4: Consumer-Migration (2-3 Wochen)
Phase 5: Scheduler & Precompute (1-2 Wochen)
Phase 6: Optimierung & Cleanup (1-2 Wochen)
Phase 7: Monitoring & Produktion (1 Woche)

Gesamt: 12-18 Wochen
```

## Phase 0: Vorbereitung

### Ziele
- Anforderungen klären
- Technologie-Stack festlegen
- Entwicklungsumgebung aufsetzen
- Team schulen

### Aufgaben

#### 1. Requirements Engineering
- [ ] Durchsatz-Anforderungen definieren (Requests/Sekunde)
- [ ] Latenz-Anforderungen definieren (P50, P95, P99)
- [ ] Verfügbarkeits-Anforderungen definieren (SLA)
- [ ] Skalierbarkeits-Anforderungen definieren (max. Nutzer)
- [ ] Kosten-Budget festlegen

#### 2. Technologie-Entscheidungen
- [ ] Kafka-Distribution wählen (Apache, Confluent, AWS MSK)
- [ ] Client-Library wählen (confluent-kafka-python empfohlen)
- [ ] Serialisierung wählen (JSON für Start, später Avro)
- [ ] Deployment-Plattform wählen (Docker Compose, Kubernetes)
- [ ] Monitoring-Stack wählen (Prometheus + Grafana)

#### 3. Entwicklungsumgebung
- [ ] Kafka-Cluster lokal aufsetzen (docker-compose)
- [ ] Schema Registry aufsetzen (optional)
- [ ] Kafdrop/Kafka-UI installieren
- [ ] Entwickler-Dokumentation erstellen

#### 4. Team-Training
- [ ] Kafka-Grundlagen (Concepts, Topics, Partitions)
- [ ] Producer/Consumer API
- [ ] Kafka Streams (optional)
- [ ] Best Practices & Patterns

### Deliverables
- Requirements-Dokument
- Technologie-Stack-Entscheidung
- Lokale Kafka-Entwicklungsumgebung
- Team-Training abgeschlossen

## Phase 1: Kafka-Infrastruktur

### Ziele
- Kafka-Cluster produktionsreif aufsetzen
- Topics erstellen
- Monitoring einrichten

### Aufgaben

#### 1. Kafka-Cluster Setup (Kafka 4.1 mit KRaft)
- [ ] CLUSTER_ID generieren: `docker run apache/kafka:4.1.0 kafka-storage.sh random-uuid`
- [ ] 2-3 Kafka-Broker auf separaten Hosts deployen
- [ ] KRaft Mode konfigurieren (einziger Modus in Kafka 4.1)
- [ ] Replication Factor = 2 oder 3 setzen (je nach Anzahl Hosts)
- [ ] Min In-Sync Replicas = 1 oder 2 setzen
- [ ] Retention Policy konfigurieren (7 Tage)
- [ ] Firewall-Regeln: Ports 9092, 9093 zwischen Hosts öffnen

#### 2. Topic-Erstellung
```bash
# CLUSTER_ID generieren (einmalig, vor erstem Start)
CLUSTER_ID=$(docker run apache/kafka:4.1.0 kafka-storage.sh random-uuid)
echo "CLUSTER_ID: $CLUSTER_ID"  # In docker-compose Dateien verwenden!

# Topics erstellen (nach Cluster-Start)
# asteroid-positions
docker exec kafka-1 kafka-topics.sh --create \
  --bootstrap-server localhost:9092 \
  --topic asteroid-positions \
  --partitions 12 \
  --replication-factor 2 \
  --config min.insync.replicas=1 \
  --config retention.ms=604800000

# comet-positions
docker exec kafka-1 kafka-topics.sh --create \
  --bootstrap-server localhost:9092 \
  --topic comet-positions \
  --partitions 12 \
  --replication-factor 2 \
  --config min.insync.replicas=1 \
  --config retention.ms=604800000

# celestial-positions
docker exec kafka-1 kafka-topics.sh --create \
  --bootstrap-server localhost:9092 \
  --topic celestial-positions \
  --partitions 12 \
  --replication-factor 2 \
  --config min.insync.replicas=1 \
  --config retention.ms=604800000

# constellation-data
docker exec kafka-1 kafka-topics.sh --create \
  --bootstrap-server localhost:9092 \
  --topic constellation-data \
  --partitions 6 \
  --replication-factor 2 \
  --config min.insync.replicas=1 \
  --config retention.ms=2592000000

# computation-requests
docker exec kafka-1 kafka-topics.sh --create \
  --bootstrap-server localhost:9092 \
  --topic computation-requests \
  --partitions 4 \
  --replication-factor 2 \
  --config min.insync.replicas=1 \
  --config retention.ms=86400000

# computation-status
docker exec kafka-1 kafka-topics.sh --create \
  --bootstrap-server localhost:9092 \
  --topic computation-status \
  --partitions 4 \
  --replication-factor 2 \
  --config min.insync.replicas=1 \
  --config retention.ms=86400000

# Cluster-Status prüfen
docker exec kafka-1 kafka-broker-api-versions.sh --bootstrap-server localhost:9092
docker exec kafka-1 kafka-topics.sh --bootstrap-server localhost:9092 --list
```

#### 3. Monitoring Setup
- [ ] Prometheus Exporter für Kafka installieren
- [ ] Grafana Dashboards importieren
- [ ] Alerting-Regeln definieren
- [ ] Log-Aggregation einrichten (ELK/Loki)

#### 4. Schema Registry (optional)
- [ ] Schema Registry deployen
- [ ] Schemas für Topics registrieren
- [ ] Compatibility Mode setzen (BACKWARD)

### Deliverables
- Produktionsreifer Kafka-Cluster
- Alle Topics erstellt und konfiguriert
- Monitoring-Dashboard funktionsfähig
- Dokumentation für Betrieb

### Docker Compose Beispiel

```yaml
# docker-compose.kafka.yml
version: '3.8'

services:
  kafka-1:
    image: confluentinc/cp-kafka:7.5.0
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka-1:9092
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka-1:9093,2@kafka-2:9093,3@kafka-3:9093
      KAFKA_LOG_DIRS: /var/lib/kafka/data
      CLUSTER_ID: asciisky-kafka-cluster
    volumes:
      - kafka-1-data:/var/lib/kafka/data

  kafka-2:
    image: confluentinc/cp-kafka:7.5.0
    environment:
      KAFKA_NODE_ID: 2
      # ... analog zu kafka-1
    volumes:
      - kafka-2-data:/var/lib/kafka/data

  kafka-3:
    image: confluentinc/cp-kafka:7.5.0
    environment:
      KAFKA_NODE_ID: 3
      # ... analog zu kafka-1
    volumes:
      - kafka-3-data:/var/lib/kafka/data

  kafdrop:
    image: obsidiandynamics/kafdrop:latest
    ports:
      - "9000:9000"
    environment:
      KAFKA_BROKERCONNECT: kafka-1:9092,kafka-2:9092,kafka-3:9092

volumes:
  kafka-1-data:
  kafka-2-data:
  kafka-3-data:
```

## Phase 2: Erste Producer (Asteroids)

### Ziele
- Asteroid Producer implementieren
- Parallel zur alten Architektur laufen lassen
- Daten in Kafka schreiben

### Aufgaben

#### 1. Producer-Implementierung

**Datei**: `producers/asteroid_producer.py`

```python
from confluent_kafka import Producer
import json
import time
from datetime import datetime, timezone
import bright_asteroids
from api.computation import LOADER, ts, eph

class AsteroidProducer:
    def __init__(self, bootstrap_servers):
        self.producer = Producer({
            'bootstrap.servers': bootstrap_servers,
            'client.id': 'asteroid-producer',
            'compression.type': 'lz4',
            'linger.ms': 10,
            'batch.size': 16384
        })
        self.topic = 'asteroid-positions'
    
    def delivery_report(self, err, msg):
        if err:
            print(f'Message delivery failed: {err}')
        else:
            print(f'Message delivered to {msg.topic()} [{msg.partition()}]')
    
    def compute_and_publish(self, location_key, lat, lon, elevation, time_bucket_dt):
        """Berechnet Asteroiden-Positionen und publiziert sie"""
        location = {
            'latitude': lat,
            'longitude': lon,
            'elevation': elevation
        }
        
        # Berechnung mit Skyfield (bestehender Code)
        asteroids = bright_asteroids.load_bright_asteroids(
            LOADER, ts, eph, location,
            max_magnitude=20.0,
            use_cache=False,  # Kein lokaler Cache mehr
            current_dt=time_bucket_dt
        )
        
        # Message erstellen
        message = {
            'location_key': location_key,
            'time_bucket': time_bucket_dt.strftime('%Y%m%dT%H'),
            'timestamp': time_bucket_dt.isoformat(),
            'asteroids': asteroids,
            'computed_at': datetime.now(timezone.utc).isoformat(),
            'producer_id': 'asteroid-producer-1'
        }
        
        # In Kafka schreiben
        key = f"{location_key}:{message['time_bucket']}"
        self.producer.produce(
            self.topic,
            key=key.encode('utf-8'),
            value=json.dumps(message).encode('utf-8'),
            callback=self.delivery_report
        )
        
        # Flush periodisch
        self.producer.poll(0)
    
    def close(self):
        self.producer.flush()
```

#### 2. Request Consumer implementieren

**Datei**: `producers/request_consumer.py`

```python
from confluent_kafka import Consumer, KafkaError
import json

class RequestConsumer:
    def __init__(self, bootstrap_servers, group_id):
        self.consumer = Consumer({
            'bootstrap.servers': bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': True
        })
        self.consumer.subscribe(['computation-requests'])
    
    def consume(self, callback):
        """Konsumiert Requests und ruft Callback auf"""
        try:
            while True:
                msg = self.consumer.poll(1.0)
                
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        print(f'Consumer error: {msg.error()}')
                        continue
                
                # Request verarbeiten
                request = json.loads(msg.value().decode('utf-8'))
                if request['type'] == 'asteroids':
                    callback(request)
        
        except KeyboardInterrupt:
            pass
        finally:
            self.consumer.close()
```

#### 3. Main Worker Loop

**Datei**: `producers/asteroid_worker.py`

```python
import os
from asteroid_producer import AsteroidProducer
from request_consumer import RequestConsumer
from cache_utils import normalize_location, location_key
from datetime import datetime

def process_request(request, producer):
    """Verarbeitet einen Computation Request"""
    location_key_str = request['location_key']
    
    # Location aus Key extrahieren
    parts = location_key_str.split('_')
    lat = float(parts[0].split('+')[1] if '+' in parts[0] else parts[0].split('-')[1])
    lon = float(parts[1].split('+')[1] if '+' in parts[1] else parts[1].split('-')[1])
    elev = float(parts[2].split('+')[1] if '+' in parts[2] else parts[2].split('-')[1])
    
    # Zeit-Range verarbeiten
    start = datetime.fromisoformat(request['time_range']['start'])
    end = datetime.fromisoformat(request['time_range']['end'])
    
    # Für jede Stunde berechnen
    current = start
    while current <= end:
        producer.compute_and_publish(location_key_str, lat, lon, elev, current)
        current += timedelta(hours=1)

def main():
    bootstrap_servers = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka-1:9092')
    
    producer = AsteroidProducer(bootstrap_servers)
    consumer = RequestConsumer(bootstrap_servers, 'asteroid-workers')
    
    def callback(request):
        process_request(request, producer)
    
    consumer.consume(callback)

if __name__ == '__main__':
    main()
```

#### 4. Docker Integration

**Datei**: `docker-compose.producers.yml`

```yaml
services:
  asteroid-producer-1:
    build:
      context: .
      dockerfile: Dockerfile.producer
    command: ["python", "producers/asteroid_worker.py"]
    environment:
      - KAFKA_BOOTSTRAP_SERVERS=kafka-1:9092,kafka-2:9092,kafka-3:9092
      - PRODUCER_ID=asteroid-producer-1
    volumes:
      - .:/app
    depends_on:
      - kafka-1
      - kafka-2
      - kafka-3
    restart: unless-stopped

  asteroid-producer-2:
    # ... analog zu producer-1 mit PRODUCER_ID=asteroid-producer-2
```

#### 5. Testing
- [ ] Unit Tests für Producer
- [ ] Integration Tests mit Test-Kafka
- [ ] Performance Tests (Throughput, Latency)
- [ ] Parallel zur alten Architektur laufen lassen
- [ ] Datenqualität vergleichen

### Deliverables
- Funktionierender Asteroid Producer
- Request Consumer implementiert
- Docker-Integration abgeschlossen
- Tests erfolgreich
- Dokumentation

## Phase 3: Weitere Producer (Comets, Celestial)

### Ziele
- Comet Producer implementieren (analog zu Asteroids)
- Celestial Producer implementieren
- Constellation Producer implementieren

### Aufgaben

#### 1. Comet Producer
- [ ] `producers/comet_producer.py` erstellen (analog zu Asteroids)
- [ ] `producers/comet_worker.py` erstellen
- [ ] Docker Service hinzufügen
- [ ] Tests durchführen

#### 2. Celestial Producer
- [ ] `producers/celestial_producer.py` erstellen
- [ ] Echtzeit-Berechnung implementieren (kein Request-basiert)
- [ ] Kontinuierliches Publishing (alle 60 Sekunden)
- [ ] Docker Service hinzufügen

#### 3. Constellation Producer
- [ ] `producers/constellation_producer.py` erstellen
- [ ] Einmalige Berechnung beim Start
- [ ] Updates bei Datenänderungen
- [ ] Docker Service hinzufügen

### Deliverables
- Alle Producer implementiert und getestet
- Docker-Integration abgeschlossen
- Dokumentation aktualisiert

## Phase 4: Consumer-Migration

### Ziele
- Web Service auf Kafka-Consumer umstellen
- Alte Cache-Logik durch Kafka-Consumer ersetzen
- Backward Compatibility sicherstellen

### Aufgaben

#### 1. Kafka Consumer in Web Service

**Datei**: `api/kafka_consumer.py`

```python
from confluent_kafka import Consumer, KafkaError
import json
from datetime import datetime, timezone
import threading

class PositionConsumer:
    def __init__(self, bootstrap_servers, topics):
        self.consumer = Consumer({
            'bootstrap.servers': bootstrap_servers,
            'group.id': 'web-service-consumers',
            'auto.offset.reset': 'latest',
            'enable.auto.commit': True
        })
        self.consumer.subscribe(topics)
        self.cache = {}  # In-memory cache
        self.running = False
        self.thread = None
    
    def start(self):
        """Startet Consumer in separatem Thread"""
        self.running = True
        self.thread = threading.Thread(target=self._consume_loop)
        self.thread.daemon = True
        self.thread.start()
    
    def _consume_loop(self):
        """Konsumiert Messages und cached sie"""
        while self.running:
            msg = self.consumer.poll(1.0)
            
            if msg is None:
                continue
            if msg.error():
                continue
            
            # Message in Cache speichern
            key = msg.key().decode('utf-8')
            value = json.loads(msg.value().decode('utf-8'))
            self.cache[key] = value
    
    def get(self, location_key, time_bucket):
        """Holt Daten aus Cache"""
        key = f"{location_key}:{time_bucket}"
        return self.cache.get(key)
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        self.consumer.close()
```

#### 2. Web Service Integration

**Datei**: `main.py` (anpassen)

```python
from api.kafka_consumer import PositionConsumer
from api.kafka_producer import RequestProducer

# Startup
@app.on_event("startup")
async def startup_event():
    # Kafka Consumer starten
    app.position_consumer = PositionConsumer(
        bootstrap_servers=os.environ.get('KAFKA_BOOTSTRAP_SERVERS'),
        topics=['asteroid-positions', 'comet-positions', 'celestial-positions']
    )
    app.position_consumer.start()
    
    # Request Producer initialisieren
    app.request_producer = RequestProducer(
        bootstrap_servers=os.environ.get('KAFKA_BOOTSTRAP_SERVERS')
    )

@app.on_event("shutdown")
async def shutdown_event():
    app.position_consumer.stop()
    app.request_producer.close()
```

#### 3. API Endpoint Anpassung

**Datei**: `api/routes/asteroids.py` (anpassen)

```python
@router.get("/bright_asteroids")
async def get_bright_asteroids(request: Request, ...):
    # Location und Zeit ermitteln
    location_key_str = ...
    time_bucket = ...
    
    # Aus Kafka-Cache holen
    data = request.app.position_consumer.get(location_key_str, time_bucket)
    
    if data is None:
        # Cache Miss: Request senden
        request.app.request_producer.send_request(
            type='asteroids',
            location_key=location_key_str,
            time_range={'start': ..., 'end': ...},
            priority='high'
        )
        
        # Fallback: Alte Berechnung (temporär)
        data = old_compute_asteroids(...)
    
    return data['asteroids']
```

#### 4. Graduelle Migration
- [ ] Feature Flag für Kafka-Consumer einbauen
- [ ] A/B Testing durchführen
- [ ] Monitoring vergleichen (alte vs. neue Architektur)
- [ ] Schrittweise Traffic umleiten (10% → 50% → 100%)

### Deliverables
- Web Service konsumiert von Kafka
- Alte Logik als Fallback vorhanden
- A/B Testing erfolgreich
- Dokumentation aktualisiert

## Phase 5: Scheduler & Precompute

### Ziele
- Precompute-Logik auf Kafka umstellen
- Scheduler für Requests implementieren
- Alte Worker-Services ersetzen

### Aufgaben

#### 1. Scheduler Service

**Datei**: `scheduler/precompute_scheduler.py`

```python
from apscheduler.schedulers.blocking import BlockingScheduler
from confluent_kafka import Producer
import json
from datetime import datetime, timedelta, timezone

class PrecomputeScheduler:
    def __init__(self, bootstrap_servers):
        self.producer = Producer({'bootstrap.servers': bootstrap_servers})
        self.scheduler = BlockingScheduler()
    
    def schedule_precompute(self):
        """Generiert Requests für rollendes Zeitfenster"""
        # Standorte ermitteln
        locations = self.get_target_locations()
        
        # Zeitfenster: jetzt + 720 Stunden
        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=720)
        
        for location in locations:
            request = {
                'request_id': f"precompute_{location['loc_key']}_{int(now.timestamp())}",
                'type': 'asteroids',
                'location_key': location['loc_key'],
                'time_range': {
                    'start': now.isoformat(),
                    'end': end.isoformat()
                },
                'priority': 'low',
                'requested_at': now.isoformat(),
                'requested_by': 'scheduler'
            }
            
            self.producer.produce(
                'computation-requests',
                key=request['request_id'].encode('utf-8'),
                value=json.dumps(request).encode('utf-8')
            )
        
        self.producer.flush()
    
    def start(self):
        # Stündlich ausführen
        self.scheduler.add_job(
            self.schedule_precompute,
            'cron',
            minute=0
        )
        self.scheduler.start()
```

#### 2. Docker Service

```yaml
services:
  scheduler:
    build:
      context: .
      dockerfile: Dockerfile.scheduler
    command: ["python", "scheduler/precompute_scheduler.py"]
    environment:
      - KAFKA_BOOTSTRAP_SERVERS=kafka-1:9092,kafka-2:9092,kafka-3:9092
    restart: unless-stopped
```

#### 3. Alte Worker deaktivieren
- [ ] `precompute_worker.py` durch Scheduler ersetzen
- [ ] `precompute_task_worker.py` durch Producer ersetzen
- [ ] Docker Services entfernen

### Deliverables
- Scheduler funktionsfähig
- Alte Worker-Services entfernt
- Precompute läuft über Kafka

## Phase 6: Optimierung & Cleanup

### Ziele
- Performance optimieren
- Alte Code-Teile entfernen
- Dokumentation vervollständigen

### Aufgaben

#### 1. Performance-Optimierung
- [ ] Batch-Processing für Producer
- [ ] Compression optimieren (lz4 vs. snappy)
- [ ] Partitioning-Strategie überprüfen
- [ ] Consumer Lag reduzieren
- [ ] Cache-Strategien optimieren (Redis?)

#### 2. Code-Cleanup
- [ ] Alte Cache-Logik entfernen
- [ ] SQLite-Pickle-Cache entfernen
- [ ] Ungenutzte Dependencies entfernen
- [ ] Code-Duplikation beseitigen

#### 3. Dokumentation
- [ ] API-Dokumentation aktualisieren
- [ ] Architektur-Diagramme erstellen
- [ ] Betriebshandbuch schreiben
- [ ] Troubleshooting-Guide erstellen

### Deliverables
- Optimierte Performance
- Sauberer Code
- Vollständige Dokumentation

## Phase 7: Monitoring & Produktion

### Ziele
- Monitoring vervollständigen
- Alerting einrichten
- Produktions-Deployment

### Aufgaben

#### 1. Monitoring
- [ ] Kafka-Metriken in Grafana
- [ ] Producer/Consumer Lag Dashboards
- [ ] Latency-Metriken (P50, P95, P99)
- [ ] Error-Rate Monitoring

#### 2. Alerting
- [ ] Consumer Lag > Threshold
- [ ] Producer Errors > Threshold
- [ ] Kafka Broker Down
- [ ] Disk Space Low

#### 3. Produktion
- [ ] Staging-Deployment
- [ ] Load Testing
- [ ] Disaster Recovery Plan
- [ ] Produktions-Deployment

### Deliverables
- Vollständiges Monitoring
- Alerting konfiguriert
- Produktions-Deployment erfolgreich

## Rollback-Plan

Falls Probleme auftreten:

1. **Feature Flag zurücksetzen**: Alte Architektur aktivieren
2. **Traffic umleiten**: Load Balancer auf alte Services
3. **Kafka-Consumer stoppen**: Keine neuen Messages konsumieren
4. **Alte Worker starten**: Precompute-Worker reaktivieren
5. **Analyse**: Ursache finden und beheben
6. **Retry**: Migration erneut versuchen

## Risiken & Mitigation

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| Kafka-Cluster instabil | Mittel | Hoch | Managed Kafka verwenden (AWS MSK) |
| Performance schlechter | Mittel | Hoch | Ausführliches Load Testing vorher |
| Datenverlust | Niedrig | Sehr hoch | Replication Factor 3, Backups |
| Komplexität zu hoch | Hoch | Mittel | Schrittweise Migration, Training |
| Kosten zu hoch | Mittel | Mittel | Kosten-Monitoring, Optimierung |

## Erfolgskriterien

- [ ] Alle API-Endpoints funktionieren
- [ ] Latenz ≤ alte Architektur
- [ ] Durchsatz ≥ alte Architektur
- [ ] Keine Datenverluste
- [ ] Monitoring vollständig
- [ ] Team kann System betreiben
- [ ] Dokumentation vollständig
