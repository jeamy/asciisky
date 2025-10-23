# Worker Setup Guide

## Architektur

ASCII Sky verwendet eine Multi-Host Worker-Architektur mit RabbitMQ:

```
┌─────────────────────────────────────────────────────────────┐
│ Hauptserver ($RABBITMQ_MAIN)                                 │
│ - Web (FastAPI)                                              │
│ - RabbitMQ (Message Broker)                                  │
│ - PostgreSQL (Cache/DB)                                      │
│ - Precompute Worker (4x)                                     │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ RabbitMQ (Port 5672)
                          │ PostgreSQL (Port 5432)
                          │
        ┌─────────────────┴─────────────────┐
        │                                   │
┌───────▼──────────┐              ┌────────▼─────────┐
│ Worker Host B    │              │ Worker Host C    │
│ (rabbit-b)       │              │ (rabbit-c)       │
│                  │              │                  │
│ - Precompute (4x)│              │ - Precompute (4x)│
│ - Asteroid (2x)  │              │ - Asteroid (2x)  │
│ - Comet (2x)     │              │ - Comet (2x)     │
└──────────────────┘              └──────────────────┘
```

## Worker-Typen

### Precompute Worker
- **Zweck:** Vorausberechnung für bekannte Locations
- **Trigger:** Coordinator erstellt Tasks stündlich
- **Queue:** `precompute.tasks`
- **Hosts:** Hauptserver + B + C (total 12 Worker)

### Asteroid Worker
- **Zweck:** On-Demand Berechnung bei Cache-Miss
- **Trigger:** API-Request ohne Cache-Hit
- **Queue:** `asteroid.compute` (via Exchange `computation.direct`)
- **Hosts:** B + C (total 4 Worker)

### Comet Worker
- **Zweck:** On-Demand Berechnung bei Cache-Miss
- **Trigger:** API-Request ohne Cache-Hit
- **Queue:** `comet.compute` (via Exchange `computation.direct`)
- **Hosts:** B + C (total 4 Worker)

## Konfiguration

### .env Dateien

Jeder Host hat seine **eigene** `.env` Datei mit generischen Variablen:

**Wichtig:** Alle Hosts verwenden die **gleichen** Passwörter (für PostgreSQL/RabbitMQ Zugriff).

#### Hauptserver (.env)
```bash
# Worker Setup
SETUP_WORKER_B=true
SETUP_WORKER_C=true

# Worker Scaling (nur Precompute auf Hauptserver)
PRECOMPUTE_WORKERS=4
ASTEROID_WORKERS=0  # Nicht verwendet auf Hauptserver
COMET_WORKERS=0     # Nicht verwendet auf Hauptserver
```

#### Worker Host B (.env auf $RABBITMQ_B)
```bash
# Worker Scaling (unterschiedlich pro Host konfigurierbar)
PRECOMPUTE_WORKERS=4
ASTEROID_WORKERS=2
COMET_WORKERS=2
```

#### Worker Host C (.env auf $RABBITMQ_C)
```bash
# Worker Scaling (unterschiedlich pro Host konfigurierbar)
PRECOMPUTE_WORKERS=4
ASTEROID_WORKERS=2
COMET_WORKERS=2
```

## Deployment

### Initial Setup

```bash
# Auf Hauptserver
cd /media/docker/asciisky
cp .env.example .env
# Bearbeite .env (Passwörter, etc.)

# Setup ausführen (deployed auf alle Hosts)
./scripts/setup-production.sh
```

Das Script:
1. Deployed Hauptserver (Web, RabbitMQ, PostgreSQL, Precompute-Worker)
2. Kopiert `.env` auf Worker-Hosts B und C
3. Deployed Worker auf B und C

### Updates

```bash
# Auf Hauptserver
cd /media/docker/asciisky
git pull

# Update auf allen Hosts
./scripts/update-production.sh
```

### Manuelle Worker-Skalierung

Wenn du die Worker-Anzahl ändern möchtest:

**Auf Hauptserver:**
```bash
# .env bearbeiten
nano .env
# PRECOMPUTE_WORKERS=8  # Erhöhe auf 8

# Neu starten
docker compose -f docker-compose.production.yml up -d --scale precompute_worker=8
```

**Auf Worker-Host B:**
```bash
ssh $RABBITMQ_B
cd ~/asciisky

# .env bearbeiten
nano .env
# ASTEROID_WORKERS=4  # Erhöhe auf 4

# Neu starten
docker compose -f docker-compose.workers.yml up -d --scale asteroid_worker=4
```

## Monitoring

### RabbitMQ Management UI

```bash
# SSH-Tunnel erstellen
ssh -L 15672:localhost:15672 $RABBITMQ_MAIN

# Browser öffnen
http://localhost:15672
# Login: admin / <RABBITMQ_PASSWORD>
```

**Was zu prüfen:**
- **Connections:** Sollte ~12 Connections zeigen (alle Worker)
- **Queues:** `precompute.tasks`, `asteroid.compute`, `comet.compute`
- **Messages:** Pending/Processing Messages

### Worker Logs

**Hauptserver:**
```bash
docker compose -f docker-compose.production.yml logs -f precompute_worker
```

**Worker Host B:**
```bash
ssh $RABBITMQ_B
cd ~/asciisky
docker compose -f docker-compose.workers.yml logs -f asteroid_worker
docker compose -f docker-compose.workers.yml logs -f comet_worker
docker compose -f docker-compose.workers.yml logs -f precompute_worker
```

**Worker Host C:**
```bash
ssh $RABBITMQ_C
cd ~/asciisky
docker compose -f docker-compose.workers.yml logs -f asteroid_worker
docker compose -f docker-compose.workers.yml logs -f comet_worker
docker compose -f docker-compose.workers.yml logs -f precompute_worker
```

## Troubleshooting

### Worker bekommen keine Tasks

**Symptom:** Logs zeigen "Waiting for messages..." aber keine Tasks werden verarbeitet.

**Prüfen:**
1. RabbitMQ Management UI → Connections (alle Worker verbunden?)
2. RabbitMQ Management UI → Queues (Messages in Queue?)
3. Exchange Bindings korrekt? (`computation.direct` → `asteroid.compute`)

**Lösung:**
```bash
# Worker neu starten
ssh $RABBITMQ_B
cd ~/asciisky
docker compose -f docker-compose.workers.yml restart
```

### Cache-Miss aber keine Berechnung

**Symptom:** API-Logs zeigen "Cache MISS" aber Worker werden nicht getriggert.

**Prüfen:**
1. API-Logs: "Published asteroid task" erscheint?
2. RabbitMQ: Messages in `asteroid.compute` Queue?
3. Worker-Logs: "Processing task" erscheint?

**Häufige Ursachen:**
- Exchange/Routing Key falsch konfiguriert
- Worker nicht gestartet
- RabbitMQ Connection-Problem

### PostgreSQL Connection Error

**Symptom:** Worker können nicht auf PostgreSQL zugreifen.

**Prüfen:**
```bash
# Von Worker-Host testen
ssh $RABBITMQ_B
telnet $RABBITMQ_MAIN 5432
```

**Lösung:**
- Firewall-Regeln prüfen
- PostgreSQL `listen_addresses` prüfen
- PostgreSQL `pg_hba.conf` prüfen

## Performance Tuning

### Worker-Anzahl optimieren

**Faustregel:**
- **Precompute:** 1 Worker pro CPU-Kern (I/O-bound)
- **Asteroid/Comet:** 2-4 Worker pro Host (CPU-bound, Skyfield-Berechnungen)

**Monitoring:**
```bash
# CPU-Auslastung prüfen
htop

# Worker-Performance
docker stats
```

### RabbitMQ Prefetch

Standardmäßig: `prefetch_count=1` (ein Task pro Worker gleichzeitig)

Für schnellere Tasks erhöhen:
```python
# In worker.py
self.channel.basic_qos(prefetch_count=2)
```

## Sicherheit

### Firewall

Nur Worker-IPs dürfen auf RabbitMQ/PostgreSQL zugreifen:

```bash
# Auf Hauptserver
sudo ./scripts/setup-firewall.sh
```

### Passwörter

Verwende starke Passwörter in `.env`:
```bash
# Generieren
openssl rand -base64 32
```

## Backup

### PostgreSQL Backup

```bash
# Auf Hauptserver
docker exec asciisky-postgres pg_dump -U asciisky asciisky > backup.sql
```

### RabbitMQ Backup

```bash
# Definitions exportieren
curl -u admin:password http://localhost:15672/api/definitions > rabbitmq-backup.json
```
