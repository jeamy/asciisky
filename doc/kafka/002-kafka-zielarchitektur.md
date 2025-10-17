# ASCII Sky - Kafka Zielarchitektur

## Übersicht

Die Kafka-basierte Architektur trennt Datenproduktion (Berechnung) von Datenkonsumption (Anzeige) durch ein Event-Streaming-System.

## Architektur-Diagramm

```
┌─────────────────────────────────────────────────────────────────┐
│                        Apache Kafka Cluster                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Broker 1   │  │   Broker 2   │  │   Broker 3   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                   │
│  Topics:                                                          │
│  ├─ asteroid-positions (partitioned by location_key)            │
│  ├─ comet-positions (partitioned by location_key)               │
│  ├─ celestial-positions (partitioned by location_key)           │
│  ├─ constellation-data (partitioned by constellation_id)        │
│  ├─ computation-requests (partitioned by priority)              │
│  └─ computation-status (partitioned by task_id)                 │
└─────────────────────────────────────────────────────────────────┘
         ▲                                    │
         │ Produce                            │ Consume
         │                                    ▼
┌────────┴────────┐                  ┌────────────────┐
│   PRODUCERS     │                  │   CONSUMERS    │
│                 │                  │                │
│ ┌─────────────┐ │                  │ ┌────────────┐ │
│ │  Asteroid   │ │                  │ │    Web     │ │
│ │  Producer   │ │                  │ │  Service   │ │
│ │  (Python)   │ │                  │ │ (FastAPI)  │ │
│ └─────────────┘ │                  │ └────────────┘ │
│                 │                  │                │
│ ┌─────────────┐ │                  │ ┌────────────┐ │
│ │   Comet     │ │                  │ │  Frontend  │ │
│ │  Producer   │ │                  │ │ WebSocket  │ │
│ │  (Python)   │ │                  │ │  Gateway   │ │
│ └─────────────┘ │                  │ └────────────┘ │
│                 │                  │                │
│ ┌─────────────┐ │                  └────────────────┘
│ │ Celestial   │ │
│ │  Producer   │ │
│ │  (Python)   │ │
│ └─────────────┘ │
│                 │
│ ┌─────────────┐ │
│ │Constellation│ │
│ │  Producer   │ │
│ │  (Python)   │ │
│ └─────────────┘ │
└─────────────────┘
```

## Komponenten

### 1. Apache Kafka Cluster

#### Broker-Konfiguration
- **Anzahl**: 3 Broker (Minimum für Produktion)
- **Replication Factor**: 3
- **Min In-Sync Replicas**: 2
- **Retention**: 7 Tage (konfigurierbar)
- **Compression**: lz4 oder snappy

#### KRaft Mode (Kafka 4.1)
- **Kafka 4.1**: KRaft ist der einzige unterstützte Modus (Zookeeper wurde entfernt)
- **Vorteile**: Einfachere Architektur, schnellere Metadata-Updates, keine separate Zookeeper-Infrastruktur

### 2. Kafka Topics

#### asteroid-positions
- **Partitions**: 12 (basierend auf location_key hash)
- **Replication**: 3
- **Retention**: 7 Tage
- **Key**: `{location_key}:{time_bucket}`
- **Value Schema**:
```json
{
  "location_key": "lat+48.2082_lon+16.3738_el+0170",
  "time_bucket": "20250117T14",
  "timestamp": "2025-01-17T14:00:00Z",
  "asteroids": [
    {
      "name": "Ceres",
      "designation": "(1) Ceres",
      "altitude": 45.2,
      "azimuth": 180.5,
      "distance_au": 2.77,
      "magnitude": 8.5,
      "rise_time": "06:30",
      "set_time": "18:45",
      "transit_time": "12:37"
    }
  ],
  "computed_at": "2025-01-17T13:55:00Z",
  "producer_id": "asteroid-producer-1"
}
```

#### comet-positions
- **Partitions**: 12
- **Replication**: 3
- **Retention**: 7 Tage
- **Key**: `{location_key}:{time_bucket}`
- **Value Schema**: Analog zu asteroid-positions

#### celestial-positions
- **Partitions**: 12
- **Replication**: 3
- **Retention**: 7 Tage (kürzer, da Echtzeit-Berechnung)
- **Key**: `{location_key}:{time_bucket}`
- **Value Schema**:
```json
{
  "location_key": "lat+48.2082_lon+16.3738_el+0170",
  "time_bucket": "20250117T14",
  "timestamp": "2025-01-17T14:00:00Z",
  "bodies": [
    {
      "name": "Sun",
      "altitude": 30.5,
      "azimuth": 180.0,
      "distance_au": 0.983,
      "magnitude": -26.7,
      "rise_time": "07:30",
      "set_time": "16:45",
      "transit_time": "12:07"
    },
    {
      "name": "Moon",
      "altitude": 45.0,
      "azimuth": 90.0,
      "distance_au": 0.0026,
      "magnitude": -12.5,
      "phase": "waxing_gibbous",
      "illumination": 0.87,
      "rise_time": "14:30",
      "set_time": "03:45",
      "transit_time": "21:07"
    }
  ],
  "computed_at": "2025-01-17T13:59:55Z",
  "producer_id": "celestial-producer-1"
}
```

#### constellation-data
- **Partitions**: 6
- **Replication**: 3
- **Retention**: 30 Tage (statische Daten, selten geändert)
- **Key**: `{constellation_id}`
- **Value Schema**:
```json
{
  "constellation_id": "Orion",
  "stellarium_code": "Ori",
  "stars": [
    {"hip_id": 27989, "name": "Betelgeuse", "ra": 88.79, "dec": 7.41, "magnitude": 0.5},
    {"hip_id": 24436, "name": "Rigel", "ra": 78.63, "dec": -8.20, "magnitude": 0.1}
  ],
  "lines": [
    {"from_hip": 27989, "to_hip": 24436}
  ],
  "computed_at": "2025-01-17T00:00:00Z",
  "producer_id": "constellation-producer-1"
}
```

#### computation-requests
- **Partitions**: 4 (basierend auf priority)
- **Replication**: 3
- **Retention**: 1 Tag
- **Key**: `{request_id}`
- **Value Schema**:
```json
{
  "request_id": "req_20250117_140000_abc123",
  "type": "asteroids",
  "location_key": "lat+48.2082_lon+16.3738_el+0170",
  "time_range": {
    "start": "2025-01-17T14:00:00Z",
    "end": "2025-01-18T14:00:00Z"
  },
  "priority": "high",
  "requested_at": "2025-01-17T14:00:00Z",
  "requested_by": "web-service-1"
}
```

#### computation-status
- **Partitions**: 4
- **Replication**: 3
- **Retention**: 1 Tag
- **Key**: `{request_id}`
- **Value Schema**:
```json
{
  "request_id": "req_20250117_140000_abc123",
  "status": "completed",
  "progress": 100,
  "started_at": "2025-01-17T14:00:05Z",
  "completed_at": "2025-01-17T14:03:22Z",
  "producer_id": "asteroid-producer-2",
  "error": null
}
```

### 3. Producer Services

#### Asteroid Producer
- **Sprache**: Python
- **Framework**: kafka-python oder confluent-kafka-python
- **Aufgaben**:
  - Liest computation-requests Topic
  - Filtert nach type="asteroids"
  - Berechnet Positionen mit Skyfield
  - Schreibt in asteroid-positions Topic
  - Aktualisiert computation-status Topic
- **Skalierung**: Horizontal (Consumer Group)
- **Parallelität**: 4-8 Instanzen

#### Comet Producer
- **Sprache**: Python
- **Framework**: kafka-python oder confluent-kafka-python
- **Aufgaben**: Analog zu Asteroid Producer
- **Skalierung**: Horizontal (Consumer Group)
- **Parallelität**: 4-8 Instanzen

#### Celestial Producer
- **Sprache**: Python
- **Framework**: kafka-python oder confluent-kafka-python
- **Aufgaben**:
  - Berechnet Planeten, Sonne, Mond
  - Echtzeit-Berechnung (kein Request-basiert)
  - Schreibt kontinuierlich in celestial-positions Topic
- **Skalierung**: Horizontal (Consumer Group)
- **Parallelität**: 2-4 Instanzen

#### Constellation Producer
- **Sprache**: Python
- **Framework**: kafka-python oder confluent-kafka-python
- **Aufgaben**:
  - Lädt Stellarium-Daten
  - Berechnet Stern-Positionen
  - Schreibt in constellation-data Topic
- **Skalierung**: Vertikal (wenig Last)
- **Parallelität**: 1-2 Instanzen

### 4. Consumer Services

#### Web Service (FastAPI)
- **Sprache**: Python
- **Framework**: FastAPI + kafka-python
- **Aufgaben**:
  - REST API für Frontend
  - Konsumiert position Topics
  - Cached Daten in Redis (optional)
  - Sendet computation-requests bei Cache Miss
  - Server-Sent Events (SSE) für Live-Updates
- **Skalierung**: Horizontal (Load Balancer)
- **Parallelität**: 4-8 Instanzen

#### WebSocket Gateway (optional)
- **Sprache**: Python oder Node.js
- **Framework**: FastAPI WebSocket oder Socket.io
- **Aufgaben**:
  - WebSocket-Verbindungen zu Clients
  - Konsumiert position Topics
  - Push-Updates an verbundene Clients
  - Reduziert Polling
- **Skalierung**: Horizontal (Sticky Sessions)
- **Parallelität**: 2-4 Instanzen

### 5. Scheduler Service

#### Precompute Scheduler
- **Sprache**: Python
- **Framework**: APScheduler oder Celery Beat
- **Aufgaben**:
  - Generiert computation-requests für rollendes Zeitfenster
  - Läuft stündlich
  - Berücksichtigt bekannte Standorte
  - Priorisiert aktuelle Zeit
- **Skalierung**: Single Instance (Leader Election)
- **Parallelität**: 1 Instanz

### 6. Monitoring & Management

#### Kafka Manager / Kafdrop
- **Funktion**: UI für Kafka-Cluster
- **Features**: Topic-Verwaltung, Consumer Lag, Broker Health

#### Prometheus + Grafana
- **Funktion**: Metriken und Dashboards
- **Metriken**:
  - Producer Throughput
  - Consumer Lag
  - Computation Latency
  - Cache Hit Rate

#### Schema Registry (optional)
- **Funktion**: Avro/Protobuf Schema Management
- **Vorteil**: Schema Evolution, Validierung

## Datenfluss

### 1. Normale Anfrage (Cache Hit)

```
Frontend → Web Service → Kafka Consumer → asteroid-positions Topic
                                        → Response
```

### 2. Cache Miss

```
Frontend → Web Service → computation-requests Topic
                      ↓
        Asteroid Producer ← computation-requests Topic
                      ↓
              Skyfield Berechnung
                      ↓
        asteroid-positions Topic
                      ↓
        Web Service Consumer → Response
```

### 3. Precompute

```
Scheduler → computation-requests Topic (priority=low)
         ↓
Producers → Berechnung → position Topics
```

### 4. Live-Updates (WebSocket)

```
Producers → position Topics
         ↓
WebSocket Gateway Consumer → WebSocket → Frontend
```

## Vorteile der Kafka-Architektur

### 1. Entkopplung
- Producer und Consumer unabhängig
- Keine direkte Prozess-Kommunikation
- Einfaches Hinzufügen neuer Consumer

### 2. Skalierbarkeit
- Horizontale Skalierung aller Komponenten
- Partitionierung für Parallelität
- Consumer Groups für Load Balancing

### 3. Fehlertoleranz
- Replication für Datensicherheit
- Automatic Failover
- Replay-Fähigkeit bei Fehlern

### 4. Performance
- Asynchrone Verarbeitung
- Batch-Processing möglich
- Niedrige Latenz durch Partitionierung

### 5. Observability
- Alle Events nachvollziehbar
- Consumer Lag Monitoring
- End-to-End Tracing möglich

### 6. Flexibilität
- Neue Datentypen einfach hinzufügbar
- Schema Evolution möglich
- Multiple Consumer für verschiedene Use Cases

## Herausforderungen

### 1. Komplexität
- Mehr Komponenten zu verwalten
- Kafka-Expertise erforderlich
- Höherer Betriebsaufwand

### 2. Latenz
- Zusätzliche Hops durch Kafka
- Netzwerk-Overhead
- Eventual Consistency

### 3. Kosten
- Kafka-Cluster benötigt Ressourcen
- Mehr Container/VMs
- Höherer Speicherbedarf

### 4. Entwicklungsaufwand
- Umstellung der gesamten Architektur
- Neue Libraries und Patterns
- Testing komplexer

## Empfohlene Technologien

### Kafka Client Libraries
1. **confluent-kafka-python** (empfohlen)
   - Performant (librdkafka)
   - Vollständige Features
   - Gute Dokumentation

2. **kafka-python** (Alternative)
   - Pure Python
   - Einfacher zu debuggen
   - Langsamer als confluent-kafka

### Serialisierung
1. **JSON** (einfach, lesbar)
2. **Avro** (kompakt, Schema Registry)
3. **Protobuf** (sehr kompakt, typsicher)

### Deployment
1. **Docker Compose Multi-Host** (Development & Produktion)
   - Kafka 4.1 mit KRaft Mode
   - 2-3 Maschinen in getrennten Netzwerken
   - Einfaches Setup, keine Orchestrierung nötig
2. **Kubernetes** (Enterprise Produktion)
3. **Managed Kafka** (Confluent Cloud, AWS MSK)
