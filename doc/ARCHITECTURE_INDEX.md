# ASCII Sky - Architektur Dokumentation

Komplette Übersicht über die System-Architektur, Datenflüsse und Implementierung.

## 📚 Inhaltsverzeichnis

### 1. [Übersicht & Precompute-Flow](ARCHITECTURE_FLOW.md)
**Datei:** `doc/ARCHITECTURE_FLOW.md`

**Inhalt:**
- System-Übersicht mit Architektur-Diagramm
- Precompute-Flow (stündliche Vorberechnung)
  - Coordinator-Ablauf
  - Task-Erstellung für alle Locations
  - RabbitMQ Queue-Verwaltung
  - Worker-Verarbeitung (12 Worker auf 3 Hosts)
  - DataFrame-Loading (Asteroiden & Kometen)
  - Position-Berechnung mit Skyfield
  - Speicherung in PostgreSQL
- Code-Referenzen mit Zeilennummern

**Wichtige Komponenten:**
- `api/background.py:precompute_coordinator()` - Stündlicher Coordinator
- `workers/precompute_worker.py:process_precompute_task()` - Task-Verarbeitung
- `bright_asteroids.py:load_bright_asteroids()` - Asteroid-Daten laden
- `db_utils.py:store_precomputed_snapshot()` - Cache speichern

---

### 2. [API Request Flow (On-Demand)](ARCHITECTURE_FLOW_API.md)
**Datei:** `doc/ARCHITECTURE_FLOW_API.md`

**Inhalt:**
- **Drei verschiedene API-Endpoints:**
  1. **Asteroiden** - RabbitMQ Worker + Cache
  2. **Kometen** - RabbitMQ Worker + Cache (identisch wie Asteroiden)
  3. **Planeten** - Direktberechnung (keine Worker, kein Cache)
- Kompletter Request-Flow für alle drei Typen
- Cache-Hit vs Cache-Miss Szenarien
- RabbitMQ RPC-Pattern für Asteroiden/Kometen
- Direktberechnung für Planeten (synchron, ~50-200ms)
- Vergleichstabelle: Asteroiden/Kometen vs Planeten
- Performance-Vergleich

**Asteroiden/Kometen Ablauf:**
1. Browser → FastAPI Endpoint
2. Precomputed Cache Check
3. Bei Cache-Miss: RabbitMQ RPC (30s Timeout)
4. Worker berechnet Positionen
5. Magnitude-Filter anwenden
6. Response zurück an Browser

**Planeten Ablauf:**
1. Browser → FastAPI Endpoint
2. Direktberechnung mit Skyfield (50-200ms)
3. Response zurück an Browser

**Wichtige Komponenten:**
- `api/routes/asteroids.py:get_bright_asteroids()` - Asteroiden Endpoint
- `api/routes/comets.py:get_comets()` - Kometen Endpoint (gleicher Flow)
- `api/routes/planets.py:get_planets()` - Planeten Endpoint (Direktberechnung)
- `workers/asteroid_worker.py` - Asteroid Worker
- `workers/comet_worker.py` - Comet Worker
- `planets.py:get_planet_positions()` - Planeten Berechnung

---

### 3. [Cache-Strategie](ARCHITECTURE_CACHE.md)
**Datei:** `doc/ARCHITECTURE_CACHE.md`

**Inhalt:**
- 4-Level Cache-Hierarchie
  - **Level 1:** Precomputed Snapshots (48h TTL)
  - **Level 2:** DataFrame Cache (31 Tage TTL)
  - **Level 3:** Position Cache (24h TTL)
  - **Level 4:** MPC Download (Fallback)
- Cache-Invalidierung bei Magnitude-Filter Änderung
- Performance-Metriken pro Cache-Level
- Response-Zeiten: 10ms (Hit) bis 30s (Cold Start)

**Cache-Invalidierung:**
- User ändert Filter → Lösche nur gefilterte Caches
- Nur `precomputed_snapshots` wird gelöscht (enthält gefilterte Daten)
- Position-Caches bleiben (ungefiltert, wiederverwendbar)
- DataFrames bleiben (MPC Orbitaldaten, Mag 20.0, wiederverwendbar)
- Nächster Request: Sofortige Anzeige neuer Objekte ohne Neuberechnung!

**Code:** `api/routes/filters.py:36-59`

---

### 4. [Datenbank-Schema](ARCHITECTURE_DATABASE.md)
**Datei:** `doc/ARCHITECTURE_DATABASE.md`

**Inhalt:**
- PostgreSQL Tabellen-Schema mit SQL
- Beispiel-Daten (JSON)
- TTL & Speicherverbrauch pro Tabelle
- Datenfluss: MPC → DataFrame → PostgreSQL → API

**Tabellen:**

#### `precomputed_snapshots`
- Key: `(location_id, timestamp)`
- TTL: 48 Stunden
- Inhalt: Komplette Snapshots (Asteroiden + Kometen + Planeten)
- Größe: ~50 KB pro Eintrag

#### `asteroids` / `comets`
- Inhalt: Pickle-serialisierte Pandas DataFrames
- TTL: 31 Tage
- Größe: ~20 MB (Asteroiden), ~1 MB (Kometen)

#### `asteroid_positions` / `comet_positions`
- Key: `(location_hash, timestamp)`
- TTL: 24 Stunden
- Inhalt: Berechnete Positionen als JSON
- Größe: ~10 KB pro Eintrag

**Total:** ~50-100 MB für vollen Cache

---

### 5. [Worker Setup Guide](WORKER_SETUP.md)
**Datei:** `doc/WORKER_SETUP.md`

**Inhalt:**
- Multi-Host Worker-Architektur
- Worker-Typen (Precompute, Asteroid, Comet)
- Deployment & Konfiguration
- Monitoring & Troubleshooting
- Firewall-Setup

**Nicht Teil dieser Architektur-Dokumentation, aber wichtig für Deployment!**

---

## 🔄 Datenfluss-Übersicht

### Precompute (Stündlich)

```
Coordinator → RabbitMQ Queue → Worker (12x) → PostgreSQL
                                    │
                                    ├─ Load DataFrame (MPC)
                                    ├─ Compute Positions (Skyfield)
                                    └─ Store Snapshot
```

**Siehe:** [ARCHITECTURE_FLOW.md](ARCHITECTURE_FLOW.md)

---

### API Request (On-Demand)

```
Browser → FastAPI → Cache Check
                         │
                    ┌────┴────┐
                Cache HIT  Cache MISS
                    │         │
                Return    RabbitMQ RPC → Worker → Compute → Return
```

**Siehe:** [ARCHITECTURE_FLOW_API.md](ARCHITECTURE_FLOW_API.md)

---

## 🗄️ Cache-Hierarchie

```
Level 1: Precomputed Snapshots (48h)
    │ MISS
    ▼
Level 2: DataFrame Cache (31d)
    │ MISS
    ▼
Level 3: Position Cache (24h)
    │ MISS
    ▼
Level 4: MPC Download (5-30s)
```

**Siehe:** [ARCHITECTURE_CACHE.md](ARCHITECTURE_CACHE.md)

---

## 📊 Performance

| Szenario | Cache Level | Response Zeit | Beschreibung |
|----------|-------------|---------------|--------------|
| **Best Case** | Level 1 | 10-50ms | Precomputed Snapshot vorhanden |
| **Cache Hit** | Level 3 | 100-200ms | Position Cache vorhanden |
| **Cache Miss** | Level 2 | 2-5s | DataFrame vorhanden, Berechnung nötig |
| **Cold Start** | Level 4 | 10-30s | MPC Download + Parse + Berechnung |

**Siehe:** [ARCHITECTURE_CACHE.md](ARCHITECTURE_CACHE.md)

---

## 🔧 Wichtige Code-Komponenten

### API Layer
```
api/
├── main.py                    # FastAPI App
├── routes/
│   ├── asteroids.py          # GET /api/bright_asteroids
│   ├── comets.py             # GET /api/comets
│   └── filters.py            # GET/POST /api/filters
└── background.py             # Precompute Coordinator
```

### Worker Layer
```
workers/
├── precompute_worker.py      # Stündliche Vorberechnung
├── asteroid_worker.py        # On-Demand Asteroid
└── comet_worker.py           # On-Demand Comet
```

### Core Logic
```
bright_asteroids.py           # Asteroid Berechnungen
comets.py                     # Comet Berechnungen
db_utils.py                   # PostgreSQL Operationen
settings.py                   # user_settings.json
```

---

## 🎯 Wichtige Funktionen

### Asteroid-Berechnung
**Datei:** `bright_asteroids.py`

```python
load_bright_asteroids(max_magnitude=20.0)
# Lädt DataFrame aus Cache oder MPC
# Zeilen: 361-520

compute_positions(df, location, time)
# Berechnet Positionen mit Skyfield
# Zeilen: 200-300
```

### RabbitMQ RPC
**Datei:** `api/routes/asteroids.py`

```python
async def get_bright_asteroids(lat, lon, time)
# API Endpoint mit Cache-Check und RPC
# Zeilen: 20-120
```

### Cache-Verwaltung
**Datei:** `db_utils.py`

```python
get_precomputed_snapshot(location_id, timestamp)
# Holt Snapshot aus PostgreSQL
# Zeilen: 185-200

store_precomputed_snapshot(location_id, timestamp, data)
# Speichert Snapshot in PostgreSQL
# Zeilen: 150-180
```

---

## 🚀 Deployment-Architektur

```
┌─────────────────────────────────────────────────────────────┐
│ Hauptserver (asciisky.eibrain.org)                          │
│ - FastAPI Web                                                │
│ - RabbitMQ (Message Broker)                                  │
│ - PostgreSQL (Cache/DB)                                      │
│ - Precompute Worker (4x)                                     │
└────────────────────┬────────────────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          │                     │
┌─────────▼────────┐   ┌────────▼─────────┐
│ Worker Host B    │   │ Worker Host C    │
│ - Precompute (4x)│   │ - Precompute (4x)│
│ - Asteroid (2x)  │   │ - Asteroid (2x)  │
│ - Comet (2x)     │   │ - Comet (2x)     │
└──────────────────┘   └──────────────────┘
```

**Total:** 12 Precompute + 4 Asteroid + 4 Comet Worker

**Siehe:** [WORKER_SETUP.md](WORKER_SETUP.md)

---

## 📖 Lesereihenfolge (Empfohlen)

1. **Start hier:** [ARCHITECTURE_INDEX.md](ARCHITECTURE_INDEX.md) ← Du bist hier!
2. **System-Übersicht:** [ARCHITECTURE_FLOW.md](ARCHITECTURE_FLOW.md)
3. **API-Flow:** [ARCHITECTURE_FLOW_API.md](ARCHITECTURE_FLOW_API.md)
4. **Cache-Details:** [ARCHITECTURE_CACHE.md](ARCHITECTURE_CACHE.md)
5. **Datenbank:** [ARCHITECTURE_DATABASE.md](ARCHITECTURE_DATABASE.md)
6. **Deployment:** [WORKER_SETUP.md](WORKER_SETUP.md)

---

## 🔍 Schnellreferenz

**Frage:** Wie funktioniert die stündliche Vorberechnung?
→ [ARCHITECTURE_FLOW.md](ARCHITECTURE_FLOW.md) - Precompute-Flow

**Frage:** Was passiert bei einem API-Request?
→ [ARCHITECTURE_FLOW_API.md](ARCHITECTURE_FLOW_API.md)

**Frage:** Wie funktioniert das Caching?
→ [ARCHITECTURE_CACHE.md](ARCHITECTURE_CACHE.md)

**Frage:** Welche Datenbank-Tabellen gibt es?
→ [ARCHITECTURE_DATABASE.md](ARCHITECTURE_DATABASE.md)

**Frage:** Wie deploye ich die Worker?
→ [WORKER_SETUP.md](WORKER_SETUP.md)

---

## 📝 Letzte Aktualisierung

**Datum:** 22. Oktober 2025
**Version:** 1.0
**Status:** Vollständig dokumentiert
