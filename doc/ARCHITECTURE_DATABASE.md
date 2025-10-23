# Database Schema

## PostgreSQL Tables

### 1. asteroids / comets (DataFrame cache)

Stores raw MPC data as pickled Pandas DataFrames.

```sql
CREATE TABLE asteroids (
    id SERIAL PRIMARY KEY,
    dataframe_pickle BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE comets (
    id SERIAL PRIMARY KEY,
    dataframe_pickle BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Contents:** Pickle-serialized Pandas DataFrames with orbital elements:
- Designation (Name)
- H (Absolute Magnitude)
- G (Slope Parameter)
- Epoch
- M (Mean Anomaly)
- Peri (Argument of Perihelion)
- Node (Longitude of Ascending Node)
- i (Inclination)
- e (Eccentricity)
- n (Mean Daily Motion)
- a (Semimajor Axis)

**Source:**
- Asteroids: https://minorplanetcenter.net/iau/MPCORB/MPCORB.DAT (~200 MB)
- Comets: https://minorplanetcenter.net/iau/Ephemerides/Comets/CometEls.txt (~100 KB)

**Code:** `db_utils.py:55-90`

---

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

**location_key:** Format `lat+XX.XXXX_lon+YY.YYYY_el+ZZZZ`

**Contents:** Unfiltered computed positions (all objects up to mag ~22)

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

**Important:** Contains ALL computed objects (unfiltered)! Filtering happens in API routes.

**Code:** 
- `db_utils.py:store_asteroid_positions()` — lines 90–112
- `db_utils.py:store_comet_positions()` — lines 180–206
- `db_utils.py:get_asteroid_positions()` — lines 114–138
- `db_utils.py:get_comet_positions()` — lines 208–232

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
PostgreSQL: asteroids/comets Tabellen
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

| Table | TTL | Reason |
|-------|-----|--------|
| asteroids/comets | 31 days | Orbital elements change slowly |
| cached_positions | Unlimited | Positions for a specific timestamp are immutable |

**Position cache:**

Positions for a **specific timestamp** (time_bucket) are **immutable**:
- The position of Ceres on 2025-12-25 at 12:00 UTC never changes
- Cached indefinitely
- Saves significant compute time for repeated queries

**Storage management:**
- Old positions can be pruned manually if needed
- Recommendation: delete positions with `time_bucket` < now() - 1 year
- Typical storage: ~10 KB per location/time combination

**Planets:** NOT cached (direct computation for each request)

## Storage Usage

| Table | Size (approx.) | Per entry |
|-------|-----------------|-----------|
| asteroids | 20–50 MB | ~20 MB (DataFrame with ~1M objects) |
| comets | 1–5 MB | ~1 MB (DataFrame with ~1000 objects) |
| cached_positions | 100–500 KB | ~10 KB (pickled array, unfiltered) |

**Total:** ~25–60 MB for a full cache (excluding planets)
