# ASCII Sky - RabbitMQ 4.1 Zielarchitektur

## Übersicht

Die RabbitMQ-basierte Architektur nutzt Message Queues für asynchrone Task-Verarbeitung und entkoppelt Datenproduktion (Berechnung) von Datenkonsumption (Anzeige).

## Architektur-Diagramm

```
┌─────────────────────────────────────────────────────────────────┐
│                    RabbitMQ 4.1 Cluster                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Node 1     │  │   Node 2     │  │   Node 3     │          │
│  │  (Master)    │  │  (Mirror)    │  │  (Mirror)    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                   │
│  Exchanges:                                                       │
│  ├─ celestial.topic (Topic Exchange)                            │
│  ├─ computation.direct (Direct Exchange)                        │
│  └─ computation.priority (Priority Queue)                       │
│                                                                   │
│  Queues:                                                          │
│  ├─ asteroid.compute (Priority 0-10)                            │
│  ├─ comet.compute (Priority 0-10)                               │
│  ├─ celestial.compute                                            │
│  ├─ constellation.compute                                        │
│  ├─ computation.results                                          │
│  └─ computation.status                                           │
└─────────────────────────────────────────────────────────────────┘
         ▲                                    │
         │ Publish                            │ Consume
         │                                    ▼
┌────────┴────────┐                  ┌────────────────┐
│   PRODUCERS     │                  │   CONSUMERS    │
│                 │                  │                │
│ ┌─────────────┐ │                  │ ┌────────────┐ │
│ │  Asteroid   │ │                  │ │    Web     │ │
│ │   Worker    │ │                  │ │  Service   │ │
│ │  (Python)   │ │                  │ │ (FastAPI)  │ │
│ └─────────────┘ │                  │ └────────────┘ │
│                 │                  │                │
│ ┌─────────────┐ │                  │ ┌────────────┐ │
│ │   Comet     │ │                  │ │  Scheduler │ │
│ │   Worker    │ │                  │ │  Service   │ │
│ │  (Python)   │ │                  │ │            │ │
│ └─────────────┘ │                  │ └────────────┘ │
│                 │                  └────────────────┘
│ ┌─────────────┐ │
│ │ Celestial   │ │
│ │   Worker    │ │
│ │  (Python)   │ │
│ └─────────────┘ │
│                 │
│ ┌─────────────┐ │
│ │Constellation│ │
│ │   Worker    │ │
│ │  (Python)   │ │
│ └─────────────┘ │
└─────────────────┘
```

## Komponenten

### 1. RabbitMQ 4.1 Cluster

#### Cluster-Konfiguration
- **Anzahl**: 2-3 Nodes (empfohlen: 3)
- **Queue-Typ**: Quorum Queues (repliziert, persistent)
- **Mirroring**: Automatisch über alle Nodes
- **Persistence**: Durable Queues & Messages
- **HA Policy**: `ha-mode: all` oder `ha-mode: exactly 2`

#### RabbitMQ 4.1 Neuerungen
- **Quorum Queue Performance**: Bis zu 2x schneller als 3.x
- **AMQP 1.0 Filter Expressions**: Selektives Konsumieren
- **Feature Flags Auto-Enable**: Automatische Aktivierung bei Cluster-Upgrade
- **rabbitmqadmin v2**: Verbessertes CLI-Tool
- **Streams Performance**: Optimiert für hohen Durchsatz

### 2. Exchanges

#### celestial.topic (Topic Exchange)
- **Typ**: Topic
- **Routing Keys**: 
  - `asteroid.position.<location_key>`
  - `comet.position.<location_key>`
  - `celestial.position.<location_key>`
  - `constellation.data.<constellation_id>`
- **Durable**: true
- **Auto-Delete**: false

#### computation.direct (Direct Exchange)
- **Typ**: Direct
- **Routing Keys**:
  - `compute.asteroid`
  - `compute.comet`
  - `compute.celestial`
  - `compute.constellation`
- **Durable**: true
- **Priority**: Unterstützt (0-10)

### 3. Queues

#### asteroid.compute (Priority Queue)
- **Typ**: Quorum Queue
- **Priority**: 0-10 (10 = höchste Priorität)
- **TTL**: 1 Stunde (Messages verfallen nach 1h)
- **Max Length**: 10.000 Messages
- **Overflow**: reject-publish
- **Message Schema**:
```json
{
  "task_id": "task_20250117_140000_abc123",
  "type": "asteroid",
  "location": {
    "latitude": 48.2082,
    "longitude": 16.3738,
    "elevation": 170
  },
  "time_range": {
    "start": "2025-01-17T14:00:00Z",
    "end": "2025-01-18T14:00:00Z"
  },
  "priority": 10,
  "requested_at": "2025-01-17T14:00:00Z",
  "requested_by": "web-service-1"
}
```

#### computation.results (Results Queue)
- **Typ**: Quorum Queue
- **TTL**: 5 Minuten
- **Max Length**: 50.000 Messages
- **Message Schema**:
```json
{
  "task_id": "task_20250117_140000_abc123",
  "location_key": "lat+48.2082_lon+16.3738_el+0170",
  "time_bucket": "20250117T14",
  "timestamp": "2025-01-17T14:00:00Z",
  "asteroids": [
    {
      "name": "Ceres",
      "altitude": 45.2,
      "azimuth": 180.5,
      "magnitude": 8.5
    }
  ],
  "computed_at": "2025-01-17T14:03:22Z",
  "worker_id": "asteroid-worker-1"
}
```

#### computation.status (Status Queue)
- **Typ**: Classic Queue (nicht repliziert, für Performance)
- **TTL**: 1 Minute
- **Message Schema**:
```json
{
  "task_id": "task_20250117_140000_abc123",
  "status": "completed",
  "progress": 100,
  "started_at": "2025-01-17T14:00:05Z",
  "completed_at": "2025-01-17T14:03:22Z",
  "worker_id": "asteroid-worker-2",
  "error": null
}
```

### 4. Worker Services (Consumers)

#### Asteroid Worker
- **Sprache**: Python
- **Library**: pika (RabbitMQ Python Client)
- **Aufgaben**:
  - Konsumiert von `asteroid.compute` Queue
  - Berechnet Positionen mit Skyfield
  - Publiziert Ergebnisse zu `computation.results`
  - Sendet Status-Updates zu `computation.status`
- **Skalierung**: Horizontal (mehrere Worker-Instanzen)
- **Prefetch**: 1 (ein Task pro Worker gleichzeitig)
- **Parallelität**: 4-8 Instanzen

#### Comet Worker
- **Analog zu Asteroid Worker**

#### Celestial Worker
- **Analog zu Asteroid Worker**
- **Besonderheit**: Berechnet Sonne, Mond, Planeten

#### Constellation Worker
- **Analog zu Asteroid Worker**
- **Besonderheit**: Lädt Stellarium-Daten

### 5. Web Service (FastAPI)

#### Aufgaben
- REST API für Frontend
- Publiziert Computation Requests zu Queues
- Konsumiert Results von `computation.results` Queue
- Cached Ergebnisse in Redis (optional)
- RPC-Pattern für synchrone Requests (mit Correlation ID)

#### RPC-Pattern (Request/Reply)
```python
# Web Service sendet Request mit reply_to und correlation_id
channel.basic_publish(
    exchange='computation.direct',
    routing_key='compute.asteroid',
    properties=pika.BasicProperties(
        reply_to='computation.results',
        correlation_id='req_123',
        priority=10,
        delivery_mode=2  # persistent
    ),
    body=json.dumps(request)
)

# Worker sendet Reply mit gleicher correlation_id
channel.basic_publish(
    exchange='',
    routing_key=properties.reply_to,
    properties=pika.BasicProperties(
        correlation_id=properties.correlation_id
    ),
    body=json.dumps(result)
)
```

### 6. Scheduler Service

#### Aufgaben
- Generiert Precompute-Tasks für rollendes Zeitfenster
- Publiziert zu Queues mit niedriger Priorität (0-2)
- Läuft stündlich (Cron-Job)
- Berücksichtigt bekannte Standorte

### 7. Management & Monitoring

#### RabbitMQ Management UI
- **Port**: 15672
- **Features**:
  - Queue-Monitoring (Länge, Rate, Consumers)
  - Message-Tracing
  - Connection-Management
  - Policy-Verwaltung

#### Prometheus Integration
- **rabbitmq_prometheus Plugin**: Metriken-Export
- **Metriken**:
  - Queue-Länge
  - Message-Rate (publish/deliver/ack)
  - Consumer-Count
  - Memory-Usage

## Datenfluss-Szenarien

### 1. Normale Anfrage (Cache Hit)

```
Frontend → Web Service → Redis Cache → Response
```

### 2. Cache Miss (On-Demand)

```
Frontend → Web Service → Publish(compute.asteroid, priority=10)
                      ↓
        Asteroid Worker ← Consume(asteroid.compute)
                      ↓
              Skyfield Berechnung
                      ↓
        Publish(computation.results, correlation_id)
                      ↓
        Web Service ← Consume(computation.results)
                      ↓
              Response + Cache Update
```

### 3. Precompute (Background)

```
Scheduler → Publish(compute.asteroid, priority=2)
         ↓
Workers ← Consume(asteroid.compute)
         ↓
Berechnung → Publish(computation.results)
         ↓
Redis Cache Update
```

### 4. Status-Tracking

```
Web Service → Publish(compute.asteroid)
           ↓
Worker ← Consume → Publish(computation.status, "started")
           ↓
Berechnung
           ↓
Publish(computation.status, "progress: 50%")
           ↓
Publish(computation.status, "completed")
```

## Vorteile der RabbitMQ-Architektur

### 1. Entkopplung
- Producer und Consumer unabhängig
- Keine direkte Prozess-Kommunikation
- Einfaches Hinzufügen neuer Worker

### 2. Skalierbarkeit
- Horizontale Skalierung aller Worker
- Load Balancing durch RabbitMQ
- Prefetch-Control für gleichmäßige Verteilung

### 3. Fehlertoleranz
- Quorum Queues repliziert über alle Nodes
- Automatic Failover bei Node-Ausfall
- Message Acknowledgements (keine Datenverluste)

### 4. Performance
- Niedrige Latenz (< 10ms)
- Priority Queues für wichtige Tasks
- Prefetch-Optimierung

### 5. Flexibilität
- Topic Exchange für flexible Routing
- Dead Letter Queues für Fehlerbehandlung
- TTL für automatisches Aufräumen

### 6. Observability
- Management UI mit Echtzeit-Monitoring
- Message-Tracing
- Prometheus-Metriken

## Herausforderungen

### 1. Kein Replay
- Messages werden nach Konsum gelöscht
- Keine Event-Sourcing-Fähigkeit
- Lösung: Zusätzliches Logging oder Kafka für Analytics

### 2. Message-Größe
- RabbitMQ nicht optimal für große Messages (> 1 MB)
- Lösung: Referenzen statt volle Daten (z.B. S3-URLs)

### 3. Komplexität
- Mehr Komponenten als aktuelle Architektur
- RabbitMQ-Expertise erforderlich

### 4. Kosten
- RabbitMQ-Cluster benötigt Ressourcen
- Mehr Container/VMs als aktuell

## Empfohlene Technologien

### RabbitMQ Client Libraries
1. **pika** (Python, empfohlen)
   - Offizieller Python-Client
   - Sync & Async Support
   - Gut dokumentiert

2. **aio-pika** (Python, Async)
   - Asyncio-basiert
   - Perfekt für FastAPI
   - Höhere Performance

### Serialisierung
1. **JSON** (empfohlen für Start)
   - Human-readable
   - Einfach zu debuggen
   - Universell

2. **MessagePack** (für Produktion)
   - Kompakter als JSON
   - Schneller als JSON
   - Binärformat

### Deployment
1. **Docker Compose Multi-Host** (Development & Produktion)
   - RabbitMQ 4.1 Cluster
   - 2-3 Maschinen in getrennten Netzwerken
   - Einfaches Setup

2. **Kubernetes** (Enterprise)
   - RabbitMQ Cluster Operator
   - Auto-Scaling
   - HA

3. **Managed RabbitMQ** (CloudAMQP, AWS MQ)
   - Kein Betrieb
   - Auto-Scaling
   - Backups

## Vergleich: RabbitMQ vs. Kafka für ASCII Sky

| Kriterium | RabbitMQ | Kafka |
|-----------|----------|-------|
| **Latenz** | ⭐⭐⭐⭐⭐ (< 10ms) | ⭐⭐⭐ (50-100ms) |
| **Durchsatz** | ⭐⭐⭐⭐ (100k msg/s) | ⭐⭐⭐⭐⭐ (1M msg/s) |
| **Komplexität** | ⭐⭐⭐ (Mittel) | ⭐⭐ (Hoch) |
| **Ressourcen** | ⭐⭐⭐⭐ (Niedrig) | ⭐⭐ (Hoch) |
| **Priority Queues** | ⭐⭐⭐⭐⭐ (Native) | ⭐ (Workaround) |
| **RPC-Pattern** | ⭐⭐⭐⭐⭐ (Native) | ⭐⭐ (Komplex) |
| **Replay** | ⭐ (Nein) | ⭐⭐⭐⭐⭐ (Ja) |
| **Management UI** | ⭐⭐⭐⭐⭐ (Eingebaut) | ⭐⭐⭐ (Kafdrop) |
| **Use Case Fit** | ⭐⭐⭐⭐⭐ (Perfekt) | ⭐⭐⭐ (Gut) |

**Empfehlung für ASCII Sky**: RabbitMQ ist die bessere Wahl.
