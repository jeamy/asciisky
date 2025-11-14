# ASCII Sky - Architecture Documentation

Complete overview of the system architecture, data flows, and implementation.

## 📚 Table of Contents

### 1. [API Request Flow (On-Demand)](ARCHITECTURE_FLOW_API.md)
**File:** `doc/ARCHITECTURE_FLOW_API.md`

**Contents:**
- **Three API endpoints:**
  1. **Asteroids** — RabbitMQ workers + cache
  2. **Comets** — RabbitMQ workers + cache (same as asteroids)
  3. **Planets** — Direct computation (no workers, no cache)
- Full request flow for all three types
- Cache hit vs cache miss scenarios
- RabbitMQ RPC pattern for asteroids/comets
- Direct computation for planets (synchronous, ~50–200ms)
- Comparison table: asteroids/comets vs planets
- Performance comparison

**Asteroids/Comets flow:**
1. Browser → FastAPI endpoint
2. Position cache check
3. On cache miss: RabbitMQ RPC (30s timeout)
4. Worker computes positions (mag 20.0, unfiltered)
5. Worker stores in cache
6. FastAPI applies magnitude filters (user_settings.json)
7. Response back to browser

**Planets flow:**
1. Browser → FastAPI endpoint
2. Direct computation with Skyfield (50–200ms)
3. Response back to browser

**Key components:**
- `api/routes/asteroids.py:get_bright_asteroids()` - Asteroids endpoint
- `api/routes/comets.py:get_comets()` - Comets endpoint (same flow)
- `api/routes/planets.py:get_planets()` - Planets endpoint (direct)
- `workers/asteroid_worker.py` - Asteroid worker
- `workers/comet_worker.py` - Comet worker
- `planets.py:get_planet_positions()` - Planet computation

---

### 3. [Cache Strategy](ARCHITECTURE_CACHE.md)
**File:** `doc/ARCHITECTURE_CACHE.md`

**Contents:**
- 3-level cache hierarchy (asteroids & comets only)
  - **Level 1:** Position cache (unlimited) — `cached_positions`
  - **Level 2:** DataFrame cache (31 days) — `asteroids`, `comets`
  - **Level 3:** MPC download (fallback) — MPCORB.DAT, CometEls.txt
- Planets: NOT cached (direct computation)
- Cache strategy on magnitude filter changes
- Performance metrics per cache level
- Response times: 100–200ms (position cache) up to 30s (cold start)

**Cache invalidation:**
- User changes filter → **NO** PostgreSQL caches are deleted!
- All caches contain unfiltered data (reusable)
- Position caches: All computed positions (up to mag ~22)
- DataFrames: MPC orbital data (mag 20.0)
- Filtering: Only in API routes based on user_settings.json
- Next request: New objects appear immediately without recomputation!

**Code:** `api/routes/filters.py:36-57`

---

### 2. [Cache Strategy](ARCHITECTURE_CACHE.md)
**File:** `doc/ARCHITECTURE_CACHE.md`

**Contents:**
- 3-level cache hierarchy (asteroids & comets only)
- Performance metrics per cache level
- Cache invalidation strategy
- Response times: 100–200ms (position cache) up to 30s (cold start)

---

### 3. [Database Schema](ARCHITECTURE_DATABASE.md)
**File:** `doc/ARCHITECTURE_DATABASE.md`

**Contents:**
- PostgreSQL table schema with SQL
- Example data (JSON)
- TTL & storage per table
- Data flow: MPC → DataFrame → PostgreSQL → API

**Tables:**

#### `asteroids` / `comets` (DataFrame cache)
- Contents: Pickle-serialized Pandas DataFrames with MPC orbital data
- TTL: 31 days
- Size: ~20 MB (asteroids), ~1 MB (comets)
- Source: MPCORB.DAT, CometEls.txt

#### `cached_positions` (Position cache)
- Key: `(object_type, location_key, time_bucket)`
- TTL: Unlimited (positions are immutable)
- Contents: Computed positions as pickled, unfiltered data
- Size: ~10 KB per entry
- Contains: Both asteroids and comets in one table

**Total:** ~25–60 MB for a full cache (excluding planets)

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
                Return    RabbitMQ RPC → Unified Worker → Compute → Return
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
| **Planets** | No cache | 50–200ms | Direct computation (only 8 bodies) |

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
│   └── filters.py            # GET/POST /api/filters
└── background.py             # Precompute Coordinator
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
# Loads DataFrame from PostgreSQL cache or MPC MPCORB.DAT
# Computes positions with Skyfield
# Lines: 200–360
```

### Comet computation
**File:** `comets.py`

```python
load_comets(ts, eph, observer_loc, max_comets=100, max_magnitude=20.0, current_dt=None)
# Loads DataFrame from PostgreSQL cache or MPC CometEls.txt
# Computes positions with Skyfield
# Lines: 280–450
```

### Planet computation
**File:** `planets.py`

```python
get_planet_positions(lat, lon, elevation, time=None)
# Direct computation (no cache)
# Uses Skyfield's built-in planetary ephemeris (de421.bsp)
# Lines: 50–200
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
│ Main server ($RABBITMQ_MAIN)                                  │
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

**See:** [WORKER_SETUP.md](WORKER_SETUP.md)

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
