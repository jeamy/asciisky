# Database Schema

## DataFrame Cache (Filesystem)

### 1. Asteroid / Comet orbital elements

Raw MPC orbital data for asteroids and comets is stored as pickled Pandas
DataFrames on the filesystem (not in PostgreSQL tables):

- **Asteroids:** `DATA_DIR/asteroid_dataframe.pkl`
  - Written by `db_utils.store_asteroid_dataframe(df_pickle)`.
  - Read by `db_utils.get_asteroid_dataframe(max_age_seconds=49*3600)` and
    `bright_asteroids.load_asteroid_dataframe()`.
- **Comets:** `DATA_DIR/comet_dataframe.pkl`
  - Written by `db_utils.store_comet_dataframe(df_pickle)`.
  - Read by `db_utils.get_comet_dataframe(max_age_seconds=49*3600)` and
    `comets.load_comet_dataframe()`.

**Contents (both DataFrames):**
- Designation / name
- Photometric parameters (e.g. H/G for asteroids, M1/k1 for comets)
- Orbital elements (e, q, i, Ω, ω, epoch, etc.)

**Sources:**
- Asteroids: `MPCORB.DAT` from MPC (~200 MB)
- Comets: MPC comet elements file (e.g. `CometEls.txt`)

**Notes:**
- These files are typically refreshed by a nightly updater script.
- The `max_age_seconds` argument in `get_*_dataframe` (~49h) is used as a
  staleness threshold for the on-disk cache.

---

## PostgreSQL Tables

`scripts/init-postgres.sql` creates orbital-element tables, legacy DataFrame
tables, `cached_positions`, updater history, and the `users` / `user_settings`
tables. The active DataFrame helpers use filesystem files rather than the legacy
`asteroid_dataframes` and `comet_dataframes` tables.

`precompute_task_claims` stores expiring, cross-process publication claims. Its
primary key is the normalized task key; workers remove a claim after successful
processing and an expired claim can be replaced after a publisher/worker crash.

### 2. cached_positions (Position cache)

Stores computed results for specific location/time combinations.
Uses a single table for asteroids, comets, and yearly sunpath data.

```sql
CREATE TABLE cached_positions (
    id SERIAL PRIMARY KEY,
    object_type VARCHAR(20) NOT NULL,      -- 'asteroid', 'comet', or 'sunpath'
    object_id INTEGER NOT NULL,
    location_key VARCHAR(100) NOT NULL,    -- 'lat+XX.XXXX_lon+YY.YYYY_el+ZZZZ'
    time_bucket VARCHAR(20) NOT NULL,      -- 'YYYYMMDDTHH' (1-hour buckets)
    observer_lat DOUBLE PRECISION NOT NULL,
    observer_lon DOUBLE PRECISION NOT NULL,
    observer_elevation DOUBLE PRECISION NOT NULL,
    computed_at TIMESTAMP NOT NULL,
    position_data BYTEA NOT NULL,          -- Pickle-serialized data
    UNIQUE(object_type, location_key, time_bucket)
);

CREATE INDEX idx_cached_loc_time ON cached_positions(location_key, time_bucket);
CREATE INDEX idx_cached_computed ON cached_positions(computed_at);
CREATE INDEX idx_cached_type ON cached_positions(object_type);
```

**location_key:** Normalized location key derived from latitude, longitude,
and elevation (see `cache_utils.location_key`).

**Contents:** Unfiltered computed positions (all cached objects up to about
**mag 20.0**)

**Example content:**
```json
[
  {
    "name": "Ceres",
    "magnitude": 7.2,
    "alt": 45.3,
    "az": 180.5,
    "ra": 12.5,
    "dec": 23.8,
    "distance": 2.3,
    "rise_time": "18:30",
    "transit_time": "00:15",
    "set_time": "06:00",
    "type": "asteroid",
    "symbol": "⚸"
  },
  ...
]
```

**Important:** Asteroid/comet rows contain the worker's computed result list
without a user-specific magnitude filter. Filtering happens later in the API
routes. Sunpath rows contain a versioned dictionary rather than a list.

**Code:**
- `db_utils.store_asteroid_positions`
- `db_utils.store_comet_positions`
- `db_utils.get_asteroid_positions`
- `db_utils.get_comet_positions`

---

## Data Flow

```
MPC Download
├─ MPCORB.DAT (Asteroiden, ~200 MB)
└─ CometEls.txt (Kometen, ~100 KB)
         │
         ▼
Pandas DataFrame (Orbital Elements)
         │
         │ Pickle Serialization
         ▼
Filesystem: asteroid_dataframe.pkl / comet_dataframe.pkl
         │
         │ Load & Deserialize
         ▼
Skyfield Position Calculation
         │
         │ For each location/time
         ▼
PostgreSQL: cached_positions
         │
         │ Unfiltered (all objects)
         ▼
API Routes (asteroids.py, comets.py)
         │
         │ Filtering based on user_settings.json
         │ API Response (JSON, filtered)
```

## TTL (Time-To-Live)

| Storage                          | TTL / Staleness window | Reason |
|----------------------------------|------------------------|--------|
| asteroid/comet DataFrame files   | ~49 hours              | Refreshed regularly; orbital elements change slowly |
| cached_positions (PostgreSQL)    | No automatic database expiry | Maintenance functions can prune or invalidate rows |

**Position cache:**

The represented instant is fixed, but a cached result can become stale when
orbital elements, magnitude limits, ephemerides, or computation code change.
Asteroid/comet stores currently use `ON CONFLICT ... DO NOTHING`, so an existing
key is not refreshed automatically.

**Storage management:**
- `db_utils.cleanup_cached_positions(retention_days, object_types)` prunes by `computed_at`.
- SQL function `cleanup_old_positions(retention_days)` defaults to 60 days.
- `db_utils.invalidate_cached_positions(object_types)` removes selected result types.

**Celestial objects (Sun, Moon, planets):** NOT cached (direct computation
via `/api/celestial` for each request)

## Storage Usage

Storage depends on the MPC datasets, configured candidate limits, locations,
precompute horizon, and serialized event data. Measure actual use with filesystem
tools and PostgreSQL's `pg_total_relation_size`; fixed estimates become stale
quickly for this workload.

Last reviewed against the code: 2026-06-30.
