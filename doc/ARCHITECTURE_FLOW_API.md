# API Request Flow (On-Demand)

## Overview

ASCII Sky has three different API endpoints with distinct computation strategies:

1. **Asteroids** (`/api/bright_asteroids`) — RabbitMQ workers (cache + on-demand)
2. **Comets** (`/api/comets`) — RabbitMQ workers (cache + on-demand) — **same as asteroids**
3. **Planets** (`/api/planets`) — Direct computation (no workers, no cache)

---

## Asteroids & Comets (Identical Flow)

Both use the same architecture with RabbitMQ workers and multi-level caches.

### Sequence Diagram

```
    ┌──────────────────┐
    │   Web Browser    │
    └────────┬─────────┘
             │
             │ GET /api/bright_asteroids?lat=52.52&lon=13.4&time=2025-10-22T20:00:00Z
             ▼
    ┌────────────────────────────────────────┐
    │  FastAPI (Main server)                  │
    │  api/routes/asteroids.py               │
    └────────┬───────────────────────────────┘
             │
             │ 1. Parse request parameters
             ▼
    ┌────────────────────────────────────────┐
    │  Check position cache                  │
    │  db_utils.py:get_asteroid_positions()  │
    └────────┬───────────────────────────────┘
             │
        ┌────┴────┐
        │         │
    Cache HIT  Cache MISS
        │         │
        ▼         ▼
    ┌────────┐  ┌───────────────────────────────────┐
    │ Filter │  │  RabbitMQ: On-demand computation  │
    │ + Ret. │  │                                   │
    └────────┘  │  2. Publish to RabbitMQ           │
                │     Exchange: "computation.direct"│
                │     Queue (Quorum, TTL 1h):       │
                │     "asteroid.compute"            │
                │                                   │
                │  3. Wait for reply (RPC)          │
                │     Timeout: 30 seconds           │
                └────────┬──────────────────────────┘
                         │
                         ▼
                ┌────────────────────────────────────┐
                │  Asteroid Worker (host B or C)     │
                │  workers/asteroid_worker.py        │
                │                                    │
                │  A. Load DataFrame from PostgreSQL │
                │  B. Compute positions (mag 20.0)   │
                │  C. Store unfiltered in cache      │
                │     (cached_positions)             │
                └────────┬───────────────────────────┘
                         │
                         │ 4. Send reply back
                         ▼
                ┌────────────────────────────────────┐
                │  FastAPI: Magnitude filtering      │
                │  api/routes/asteroids.py:188-189   │
                │                                    │
                │  if asteroid['magnitude'] <= max:  │
                │      result.add(asteroid)          │
                │                                    │
                │  Format JSON response              │
                └────────┬───────────────────────────┘
                         │
                         ▼
                ┌────────────────────────────────────┐
                │  Web browser shows asteroids       │
                └────────────────────────────────────┘
```

## Code References: Asteroids & Comets

### Asteroids

| Component | File | Function | Lines |
|------------|-------|----------|--------|
| API Endpoint | `api/routes/asteroids.py` | `get_bright_asteroids()` | 20-120 |
| Worker | `workers/asteroid_worker.py` | `process_asteroid_task()` | 50-150 |
| Core Logic | `bright_asteroids.py` | `load_bright_asteroids()` | 361-520 |
| Core Logic | `bright_asteroids.py` | `compute_positions()` | 200-300 |
| Magnitude Filter | `settings.py` | `get_magnitude_filters()` | 45-60 |

### Comets (Identical Flow)

| Component | File | Function | Lines |
|------------|-------|----------|--------|
| API Endpoint | `api/routes/comets.py` | `get_comets()` | 20-120 |
| Worker | `workers/comet_worker.py` | `process_comet_task()` | 50-150 |
| Core Logic | `comets.py` | `load_comets()` | 748-850 |
| Core Logic | `comets.py` | `compute_positions()` | 200-300 |
| Magnitude Filter | `settings.py` | `get_magnitude_filters()` | 45-60 |

**Differences:**
- Different MPC data source (MPCORB.DAT vs Comets Ephemerides)
- Different RabbitMQ queue (quorum, TTL 1h: `asteroid.compute` vs `comet.compute`)
- Different PostgreSQL tables (`asteroids` vs `comets`)
- **Same architecture, same sequence!**

---

### RabbitMQ Queues

- Precompute: `precompute.tasks` (Classic, Priority 0–10)
- On-Demand: `asteroid.compute`, `comet.compute` (Quorum, TTL 1h)

## Planets (Direct Computation)

Planets use a **completely different strategy**: no workers, no cache, direct computation.

### Flow Diagram

```
    ┌──────────────────┐
    │   Web Browser    │
    └────────┬─────────┘
             │
             │ GET /api/planets?lat=52.52&lon=13.4&time=2025-10-22T20:00:00Z
             ▼
    ┌────────────────────────────────────────┐
    │  FastAPI (Main server)                 │
    │  api/routes/planets.py                 │
    └────────┬───────────────────────────────┘
             │
             │ 1. Parse request parameters
             ▼
    ┌────────────────────────────────────────┐
    │  Direct computation (synchronous)      │
    │  planets.py:get_planet_positions()     │
    │                                        │
    │  - No cache check                      │
    │  - No RabbitMQ                         │
    │  - No workers                          │
    │                                        │
    │  A. Create Skyfield observer           │
    │  B. For each planet:                   │
    │     - Load ephemeris (de421.bsp)       │
    │     - Compute position (RA/Dec)        │
    │     - Transform to Alt/Az              │
    │     - Compute magnitude                │
    │     - Compute rise/set times           │
    │  C. Filter visible planets             │
    └────────┬───────────────────────────────┘
             │
             │ 2. Return JSON (directly)
             ▼
    ┌────────────────────────────────────────┐
    │  Web browser shows planets            │
    └────────────────────────────────────────┘
```

### Why no workers for planets?

**Reasons:**
1. **Fast:** Only 8 planets → computation takes ~50–200ms
2. **No download:** Ephemeris data (de421.bsp) is local
3. **No large datasets:** Asteroids ≈ ~1M objects, planets = 8 objects
4. **Simpler:** Less complexity, fewer failure points

**Drawbacks:**
- Blocks request thread (briefly)
- No scaling via workers
- No cache (not needed at <200ms)

### Code References: Planets

| Component | File | Function | Lines |
|------------|-------|----------|--------|
| API Endpoint | `api/routes/planets.py` | `get_planets()` | 20-80 |
| Core Logic | `planets.py` | `get_planet_positions()` | 50-200 |
| Ephemeris | `planets.py` | Skyfield Loader | 20-40 |

**Important:** Planets use Skyfield's built-in planetary ephemeris (de421.bsp), not MPC data!

---

## Comparison: Asteroids/Comets vs Planets

| Aspect | Asteroids/Comets | Planets |
|--------|-------------------|----------|
| **Number of objects** | ~1M asteroids, ~1000 comets | 8 planets |
| **Data source** | MPC (download) | Skyfield ephemeris (local) |
| **Cache** | 4-level cache | No cache |
| **Workers** | RabbitMQ workers (4–8 workers) | No workers |
| **Response time** | 10ms (cache) – 30s (cold start) | 50–200ms (always) |
| **Complexity** | High (multi-host, queue, cache) | Low (direct computation) |
| **Scaling** | Horizontal (more workers) | Vertical (faster server) |
| **Error handling** | Fallback, retry, timeout | Simple (try/catch) |

---

## Performance Comparison

### Asteroids/Comets
```
Best Case (Precomputed):  10-50ms
Cache Hit (Position):     100-200ms
Cache Miss (DataFrame):   2-5s
Cold Start (MPC):         10-30s
```

### Planets
```
Always:                   50–200ms
```

**Conclusion:** Planets are consistently fast; asteroids/comets have variable performance but better best-case performance due to precompute.
