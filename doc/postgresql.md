# PostgreSQL Database Documentation

ASCII Sky uses PostgreSQL for efficient storage and retrieval of astronomical data, providing multi-host capability and better concurrency than PostgreSQL.

## Database Overview

- **Database**: PostgreSQL 16
- **Host**: Configured via `POSTGRES_HOST` environment variable
- **Port**: 5432 (default)
- **Database Name**: `asciisky`
- **Thread Safety**: Uses thread-local connections with proper configuration
- **Multi-Host**: All workers connect to central PostgreSQL instance

## Schema

The database consists of the following tables:

### 1. `db_metadata`

Stores database metadata including schema version.

```sql
CREATE TABLE IF NOT EXISTS db_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
)
```

### 2. `asteroids`

Stores asteroid orbital data from the Minor Planet Center (MPC).

```sql
CREATE TABLE IF NOT EXISTS asteroids (
    id INTEGER PRIMARY KEY,
    designation TEXT UNIQUE NOT NULL,
    number INTEGER,
    magnitude_h REAL,
    magnitude_g REAL,
    epoch_packed TEXT,
    mean_anomaly REAL,
    argument_perihelion REAL,
    longitude_node REAL,
    inclination REAL,
    eccentricity REAL,
    mean_daily_motion REAL,
    semimajor_axis REAL,
    orbit_data BLOB,  -- Serialized mpcorb row for Skyfield
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### 3. `comets`

Stores comet orbital data from the Minor Planet Center (MPC).

```sql
CREATE TABLE IF NOT EXISTS comets (
    id INTEGER PRIMARY KEY,
    designation TEXT UNIQUE NOT NULL,
    name TEXT,
    magnitude_h REAL,
    magnitude_g REAL,
    epoch_packed TEXT,
    perihelion_distance REAL,
    eccentricity REAL,
    argument_perihelion REAL,
    longitude_node REAL,
    inclination REAL,
    orbit_data BLOB,  -- Serialized comet row for Skyfield
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### 4. `asteroid_positions`

Caches computed asteroid positions for specific locations and time buckets.

```sql
CREATE TABLE IF NOT EXISTS asteroid_positions (
    asteroid_id INTEGER,
    location_key TEXT,
    time_bucket TEXT,
    observer_lat REAL,
    observer_lon REAL,
    observer_elevation REAL,
    computed_at TIMESTAMP,
    position_data BLOB,  -- Serialized position/magnitude/times data
    PRIMARY KEY (asteroid_id, location_key, time_bucket),
    FOREIGN KEY (asteroid_id) REFERENCES asteroids (id)
)
```

### 5. `comet_positions`

Caches computed comet positions for specific locations and time buckets.

```sql
CREATE TABLE IF NOT EXISTS comet_positions (
    comet_id INTEGER,
    location_key TEXT,
    time_bucket TEXT,
    observer_lat REAL,
    observer_lon REAL,
    observer_elevation REAL,
    computed_at TIMESTAMP,
    position_data BLOB,  -- Serialized position/magnitude/times data
    PRIMARY KEY (comet_id, location_key, time_bucket),
    FOREIGN KEY (comet_id) REFERENCES comets (id)
)
```

### 6. `celestial_snapshots`

Caches computed positions for celestial bodies (sun, moon, planets) for specific locations and time buckets.

```sql
CREATE TABLE IF NOT EXISTS celestial_snapshots (
    location_key TEXT,
    time_bucket TEXT,
    observer_lat REAL,
    observer_lon REAL,
    observer_elevation REAL,
    computed_at TIMESTAMP,
    snapshot_data BLOB,  -- Serialized celestial snapshot
    PRIMARY KEY (location_key, time_bucket)
)
```

## Indexes

The following indexes are created to optimize query performance:

```sql
CREATE INDEX IF NOT EXISTS idx_asteroids_designation ON asteroids (designation)
CREATE INDEX IF NOT EXISTS idx_asteroids_magnitude_h ON asteroids (magnitude_h)
CREATE INDEX IF NOT EXISTS idx_comets_designation ON comets (designation)
CREATE INDEX IF NOT EXISTS idx_comets_magnitude_h ON comets (magnitude_h)
CREATE INDEX IF NOT EXISTS idx_positions_location_time ON asteroid_positions (location_key, time_bucket)
CREATE INDEX IF NOT EXISTS idx_positions_computed_at ON asteroid_positions (computed_at)
CREATE INDEX IF NOT EXISTS idx_comet_positions_location_time ON comet_positions (location_key, time_bucket)
CREATE INDEX IF NOT EXISTS idx_comet_positions_computed_at ON comet_positions (computed_at)
CREATE INDEX IF NOT EXISTS idx_celestial_location_time ON celestial_snapshots (location_key, time_bucket)
CREATE INDEX IF NOT EXISTS idx_celestial_computed_at ON celestial_snapshots (computed_at)
```

## Database Configuration

The PostgreSQL database is configured with the following PRAGMA settings for optimal performance:

```sql
PRAGMA synchronous=NORMAL  -- Balance safety/performance
PRAGMA cache_size=10000    -- 10MB cache
PRAGMA temp_store=MEMORY   -- Use RAM for temp tables
```

## Key Functions

### Connection Management

- `get_db_connection()`: Returns a thread-local database connection with proper configuration
- `db_transaction()`: Context manager for database transactions with automatic rollback on error

### Schema Management

- `init_database()`: Initializes database schema if it doesn't exist
- `create_schema()`: Creates database tables and indexes

### Asteroid Functions

- `store_asteroid_dataframe()`: Stores asteroid DataFrame in database
- `get_asteroids_by_magnitude()`: Retrieves asteroids filtered by H magnitude
- `get_asteroid_orbit_data()`: Gets deserialized orbit data for Skyfield calculations
- `store_asteroid_positions()`: Stores computed asteroid positions for a location/time bucket
- `get_asteroid_positions()`: Retrieves cached asteroid positions if fresh enough

### Comet Functions

- `store_comet_dataframe()`: Stores comet DataFrame in database
- `get_comets_by_magnitude()`: Retrieves comets filtered by H magnitude
- `store_comet_positions()`: Stores computed comet positions for a location/time bucket
- `get_comet_positions()`: Retrieves cached comet positions if fresh enough

### Celestial Functions

- `store_celestial_snapshot()`: Stores computed celestial snapshot for a location/time bucket
- `get_celestial_snapshot()`: Retrieves cached celestial snapshot if fresh enough

### Maintenance Functions

- `cleanup_old_positions()`: Removes position cache entries older than retention period
- `get_database_stats()`: Gets database statistics for monitoring
- `migrate_from_pickle_cache()`: Migrates existing pickle cache files to PostgreSQL database

## Cache Keys

- **Location Key**: Normalized format `lat+XX.XXXX_lon+YY.YYYY_el+ZZZZ`
- **Time Bucket**: ISO format with hourly granularity `YYYYMMDDTHH`

## Migration from Pickle Cache

The system includes functionality to migrate data from the legacy pickle cache files to the PostgreSQL database:

1. Asteroid DataFrame migration from `cache/asteroids_dataframe.pkl`
2. Position cache migration from `cache/asteroids/*` structure (planned)

## Environment Variables

- `ASCII_SKY_RETENTION_DAYS`: Number of days to retain cached data (default: 30)

## Performance Considerations

- PostgreSQL provides significant performance improvements over pickle files for:
  - Filtering by magnitude without loading entire datasets
  - Efficient location/time-based lookups
  - Reduced memory usage for large datasets
  - Atomic transactions for data integrity
  - Concurrent access from multiple threads/processes

## Hybrid Cache System

ASCII Sky uses a hybrid cache system:
- PostgreSQL as the primary cache backend
- Pickle files as fallback for backward compatibility

This approach ensures reliable operation while providing significant performance improvements.
