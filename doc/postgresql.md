# PostgreSQL Database Documentation

ASCII Sky uses PostgreSQL for efficient storage and retrieval of astronomical data, providing multi-host capability and better concurrency than SQLite.

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

### 2. `asteroid_dataframes`

Stores pickled asteroid DataFrames from MPC.

```sql
CREATE TABLE IF NOT EXISTS asteroid_dataframes (
    id SERIAL PRIMARY KEY,
    data_pickle BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### 3. `comet_dataframes`

Stores pickled comet DataFrames from MPC.

```sql
CREATE TABLE IF NOT EXISTS comet_dataframes (
    id SERIAL PRIMARY KEY,
    data_pickle BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### 4. `cached_positions`

Caches computed positions for asteroids, comets, and celestial bodies.

```sql
CREATE TABLE IF NOT EXISTS cached_positions (
    id SERIAL PRIMARY KEY,
    object_type VARCHAR(20) NOT NULL,
    object_id VARCHAR(100),
    location_key VARCHAR(100) NOT NULL,
    time_bucket VARCHAR(20) NOT NULL,
    position_data BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    UNIQUE(object_type, object_id, location_key, time_bucket)
)
```

### 5. `data_updates`

Tracks data update operations (asteroid/comet data downloads).

```sql
CREATE TABLE IF NOT EXISTS data_updates (
    id SERIAL PRIMARY KEY,
    update_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

## Indexes

The following indexes are created to optimize query performance:

```sql
CREATE INDEX idx_cached_positions_lookup 
    ON cached_positions(object_type, location_key, time_bucket);
CREATE INDEX idx_cached_positions_expires 
    ON cached_positions(expires_at);
CREATE INDEX idx_data_updates_type 
    ON data_updates(update_type, created_at DESC);
```

## Database Configuration

The PostgreSQL database is configured with the following settings:

```python
# Connection pooling
min_connections = 1
max_connections = 20

# Timeouts
connect_timeout = 10
command_timeout = 300  # 5 minutes for long computations

# Multi-Host
# All workers (main, rabbit-b, rabbit-c) connect to central PostgreSQL
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'postgres')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5432))
```

## Key Functions

### Connection Management

- `get_db_connection()`: Returns a thread-local database connection with proper configuration
- `db_transaction()`: Context manager for database transactions with automatic rollback on error

### Schema Management

- `init_database()`: Initializes database schema if it doesn't exist
- `create_schema()`: Creates database tables and indexes

### DataFrame Functions

- `store_asteroid_dataframe(df_pickle)`: Stores pickled asteroid DataFrame
- `get_asteroid_dataframe(max_age_seconds)`: Retrieves asteroid DataFrame if fresh
- `store_comet_dataframe(df_pickle)`: Stores pickled comet DataFrame
- `get_comet_dataframe(max_age_seconds)`: Retrieves comet DataFrame if fresh

### Position Cache Functions

- `store_asteroid_positions(asteroid_id, location_key, time_bucket, ...)`: Stores computed positions
- `get_asteroid_positions(location_key, time_bucket, max_age_seconds)`: Retrieves cached positions
- `store_comet_positions(comet_id, location_key, time_bucket, ...)`: Stores computed positions
- `get_comet_positions(location_key, time_bucket, max_age_seconds)`: Retrieves cached positions

### Data Update Tracking

- `record_data_update(update_type, status, message)`: Records data update operations
- `get_last_data_update(update_type)`: Gets last update timestamp for a data type

### Maintenance Functions

- `cleanup_old_positions(retention_days)`: Removes expired cache entries
- `get_database_stats()`: Gets database statistics for monitoring

## Cache Keys

- **Location Key**: Normalized format `lat+XX.XXXX_lon+YY.YYYY_el+ZZZZ`
- **Time Bucket**: ISO format with hourly granularity `YYYYMMDDTHH`

## Multi-Host Architecture

PostgreSQL enables multi-host deployment:

- **Main Server** (asciisky.eibrain.org): Runs PostgreSQL container
- **Worker Servers** (rabbit-b/c.eibrain.org): Connect to central PostgreSQL
- **Benefits**:
  - Single source of truth for all data
  - No SQLite file locking issues
  - Better concurrency for multiple workers
  - Centralized data management

## RabbitMQ Integration

PostgreSQL works with RabbitMQ for async computation:

1. **API Request**: Check PostgreSQL cache
2. **Cache Miss**: Publish task to RabbitMQ
3. **Worker**: Compute positions, store in PostgreSQL
4. **Next Request**: Serve from PostgreSQL cache

## Environment Variables

- `ASCII_SKY_RETENTION_DAYS`: Number of days to retain cached data (default: 30)

## Performance Considerations

- PostgreSQL provides significant performance improvements:
  - **Multi-Host**: All workers share same cache
  - **Concurrency**: No file locking issues
  - **Indexes**: Fast location/time lookups
  - **Transactions**: Atomic operations
  - **Scalability**: Handles multiple workers efficiently

## Cache Strategy

- **DataFrames**: Stored as pickled BYTEA (12h TTL)
- **Positions**: Stored as pickled BYTEA (6h TTL)
- **Filtering**: Always cache with mag 20.0, filter in API
- **Cleanup**: Automatic expiration via `expires_at` timestamp
