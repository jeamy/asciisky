# Precompute mit RabbitMQ - Einfache Koordination

## 🎯 Konzept

**Problem gelöst:** Keine manuelle Location-Aufteilung mehr nötig!

**Lösung:** RabbitMQ Queue-basierte Koordination

```
┌─────────────────────────────────────────────────────────┐
│ Coordinator (Hauptserver)                               │
│ ├─ Liest Locations (user_settings.json + precompute_   │
│ │  locations.json)                                      │
│ ├─ Erstellt Tasks für alle Locations × Zeiten          │
│ └─ Publiziert Tasks in RabbitMQ Queue                  │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │ RabbitMQ Queue        │
            │ 'precompute.tasks'    │
            │ (Priority Queue)      │
            └───────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Workers x4   │ │ Workers x4   │ │ Workers x4   │
│ (Hauptserver)│ │ (rabbit-b)   │ │ (rabbit-c)   │
│ (skalierbar) │ │ (skalierbar) │ │ (skalierbar) │
│              │ │              │ │              │
│ Holt Task    │ │ Holt Task    │ │ Holt Task    │
│ Berechnet    │ │ Berechnet    │ │ Berechnet    │
│ Speichert DB │ │ Speichert DB │ │ Speichert DB │
│ ACK          │ │ ACK          │ │ ACK          │
└──────────────┘ └──────────────┘ └──────────────┘

Default: 12 Worker total (4 pro Server)
Skalierbar via .env: PRECOMPUTE_WORKERS, PRECOMPUTE_WORKERS_B/C
```

---

## ✅ Vorteile

1. **Keine Duplikate**
   - Jeder Task wird nur 1x bearbeitet
   - RabbitMQ garantiert Fair Dispatch

2. **Automatische Lastverteilung**
   - Worker holen sich Tasks wenn frei
   - Schnellere Worker bearbeiten mehr Tasks

3. **Einfach skalierbar**
   - Mehr Worker = schneller fertig
   - Skalierung via `.env`: `PRECOMPUTE_WORKERS=8`
   - Dann: `docker compose up -d`

4. **Failover**
   - Worker fällt aus → anderer übernimmt
   - Tasks werden nicht verloren (Persistent Queue)

5. **Prioritäten**
   - Nächste 24h = HIGH Priority (10)
   - Danach = NORMAL Priority (5)

---

## 🚀 Setup

### 1. Automatisches Setup (Empfohlen)

```bash
# Auf Entwicklungsrechner
./scripts/setup-production.sh
```

Das Script deployed automatisch:
- Hauptserver: Coordinator + 4 Precompute Workers
- Worker-B: 4 Precompute Workers
- Worker-C: 4 Precompute Workers

### 2. Worker-Skalierung (via .env)

```bash
# .env editieren
PRECOMPUTE_WORKERS=8        # Hauptserver
PRECOMPUTE_WORKERS_B=8      # Worker-B
PRECOMPUTE_WORKERS_C=8      # Worker-C

# Neu starten
docker compose up -d
```

### 3. Manuelles Setup

```bash
# Hauptserver
docker compose -f docker-compose.production.yml up -d

# Worker-B (optional)
ssh rabbit-b.eibrain.org
cd ~/asciisky
docker compose -f docker-compose.worker-b.yml up -d

# Worker-C (optional)
ssh rabbit-c.eibrain.org
cd ~/asciisky
docker compose -f docker-compose.worker-c.yml up -d
```

---

## 📊 Skalierungs-Szenarien

### Szenario 1: Kleine Installation (1-2 Locations)

**Setup:**
- 1 Coordinator (Hauptserver)
- 4 Worker (Hauptserver)

```bash
# .env
PRECOMPUTE_WORKERS=4

# Nur Hauptserver
docker compose -f docker-compose.production.yml up -d
```

**Performance:** ~30 min für 720h × 2 Locations

---

### Szenario 2: Standard Production (2-5 Locations)

**Setup:**
- 1 Coordinator (Hauptserver)
- 12 Worker (4 Hauptserver + 4 rabbit-b + 4 rabbit-c)

```bash
# .env (Default)
PRECOMPUTE_WORKERS=4
PRECOMPUTE_WORKERS_B=4
PRECOMPUTE_WORKERS_C=4

# Deployment
./scripts/setup-production.sh
```

**Performance:** ~10 min für 720h × 5 Locations

---

### Szenario 3: High-Performance (5+ Locations)

**Setup:**
- 1 Coordinator (Hauptserver)
- 24 Worker (8 Hauptserver + 8 rabbit-b + 8 rabbit-c)

```bash
# .env
PRECOMPUTE_WORKERS=8
PRECOMPUTE_WORKERS_B=8
PRECOMPUTE_WORKERS_C=8

# Deployment
./scripts/setup-production.sh
```

**Performance:** ~5 min für 720h × 10 Locations

---

## 🔍 Monitoring

### RabbitMQ UI

**Zugriff via SSH-Tunnel:**
```bash
# Von deinem lokalen Rechner
ssh -L 15672:localhost:15672 asciisky.eibrain.org

# Dann im Browser öffnen
http://localhost:15672

User: admin
Password: <RABBITMQ_PASSWORD aus .env>

Queue: precompute.tasks
```

**Prüfen:**
- ✅ Tasks in Queue
- ✅ Worker verbunden (Consumers) - sollte 12 sein (Default)
- ✅ Messages/sec Rate

### Logs

```bash
# Coordinator
docker logs -f asciisky-precompute-coordinator

# Worker (Hauptserver)
docker logs -f asciisky-precompute-worker

# Worker (rabbit-b) - alle 4 Worker
ssh rabbit-b.eibrain.org "docker compose -f docker-compose.worker-b.yml logs -f precompute_worker"

# Worker (rabbit-c) - alle 4 Worker
ssh rabbit-c.eibrain.org "docker compose -f docker-compose.worker-c.yml logs -f precompute_worker"
```

### PostgreSQL Cache-Status

```bash
docker exec asciisky-postgres psql -U asciisky -d asciisky -c "
SELECT 
    location_key,
    COUNT(*) as entries,
    MIN(created_at) as oldest,
    MAX(created_at) as newest
FROM cached_positions
GROUP BY location_key;
"
```

---

## ⚙️ Konfiguration

### Coordinator (precompute_coordinator.py)

**Environment Variables:**
- `ASCII_SKY_PRECOMPUTE_HOURS`: Wie viele Stunden voraus (default: 720)
- `PRECOMPUTE_COORDINATOR_INTERVAL`: Wie oft Tasks erstellen in Sekunden (default: 3600 = 1h)
- `RABBITMQ_URL`: RabbitMQ Verbindung

**Locations-Quellen (in Reihenfolge):**
1. `user_settings.json` - Persönliche Location
2. `precompute_locations.json` - Konfigurierte Locations
3. `ASCII_SKY_PRECOMPUTE_LOCATIONS` - Environment Variable

### Worker (workers/precompute_worker.py)

**Environment Variables:**
- `WORKER_ID`: Eindeutige Worker-ID (für Logging)
- `RABBITMQ_URL`: RabbitMQ Verbindung
- `RABBITMQ_PREFETCH_COUNT`: Wie viele Tasks gleichzeitig (default: 1)
- `POSTGRES_HOST`: PostgreSQL Server
- `USE_POSTGRES`: true für PostgreSQL

---

## 🔧 Troubleshooting

### Problem: Keine Tasks in Queue

```bash
# Prüfe Coordinator Logs
docker logs asciisky-precompute-coordinator

# Prüfe ob Locations konfiguriert
cat precompute_locations.json
cat user_settings.json
```

### Problem: Worker bearbeiten keine Tasks

```bash
# Prüfe Worker Logs
docker logs asciisky-precompute-worker

# Prüfe RabbitMQ Verbindung
docker exec asciisky-precompute-worker ping rabbitmq

# Prüfe PostgreSQL Verbindung
docker exec asciisky-precompute-worker pg_isready -h postgres -U asciisky
```

### Problem: Tasks werden nicht abgearbeitet

```bash
# Prüfe Queue in RabbitMQ UI
# http://asciisky.eibrain.org:15672

# Prüfe Consumer Count
# Sollte = Anzahl Worker sein
```

---

## 📈 Performance-Tipps

### 1. Mehr Worker starten

```bash
# .env editieren
PRECOMPUTE_WORKERS=8  # Statt 4

# Neu starten
docker compose -f docker-compose.production.yml up -d
```

### 2. PREFETCH_COUNT erhöhen

```yaml
# Für schnellere Worker
environment:
  - RABBITMQ_PREFETCH_COUNT=2  # Statt 1
```

**Achtung:** Nur wenn Worker schnell genug sind!

### 3. Coordinator-Intervall anpassen

```yaml
# Öfter Tasks erstellen
environment:
  - PRECOMPUTE_COORDINATOR_INTERVAL=1800  # 30 Minuten statt 1h
```

---

## 🎉 Zusammenfassung

**Vorher (kompliziert):**
- ❌ Manuelle Location-Aufteilung
- ❌ Komplizierte Konfiguration
- ❌ Duplikate möglich

**Jetzt (einfach):**
- ✅ RabbitMQ koordiniert automatisch
- ✅ Einfach skalierbar (mehr Worker = schneller)
- ✅ Keine Duplikate (Fair Dispatch)
- ✅ Failover inkludiert
- ✅ Prioritäten (nächste 24h zuerst)

**Deployment:**
```bash
# Automatisch (empfohlen)
./scripts/setup-production.sh

# Oder manuell:
# Hauptserver
docker compose -f docker-compose.production.yml up -d

# Worker-Server B
ssh rabbit-b.eibrain.org "cd ~/asciisky && docker compose -f docker-compose.worker-b.yml up -d"

# Worker-Server C
ssh rabbit-c.eibrain.org "cd ~/asciisky && docker compose -f docker-compose.worker-c.yml up -d"
```

**Worker-Skalierung:**
```bash
# .env editieren
PRECOMPUTE_WORKERS=8        # Hauptserver: 8 Worker
PRECOMPUTE_WORKERS_B=8      # Worker-B: 8 Worker
PRECOMPUTE_WORKERS_C=8      # Worker-C: 8 Worker
# = 24 Worker total

# Neu starten
docker compose up -d
```

**Fertig!** 🚀
