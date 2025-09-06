# AsciiSky Cache System Documentation

## Overview

The AsciiSky cache system uses a hybrid approach combining **SQLite database** and **hierarchical file structure** for efficient storage of astronomical calculations. The system is based on **location and time-based buckets** with both **SQLite storage** (primary) and **Pickle serialization** (fallback).

## Hybrid Cache Structure

### SQLite Database (Primary)

```
cache/asciisky.db               # Main SQLite database file
```

The SQLite database contains tables for:
- `asteroids` - Asteroid orbital data
- `comets` - Comet orbital data
- `asteroid_positions` - Cached asteroid positions by location and time
- `comet_positions` - Cached comet positions by location and time
- `celestial_snapshots` - Cached celestial body positions by location and time

See `doc/sqlite.md` for detailed schema information.

### Pickle Files (Fallback)

```
cache/
├── celestial/                    # Planets and stars
│   └── lat+52.5200_lon+13.4050_el+0040/
│       ├── 20250906T00.pkl      # 00:00-05:59 UTC
│       ├── 20250906T06.pkl      # 06:00-11:59 UTC
│       ├── 20250906T12.pkl      # 12:00-17:59 UTC
│       └── 20250906T18.pkl      # 18:00-23:59 UTC
├── asteroids/                   # Asteroids
│   └── lat+52.5200_lon+13.4050_el+0040/
│       ├── 20250906T00.pkl      # Hourly buckets
│       ├── 20250906T01.pkl
│       └── ...
├── comets/                      # Comets
│   └── lat+52.5200_lon+13.4050_el+0040/
│       ├── 20250906T00.pkl      # Hourly buckets
│       ├── 20250906T01.pkl
│       └── ...
├── asteroids_dataframe.pkl     # Global asteroid catalog
├── comets_dataframe.pkl        # Global comet catalog
├── MPCORB.DAT                  # Minor Planet Center data
└── CometEls.txt                # Comet elements
```

## Location Normalization

### Location Key Format
```
lat{±DD.DDDD}_lon{±DD.DDDD}_el{±DDDDD}
```

**Example:** `lat+52.5200_lon+13.4050_el+0040`

### Normalization Rules
```python
# cache_utils.py: normalize_location()
lat_n = round(lat, 4)           # 4 decimal places (~11m accuracy)
lon_n = round(lon, 4)           # 4 decimal places (~11m accuracy)  
elev_n = math.ceil(elev / 10) * 10  # Round up to next 10m
```

**Examples:**
- `405m` → `410m`
- `415m` → `420m`
- `425m` → `430m`

## Time Bucketing

### Bucket Sizes by Data Type

| Data Type | Bucket Size | Reason |
|----------|--------------|-------|
| **celestial** | 6 hours | Slow change in planet positions |
| **asteroids** | 1 hour | Faster movement, more precise tracking |
| **comets** | 1 hour | Faster movement, more precise tracking |

### Bucket Label Format
```
YYYYMMDDTHH
```

**Examples:**
- `20250906T00` = 06.09.2025, 00:00-05:59 UTC (celestial)
- `20250906T13` = 06.09.2025, 13:00-13:59 UTC (asteroids/comets)

### Bucket Calculation
```python
# cache_utils.py: time_bucket_utc()
bucket_hour = (dt.hour // bucket_hours) * bucket_hours
return f"{dt:%Y%m%d}T{bucket_hour:02d}"
```

## Cache File Contents

### Celestial Cache (.pkl)
```python
{
    "time": "2025-09-06T12:00:00+00:00",
    "location": {
        "latitude": 52.5200,
        "longitude": 13.4050, 
        "elevation": 40
    },
    "bodies": {
        "sun": {"alt": 45.2, "az": 180.5, "magnitude": -26.7},
        "moon": {"alt": -12.3, "az": 95.1, "magnitude": -12.1, "phase": 0.85},
        "mercury": {"alt": 5.2, "az": 200.1, "magnitude": 0.1},
        # ... other planets
    },
    "loading": false
}
```

### Asteroids/Comets Cache (.pkl)
```python
[
    {
        "name": "1 Ceres",
        "magnitude": 8.2,
        "alt": 25.5,
        "az": 145.2,
        "rise_time": "2025-09-06T18:30:00+02:00",
        "set_time": "2025-09-07T06:15:00+02:00",
        "transit_time": "2025-09-07T00:22:00+02:00"
    },
    # ... other objects
]
```

## Cache Management

### TTL (Time To Live)

| Cache Type | TTL | Reason |
|-----------|-----|-------|
| **celestial** | 6 hours | Bucket size |
| **asteroids** | 49 hours | Precompute window + buffer |
| **comets** | 49 hours | Precompute window + buffer |
| **dataframes** | 12 hours | Catalog updates |

### Automatic Cleanup
```yaml
# docker-compose.yml
ASCII_SKY_RETENTION_DAYS: 30  # Delete data older than 30 days
```

### Database Configuration
```yaml
# docker-compose.yml
ASTEROID_USE_SQLITE: 1       # Enable SQLite backend for asteroids
COMET_USE_SQLITE: 1          # Enable SQLite backend for comets
CELESTIAL_USE_SQLITE: 1      # Enable SQLite backend for celestial objects
```

## Precompute Worker

### Configuration
```yaml
# docker-compose.yml
ASCII_SKY_PRECOMPUTE_HOURS: 144      # 6 days lead time
ASCII_SKY_PRECOMPUTE_KINDS: celestial,asteroids,comets
ASCII_SKY_PRECOMPUTE_WORKERS: 4      # Parallel threads
ASCII_SKY_ADAPTIVE_WORKERS: 1        # Dynamic scaling
```

### Location Discovery
The worker finds target locations from three sources:

1. **User location** (`settings.get_location()`)
2. **Configured lists** (ENV/file)
3. **Existing caches** (scans `cache/<kind>/*` directories)

### Rolling Window
- **Window:** 144 hours (6 days)
- **Update:** Hourly
- **Strategy:** Forward if `dt >= now`, otherwise backward

## API Integration

### Cache Status Endpoint
```
GET /api/cache_status?lat=52.52&lon=13.41&elevation=35
```

**Response:**
```json
{
    "now_utc": "2025-09-06T12:00:00+00:00",
    "precompute_horizon_hours": 48,
    "window": {
        "start": "2025-09-06T12:00:00+00:00",
        "end": "2025-09-08T12:00:00+00:00"
    },
    "kinds": ["celestial", "asteroids", "comets"],
    "locations": [{
        "latitude": 52.5200,
        "longitude": 13.4050,
        "elevation": 40,
        "loc_key": "lat+52.5200_lon+13.4050_el+0040",
        "counts": {
            "celestial": 8,   # 48h / 6h = 8 Buckets
            "asteroids": 48,  # 48h / 1h = 48 Buckets  
            "comets": 48      # 48h / 1h = 48 Buckets
        },
        "earliest": {
            "celestial": "2025-09-06T12:00:00+00:00",
            "asteroids": "2025-09-06T12:00:00+00:00",
            "comets": "2025-09-06T12:00:00+00:00"
        },
        "latest": {
            "celestial": "2025-09-08T06:00:00+00:00",
            "asteroids": "2025-09-08T11:00:00+00:00", 
            "comets": "2025-09-08T11:00:00+00:00"
        }
    }],
    "totals": {
        "celestial": 8,
        "asteroids": 48,
        "comets": 48
    }
}
```

## Cache Path Generation

### Functions
```python
# cache_utils.py
def build_cache_path(kind, lat, lon, elevation, dt=None, bucket_hours=6):
    lat_n, lon_n, elev_n = normalize_location(lat, lon, elevation)
    loc_key = location_key(lat_n, lon_n, elev_n)
    bucket = time_bucket_utc(dt=dt, bucket_hours=bucket_hours)
    return f"cache/{kind}/{loc_key}/{bucket}.pkl"
```

### Example Call
```python
path = build_cache_path(
    'celestial', 
    52.5200, 13.4050, 35,
    datetime(2025, 9, 6, 14, 30, tzinfo=timezone.utc),
    bucket_hours=6
)
# → "cache/celestial/lat+52.5200_lon+13.4050_el+0040/20250906T12.pkl"
```

## Atomic Write Operations

### Pickle Files
```python
# cache_utils.py: atomic_write_pickle()
def atomic_write_pickle(path, data):
    tmp_path = f"{path}.tmp-{os.getpid()}-{int(time.time())}"
    with open(tmp_path, 'wb') as f:
        pickle.dump(data, f)
    os.replace(tmp_path, path)  # Atomic replacement
```

### SQLite Database
```python
# db_utils.py: db_transaction()
@contextmanager
def db_transaction():
    """Context manager for database transactions with automatic rollback on error."""
    conn = get_db_connection()
    try:
        conn.execute("BEGIN")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
```

**Benefits:**
- No corrupt files or database entries during interruptions
- Thread-safe operations
- Consistent data with transaction support
- Automatic rollback on errors

## Performance Optimizations

### SQLite Optimizations
- Indexed queries for efficient data retrieval
- Prepared statements for repeated operations
- Connection pooling with thread-local storage
- Optimized PRAGMA settings for performance

### Lazy Loading
- Dataframes are loaded only when needed
- In-memory caching for frequently used data

### Parallel Processing
- Multi-threading in the precompute worker
- Adaptive worker scaling based on system load

### Efficient Search
- SQL queries for filtering by magnitude, location, and time
- Hierarchical directory structure (fallback cache)
- Fast location normalization
- Time bucket alignment

## Error Handling

### Cache Miss Strategies
1. **Real-time:** Calculate on-demand and write to cache (both SQLite and pickle)
2. **Simulated-time:** Read only from cache, no fallback
3. **Background:** Trigger precompute for missing time window

### Hybrid Fallback
- Try SQLite first, fall back to pickle files if not found
- Migrate data from pickle to SQLite when encountered
- Consistent cache keys between both systems

### Error Recovery
- Automatically skip on pickle errors or database corruption
- Transaction rollback on database errors
- Recalculate on next access
- Logging for debugging

## Monitoring

### Cache Statistics
- Number of snapshots per location/type
- Time span of available data
- Cache hit/miss rates
- Database size and row counts

### Worker Status
- Precomputation progress
- Processed hours
- Error rate per location/type

### Database Stats API
```python
# From db_utils.py: get_database_stats()
{
    'asteroids_count': 1234,
    'comets_count': 56,
    'positions_count': 4567,
    'comet_positions_count': 890,
    'celestial_snapshots_count': 123,
    'db_size_mb': 42.5,
    'cache_oldest': '2025-09-01T00:00:00+00:00',
    'cache_newest': '2025-09-06T23:00:00+00:00'
}
```
