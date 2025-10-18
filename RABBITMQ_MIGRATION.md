# RabbitMQ Migration - Quick Start Guide

## Status: Phase 0, 1, 2, 3 Abgeschlossen 

Die RabbitMQ-Migration ist vollständig implementiert und kann schrittweise aktiviert werden.

## ⚠️ WICHTIG: Asynchrone Architektur

Die RabbitMQ-Integration nutzt **NICHT** synchrones Request/Reply (RPC), sondern:
**Asynchrones Message Processing mit Cache** - genau wie das Legacy-System!

### Architektur-Übersicht:

```
┌─────────────┐
│  Frontend   │ ──┐ Pollt alle 60s
└─────────────┘   │
       ↓          │
┌─────────────┐   │
│     API     │ ←─┘
└─────────────┘
  │         ↑
  │ Cache   │ Cache
  │ Miss    │ Hit
  ↓         │
┌─────────────┐
│  RabbitMQ   │ Async Tasks
│   Queue     │
└─────────────┘
       ↓
┌─────────────┐
│   Worker    │ Berechnet 2-3 Min
└─────────────┘
       ↓
┌─────────────┐
│  Cache/DB   │ SQLite + Pickle
└─────────────┘
```

### Flow:
1. **User Request** → API liest Cache
2. **Cache Miss** → API triggert RabbitMQ Background Task + Return leer
3. **Worker** → Empfängt Task, berechnet Daten, speichert in Cache
4. **Frontend** → Pollt nach 60s, API liest Cache → Daten vorhanden!
5. **Frontend** → Zeigt Daten an

## Was wurde implementiert?

### ✅ Abgeschlossen - 100% RabbitMQ, kein Legacy!

1. **Feature Flags System** (`config/feature_flags.py`)
   - Typ-spezifische Flags für Asteroids & Comets
   - 100% RabbitMQ aktiviert

2. **RabbitMQ Task Publisher** (`api/rabbitmq/task_publisher.py`)
   - Asynchrones Publishing von Background Tasks
   - Thread-safe mit thread-local Connections
   - Batch-Support für viele Tasks
   - KEIN synchrones Request/Reply!

3. **Worker implementiert** (nur für Asteroids & Comets)
   - `workers/asteroid_worker.py` - Asteroiden-Berechnungen
   - `workers/comet_worker.py` - Kometen-Berechnungen
   - Je 2 Worker-Instanzen für Lastverteilung
   - Speichern automatisch in Cache/DB

4. **API-Integration** (`api/routes/asteroids.py`, `comets.py`)
   - **Cache-First**: Liest zuerst aus Cache (SQLite + Pickle)
   - **Background Tasks**: Triggert RabbitMQ wenn Cache leer
   - **Leere Response**: Frontend pollt und zeigt Daten wenn verfügbar
   - `trigger_rabbitmq_precompute()` - Sendet ±12h Tasks an Queue
   - Feature Flags integriert
   - **KEIN Fallback** - 100% RabbitMQ

5. **Celestial & Zodiac** (KEIN RabbitMQ)
   - Bleiben bei direkter Berechnung (< 1s)
   - Kein Cache nötig
   - Kein RabbitMQ nötig

6. **Docker Compose** (`docker-compose.yml`)
   - 4 RabbitMQ Worker
   - 2x Asteroid, 2x Comet
   - Automatische Lastverteilung

## Zwei Wege zum Testen

### Option 1: Lokales Testing (EMPFOHLEN für Start) 🏠

**Alles auf einem Rechner** - Einfach und schnell!

Siehe **[TESTING_LOCAL.md](TESTING_LOCAL.md)** für vollständige Anleitung.

**Quick Start (3 Befehle!)**

```bash
# 1. Alles starten (RabbitMQ + 4 Worker)
docker compose up -d

# 2. Queues erstellen
./scripts/setup-rabbitmq-queues.sh

# 3. Testen!
curl "http://localhost:8000/api/bright_asteroids?lat=48.2&lon=16.3"
```

**Neue `docker-compose.yml`** enthält jetzt:
- ✅ RabbitMQ Service (integriert)
- ✅ 4 Worker (2x Asteroid, 2x Comet)
- ✅ 100% RabbitMQ Traffic, kein Fallback
- ✅ Keine Override-Files mehr nötig!

**Hinweis:** Celestial & Zodiac nutzen KEIN RabbitMQ (zu schnell, < 1s)

## Nützliche RabbitMQ Befehle

### Queue Status prüfen

```bash
# Alle Queues mit Messages und Consumers
docker exec asciisky-rabbitmq rabbitmqctl list_queues name messages consumers

# Detaillierte Queue-Info
docker exec asciisky-rabbitmq rabbitmqctl list_queues name messages consumers durable

# Nur bestimmte Queue
docker exec asciisky-rabbitmq rabbitmqctl list_queues | grep asteroid
```

### Worker Status prüfen

```bash
# Alle Connections
docker exec asciisky-rabbitmq rabbitmqctl list_connections name peer_host peer_port state

# Alle Channels
docker exec asciisky-rabbitmq rabbitmqctl list_channels connection name number consumer_count

# Consumer pro Queue
docker exec asciisky-rabbitmq rabbitmqctl list_consumers
```

### Messages & Bindings

```bash
# Alle Exchanges
docker exec asciisky-rabbitmq rabbitmqctl list_exchanges name type durable

# Alle Bindings
docker exec asciisky-rabbitmq rabbitmqctl list_bindings source_name destination_name routing_key

# Queue leeren (VORSICHT!)
docker exec asciisky-rabbitmq rabbitmqctl purge_queue asteroid.compute
```

### Monitoring

```bash
# RabbitMQ Status
docker exec asciisky-rabbitmq rabbitmqctl status

# Cluster Status (bei Multi-Host)
docker exec asciisky-rabbitmq rabbitmqctl cluster_status

# Memory Usage
docker exec asciisky-rabbitmq rabbitmqctl status | grep -A 10 memory
```

### Management UI

```bash
# Öffne im Browser:
http://localhost:15672

# Login:
Username: admin
Password: password
```

### Logs

```bash
# RabbitMQ Logs
docker compose logs rabbitmq --tail=50

# Worker Logs
docker compose logs asteroid-worker-1 --tail=20
docker compose logs comet-worker-1 --tail=20

# Web Logs (API)
docker compose logs web --tail=30 | grep -i rabbitmq

# Alle Logs live
docker compose logs -f
```

### Option 2: Multi-Host Setup (für Produktion) 🌐

**RabbitMQ auf separaten Hosts** - Siehe unten.

## Voraussetzungen (Multi-Host)

### RabbitMQ Cluster

Für Produktions-Setup muss ein RabbitMQ-Cluster auf separaten Hosts laufen:

```bash
# Siehe doc/rabbitmq/003-rabbitmq-4.1-multi-host-setup.md
# für vollständiges Setup auf 2-3 Hosts

# Oder lokal für Tests:
docker run -d --name rabbitmq \
  -p 5672:5672 \
  -p 15672:15672 \
  -e RABBITMQ_DEFAULT_USER=admin \
  -e RABBITMQ_DEFAULT_PASS=password \
  rabbitmq:4.1-management
```

### Queues erstellen

```bash
# Exchange erstellen (einmalig)
docker exec rabbitmq rabbitmqadmin declare exchange \
  name=computation.direct \
  type=direct \
  durable=true

# Asteroid Compute Queue
docker exec rabbitmq rabbitmqadmin declare queue \
  name=asteroid.compute \
  durable=true \
  arguments='{"x-queue-type":"quorum","x-max-priority":10}'

docker exec rabbitmq rabbitmqadmin declare binding \
  source=computation.direct \
  destination=asteroid.compute \
  routing_key=compute.asteroid

# Comet Compute Queue
docker exec rabbitmq rabbitmqadmin declare queue \
  name=comet.compute \
  durable=true \
  arguments='{"x-queue-type":"quorum","x-max-priority":10}'

docker exec rabbitmq rabbitmqadmin declare binding \
  source=computation.direct \
  destination=comet.compute \
  routing_key=compute.comet

# Results & Status Queues (für Monitoring)
docker exec rabbitmq rabbitmqadmin declare queue \
  name=computation.results \
  durable=true

docker exec rabbitmq rabbitmqadmin declare queue \
  name=computation.status \
  durable=true
```

## Migration aktivieren

### Schritt 1: Dependencies installieren

```bash
# Im Docker Container oder lokal
pip install pika==1.3.2 prometheus-client==0.19.0
```

### Schritt 2: RabbitMQ Worker starten

```bash
# Alle Worker mit Docker Compose Profile starten
docker compose --profile rabbitmq up -d

# Oder einzelne Worker:
docker compose --profile rabbitmq up -d asteroid-worker-1 asteroid-worker-2
docker compose --profile rabbitmq up -d comet-worker-1 comet-worker-2
docker compose --profile rabbitmq up -d celestial-worker-1
docker compose --profile rabbitmq up -d constellation-worker-1

# Logs prüfen
docker compose logs -f asteroid-worker-1
docker compose logs -f comet-worker-1

# Alle Worker-Logs
docker compose logs -f | grep worker
```

### Schritt 3: Feature Flags aktivieren (schrittweise!)

#### 3.1 Nur 10% Traffic über RabbitMQ

```bash
# docker-compose.yml anpassen:
# - USE_RABBITMQ=true
# - USE_RABBITMQ_ASTEROIDS=true
# - RABBITMQ_PERCENTAGE=10

docker compose up -d web
```

#### 3.2 Monitoring prüfen

```bash
# Logs beobachten
docker compose logs -f web | grep -i rabbitmq
docker compose logs -f asteroid-worker-1

# Fehlerrate prüfen
docker compose logs web | grep -i "falling back"
```

#### 3.3 Schrittweise erhöhen

```bash
# Wenn alles gut läuft:
# RABBITMQ_PERCENTAGE=10 -> 25 -> 50 -> 75 -> 100

# Nach jeder Änderung:
docker compose up -d web
```

### Schritt 4: 100% auf RabbitMQ

```bash
# docker-compose.yml:
# - RABBITMQ_PERCENTAGE=100
# - FALLBACK_TO_OLD_ON_ERROR=false  # Optional, für Produktion

docker compose up -d web

# Alte Worker stoppen (optional)
docker compose stop worker worker_once
```

## Rollback

### Schneller Rollback (< 1 Minute)

```bash
# Feature Flags deaktivieren
# docker-compose.yml:
# - USE_RABBITMQ=false

docker compose up -d web

# Alte Worker sicherstellen
docker compose up -d worker
```

### Vollständiger Rollback

```bash
# Git Rollback
git revert HEAD

# Rebuild
docker compose build
docker compose up -d
```

## Monitoring

### Wichtige Metriken

```bash
# RabbitMQ Management UI
open http://localhost:15672
# Login: admin / password

# Queue-Länge prüfen
docker exec rabbitmq rabbitmqctl list_queues name messages consumers

# Worker-Status
docker compose ps | grep worker
```

### Logs

```bash
# Web Service (Feature Flag Entscheidungen)
docker compose logs -f web | grep -E "(Using RabbitMQ|Using old|Falling back)"

# Worker (Task-Verarbeitung)
docker compose logs -f asteroid-worker-1 | grep -E "(Processing|completed|failed)"

# Fehler
docker compose logs web | grep -i error
docker compose logs asteroid-worker-1 | grep -i error
```

## Troubleshooting

### Problem: RabbitMQ Connection Failed

```bash
# RabbitMQ erreichbar?
telnet localhost 5672

# Container läuft?
docker ps | grep rabbitmq

# Logs prüfen
docker logs rabbitmq
```

### Problem: Worker verarbeitet keine Tasks

```bash
# Queue existiert?
docker exec rabbitmq rabbitmqctl list_queues

# Worker läuft?
docker compose ps asteroid-worker-1

# Binding korrekt?
docker exec rabbitmq rabbitmqctl list_bindings
```

### Problem: Hohe Fehlerrate

```bash
# Fallback aktiviert?
# docker-compose.yml: FALLBACK_TO_OLD_ON_ERROR=true

# Timeout erhöhen?
# docker-compose.yml: RABBITMQ_TIMEOUT=60

# Mehr Worker?
docker compose --profile rabbitmq up -d --scale asteroid-worker-1=4
```

## Nächste Schritte

### Phase 3: Weitere Worker

1. Comet Worker implementieren (analog zu Asteroid Worker)
2. Celestial Worker implementieren
3. Constellation Worker implementieren

### Phase 4: Monitoring

1. Prometheus-Metriken hinzufügen
2. Grafana Dashboard erstellen
3. Alerting konfigurieren

### Phase 5: Produktion

1. RabbitMQ Cluster auf 3 Hosts (siehe `doc/rabbitmq/003-rabbitmq-4.1-multi-host-setup.md`)
2. HAProxy Load Balancer
3. SSL/TLS aktivieren
4. Backup-Strategie

## Dokumentation

Vollständige Dokumentation in `/doc/rabbitmq/`:

- `001-architektur-analyse.md` - Vergleich Kafka vs. RabbitMQ
- `002-rabbitmq-zielarchitektur.md` - Zielarchitektur
- `003-rabbitmq-4.1-multi-host-setup.md` - Setup-Guide
- `004-migrationsplan.md` - Vollständiger Migrationsplan
- `007-migrations-strategie.md` - Trennung alte/neue Sourcen

## Support

Bei Fragen oder Problemen:
1. Logs prüfen (siehe oben)
2. Dokumentation lesen (`/doc/rabbitmq/`)
3. Feature Flags zurücksetzen (Rollback)
