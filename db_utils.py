"""
PostgreSQL database utilities for AsciiSky astronomical data caching.
Provides efficient storage and retrieval of asteroid orbital data and computed positions.
Multi-host compatible.
"""
import psycopg2
import psycopg2.extras
import pickle
import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager
import threading

# PostgreSQL configuration from environment
POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.environ.get('POSTGRES_PORT', '5432'))
POSTGRES_DB = os.environ.get('POSTGRES_DB', 'asciisky')
POSTGRES_USER = os.environ.get('POSTGRES_USER', 'asciisky')
POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'changeme')

# Thread-local storage for database connections
_thread_local = threading.local()

def get_db_connection():
    """Get thread-local PostgreSQL connection."""
    if not hasattr(_thread_local, 'connection') or _thread_local.connection is None or _thread_local.connection.closed:
        _thread_local.connection = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        _thread_local.connection.autocommit = False
    return _thread_local.connection

@contextmanager
def db_transaction():
    """Context manager for PostgreSQL transactions."""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

def close_db_connection():
    """Close thread-local PostgreSQL connection."""
    if hasattr(_thread_local, 'connection') and _thread_local.connection is not None:
        try:
            _thread_local.connection.close()
        except Exception:
            pass
        _thread_local.connection = None

# ===== Asteroid Functions =====

def store_asteroid_dataframe(df_pickle: bytes) -> None:
    """Store asteroid DataFrame in FILESYSTEM (not PostgreSQL - too large for DB!)."""
    import os
    from data_paths import DATA_DIR
    
    # Store in filesystem instead of PostgreSQL to avoid OOM killer
    cache_file = os.path.join(DATA_DIR, 'asteroid_dataframe.pkl')
    with open(cache_file, 'wb') as f:
        f.write(df_pickle)
    
    logger.info(f"Stored asteroid DataFrame in filesystem: {cache_file} ({len(df_pickle) / 1024 / 1024:.1f} MB)")

def get_asteroid_dataframe(max_age_seconds: int = 49 * 3600) -> Optional[bytes]:
    """Retrieve cached asteroid DataFrame from FILESYSTEM (not PostgreSQL)."""
    import os
    from data_paths import DATA_DIR
    
    cache_file = os.path.join(DATA_DIR, 'asteroid_dataframe.pkl')
    
    # Check if file exists and is recent enough
    if not os.path.exists(cache_file):
        return None
    
    file_age = time.time() - os.path.getmtime(cache_file)
    if file_age > max_age_seconds:
        logger.warning(f"Asteroid DataFrame cache too old ({file_age / 3600:.1f}h > {max_age_seconds / 3600:.1f}h)")
        return None
    
    with open(cache_file, 'rb') as f:
        df_pickle = f.read()
    
    logger.info(f"Loaded asteroid DataFrame from filesystem: {len(df_pickle) / 1024 / 1024:.1f} MB")
    return df_pickle

def store_asteroid_positions(asteroid_id: int, location_key: str, time_bucket: str,
                                observer_lat: float, observer_lon: float, observer_elevation: float,
                                position_data: List[Dict]) -> None:
    """Store computed asteroid positions in PostgreSQL."""
    with db_transaction() as conn:
        cursor = conn.cursor()
        serialized_data = psycopg2.Binary(pickle.dumps(position_data))
        
        cursor.execute("""
            INSERT INTO cached_positions (
                object_type, object_id, location_key, time_bucket,
                observer_lat, observer_lon, observer_elevation,
                computed_at, position_data
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (object_type, location_key, time_bucket)
            DO NOTHING
        """, (
            'asteroid', asteroid_id, location_key, time_bucket,
            observer_lat, observer_lon, observer_elevation,
            datetime.now(timezone.utc), serialized_data
        ))

def get_asteroid_positions(location_key: str, time_bucket: str,
                              max_age_seconds: int = None) -> Optional[List[Dict]]:
    """
    Retrieve cached asteroid positions from PostgreSQL.
    
    Note: Positions for a specific time_bucket are immutable and can be cached indefinitely.
    The max_age_seconds parameter is deprecated and ignored.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Positions for a specific time_bucket are immutable - no TTL needed!
    # We simply retrieve the most recent calculation for this location/time combination
    cursor.execute("""
        SELECT position_data FROM cached_positions
        WHERE object_type = 'asteroid'
          AND location_key = %s
          AND time_bucket = %s
        ORDER BY computed_at DESC LIMIT 1
    """, (location_key, time_bucket))
    
    row = cursor.fetchone()
    if row and row['position_data']:
        return pickle.loads(bytes(row['position_data']))
    return None

# ===== Comet Functions =====

def store_comet_dataframe(df_pickle: bytes) -> None:
    """Store comet DataFrame in FILESYSTEM (not PostgreSQL - too large for DB!)."""
    import os
    from data_paths import DATA_DIR
    
    # Store in filesystem instead of PostgreSQL to avoid OOM killer
    cache_file = os.path.join(DATA_DIR, 'comet_dataframe.pkl')
    with open(cache_file, 'wb') as f:
        f.write(df_pickle)
    
    logger.info(f"Stored comet DataFrame in filesystem: {cache_file} ({len(df_pickle) / 1024 / 1024:.1f} MB)")

def get_comet_dataframe(max_age_seconds: int = 49 * 3600) -> Optional[bytes]:
    """Retrieve cached comet DataFrame from FILESYSTEM (not PostgreSQL)."""
    import os
    from data_paths import DATA_DIR
    
    cache_file = os.path.join(DATA_DIR, 'comet_dataframe.pkl')
    
    # Check if file exists and is recent enough
    if not os.path.exists(cache_file):
        return None
    
    file_age = time.time() - os.path.getmtime(cache_file)
    if file_age > max_age_seconds:
        logger.warning(f"Comet DataFrame cache too old ({file_age / 3600:.1f}h > {max_age_seconds / 3600:.1f}h)")
        return None
    
    with open(cache_file, 'rb') as f:
        df_pickle = f.read()
    
    logger.info(f"Loaded comet DataFrame from filesystem: {len(df_pickle) / 1024 / 1024:.1f} MB")
    return df_pickle

def get_comets_by_magnitude(max_absolute_mag: float) -> List[Dict]:
    """Get comets filtered by magnitude from PostgreSQL."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, designation, m1_mag, orbit_data
        FROM comet_elements
        WHERE m1_mag <= %s
        ORDER BY m1_mag ASC
    """, (max_absolute_mag,))
    
    return [dict(row) for row in cursor.fetchall()]

def store_comet_positions(comet_id: int, location_key: str, time_bucket: str,
                             observer_lat: float, observer_lon: float, observer_elevation: float,
                             position_data: List[Dict]) -> None:
    """Store computed comet positions in PostgreSQL."""
    with db_transaction() as conn:
        cursor = conn.cursor()
        serialized_data = psycopg2.Binary(pickle.dumps(position_data))
        
        cursor.execute("""
            INSERT INTO cached_positions (
                object_type, object_id, location_key, time_bucket,
                observer_lat, observer_lon, observer_elevation,
                computed_at, position_data
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (object_type, location_key, time_bucket)
            DO NOTHING
        """, (
            'comet', comet_id, location_key, time_bucket,
            observer_lat, observer_lon, observer_elevation,
            datetime.now(timezone.utc), serialized_data
        ))

def get_comet_positions(location_key: str, time_bucket: str,
                           max_age_seconds: int = None) -> Optional[List[Dict]]:
    """
    Retrieve cached comet positions from PostgreSQL.
    
    Note: Positions for a specific time_bucket are immutable and can be cached indefinitely.
    The max_age_seconds parameter is deprecated and ignored.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Positions for a specific time_bucket are immutable - no TTL needed!
    # We simply retrieve the most recent calculation for this location/time combination
    cursor.execute("""
        SELECT position_data FROM cached_positions
        WHERE object_type = 'comet'
          AND location_key = %s
          AND time_bucket = %s
        ORDER BY computed_at DESC LIMIT 1
    """, (location_key, time_bucket))
    
    row = cursor.fetchone()
    if row and row['position_data']:
        return pickle.loads(bytes(row['position_data']))
    return None

# ===== Data Update Tracking =====

def record_data_update(update_type: str, status: str, message: str = None) -> None:
    """Record data update in PostgreSQL."""
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO data_updates (update_type, status, message, updated_at)
            VALUES (%s, %s, %s, %s)
        """, (update_type, status, message, datetime.now(timezone.utc)))

def get_last_data_update(update_type: str = None) -> Optional[Dict]:
    """Get last data update from PostgreSQL."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if update_type:
        cursor.execute("""
            SELECT * FROM data_updates
            WHERE update_type = %s
            ORDER BY updated_at DESC LIMIT 1
        """, (update_type,))
    else:
        cursor.execute("""
            SELECT * FROM data_updates
            ORDER BY updated_at DESC LIMIT 1
        """)
    
    row = cursor.fetchone()
    return dict(row) if row else None

def get_database_stats() -> dict:
    """Get database statistics (asteroid/comet DataFrame availability)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if DataFrames exist (not individual elements)
    cursor.execute("SELECT COUNT(*) as count FROM asteroid_dataframes")
    asteroid_df_count = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM comet_dataframes")
    comet_df_count = cursor.fetchone()['count']
    
    return {
        'asteroids_count': asteroid_df_count,
        'comets_count': comet_df_count
    }

# ===== Computation Lock Functions =====

def is_computation_in_progress(computation_key: str) -> bool:
    """Check if a computation is already in progress."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) as count FROM computation_locks
        WHERE lock_key = %s
          AND expires_at > NOW()
    """, (computation_key,))
    
    row = cursor.fetchone()
    return row['count'] > 0 if row else False

def mark_computation_in_progress(computation_key: str, ttl_seconds: int = 300) -> None:
    """Mark a computation as in progress."""
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO computation_locks (lock_key, created_at, expires_at)
            VALUES (%s, NOW(), NOW() + INTERVAL '%s seconds')
            ON CONFLICT (lock_key) DO UPDATE SET
                created_at = NOW(),
                expires_at = NOW() + INTERVAL '%s seconds'
        """, (computation_key, ttl_seconds, ttl_seconds))

def clear_computation_lock(computation_key: str) -> None:
    """Clear a computation lock (called by worker when done)."""
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM computation_locks WHERE lock_key = %s
        """, (computation_key,))

def cleanup_expired_locks() -> int:
    """Remove expired computation locks. Returns number of removed locks."""
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM computation_locks WHERE expires_at < NOW()
        """)
        return cursor.rowcount

