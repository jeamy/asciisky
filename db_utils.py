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
    """Store asteroid DataFrame in PostgreSQL."""
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO asteroid_dataframes (computed_at, dataframe_pickle)
            VALUES (%s, %s)
            ON CONFLICT (id) DO UPDATE SET
                computed_at = EXCLUDED.computed_at,
                dataframe_pickle = EXCLUDED.dataframe_pickle
        """, (datetime.now(timezone.utc), psycopg2.Binary(df_pickle)))

def get_asteroid_dataframe(max_age_seconds: int = 49 * 3600) -> Optional[bytes]:
    """Retrieve cached asteroid DataFrame from PostgreSQL."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cutoff_time = datetime.now(timezone.utc).timestamp() - max_age_seconds
    
    cursor.execute("""
        SELECT dataframe_pickle FROM asteroid_dataframes
        WHERE EXTRACT(EPOCH FROM computed_at) > %s
        ORDER BY computed_at DESC LIMIT 1
    """, (cutoff_time,))
    
    row = cursor.fetchone()
    return bytes(row['dataframe_pickle']) if row else None

def get_asteroids_by_magnitude(max_absolute_mag: float, max_apparent_mag: float) -> List[Dict]:
    """Get asteroids filtered by magnitude from PostgreSQL."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, designation, h_mag, orbit_data
        FROM asteroid_elements
        WHERE h_mag <= %s
        ORDER BY h_mag ASC
    """, (max_absolute_mag,))
    
    return [dict(row) for row in cursor.fetchall()]

def get_asteroid_orbit_data(asteroid_id: int) -> Optional[Any]:
    """Get orbit data for specific asteroid from PostgreSQL."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT orbit_data FROM asteroid_elements
        WHERE id = %s
    """, (asteroid_id,))
    
    row = cursor.fetchone()
    if row and row['orbit_data']:
        return pickle.loads(bytes(row['orbit_data']))
    return None

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
            DO UPDATE SET
                computed_at = EXCLUDED.computed_at,
                position_data = EXCLUDED.position_data
        """, (
            'asteroid', asteroid_id, location_key, time_bucket,
            observer_lat, observer_lon, observer_elevation,
            datetime.now(timezone.utc), serialized_data
        ))

def get_asteroid_positions(location_key: str, time_bucket: str,
                              max_age_seconds: int = 49 * 3600) -> Optional[List[Dict]]:
    """Retrieve cached asteroid positions from PostgreSQL."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cutoff_time = datetime.now(timezone.utc).timestamp() - max_age_seconds
    
    cursor.execute("""
        SELECT position_data FROM cached_positions
        WHERE object_type = 'asteroid'
          AND location_key = %s
          AND time_bucket = %s
          AND EXTRACT(EPOCH FROM computed_at) > %s
        ORDER BY computed_at DESC LIMIT 1
    """, (location_key, time_bucket, cutoff_time))
    
    row = cursor.fetchone()
    if row and row['position_data']:
        return pickle.loads(bytes(row['position_data']))
    return None

# ===== Comet Functions =====

def store_comet_dataframe(df_pickle: bytes) -> None:
    """Store comet DataFrame in PostgreSQL."""
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO comet_dataframes (computed_at, dataframe_pickle)
            VALUES (%s, %s)
            ON CONFLICT (id) DO UPDATE SET
                computed_at = EXCLUDED.computed_at,
                dataframe_pickle = EXCLUDED.dataframe_pickle
        """, (datetime.now(timezone.utc), psycopg2.Binary(df_pickle)))

def get_comet_dataframe(max_age_seconds: int = 49 * 3600) -> Optional[bytes]:
    """Retrieve cached comet DataFrame from PostgreSQL."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cutoff_time = datetime.now(timezone.utc).timestamp() - max_age_seconds
    
    cursor.execute("""
        SELECT dataframe_pickle FROM comet_dataframes
        WHERE EXTRACT(EPOCH FROM computed_at) > %s
        ORDER BY computed_at DESC LIMIT 1
    """, (cutoff_time,))
    
    row = cursor.fetchone()
    return bytes(row['dataframe_pickle']) if row else None

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
            DO UPDATE SET
                computed_at = EXCLUDED.computed_at,
                position_data = EXCLUDED.position_data
        """, (
            'comet', comet_id, location_key, time_bucket,
            observer_lat, observer_lon, observer_elevation,
            datetime.now(timezone.utc), serialized_data
        ))

def get_comet_positions(location_key: str, time_bucket: str,
                           max_age_seconds: int = 3600) -> Optional[List[Dict]]:
    """Retrieve cached comet positions from PostgreSQL."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cutoff_time = datetime.now(timezone.utc).timestamp() - max_age_seconds
    
    cursor.execute("""
        SELECT position_data FROM cached_positions
        WHERE object_type = 'comet'
          AND location_key = %s
          AND time_bucket = %s
          AND EXTRACT(EPOCH FROM computed_at) > %s
        ORDER BY computed_at DESC LIMIT 1
    """, (location_key, time_bucket, cutoff_time))
    
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

