# API Request Flow (On-Demand)

## Übersicht

ASCII Sky hat drei verschiedene API-Endpoints mit unterschiedlichen Berechnungsstrategien:

1. **Asteroiden** (`/api/bright_asteroids`) - RabbitMQ Worker (Cache + On-Demand)
2. **Kometen** (`/api/comets`) - RabbitMQ Worker (Cache + On-Demand) - **Gleich wie Asteroiden**
3. **Planeten** (`/api/planets`) - Direktberechnung (kein Worker, kein Cache)

---

## Asteroiden & Kometen (Identischer Flow)

Beide verwenden die gleiche Architektur mit RabbitMQ Workers und mehrstufigem Cache.

### Ablauf-Diagramm

```
    ┌──────────────────┐
    │   Web Browser    │
    └────────┬─────────┘
             │
             │ GET /api/bright_asteroids?lat=52.52&lon=13.4&time=2025-10-22T20:00:00Z
             ▼
    ┌────────────────────────────────────────┐
    │  FastAPI (Hauptserver)                 │
    │  api/routes/asteroids.py               │
    └────────┬───────────────────────────────┘
             │
             │ 1. Parse Request Parameter
             ▼
    ┌────────────────────────────────────────┐
    │  Prüfe Position Cache                  │
    │  db_utils.py:get_asteroid_positions()  │
    └────────┬───────────────────────────────┘
             │
        ┌────┴────┐
        │         │
    Cache HIT  Cache MISS
        │         │
        ▼         ▼
    ┌────────┐  ┌───────────────────────────────────┐
    │ Filter │  │  RabbitMQ: On-Demand Berechnung   │
    │ + Ret. │  │                                   │
    └────────┘  │  2. Publiziere zu RabbitMQ        │
                │     Exchange: "computation.direct"│
                │     Queue (Quorum, TTL 1h):       │
                │     "asteroid.compute"            │
                │                                   │
                │  3. Warte auf Antwort (RPC)       │
                │     Timeout: 30 Sekunden          │
                └────────┬──────────────────────────┘
                         │
                         ▼
                ┌────────────────────────────────────┐
                │  Asteroid Worker (Host B oder C)   │
                │  workers/asteroid_worker.py        │
                │                                    │
                │  A. Lade DataFrame aus PostgreSQL  │
                │  B. Berechne Positionen (Mag 20.0) │
                │  C. Speichere ungefiltert in Cache │
                │     (cached_positions)             │
                └────────┬───────────────────────────┘
                         │
                         │ 4. Sende Antwort zurück
                         ▼
                ┌────────────────────────────────────┐
                │  FastAPI: Magnitude-Filterung      │
                │  api/routes/asteroids.py:188-189   │
                │                                    │
                │  if asteroid['magnitude'] <= max:  │
                │      result.add(asteroid)          │
                │                                    │
                │  Formatiert JSON Response          │
                └────────┬───────────────────────────┘
                         │
                         ▼
                ┌────────────────────────────────────┐
                │  Web Browser zeigt Asteroiden      │
                └────────────────────────────────────┘
```

## Code-Referenzen: Asteroiden & Kometen

### Asteroiden

| Komponente | Datei | Funktion | Zeilen |
|------------|-------|----------|--------|
| API Endpoint | `api/routes/asteroids.py` | `get_bright_asteroids()` | 20-120 |
| Worker | `workers/asteroid_worker.py` | `process_asteroid_task()` | 50-150 |
| Core Logic | `bright_asteroids.py` | `load_bright_asteroids()` | 361-520 |
| Core Logic | `bright_asteroids.py` | `compute_positions()` | 200-300 |
| Magnitude Filter | `settings.py` | `get_magnitude_filters()` | 45-60 |

### Kometen (Identischer Ablauf)

| Komponente | Datei | Funktion | Zeilen |
|------------|-------|----------|--------|
| API Endpoint | `api/routes/comets.py` | `get_comets()` | 20-120 |
| Worker | `workers/comet_worker.py` | `process_comet_task()` | 50-150 |
| Core Logic | `comets.py` | `load_comets()` | 748-850 |
| Core Logic | `comets.py` | `compute_positions()` | 200-300 |
| Magnitude Filter | `settings.py` | `get_magnitude_filters()` | 45-60 |

**Unterschiede:**
- Andere MPC-Datenquelle (MPCORB.DAT vs Comets Ephemerides)
- Andere RabbitMQ Queue (Quorum, TTL 1h: `asteroid.compute` vs `comet.compute`)
- Andere PostgreSQL Tabellen (`asteroids` vs `comets`)
- **Gleiche Architektur, gleicher Ablauf!**

---

### RabbitMQ Queues

- Precompute: `precompute.tasks` (Classic, Priority 0–10)
- On-Demand: `asteroid.compute`, `comet.compute` (Quorum, TTL 1h)

## Planeten (Direktberechnung)

Planeten verwenden eine **komplett andere Strategie**: Keine Worker, kein Cache, direkte Berechnung.

### Ablauf-Diagramm

```
    ┌──────────────────┐
    │   Web Browser    │
    └────────┬─────────┘
             │
             │ GET /api/planets?lat=52.52&lon=13.4&time=2025-10-22T20:00:00Z
             ▼
    ┌────────────────────────────────────────┐
    │  FastAPI (Hauptserver)                 │
    │  api/routes/planets.py                 │
    └────────┬───────────────────────────────┘
             │
             │ 1. Parse Request Parameter
             ▼
    ┌────────────────────────────────────────┐
    │  Direktberechnung (Synchron)           │
    │  planets.py:get_planet_positions()     │
    │                                        │
    │  - Keine Cache-Prüfung                 │
    │  - Keine RabbitMQ                      │
    │  - Keine Worker                        │
    │                                        │
    │  A. Erstelle Skyfield Observer         │
    │  B. Für jeden Planeten:                │
    │     - Lade Ephemeris (de421.bsp)       │
    │     - Berechne Position (RA/Dec)       │
    │     - Transformiere zu Alt/Az          │
    │     - Berechne Magnitude               │
    │     - Berechne Auf-/Untergangszeiten   │
    │  C. Filtere sichtbare Planeten         │
    └────────┬───────────────────────────────┘
             │
             │ 2. Return JSON (direkt)
             ▼
    ┌────────────────────────────────────────┐
    │  Web Browser zeigt Planeten            │
    └────────────────────────────────────────┘
```

### Warum keine Worker für Planeten?

**Gründe:**
1. **Schnell:** Nur 8 Planeten → Berechnung dauert ~50-200ms
2. **Kein Download:** Ephemeris-Daten (de421.bsp) sind lokal vorhanden
3. **Keine großen Datasets:** Asteroiden = ~1M Objekte, Planeten = 8 Objekte
4. **Einfacher:** Weniger Komplexität, weniger Fehlerquellen

**Nachteile:**
- Blockiert Request-Thread (aber nur kurz)
- Keine Skalierung über Worker
- Kein Cache (aber auch nicht nötig bei <200ms)

### Code-Referenzen: Planeten

| Komponente | Datei | Funktion | Zeilen |
|------------|-------|----------|--------|
| API Endpoint | `api/routes/planets.py` | `get_planets()` | 20-80 |
| Core Logic | `planets.py` | `get_planet_positions()` | 50-200 |
| Ephemeris | `planets.py` | Skyfield Loader | 20-40 |

**Wichtig:** Planeten verwenden Skyfield's eingebaute Planeten-Ephemeris (de421.bsp), keine MPC-Daten!

---

## Vergleich: Asteroiden/Kometen vs Planeten

| Aspekt | Asteroiden/Kometen | Planeten |
|--------|-------------------|----------|
| **Anzahl Objekte** | ~1M Asteroiden, ~1000 Kometen | 8 Planeten |
| **Datenquelle** | MPC (Download) | Skyfield Ephemeris (lokal) |
| **Cache** | 4-Level Cache | Kein Cache |
| **Worker** | RabbitMQ Worker (4-8 Worker) | Keine Worker |
| **Response Zeit** | 10ms (Cache) - 30s (Cold Start) | 50-200ms (immer) |
| **Komplexität** | Hoch (Multi-Host, Queue, Cache) | Niedrig (Direktberechnung) |
| **Skalierung** | Horizontal (mehr Worker) | Vertikal (schnellerer Server) |
| **Fehlerbehandlung** | Fallback, Retry, Timeout | Einfach (try/catch) |

---

## Performance-Vergleich

### Asteroiden/Kometen
```
Best Case (Precomputed):  10-50ms
Cache Hit (Position):     100-200ms
Cache Miss (DataFrame):   2-5s
Cold Start (MPC):         10-30s
```

### Planeten
```
Immer:                    50-200ms
```

**Fazit:** Planeten sind konsistent schnell, Asteroiden/Kometen haben variable Performance aber bessere Best-Case Performance durch Precompute.
