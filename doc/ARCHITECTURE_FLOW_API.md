# API Request Flow (On-Demand)

## Ablauf-Diagramm

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
    │  Prüfe Precomputed Cache               │
    │  db_utils.py:get_precomputed_snapshot()│
    └────────┬───────────────────────────────┘
             │
        ┌────┴────┐
        │         │
    Cache HIT  Cache MISS
        │         │
        ▼         ▼
    ┌────────┐  ┌──────────────────────────────────┐
    │ Return │  │  RabbitMQ: On-Demand Berechnung  │
    │ Data   │  │                                  │
    └────────┘  │  2. Publiziere zu RabbitMQ       │
                │     Exchange: "computation.direct"│
                │     Queue: "asteroid.compute"    │
                │                                  │
                │  3. Warte auf Antwort (RPC)      │
                │     Timeout: 30 Sekunden         │
                └────────┬─────────────────────────┘
                         │
                         ▼
                ┌────────────────────────────────────┐
                │  Asteroid Worker (Host B oder C)   │
                │  workers/asteroid_worker.py        │
                │                                    │
                │  A. Lade DataFrame aus PostgreSQL  │
                │  B. Berechne Positionen            │
                │  C. Wende Magnitude-Filter an      │
                │  D. Speichere Positions-Cache      │
                └────────┬───────────────────────────┘
                         │
                         │ 4. Sende Antwort zurück
                         ▼
                ┌────────────────────────────────────┐
                │  FastAPI formatiert JSON Response  │
                │  {                                 │
                │    "asteroids": [...],             │
                │    "count": 42                     │
                │  }                                 │
                └────────┬───────────────────────────┘
                         │
                         ▼
                ┌────────────────────────────────────┐
                │  Web Browser zeigt Asteroiden      │
                └────────────────────────────────────┘
```

## Code-Referenzen

| Komponente | Datei | Funktion | Zeilen |
|------------|-------|----------|--------|
| API Endpoint | `api/routes/asteroids.py` | `get_bright_asteroids()` | 20-120 |
| Worker | `workers/asteroid_worker.py` | `process_asteroid_task()` | 50-150 |
| Magnitude Filter | `settings.py` | `get_magnitude_filters()` | 45-60 |
