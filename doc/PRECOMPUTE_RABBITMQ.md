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
│ Worker 1     │ │ Worker 2     │ │ Worker 3     │
│ (Hauptserver)│ │ (rabbit-b)   │ │ (rabbit-c)   │
│              │ │              │ │              │
│ Holt Task    │ │ Holt Task    │ │ Holt Task    │
│ Berechnet    │ │ Berechnet    │ │ Berechnet    │
│ Speichert DB │ │ Speichert DB │ │ Speichert DB │
│ ACK          │ │ ACK          │ │ ACK          │
└──────────────┘ └──────────────┘ └──────────────┘
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
   - Einfach Container starten: `docker compose up -d precompute-worker`

4. **Failover**
   - Worker fällt aus → anderer übernimmt
   - Tasks werden nicht verloren (Persistent Queue)

5. **Prioritäten**
   - Nächste 24h = HIGH Priority (10)
   - Danach = NORMAL Priority (5)

---

## 🚀 Setup

### 1. Hauptserver (Coordinator + 1 Worker)

```bash
# Bereits in docker-compose.production.yml enthalten
docker compose -f docker-compose.production.yml up -d precompute_coordinator
docker compose -f docker-compose.production.yml up -d precompute_worker
```

**Komponenten:**
- `precompute_coordinator`: Erstellt Tasks stündlich
- `precompute_worker`: Bearbeitet Tasks

### 2. Worker-Server B (optional, empfohlen)

```bash
# Auf rabbit-b.eibrain.org
docker compose -f docker-compose.worker-b.yml up -d precompute-worker
```

### 3. Worker-Server C (optional)

```bash
# Auf rabbit-c.eibrain.org
docker compose -f docker-compose.worker-c.yml up -d precompute-worker
```

---

## 📊 Skalierungs-Szenarien

### Szenario 1: Kleine Installation (1-2 Locations)

**Setup:**
- 1 Coordinator (Hauptserver)
- 1 Worker (Hauptserver)

```bash
# Nur Hauptserver
docker compose -f docker-compose.production.yml up -d
```

**Performance:** ~60 min für 720h × 2 Locations

---

### Szenario 2: Standard Production (2-5 Locations)

**Setup:**
- 1 Coordinator (Hauptserver)
- 2 Worker (Hauptserver + rabbit-b)

```bash
# Hauptserver
docker compose -f docker-compose.production.yml up -d

# rabbit-b
docker compose -f docker-compose.worker-b.yml up -d precompute-worker
```

**Performance:** ~30 min für 720h × 5 Locations

---

### Szenario 3: High-Performance (5+ Locations)

**Setup:**
- 1 Coordinator (Hauptserver)
- 3 Worker (Hauptserver + rabbit-b + rabbit-c)

```bash
# Hauptserver
docker compose -f docker-compose.production.yml up -d

# rabbit-b
docker compose -f docker-compose.worker-b.yml up -d precompute-worker

# rabbit-c
docker compose -f docker-compose.worker-c.yml up -d precompute-worker
```

**Performance:** ~20 min für 720h × 10 Locations

---

## 🔍 Monitoring

### RabbitMQ UI

```
URL: http://asciisky.eibrain.org:15672
Queue: precompute.tasks
```

**Prüfen:**
- ✅ Tasks in Queue
- ✅ Worker verbunden (Consumers)
- ✅ Messages/sec Rate

### Logs

```bash
# Coordinator
docker logs -f asciisky-precompute-coordinator

# Worker (Hauptserver)
docker logs -f asciisky-precompute-worker

# Worker (rabbit-b)
ssh rabbit-b.eibrain.org "docker logs -f asciisky-precompute-worker-b"

# Worker (rabbit-c)
ssh rabbit-c.eibrain.org "docker logs -f asciisky-precompute-worker-c"
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
# Einfach mehr Container starten
docker compose -f docker-compose.production.yml up -d --scale precompute_worker=2
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
# Hauptserver (immer)
docker compose -f docker-compose.production.yml up -d

# Worker-Server (optional, für mehr Performance)
docker compose -f docker-compose.worker-b.yml up -d precompute-worker
docker compose -f docker-compose.worker-c.yml up -d precompute-worker
```

**Fertig!** 🚀
