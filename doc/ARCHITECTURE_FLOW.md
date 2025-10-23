# ASCII Sky - Architecture & Data Flow

Detailed documentation of the full request flow from the web request to the response.

## Overview

ASCII Sky uses two parallel data flows:

1. **Precompute flow**: Hourly precomputation for known locations
2. **On-demand flow**: Real-time computation on cache miss

```
┌─────────────────────────────────────────────────────────────────┐
│                         ASCII Sky System                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐              ┌──────────────────┐         │
│  │  Precompute      │              │  On-Demand       │         │
│  │  (Hourly)        │              │  (On-Demand)     │         │
│  └──────────────────┘              └──────────────────┘         │
│           │                                  │                  │
│           ├──────────────┬──────────────────┤                   │
│           │              │                  │                   │
│           ▼              ▼                  ▼                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ PostgreSQL  │  │  RabbitMQ   │  │   Worker    │              │
│  │   Cache     │  │   Queues    │  │   Cluster   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Precompute Flow (Hourly)

### Sequence Diagram

```
    ┌──────────────────┐
    │  Coordinator     │  api/background.py:precompute_coordinator()
    │  (Main server)   │  Runs every 3600 seconds
    └────────┬─────────┘
             │
             │ 1. Load locations from user_settings.json
             ▼
    ┌────────────────────────────────────────────────────────────┐
    │ For each location & next X hours:                          │
    │ - X = ASCII_SKY_PRECOMPUTE_HOURS (default: 720 = 30 days)  │
    │ - Create a task for each hour                              │
    └────────┬───────────────────────────────────────────────────┘
             │
             │ 2. Publish tasks to RabbitMQ queue: "precompute.tasks"
             ▼
    ┌────────────────────────────────────────┐
    │         RabbitMQ Queue                 │
    │  [Task1] [Task2] [Task3] ... [TaskN]   │
    └────────┬───────────────────────────────┘
             │
             │ 3. Workers pull tasks (12 workers total)
             ▼
  ┌────────┐  ┌────────┐  ┌────────┐
  │Worker 1│  │Worker 2│  │ ... 12 │
  └───┬────┘  └───┬────┘  └───┬────┘
      │           │           │
      │ 4. Process task       │
      ▼           ▼           ▼
┌──────────────────────────────────────────────────┐
│  process_precompute_task()                       │
│  workers/precompute_worker.py:200-350            │
│                                                  │
│  A. Load asteroid DataFrame                      │
│     bright_asteroids.py:load_bright_asteroids()  │
│     - Check PostgreSQL cache (TTL 31 days)       │
│     - If missing: download MPC MPCORB.DAT        │
│                                                  │
│  B. Load comet DataFrame                         │
│     comets.py:load_comets()                      │
│     - Check PostgreSQL cache (TTL 31 days)       │
│     - If missing: download MPC CometEls.txt      │
│                                                  │
│  C. Compute positions                            │
│     - Skyfield calculations for each location/time│
│     - Asteroids & comets                         │
│                                                  │
│  D. Store in PostgreSQL                          │
│     db_utils.py:store_asteroid_positions()       │
│     db_utils.py:store_comet_positions()          │
│     Tabelle: cached_positions                    │
└──────────────────────────────────────────────────┘
```

### Code References

| Component | File | Function | Lines |
|------------|-------|----------|--------|
| Coordinator | `api/background.py` | `precompute_coordinator()` | 130-195 |
| Worker | `workers/precompute_worker.py` | `process_precompute_task()` | 80-190 |
| Asteroid load | `bright_asteroids.py` | `load_bright_asteroids()` | 200-360 |
| Comet load | `comets.py` | `load_comets()` | 280-450 |
| Asteroid store | `db_utils.py` | `store_asteroid_positions()` | 90-112 |
| Comet store | `db_utils.py` | `store_comet_positions()` | 180-202 |

---

## API Request Flow (On-Demand)

See separate file: `ARCHITECTURE_FLOW_API.md`
