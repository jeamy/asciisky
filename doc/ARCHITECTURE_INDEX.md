# ASCII Sky - Architecture Documentation

Complete overview of the system architecture, data flows, and implementation.

## 📚 Table of Contents

### 1. [API Request Flow (On-Demand)](ARCHITECTURE_FLOW_API.md)
**File:** `doc/ARCHITECTURE_FLOW_API.md`

**Contents:**
- **Three API groups:**
  1. **Asteroids** (`/api/bright_asteroids`, alias `/api/asteroids`) — cache-first via PostgreSQL, background RabbitMQ workers + precompute.
  2. **Comets** (`/api/comets`) — same architecture as asteroids.
  3. **Celestial objects** (`/api/celestial`, `/api/celestial/{body_id}`) — direct real-time computation (no workers, no cache).
- Full request flow for all three groups.
- Cache hit vs cache miss scenarios.
- Background worker + precompute pipeline for asteroids/comets (no RPC in the hot path).
- Direct computation for celestial objects (synchronous, ~50–200ms).
- Comparison table: asteroids/comets vs celestial.
- Performance notes.

**Asteroids/Comets flow (cache-first + background workers):**
1. Browser → FastAPI endpoint (`/api/bright_asteroids` / `/api/comets`).
2. Compute location + time bucket, try to load positions from `cached_positions` (with interpolation).
3. Cache hit → API applies user magnitude filter (`user_settings.json`) and returns JSON.
4. Cache miss → API checks computation lock (per location/bucket).
5. If no computation in progress → schedule background worker task via RabbitMQ; current request returns (typically with empty `bodies`).
6. Worker computes positions (up to mag ~20.0), stores them in `cached_positions` for future requests.

**Celestial flow (Sun, Moon, planets via /api/celestial):**
1. Browser → FastAPI endpoint (`/api/celestial` or `/api/celestial/{body_id}`).
2. API calls `compute_celestial_snapshot` (Skyfield) to compute positions, magnitudes, and rise/set/transit times on demand.
3. Response is returned directly; no cache or RabbitMQ involved.

**Key components:**
- `api/routes/asteroids.py:get_bright_asteroids()` – Asteroids endpoint.
- `api/routes/comets.py:get_comets()` – Comets endpoint (same flow).
- `api/routes/celestial.py:get_celestial_objects()` / `get_celestial_object()` – Celestial endpoints.
- `workers/asteroid_worker.py` – On-demand asteroid worker.
- `workers/comet_worker.py` – On-demand comet worker.
- `workers/precompute_worker.py` – Precompute worker for asteroids/comets.
- `api/computation.py:compute_celestial_snapshot()` – Celestial computation.

---

### 2. [Cache Strategy](ARCHITECTURE_CACHE.md)
**File:** `doc/ARCHITECTURE_CACHE.md`

**Contents:**
- 3-level cache hierarchy (asteroids & comets only)
  - **Level 1:** Position cache (unlimited) — `cached_positions`
  - **Level 2:** DataFrame cache (filesystem) — `asteroid_dataframe.pkl`, `comet_dataframe.pkl`
  - **Level 3:** MPC download (fallback) — MPCORB.DAT, comet elements file
- Performance metrics per cache level.
- Cache invalidation strategy (filters do not clear caches).
- Response times: 100–200ms (position cache) up to 30s (cold start).

**Cache invalidation:**
- User changes filter → **NO** caches are deleted.
- All caches contain unfiltered data (reusable):
  - Position cache: all computed positions (up to about mag 20.0).
  - DataFrame cache files: MPC orbital data (up to mag 20.0, on filesystem).
- Filtering happens only in API routes based on `user_settings.json`.
- Next request: New objects appear immediately without recomputation.

**Code:** `api/routes/filters.py:36-57`

---

### 3. [Database Schema](ARCHITECTURE_DATABASE.md)
**File:** `doc/ARCHITECTURE_DATABASE.md`

**Contents:**
- PostgreSQL schema for `cached_positions` with SQL.
- Example data (JSON) for cached positions.
- DataFrame cache layout on filesystem (asteroid/comet DataFrame pickles).
- TTL & storage per cache layer.
- Data flow: MPC → DataFrame (filesystem) → PostgreSQL `cached_positions` → API.

**Caches:**

#### DataFrame files (filesystem)
- Paths: `asteroid_dataframe.pkl`, `comet_dataframe.pkl` under `DATA_DIR`.
- Contents: pickled Pandas DataFrames with MPC orbital data (up to mag ~20.0).
- Staleness window: ~49 hours.

#### `cached_positions` (Position cache, PostgreSQL)
- Key: `(object_type, location_key, time_bucket)`.
- TTL: Unlimited (positions for a time bucket are immutable).
- Contents: computed positions as pickled, unfiltered lists (up to mag ~20.0).
- Contains: both asteroids and comets in one table.

**Total:** ~25–60 MB for a typical cache snapshot (excluding celestial objects).

---

### 4. [Hybrid Deduplication](hybrid-deduplication.md)
**File:** `doc/hybrid-deduplication.md`

**Contents:**
- RabbitMQ Message Deduplication + PostgreSQL Advisory Locks
- Two-layer protection against duplicate computations
- Performance benefits: -80% memory, +35% throughput
- Implementation details and monitoring

---

### 5. [Production Deployment](PRODUCTION_DEPLOYMENT.md)
**File:** `doc/PRODUCTION_DEPLOYMENT.md`

**Contents:**
- Multi-host deployment guide
- Firewall configuration
- Environment variables setup
- Monitoring and troubleshooting

---

## 🔄 Data Flow Overview

### API Request (on-demand)

```
Browser → FastAPI → Cache Check
                         │
                    ┌────┴────┐
                Cache HIT  Cache MISS
                    │         │
                Return    RabbitMQ → Workers (on-demand/precompute) → Compute & store in cache
```

---

## 📚 Additional Documentation

### [Celestial Objects](asteroids.md | comets.md | planets.md)
- **Asteroids:** IAU H-G magnitude model, orbital mechanics
- **Comets:** M1/k1 magnitude model, comet-specific calculations  
- **Planets:** Direct Skyfield computation, no caching

### [PostgreSQL](postgresql.md)
- Database setup, optimization, and maintenance
- Advisory locks for Hybrid Deduplication
- Performance tuning

### [Firewall Setup](FIREWALL_SETUP.md)
- UFW configuration for production
- Port security for RabbitMQ and PostgreSQL
- Multi-host network security

---

## 📊 Performance

| Scenario | Cache level | Response time | Description |
|----------|-------------|---------------|--------------|
| **Position cache hit** | Level 1 | 100–200ms | Computed positions available |
| **DataFrame cache hit** | Level 2 | 2–5s | DataFrame present, computation needed |
| **Cold start** | Level 3 | 10–30s | MPC download + parse + compute |
| **Celestial (/api/celestial)** | No cache | 50–200ms | Direct computation of Sun/Moon/planets |

**See:** [ARCHITECTURE_CACHE.md](ARCHITECTURE_CACHE.md)

---

## 🔧 Key Code Components

### API Layer
```
api/
├── main.py                    # FastAPI App
├── routes/
│   ├── asteroids.py          # GET /api/bright_asteroids
│   ├── comets.py             # GET /api/comets
│   ├── celestial.py          # GET /api/celestial, /api/celestial/{body_id}
│   └── filters.py            # GET/POST /api/filters
```

### Worker layer
```
workers/
├── precompute_worker.py      # Hourly precompute
├── asteroid_worker.py        # On-demand asteroid
└── comet_worker.py           # On-demand comet
```

### Core logic
```
bright_asteroids.py           # Asteroid computations
comets.py                     # Comet computations
db_utils.py                   # PostgreSQL operations
settings.py                   # user_settings.json
```

---

## 🎯 Key Functions

### Asteroid computation
**File:** `bright_asteroids.py`

```python
load_bright_asteroids(loader, ts, eph, observer_loc, max_magnitude=20.0, current_dt=None)
# Loads asteroid DataFrame from filesystem cache (or MPCORB.DAT on cold start)
# Computes positions with Skyfield and stores results in cached_positions
```

### Comet computation
**File:** `comets.py`

```python
load_comets(ts, eph, observer_loc, max_comets=100, max_magnitude=20.0, current_dt=None)
# Loads comet DataFrame from filesystem cache (or MPC comet elements file on cold start)
# Computes positions with Skyfield and stores results in cached_positions
```

### Celestial computation (Sun, Moon, planets)
**File:** `api/computation.py`

```python
compute_celestial_snapshot(lat, lon, elevation, dt_utc)
# Direct computation (no cache) using Skyfield
# Computes alt/az, distance, magnitude, rise/set/transit times
```

### Cache management
**File:** `db_utils.py`

```python
# DataFrame cache
store_asteroid_dataframe(df_pickle)  # Zeilen: 55-67
get_asteroid_dataframe()             # Zeilen: 69-88
store_comet_dataframe(df_pickle)     # Zeilen: 138-148
get_comet_dataframe()                # Zeilen: 150-164

# Position cache
store_asteroid_positions(asteroid_id, location_key, time_bucket, ...)  # Zeilen: 90-112
get_asteroid_positions(location_key, time_bucket)                      # Zeilen: 114-134
store_comet_positions(comet_id, location_key, time_bucket, ...)        # Zeilen: 180-202
get_comet_positions(location_key, time_bucket)                         # Zeilen: 204-224
```

---

## 🚀 Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Main server ($RABBITMQ_MAIN)                                │
│ - FastAPI Web                                               │
│ - RabbitMQ (Message Broker)                                 │
│ - PostgreSQL (Cache/DB)                                     │
│ - Precompute Worker (4x)                                    │
└────────────────────┬────────────────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          │                     │
┌─────────▼────────┐   ┌────────▼─────────┐
│ Worker Host B    │   │ Worker Host C    │
│ - Unified        │   │ - Unified        │
│   Workers        │   │   Workers        │
│   (precompute +  │   │   (precompute +  │
│    asteroids +   │   │    asteroids +   │
│    comets)       │   │    comets)       │
└──────────────────┘   └──────────────────┘
```

**Example:** 4 precompute workers on the main server and a configurable number
of unified workers per worker host (see `.env.b.example` / `.env.c.example`).

**See:** [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md)

---

## 📖 Reading order (recommended)

1. **Start here:** [ARCHITECTURE_INDEX.md](ARCHITECTURE_INDEX.md) ← You are here!
2. **System overview:** [ARCHITECTURE_FLOW.md](ARCHITECTURE_FLOW.md)
3. **API flow:** [ARCHITECTURE_FLOW_API.md](ARCHITECTURE_FLOW_API.md)
4. **Cache details:** [ARCHITECTURE_CACHE.md](ARCHITECTURE_CACHE.md)
5. **Database:** [ARCHITECTURE_DATABASE.md](ARCHITECTURE_DATABASE.md)
6. **Deployment:** [WORKER_SETUP.md](WORKER_SETUP.md)

---

## 🔍 Quick reference

**Question:** How does the hourly precompute work?
→ [ARCHITECTURE_FLOW.md](ARCHITECTURE_FLOW.md) - Precompute flow

**Question:** What happens on an API request?
→ [ARCHITECTURE_FLOW_API.md](ARCHITECTURE_FLOW_API.md)

**Question:** How does caching work?
→ [ARCHITECTURE_CACHE.md](ARCHITECTURE_CACHE.md)

**Question:** Which database tables exist?
→ [ARCHITECTURE_DATABASE.md](ARCHITECTURE_DATABASE.md)

**Question:** How do I deploy the workers?
→ [WORKER_SETUP.md](WORKER_SETUP.md)

---

## 📝 Last updated

**Date:** 22 October 2025
**Version:** 1.0
**Status:** Fully documented
