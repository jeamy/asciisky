# API Request Flow (On-Demand)

## Overview
 
ASCII Sky currently exposes four groups of API endpoints with different computation strategies:

1. **Asteroids** (`/api/bright_asteroids`, alias `/api/asteroids`) — cache‑first via PostgreSQL; RabbitMQ workers and precompute fill the cache.
2. **Comets** (`/api/comets`) — same architecture as asteroids.
3. **Celestial objects** (`/api/celestial`, `/api/celestial/{body_id}`) — direct real‑time computation (no workers, no cache).
4. **Sunpath overlay** (`/api/celestial/sunpath`) — yearly sunrise/sunset and twilight curves per location and year, cached in PostgreSQL; computation runs in a background thread without RabbitMQ.

---

## Asteroids & Comets (Cache‑First + Background Workers)

Asteroids and comets share the same flow:

- Positions are stored per **location** and **1‑hour time bucket** in the PostgreSQL table `cached_positions`.
- The API always tries to **load from cache first** (with interpolation).
- If a bucket is missing, the API triggers a **background RabbitMQ worker** to compute and store the bucket asynchronously.
- A separate **precompute pipeline** fills future buckets ahead of time.

### Sequence Diagram (Asteroids/Comets)

```text
Step 1: HTTP request

    Web Browser
        |
        |  GET /api/bright_asteroids?lat=52.52&lon=13.4&time=...
        v
    FastAPI (api/routes/asteroids.py)

Step 2: Parameter parsing

    FastAPI parses:
        - Location (lat, lon, elevation)
        - Time (dt_utc)
        - User magnitude limit (from query or settings)

Step 3: Cache lookup (PostgreSQL)

    compute bucket = time_bucket_utc(dt_utc, 1h)
    positions = get_*_positions(location_key, bucket)

    if positions available:
        -> apply magnitude filter (user max_magnitude)
        -> build JSON response
        -> return to browser

    else (Cache MISS):

Step 4: Best-effort in-progress check

    computation_key = "computing:{object_type}:{location_key}:{bucket_key}"

    if is_computation_in_progress(computation_key):
        -> another worker is already computing this bucket
        -> return (empty bodies or nearest bucket)
    else:
        -> schedule background worker task

Step 5: Background worker scheduling (RabbitMQ)

    FastAPI BackgroundTask:
        - publishes task to exchange "computation.direct"
        - routing_key = "compute.asteroid" or "compute.comet"
        - queues: "asteroid.compute", "comet.compute" (classic, TTL ≈ 1h)

Step 6: Worker computation

    Unified worker:
        - loads asteroid/comet DataFrame from filesystem cache (or MPC)
        - computes positions with Skyfield (up to mag ≈ 20.0)
        - stores result list into PostgreSQL `cached_positions`
        - clears computation lock

Step 7: Future requests

    Subsequent requests for the same location/time bucket:
        - hit `cached_positions`
        - apply user magnitude filter
        - return filtered JSON immediately
```

### Precompute Pipeline

In addition to on-demand workers there is a precompute pipeline:

- `precompute_coordinator.create_precompute_tasks`:
  - Iterates over configured locations and a time window (e.g. 30 days).
    The target locations are collected by `get_target_locations()` from several sources:
    - The last global location from `user_settings.json` via `settings.get_location()`.
    - Static locations from `precompute_locations.json` (if the file is mounted into the coordinator container).
    - All distinct user locations stored in the database `user_settings` JSONB table via `db_utils.get_all_user_locations()`.
    - Optional extra locations from the environment variable `ASCII_SKY_PRECOMPUTE_LOCATIONS` (JSON array of locations).
  - For each location + hour:
    - Checks `cached_positions` via `get_asteroid_positions` / `get_comet_positions`.
    - Skips buckets that are already cached or already queued.
    - Enqueues missing buckets as tasks to `precompute.tasks` (classic queue, with priorities).
    - Prioritizes the current hour, then ±1 hour and ±2 hours, followed by the
      next six hours and the remaining horizon in progressively lower classes.
    - Claims a normalized key in PostgreSQL before publishing, preventing a
      second coordinator/restart from publishing the same task until completion
      or claim expiry.
- `workers/unified_worker.py` (and the compatible `precompute_worker.py` entry point):
  - Consumes from `precompute.tasks` plus the on-demand queues.
  - For each task (`kind = 'asteroids' | 'comets'`):
    - Calls `bright_asteroids.load_bright_asteroids(...)` or `comets.load_comets(...)`.
    - Stores the resulting list in `cached_positions` via
      `store_asteroid_positions` / `store_comet_positions`.
    - Rechecks the cache after acquiring the advisory lock, so a redelivered or
      duplicate message skips computation when another worker already completed it.

### Magnitude Filtering

- Workers compute a broad cache result using their active environment limits.
  Local Compose defaults the unified worker's apparent-magnitude limits to 20.0;
  other Compose stacks and Python fallbacks differ.
- The **user-specific magnitude filter** is only applied in the FastAPI routes:
  - Asteroids: `get_bright_asteroids` filters by `asteroid["magnitude"] <= max_magnitude`.
  - Comets: `get_comets` filters by `comet["magnitude"] <= max_magnitude`.

### Smart Interpolation Feature Flags

Smart interpolation can be rolled out gradually and configured via environment variables
in `config/interpolation_config.py`:

- `ENABLE_SMART_INTERPOLATION` (default `false`): master flag to enable smart interpolation.
- `INTERPOLATION_STRATEGY` (e.g. `nearest_bucket`, `smart_interpolation`, `on_demand_only`, `hybrid`):
  selects the algorithm used by `smart_interpolation`.
- `ENABLE_INTERPOLATION_BACKGROUND_TASKS` (default `true`): controls whether missing buckets
  are computed via background workers or synchronously.
- `INTERPOLATION_ENABLED_USER_IDS` / `INTERPOLATION_ENABLED_PERCENTAGE`:
  allow a gradual rollout per user or per user-percentage.
- Helper functions:
  - `is_smart_interpolation_enabled(user_id)` – returns whether smart interpolation is active
    for a given user.
  - `get_interpolation_strategy(user_id)` – returns the effective strategy for that user.

The asteroid/comet routes read these flags to decide whether to call
`load_*_with_smart_interpolation` or the simpler nearest-bucket loader.

### RabbitMQ Queues & Status

RabbitMQ is used both for precompute and on-demand computation:

- **Exchange**
  - `computation.direct` – direct exchange for on-demand asteroid/comet tasks.

- **Queues**
  - `precompute.tasks` (classic, durable, `x-max-priority = 10`)
    - Used by the unified worker for scheduled bucket computations.
  - `asteroid.compute` (classic, durable, `x-message-ttl = 3600000` ms ≈ 1h)
    - On-demand asteroid bucket computations.
  - `comet.compute` (classic, durable, `x-message-ttl = 3600000` ms ≈ 1h)
    - On-demand comet bucket computations.
  - `computation.status` (classic, durable)
    - Worker status updates (started/progress/completed/failed) via `publish_worker_status`.

The FastAPI background tasks (`trigger_asteroid_worker`, `trigger_comet_worker`) publish
messages to `computation.direct` with routing keys `compute.asteroid` / `compute.comet`,
which are bound to the respective queues.

### Computation Locks (PostgreSQL Advisory Locks)

The API checks an advisory-lock key of the form:

- `computing:{object_type}:{location_key}:{bucket_key}`
  - `object_type` – `asteroid` or `comet`.
  - `location_key` – normalized location (lat/lon/elev) via `cache_utils.location_key`.
  - `bucket_key` – 1‑hour bucket timestamp via `time_bucket_utc(..., 1)`.

Lock handling is implemented in `db_utils.py` using PostgreSQL advisory locks:

- `is_computation_in_progress(computation_key)`
  - Hashes the key into an integer and calls `pg_try_advisory_lock`.
  - If the lock **cannot** be acquired, a computation for that bucket is already running.
  - If the lock **can** be acquired, it is immediately released and the function returns
    "no computation in progress".
- `computation_lock(computation_key)` is a context manager that acquires
  `pg_advisory_lock` and releases it on exit.

Current limitation: the route calls `computation_lock(...)` without entering it
with `with`, so that call does not acquire a lock around publication. The check and
publish are therefore racy and multiple cache misses can enqueue duplicate tasks.
Precompute workers do enter `computation_lock()`, but use a different
`precompute_{kind}:...` key. See [hybrid-deduplication.md](hybrid-deduplication.md)
for the exact semantics and limitations.

---

## Celestial Objects (Sun, Moon, Planets)

Planets (und andere helle Himmelskörper) werden heute über die
`/api/celestial`‑Endpoints ausgeliefert, nicht mehr über `/api/planets`.

### Flow Diagram

```text
    ┌──────────────────┐
    │   Web Browser    │
    └────────┬─────────┘
             │
             │ GET /api/celestial?lat=52.52&lon=13.4&time=2025-10-22T20:00:00Z
             ▼
    ┌────────────────────────────────────────┐
    │  FastAPI (Main server)                │
    │  api/routes/celestial.py              │
    └────────┬──────────────────────────────┘
             │
             │ 1. Parse location + time
             ▼
    ┌────────────────────────────────────────┐
    │  Direct computation (synchronous)      │
    │  api/computation.py:                   │
    │    compute_celestial_snapshot()        │
    │                                        │
    │  - Builds Skyfield observer            │
    │  - Computes alt/az, distance,          │
    │    magnitude for:                      │
    │      sun, moon, mercury, venus, mars,  │
    │      jupiter, saturn, uranus, neptune  │
    │  - Computes rise/set (and transit)     │
    └────────┬──────────────────────────────┘
             │
             │ 2. Return JSON (directly)
             ▼
    ┌────────────────────────────────────────┐
    │  Web browser shows celestial objects   │
    └────────────────────────────────────────┘
```

**Important characteristics:**

- No cache: each request is computed on the fly.
- No workers / RabbitMQ.
- Typical response time is in the range of tens to a few hundred milliseconds.

---

## Code References

### Asteroids & Comets

| Component                    | File                          | Function(s)                                      |
|------------------------------|-------------------------------|--------------------------------------------------|
| Asteroid endpoint            | `api/routes/asteroids.py`     | `get_bright_asteroids`, `get_asteroids`          |
| Comet endpoint               | `api/routes/comets.py`        | `get_comets`                                     |
| Cache loading (nearest)      | `api/cache_interpolation.py`  | `load_asteroids_with_interpolation`, `load_comets_with_interpolation` |
| Smart interpolation (optional)| `api/smart_interpolation.py` | `load_asteroids_with_smart_interpolation`, `load_comets_with_smart_interpolation` |
| Positions cache backend      | `db_utils.py`                 | `get_asteroid_positions`, `get_comet_positions`, `store_asteroid_positions`, `store_comet_positions` |
| Asteroid computation         | `bright_asteroids.py`         | `load_bright_asteroids`, `_compute_asteroids_vectorized` |
| Comet computation            | `comets.py`                   | `load_comets`, `_compute_comets_vectorized`     |
| On-demand worker             | `workers/unified_worker.py`   | `UnifiedWorker` queue callbacks                  |
| Precompute coordinator       | `precompute_coordinator.py`   | `create_precompute_tasks`, `publish_tasks_to_rabbitmq` |
| Precompute worker            | `workers/unified_worker.py`   | `UnifiedWorker.process_task`, `main`            |

### Celestial Objects (Sun, Moon, Planets)

| Component            | File                      | Function(s)                            |
|---------------------|---------------------------|----------------------------------------|
| Celestial endpoints | `api/routes/celestial.py` | `get_celestial_objects`, `get_celestial_object` |
| Core computation    | `api/computation.py`      | `compute_celestial_snapshot`, `CELESTIAL_BODIES` |

### Sunpath Overlay

| Component         | File                      | Function(s)                                      |
|-------------------|---------------------------|--------------------------------------------------|
| Sunpath endpoint  | `api/routes/celestial.py` | `get_sunpath_year`                               |
| Core computation  | `api/computation.py`      | `compute_sunpath_year`, `SUNPATH_VERSION`        |
| Cache backend     | `db_utils.py`             | `store_sunpath_year`, `get_sunpath_year`         |

---

## Comparison: Asteroids/Comets vs Celestial

| Aspect                | Asteroids/Comets                                           | Celestial (Sun, Moon, planets)                 |
|-----------------------|------------------------------------------------------------|-----------------------------------------------|
| Number of objects     | Many (up to thousands in cache per bucket)                | 9 bodies (Sun, Moon, 7 major planets)         |
| Data source           | MPC orbital files + DataFrame cache on filesystem         | Skyfield ephemeris (`de421.bsp` on filesystem) |
| Cache                 | PostgreSQL `cached_positions` (1‑hour buckets)            | No cache                                      |
| Workers               | RabbitMQ workers + precompute pipeline                    | No workers                                    |
| Response time         | Best case: cache hit (few 10–100 ms)                      | Typically 50–200 ms                           |
| Cold start            | Slow if MPC data or first buckets must be computed        | N/A (no heavy precomputation)                 |
| Complexity            | High (queues, workers, locks, interpolation, DB caching)  | Low (single synchronous computation)          |
| Scaling               | Horizontal via more workers                                | Vertical via faster API server                |

---

## Performance Notes

- **Asteroids/Comets**
  - Best case: cached bucket loaded from PostgreSQL + simple magnitude filter.
  - Typical cache‑hit latency: dominated by DB read + JSON formatting.
  - Cache‑miss: first request returns quickly but may be empty; workers fill the cache asynchronously.

- **Celestial**
  - Always computed on demand with Skyfield.
  - No caching overhead; complexity is bounded by a fixed small number of bodies.

The repository has no controlled end-to-end benchmark for fixed response-time
guarantees; actual timings depend on data, cache state, database, and hardware.

Last reviewed against the code: 2026-06-30.
