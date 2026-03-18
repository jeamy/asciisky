"""
PostgreSQL database utilities for AsciiSky astronomical data caching.
Provides efficient storage and retrieval of asteroid orbital data and computed positions.
Multi-host compatible.
"""
import psycopg
from psycopg.rows import dict_row
import pickle
import json
import os
import time
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager
import threading

try:
    # Optional import; used only for cache versioning of sunpath data.
    from api.computation import SUNPATH_VERSION as CURRENT_SUNPATH_VERSION
except Exception:  # pragma: no cover - defensive fallback if computation import fails
    CURRENT_SUNPATH_VERSION = None

# Logger setup
logger = logging.getLogger(__name__)

# PostgreSQL configuration from environment
POSTGRES_HOST = os.environ.get('POSTGRES_HOST', '127.0.0.1')
POSTGRES_PORT = int(os.environ.get('POSTGRES_PORT', '5432'))
POSTGRES_DB = os.environ.get('POSTGRES_DB', 'asciisky')
POSTGRES_USER = os.environ.get('POSTGRES_USER', 'asciisky')
POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'changeme')

# Thread-local storage for database connections
_thread_local = threading.local()

def get_db_connection():
    """Get thread-local PostgreSQL connection."""
    if not hasattr(_thread_local, 'connection') or _thread_local.connection is None or _thread_local.connection.closed:
        _thread_local.connection = psycopg.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            row_factory=dict_row,
            autocommit=False
        )
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
        serialized_data = pickle.dumps(position_data)
        
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
    try:
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
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

# ===== Sunpath Functions =====

def store_sunpath_year(location_key: str, year_bucket: str,
                        observer_lat: float, observer_lon: float, observer_elevation: float,
                        sunpath_data: Dict[str, Any]) -> None:
    """Store yearly sunpath data in PostgreSQL cached_positions.

    Uses object_type='sunpath' and the year (as string) as time_bucket, so the
    combination (object_type, location_key, time_bucket) stays unique just like
    for asteroid/comet buckets.
    """
    with db_transaction() as conn:
        cursor = conn.cursor()
        serialized_data = pickle.dumps(sunpath_data)

        cursor.execute("""
            INSERT INTO cached_positions (
                object_type, object_id, location_key, time_bucket,
                observer_lat, observer_lon, observer_elevation,
                computed_at, position_data
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (object_type, location_key, time_bucket)
            DO UPDATE SET
                observer_lat = EXCLUDED.observer_lat,
                observer_lon = EXCLUDED.observer_lon,
                observer_elevation = EXCLUDED.observer_elevation,
                computed_at = EXCLUDED.computed_at,
                position_data = EXCLUDED.position_data
        """, (
            'sunpath', 0, location_key, year_bucket,
            observer_lat, observer_lon, observer_elevation,
            datetime.now(timezone.utc), serialized_data
        ))


def get_sunpath_year(location_key: str, year_bucket: str,
                      max_age_seconds: int = None) -> Optional[Dict[str, Any]]:
    """Retrieve cached yearly sunpath data from PostgreSQL.

    Sunpath for a given (location, year) is effectively immutable, so max_age_seconds
    is optional and normally unused. If provided and the cached entry is older than
    max_age_seconds, the function returns None to force a recomputation.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT position_data, computed_at
            FROM cached_positions
            WHERE object_type = 'sunpath'
              AND location_key = %s
              AND time_bucket = %s
            ORDER BY computed_at DESC
            LIMIT 1
        """, (location_key, year_bucket))

        row = cursor.fetchone()
        if not row or not row.get('position_data'):
            return None

        if max_age_seconds is not None:
            age = (datetime.now(timezone.utc) - row['computed_at']).total_seconds()
            if age > max_age_seconds:
                return None

        data = pickle.loads(bytes(row['position_data']))

        # Optional schema/version guard: invalidate old cached sunpath data when
        # the computation logic changes and SUNPATH_VERSION is bumped.
        if CURRENT_SUNPATH_VERSION is not None:
            try:
                version = data.get("version") if isinstance(data, dict) else None
            except Exception:
                version = None

            if version is None or version < CURRENT_SUNPATH_VERSION:
                return None

        return data
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

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
    
    with open(cache_file, 'rb') as f:
        df_pickle = f.read()
    
    logger.info(f"Loaded comet DataFrame from filesystem: {len(df_pickle) / 1024 / 1024:.1f} MB")
    return df_pickle

def get_comets_by_magnitude(max_absolute_mag: float) -> List[Dict]:
    """Get comets filtered by magnitude from PostgreSQL."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, designation, m1_mag, orbit_data
            FROM comet_elements
            WHERE m1_mag <= %s
            ORDER BY m1_mag ASC
        """, (max_absolute_mag,))
        
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def store_comet_positions(comet_id: int, location_key: str, time_bucket: str,
                             observer_lat: float, observer_lon: float, observer_elevation: float,
                             position_data: List[Dict]) -> None:
    """Store computed comet positions in PostgreSQL."""
    with db_transaction() as conn:
        cursor = conn.cursor()
        serialized_data = pickle.dumps(position_data)
        
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
    try:
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
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

# ===== Cache Maintenance Functions =====

def cleanup_cached_positions(retention_days: int, object_types: Optional[List[str]] = None) -> int:
    """Delete cached position rows older than retention_days.

    Args:
        retention_days: Number of days to keep. Values < 0 are treated as 0.
        object_types: Optional list of object types to restrict the cleanup to.

    Returns:
        Number of deleted rows.
    """
    retention_days = max(int(retention_days), 0)

    with db_transaction() as conn:
        cursor = conn.cursor()

        if object_types:
            cursor.execute("""
                DELETE FROM cached_positions
                WHERE computed_at < NOW() - (%s * INTERVAL '1 day')
                  AND object_type = ANY(%s)
            """, (retention_days, object_types))
        else:
            cursor.execute("""
                DELETE FROM cached_positions
                WHERE computed_at < NOW() - (%s * INTERVAL '1 day')
            """, (retention_days,))

        deleted_rows = cursor.rowcount if cursor.rowcount is not None else 0

    logger.info(
        "Deleted %s cached_positions rows older than %s days%s",
        deleted_rows,
        retention_days,
        f" for {object_types}" if object_types else "",
    )
    return deleted_rows


def invalidate_cached_positions(object_types: List[str]) -> int:
    """Delete cached position rows for the provided object types."""
    if not object_types:
        return 0

    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM cached_positions
            WHERE object_type = ANY(%s)
        """, (object_types,))
        deleted_rows = cursor.rowcount if cursor.rowcount is not None else 0

    logger.info("Invalidated %s cached_positions rows for %s", deleted_rows, object_types)
    return deleted_rows

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
    try:
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
    finally:
        conn.close()

def get_database_stats() -> dict:
    """Get database statistics (asteroid/comet DataFrame availability)."""
    conn = get_db_connection()
    try:
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
    finally:
        conn.close()

# ===== User Settings Functions =====

def get_user_settings(user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve JSONB user settings for a given user_id."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT settings FROM user_settings WHERE user_id = %s",
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        settings_obj = row.get("settings")
        if isinstance(settings_obj, dict):
            return settings_obj
        try:
            return json.loads(settings_obj)
        except Exception:
            return None
    finally:
        conn.close()


def save_user_settings(user_id: int, settings: Dict[str, Any]) -> None:
    """Upsert JSONB user settings for a given user_id."""
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_settings (user_id, settings, last_updated)
            VALUES (%s, %s::jsonb, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET
                settings = EXCLUDED.settings,
                last_updated = EXCLUDED.last_updated
            """,
            (user_id, json.dumps(settings), datetime.now(timezone.utc)),
        )


def get_all_user_locations() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                (settings->'location'->>'latitude')::double precision AS latitude,
                (settings->'location'->>'longitude')::double precision AS longitude,
                (settings->'location'->>'elevation')::double precision AS elevation,
                settings->'location'->>'name' AS name
            FROM user_settings
            WHERE settings ? 'location'
            """
        )

        locations: List[Dict[str, Any]] = []
        for row in cursor.fetchall():
            lat = row.get("latitude")
            lon = row.get("longitude")
            if lat is None or lon is None:
                continue
            elevation = row.get("elevation") if row.get("elevation") is not None else 0.0
            name = row.get("name") or "User Location"
            locations.append(
                {
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "elevation": float(elevation),
                    "name": name,
                }
            )

        return locations
    finally:
        conn.close()

# ===== Computation Lock Functions =====

def is_computation_in_progress(computation_key: str) -> bool:
    """Check if a computation is already in progress using PostgreSQL Advisory Locks."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Try to acquire lock in non-blocking mode
        # Returns 1 if lock acquired, 0 if already locked
        lock_id = hash(computation_key) & 0x7FFFFFFF  # Ensure positive for advisory lock
        cursor.execute("SELECT pg_try_advisory_lock(%s) as acquired", (lock_id,))
        
        result = cursor.fetchone()
        acquired = result['acquired']
        
        if acquired:
            # We got the lock, release it immediately (we were just checking)
            cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
            return False  # No computation in progress
        else:
            return True   # Computation is in progress (lock held by someone else)
    finally:
        conn.close()

@contextmanager
def computation_lock(computation_key: str, ttl_seconds: int = 300):
    """Context manager for PostgreSQL Advisory Locks."""
    conn = get_db_connection()
    lock_id = hash(computation_key) & 0x7FFFFFFF  # Ensure positive
    
    try:
        cursor = conn.cursor()
        # Try to acquire lock (blocking with timeout)
        cursor.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
        
        # Set up automatic cleanup after TTL
        cursor.execute("""
            SELECT pg_notify('computation_lock_timeout', %s)
        """, (f"{computation_key}:{ttl_seconds}",))
        
        yield conn
        
    finally:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id))
        except:
            pass  # Lock might already be released
        finally:
            conn.close()

# Advisory Locks cleanup automatically on connection close
# No manual cleanup needed!
