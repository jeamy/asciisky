# Cache Strategy

## Cache Hierarchy

```
Level 1: Position Cache (PostgreSQL)
┌────────────────────────────────────────────────────────────────┐
│ Table: cached_positions                                      │
│ Key: (object_type, location_key, time_bucket)                  │
│ TTL: Unlimited (positions are immutable)                       │
│ Contents: Computed positions (unfiltered)                      │
│ Created by: Precompute workers (hourly) + on-demand workers    │
│ Used by: All API requests (first check)                        │
│ Celestial (Sun/Moon/planets): NOT cached (direct via/celestial)│
└────────────────────────────────────────────────────────────────┘
         │ Cache MISS
         ▼
Level 2: DataFrame Cache (Filesystem)
┌────────────────────────────────────────────────────────────────┐
│ Files: asteroid_dataframe.pkl, comet_dataframe.pkl             │
│ Staleness: ~49 hours (max_age_seconds in db_utils)            │
│ Content: raw MPC data (orbital elements)                      │
│ Created by: nightly updater / db_utils.store_*_dataframe      │
│ Used by: bright_asteroids/comets for position computation     │
└────────────────────────────────────────────────────────────────┘
         │ Cache MISS
         ▼
Level 3: MPC download
┌────────────────────────────────────────────────────────────────┐
│ URLs:                                                          │
│ - Asteroids: https://minorplanetcenter.net/iau/MPCORB/...      │
│   MPCORB.DAT (~200 MB, ~1M objects)                            │
│ - Comets: https://minorplanetcenter.net/iau/Ephemerides/...    │
│   Comets/CometEls.txt (~100 KB, ~1000 objects)                 │
│ Duration: 5–30 seconds (asteroids), 1–5 seconds (comets)       │
└────────────────────────────────────────────────────────────────┘
```

## Cache Invalidation

```
User changes Magnitude Filter (e.g., 14 → 18)
         │
         │ POST /api/filters
         ▼
┌────────────────────────────────────────────────────────────────┐
│ 1. Store new filters in user_settings.json                     │
│    settings.py:set_magnitude_filters()                         │
└────────┬───────────────────────────────────────────────────────┘
         ▼
┌────────────────────────────────────────────────────────────────┐
│ 2. Clear in-memory caches                                      │
│    bright_asteroids.py:clear_in_memory_cache()                 │
└────────┬───────────────────────────────────────────────────────┘
         ▼
┌────────────────────────────────────────────────────────────────┐
│ 3. NO PostgreSQL caches are deleted!                           │
│                                                                │
│    All caches remain:                                          │
│    - asteroid_positions (unfiltered, reusable)                 │
│    - comet_positions (unfiltered, reusable)                    │
│    - asteroids (MPC MPCORB.DAT, mag 20.0)                      │
│    - comets (MPC CometEls.txt, mag 20.0)                       │
│                                                                │
│    Filtering happens in API routes!                            │
└────────┬───────────────────────────────────────────────────────┘
         ▼
┌────────────────────────────────────────────────────────────────┐
│ 4. Next Request                                                │
│    - DataFrame cache available (mag 20.0)                      │
│    - Position cache available (unfiltered)                     │
│    - API filters to mag 18.0                                   │
│    - Objects 14–18 appear immediately!                         │
│    - No recomputation required!                                │ 
└────────────────────────────────────────────────────────────────┘
```

**Code:** `api/routes/filters.py:44-71`

### Cache Strategy when Filters Change

**Architecture:**
- Workers always compute with mag 20.0 (hard-coded)
- DataFrame cache contains **all** objects up to mag 20
- Filtering happens **only** in API routes based on `user_settings.json`
- **One cache for all user filters!**

**What happens when filters change:**

On filter change (e.g., 14 → 18) **NO** PostgreSQL caches are deleted!

**All caches remain:**
```
asteroid_positions  ← Unfiltered, contains ALL computed positions
comet_positions     ← Unfiltered, contains ALL computed positions
asteroid_dataframe  ← MPCORB.DAT-based orbital data, mag 20 (filesystem)
comet_dataframe     ← MPC comet elements orbital data, mag 20 (filesystem)
```

**Why are caches NOT deleted?**

All caches used by workers contain **unfiltered** data:
- Position cache (`cached_positions`): all computed positions (up to about mag 20.0)
- DataFrame cache files: all objects up to mag 20.0
- Filtering happens **only** in API routes (based on `user_settings.json`)
- **Reusable for all filter settings!**

**Sequence after a filter change:**
1. User changes filter from 14 → 18
2. **No** caches are deleted
3. Next request:
   - DataFrame cache available (mag 20.0) ✅
   - Position cache available (unfiltered) ✅
   - API filters to mag 18.0
   - Objects 14–18 appear **immediately**!
   - **No recomputation required!** 🚀

**Celestial objects (Sun, Moon, planets):**
- Are **not** cached
- Direct computation for each request (~50–200ms) via `/api/celestial`
- Only a small fixed set of bodies, fast enough without cache

**Code references:**
- `workers/precompute_worker.py:305` — `max_magnitude=20.0`
- `workers/asteroid_worker.py:40` — `max_magnitude=20.0`
- `bright_asteroids.py:361-520` — `load_bright_asteroids(max_magnitude=20.0)`
- `comets.py:748-850` — `load_comets(max_magnitude=20.0)`
- `api/routes/asteroids.py:75-78` — filtering based on user_settings
- `api/routes/comets.py:75-78` — filtering based on user_settings
- `settings.py:get_magnitude_filters()` — reads user_settings.json

## Performance Metrics

### Asteroids & Comets

| Scenario                | Cache | Time     |
|-------------------------|-------|----------|
| Position cache hit      | L1    | 100–200ms|
| DataFrame cache hit     | L2    | 2–5s     |
| Cold start (MPC download)| L3   | 10–30s   |

### Celestial (Sun, Moon, planets)

| Scenario           | Cache    | Time      |
|--------------------|----------|-----------|
| Direct computation | No cache | 50–200ms  |

**Note:** Celestial objects are faster than asteroids/comets on cache miss because only a
small fixed set of bodies is computed.
