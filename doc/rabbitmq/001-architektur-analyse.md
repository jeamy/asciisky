# ASCII Sky - Aktuelle Architektur-Analyse (für RabbitMQ-Migration)

## Übersicht der aktuellen Architektur

Diese Analyse ist identisch zur Kafka-Analyse, da die aktuelle Architektur unabhängig vom Ziel-Message-Broker ist.

### Komponenten

#### 1. Web Service (FastAPI)
- **Funktion**: REST API Server
- **Port**: 8000
- **Technologie**: Python, FastAPI, Uvicorn
- **Aufgaben**:
  - Empfängt HTTP-Requests vom Frontend
  - Liefert vorberechnete Daten aus Cache/SQLite
  - Triggert Background-Tasks für fehlende Daten
  - Session-Management

#### 2. Worker Service (Precompute Worker)
- **Funktion**: Kontinuierliche Cache-Generierung
- **Technologie**: Python, Skyfield
- **Aufgaben**:
  - Berechnet Himmelsdaten für 720 Stunden (30 Tage) im Voraus
  - Läuft stündlich und aktualisiert rollendes Zeitfenster
  - Nutzt 4 parallele Worker-Threads
  - Adaptive Worker-Skalierung basierend auf CPU-Last
  - Retention-Pruning (löscht Daten älter als 30 Tage)

#### 3. Task Worker (Precompute Task Worker)
- **Funktion**: On-Demand Berechnung für spezifische Zeiträume
- **Technologie**: Python, Skyfield
- **Aufgaben**:
  - Wird vom Web Service per `docker exec` gestartet
  - Berechnet Daten für benutzerdefinierte Zeiträume
  - Prioritätsbasierte Verarbeitung (aktuell → Zukunft → Vergangenheit)
  - Schreibt Status in JSON-Dateien

#### 4. Data Updater Service
- **Funktion**: Nächtliche Datenaktualisierung
- **Technologie**: Python
- **Aufgaben**:
  - Läuft täglich um 2:00 Uhr
  - Lädt aktuelle Orbital-Elemente von MPC
  - Aktualisiert SQLite-Datenbank

#### 5. Task Cleanup Service
- **Funktion**: Aufräumen alter Task-Dateien
- **Technologie**: Python
- **Aufgaben**:
  - Läuft alle 60 Sekunden
  - Löscht alte Task- und Status-Dateien

### Datenfluss (aktuell)

```
┌─────────────────┐
│   Frontend      │
│  (Browser)      │
└────────┬────────┘
         │ HTTP Request
         ▼
┌─────────────────┐
│   Web Service   │◄──────┐
│   (FastAPI)     │       │
└────────┬────────┘       │
         │                │
         ├─ Read Cache ───┤
         │                │
         ▼                │
┌─────────────────┐       │
│  SQLite DB +    │       │
│  Pickle Cache   │       │
└────────┬────────┘       │
         │                │
         │ Cache Miss     │
         ▼                │
┌─────────────────┐       │
│  Background     │       │
│  Trigger        │       │
└────────┬────────┘       │
         │                │
         ▼                │
┌─────────────────┐       │
│  Task Worker    │       │
│  (docker exec)  │       │
└────────┬────────┘       │
         │                │
         │ Compute        │
         │ (Skyfield)     │
         │                │
         ├─ Write Cache ──┘
         │
         ▼
┌─────────────────┐
│  Precompute     │
│  Worker         │
│  (continuous)   │
└─────────────────┘
```

### Skalierungsprobleme

#### 1. Shared Filesystem
- Alle Container teilen Volume für Cache
- Keine echte Verteilung möglich
- Single Point of Failure

#### 2. Tight Coupling
- Web Service startet Task Worker per `docker exec`
- Keine Entkopplung zwischen Komponenten
- Schwierig zu skalieren

#### 3. Polling-basierte Kommunikation
- Task Status über JSON-Dateien
- Keine Event-basierte Architektur
- Ineffizient bei vielen Requests

#### 4. Standort-spezifische Caches
- Jeder Standort benötigt eigenen Cache
- Keine Wiederverwendung zwischen Standorten
- Cache-Explosion bei vielen Nutzern

#### 5. Synchrone Berechnungen
- Task Worker blockiert während Berechnung
- Keine Parallelisierung über Container hinweg
- Begrenzte Durchsatzrate

### Stärken der aktuellen Architektur

1. **Skyfield Integration**: Bewährte, präzise Berechnungen
2. **Precompute-Strategie**: Reduziert Latenz für häufige Anfragen
3. **Prioritätsbasierte Verarbeitung**: Aktuelle Daten zuerst
4. **Adaptive Worker-Skalierung**: Passt sich an Systemlast an
5. **Retention-Management**: Automatisches Aufräumen alter Daten
6. **SQLite-Backend**: Schneller als Pickle, strukturiert

### Schwächen für Message-Broker-Migration

1. **Monolithische Worker**: Berechnen alle Datentypen
2. **Keine Message Queue**: Direkte Prozess-Kommunikation
3. **Keine Event-Sourcing**: Zustandsänderungen nicht nachvollziehbar
4. **Keine Worker Pools**: Keine parallele Verarbeitung
5. **Keine Replay-Fähigkeit**: Daten können nicht neu verarbeitet werden
6. **Keine Priorisierung**: Alle Tasks gleich wichtig

## Vergleich: Kafka vs. RabbitMQ für ASCII Sky

### Kafka-Ansatz
- **Paradigma**: Event Streaming, Log-basiert
- **Stärke**: Hoher Durchsatz, Replay, Event-Sourcing
- **Schwäche**: Komplexer, höhere Latenz für Request/Reply
- **Ideal für**: Event-Logs, Analytics, Stream Processing

### RabbitMQ-Ansatz
- **Paradigma**: Message Queue, Task-basiert
- **Stärke**: Niedrige Latenz, einfacher, flexibles Routing
- **Schwäche**: Kein Replay, Messages werden gelöscht nach Konsum
- **Ideal für**: Task Queues, RPC, Request/Reply

### Empfehlung für ASCII Sky

**RabbitMQ ist besser geeignet**, weil:

1. ✅ **Task-Queue-Pattern**: Perfekt für Berechnungs-Tasks
2. ✅ **Niedrigere Latenz**: Wichtig für On-Demand Requests
3. ✅ **Einfachere Architektur**: Weniger Komplexität als Kafka
4. ✅ **Priority Queues**: Native Unterstützung für Task-Priorisierung
5. ✅ **RPC-Pattern**: Gut für Request/Reply (Web Service ↔ Worker)
6. ✅ **Geringere Ressourcen**: Weniger RAM/CPU als Kafka
7. ✅ **Management UI**: Eingebautes Web-Interface

**Kafka wäre besser für**:
- Event-Sourcing (alle Berechnungen nachvollziehbar)
- Analytics (Auswertung von Nutzungsmustern)
- Stream Processing (Echtzeit-Aggregationen)
- Replay (Neuberechnung historischer Daten)

**Für ASCII Sky**: RabbitMQ ist die pragmatischere Wahl.
