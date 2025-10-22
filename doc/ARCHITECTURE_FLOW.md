# ASCII Sky - Architektur & Datenfluss

Detaillierte Dokumentation über den kompletten Request-Flow von der Web-Anfrage bis zur Antwort.

## Übersicht

ASCII Sky verwendet zwei parallele Datenflüsse:

1. **Precompute-Flow**: Stündliche Vorberechnung für bekannte Locations
2. **On-Demand-Flow**: Echtzeit-Berechnung bei Cache-Miss

```
┌─────────────────────────────────────────────────────────────────┐
│                         ASCII Sky System                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────┐              ┌──────────────────┐         │
│  │  Precompute      │              │  On-Demand       │         │
│  │  (Stündlich)     │              │  (Bei Bedarf)    │         │
│  └──────────────────┘              └──────────────────┘         │
│           │                                  │                   │
│           ├──────────────┬──────────────────┤                   │
│           │              │                  │                   │
│           ▼              ▼                  ▼                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │ PostgreSQL  │  │  RabbitMQ   │  │   Worker    │            │
│  │   Cache     │  │   Queues    │  │   Cluster   │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Precompute-Flow (Stündlich)

### Ablauf-Diagramm

```
    ┌──────────────────┐
    │  Coordinator     │  api/background.py:precompute_coordinator()
    │  (Hauptserver)   │  Läuft alle 3600 Sekunden
    └────────┬─────────┘
             │
             │ 1. Lade Locations aus user_settings.json
             ▼
    ┌────────────────────────────────────────┐
    │ Für jede Location & nächste 48h:      │
    │ - Erstelle Task für jede Stunde       │
    └────────┬───────────────────────────────┘
             │
             │ 2. Publiziere Tasks zu RabbitMQ Queue: "precompute.tasks"
             ▼
    ┌────────────────────────────────────────┐
    │         RabbitMQ Queue                 │
    │  [Task1] [Task2] [Task3] ... [TaskN]  │
    └────────┬───────────────────────────────┘
             │
             │ 3. Worker holen Tasks (12 Worker total)
             ▼
  ┌────────┐  ┌────────┐  ┌────────┐
  │Worker 1│  │Worker 2│  │ ... 12 │
  └───┬────┘  └───┬────┘  └───┬────┘
      │           │           │
      │ 4. Verarbeite Task    │
      ▼           ▼           ▼
┌──────────────────────────────────────────────────┐
│  process_precompute_task()                       │
│  workers/precompute_worker.py:200-350            │
│                                                  │
│  A. Lade Asteroiden-DataFrame                    │
│     bright_asteroids.py:load_bright_asteroids()  │
│     - Prüfe PostgreSQL Cache (TTL 31 Tage)       │
│     - Falls fehlt: Download von MPC MPCORB.DAT   │
│                                                  │
│  B. Lade Kometen-DataFrame                       │
│     comets.py:load_comets()                      │
│     - Prüfe PostgreSQL Cache (TTL 31 Tage)       │
│     - Falls fehlt: Download MPC CometEls.txt     │
│                                                  │
│  C. Berechne Positionen                          │
│     - Skyfield Berechnungen für jeden Ort/Zeit   │
│     - Asteroiden & Kometen                       │
│                                                  │
│  D. Speichere in PostgreSQL                      │
│     db_utils.py:store_asteroid_positions()       │
│     db_utils.py:store_comet_positions()          │
│     Tabellen: asteroid_positions, comet_positions│
└──────────────────────────────────────────────────┘
```

### Code-Referenzen

| Komponente | Datei | Funktion | Zeilen |
|------------|-------|----------|--------|
| Coordinator | `api/background.py` | `precompute_coordinator()` | 130-195 |
| Worker | `workers/precompute_worker.py` | `process_precompute_task()` | 80-190 |
| Asteroid Load | `bright_asteroids.py` | `load_bright_asteroids()` | 200-360 |
| Comet Load | `comets.py` | `load_comets()` | 280-450 |
| Asteroid Store | `db_utils.py` | `store_asteroid_positions()` | 90-112 |
| Comet Store | `db_utils.py` | `store_comet_positions()` | 180-202 |

---

## API-Request-Flow (On-Demand)

Siehe separate Datei: `ARCHITECTURE_FLOW_API.md`
