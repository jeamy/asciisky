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

### 2. cached_positions (Position cache)

Stores computed positions for specific location/time combinations.
Uses a single table for both asteroids and comets.

```sql
CREATE TABLE cached_positions (
    id SERIAL PRIMARY KEY,
    object_type VARCHAR(20) NOT NULL,      -- 'asteroid' or 'comet'
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

**Important:** Contains all computed objects for that bucket (unfiltered by
user magnitude). Filtering happens later in the API routes.

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
| cached_positions (PostgreSQL)    | Unlimited              | Positions for a specific timestamp are immutable |

**Position cache:**

Positions for a **specific timestamp** (time_bucket) are **immutable**:
- The position of Ceres on 2025-12-25 at 12:00 UTC never changes
- Cached indefinitely
- Saves significant compute time for repeated queries

**Storage management:**
- Old positions can be pruned manually if needed
- Recommendation: delete positions with `time_bucket` < now() - 1 year
- Typical storage: ~10 KB per location/time combination

**Celestial objects (Sun, Moon, planets):** NOT cached (direct computation
via `/api/celestial` for each request)

## Storage Usage

| Storage              | Size (approx.)       | Per entry / file                |
|----------------------|----------------------|---------------------------------|
| asteroid DataFrame   | 20–50 MB             | ~20 MB (DataFrame with ~1M rows) |
| comet DataFrame      | 1–5 MB               | ~1 MB (DataFrame with ~1000 rows) |
| cached_positions row | 100–500 KB           | ~10 KB (pickled list, unfiltered) |

**Total:** ~25–60 MB for a typical cache snapshot (excluding celestial
objects, which are computed on demand).
