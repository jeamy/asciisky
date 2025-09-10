"""
SQLite database utilities for AsciiSky astronomical data caching.
Provides efficient storage and retrieval of asteroid orbital data and computed positions.
"""
import sqlite3
import pickle
import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager
import threading

# Database configuration
DB_PATH = "cache/asciisky.db"
DB_VERSION = 2

# Thread-local storage for database connections
_thread_local = threading.local()
_connection_counter = 0
_connection_lock = threading.Lock()

def get_db_connection() -> sqlite3.Connection:
    """Get thread-local database connection with proper configuration."""
    global _connection_counter
    
    if not hasattr(_thread_local, 'connection') or _thread_local.connection is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        # Skip WAL mode in Docker to avoid I/O issues
        conn.execute("PRAGMA synchronous=NORMAL")  # Balance safety/performance
        conn.execute("PRAGMA cache_size=2000")  # Reduce cache size to 2MB
        conn.execute("PRAGMA temp_store=MEMORY")  # Use RAM for temp tables
        _thread_local.connection = conn
        
        # Track connection count for debugging
        with _connection_lock:
            _connection_counter += 1
        
        # Initialize schema if needed
        init_database(conn)
    
    return _thread_local.connection

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

def init_database(conn: sqlite3.Connection):
    """Initialize database schema if not exists."""
    
    # Metadata table for schema versioning
    conn.execute("""
        CREATE TABLE IF NOT EXISTS db_metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Check current schema version
    cursor = conn.execute("SELECT value FROM db_metadata WHERE key = 'version'")
    row = cursor.fetchone()
    current_version = int(row[0]) if row else 0
    
    if current_version < DB_VERSION:
        create_schema(conn)
        conn.execute(
            "INSERT OR REPLACE INTO db_metadata (key, value) VALUES ('version', ?)",
            (str(DB_VERSION),)
        )
        conn.commit()

def create_schema(conn: sqlite3.Connection):
    """Create database schema for asteroid and comet data."""
    
    # Asteroid orbital data table
    conn.execute("""
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
    """)
    
    # Comet orbital data table
    conn.execute("""
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
    """)
    
    # Computed positions cache table (shared for asteroids and comets)
    conn.execute("""
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
    """)
    
    # Comet positions cache table
    conn.execute("""
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
    """)
    
    # Celestial bodies cache table (sun, moon, planets)
    conn.execute("""
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
    """)
    
    # Create indexes for efficient queries
    conn.execute("CREATE INDEX IF NOT EXISTS idx_asteroids_designation ON asteroids (designation)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_asteroids_magnitude_h ON asteroids (magnitude_h)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_comets_designation ON comets (designation)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_comets_magnitude_h ON comets (magnitude_h)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_location_time ON asteroid_positions (location_key, time_bucket)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_computed_at ON asteroid_positions (computed_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_comet_positions_location_time ON comet_positions (location_key, time_bucket)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_comet_positions_computed_at ON comet_positions (computed_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_celestial_location_time ON celestial_snapshots (location_key, time_bucket)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_celestial_computed_at ON celestial_snapshots (computed_at)")

def store_asteroid_dataframe(df) -> int:
    """Store asteroid DataFrame in database, return count of stored records."""
    with db_transaction() as conn:
        stored_count = 0
        
        for index, row in df.iterrows():
            try:
                # Serialize the complete row for Skyfield compatibility
                orbit_data = pickle.dumps(row)
                
                # Convert values to proper types for SQLite
                import pandas as pd
                number = None
                if isinstance(index, (int, float)) and not pd.isna(index):
                    number = int(index)
                elif 'number' in row and not pd.isna(row['number']):
                    number = int(row['number'])
                
                # Handle NaN values properly
                def safe_float(val):
                    return float(val) if not pd.isna(val) else None
                
                def safe_str(val):
                    return str(val) if not pd.isna(val) else ''
                
                conn.execute("""
                    INSERT OR REPLACE INTO asteroids (
                        designation, number, magnitude_h, magnitude_g,
                        epoch_packed, mean_anomaly, argument_perihelion,
                        longitude_node, inclination, eccentricity,
                        mean_daily_motion, semimajor_axis, orbit_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    safe_str(row.get('designation', '')),
                    number,
                    safe_float(row.get('magnitude_H')),
                    safe_float(row.get('magnitude_G')),
                    safe_str(row.get('epoch_packed', '')),
                    safe_float(row.get('mean_anomaly_degrees')),
                    safe_float(row.get('argument_of_perihelion_degrees')),
                    safe_float(row.get('longitude_of_ascending_node_degrees')),
                    safe_float(row.get('inclination_degrees')),
                    safe_float(row.get('eccentricity')),
                    safe_float(row.get('mean_daily_motion_degrees')),
                    safe_float(row.get('semimajor_axis_au')),
                    orbit_data
                ))
                stored_count += 1
                
            except Exception as e:
                print(f"Error storing asteroid {row.get('designation', 'unknown')}: {e}")
                continue
        
        return stored_count

def get_asteroids_by_magnitude(max_h_magnitude: float, limit: int = 1000) -> List[sqlite3.Row]:
    """Retrieve asteroids filtered by H magnitude, ordered by brightness."""
    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT * FROM asteroids 
        WHERE magnitude_h <= ? AND magnitude_h IS NOT NULL
        ORDER BY magnitude_h ASC
        LIMIT ?
    """, (max_h_magnitude, limit))
    
    result = cursor.fetchall()
    cursor.close()
    return result

def get_asteroid_orbit_data(asteroid_id: int) -> Optional[Any]:
    """Get deserialized orbit data for Skyfield calculations."""
    conn = get_db_connection()
    cursor = conn.execute("SELECT orbit_data FROM asteroids WHERE id = ?", (asteroid_id,))
    row = cursor.fetchone()
    cursor.close()
    
    if row and row['orbit_data']:
        return pickle.loads(row['orbit_data'])
    return None

def store_asteroid_positions(asteroid_id: int, location_key: str, time_bucket: str,
                           observer_lat: float, observer_lon: float, observer_elevation: float,
                           position_data: List[Dict]) -> None:
    """Store computed asteroid positions for a location/time bucket."""
    with db_transaction() as conn:
        serialized_data = pickle.dumps(position_data)
        
        conn.execute("""
            INSERT OR REPLACE INTO asteroid_positions (
                asteroid_id, location_key, time_bucket,
                observer_lat, observer_lon, observer_elevation,
                computed_at, position_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(asteroid_id), str(location_key), str(time_bucket),
            float(observer_lat), float(observer_lon), float(observer_elevation),
            datetime.now(timezone.utc).isoformat(), serialized_data
        ))

def get_asteroid_positions(location_key: str, time_bucket: str, 
                         max_age_seconds: int = 49 * 3600) -> Optional[List[Dict]]:
    """Retrieve cached asteroid positions for location/time if fresh enough."""
    conn = get_db_connection()
    
    # Calculate cutoff time
    cutoff_time = datetime.now(timezone.utc).timestamp() - max_age_seconds
    
    cursor = conn.execute("""
        SELECT position_data FROM asteroid_positions
        WHERE location_key = ? AND time_bucket = ?
        AND strftime('%s', computed_at) > ?
    """, (str(location_key), str(time_bucket), str(cutoff_time)))
    
    # Collect all asteroid positions for this location/time
    all_positions = []
    for row in cursor.fetchall():
        if row and row['position_data']:
            positions = pickle.loads(row['position_data'])
            if isinstance(positions, list):
                all_positions.extend(positions)
    
    cursor.close()
    return all_positions if all_positions else None

def cleanup_old_positions(retention_days: int = 30) -> int:
    """Remove position cache entries older than retention period."""
    with db_transaction() as conn:
        cutoff_time = datetime.now(timezone.utc).timestamp() - (retention_days * 24 * 3600)
        
        cursor = conn.execute("""
            DELETE FROM asteroid_positions 
            WHERE strftime('%s', computed_at) < ?
        """, (str(cutoff_time),))
        
        return cursor.rowcount

def store_comet_dataframe(df) -> int:
    """Store comet DataFrame in database, return count of stored records."""
    with db_transaction() as conn:
        stored_count = 0
        
        for index, row in df.iterrows():
            try:
                # Serialize the complete row for Skyfield compatibility
                orbit_data = pickle.dumps(row)
                
                # Convert values to proper types for SQLite
                import pandas as pd
                def safe_float(val):
                    return float(val) if not pd.isna(val) else None
                
                def safe_str(val):
                    return str(val) if not pd.isna(val) else ''
                
                conn.execute("""
                    INSERT OR REPLACE INTO comets (
                        designation, name, magnitude_h, magnitude_g,
                        epoch_packed, perihelion_distance, eccentricity,
                        argument_perihelion, longitude_node, inclination, orbit_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    safe_str(row.get('designation', '')),
                    safe_str(row.get('name', '')),
                    safe_float(row.get('magnitude_H')),
                    safe_float(row.get('magnitude_G')),
                    safe_str(row.get('epoch_packed', '')),
                    safe_float(row.get('perihelion_distance_au')),
                    safe_float(row.get('eccentricity')),
                    safe_float(row.get('argument_of_perihelion_degrees')),
                    safe_float(row.get('longitude_of_ascending_node_degrees')),
                    safe_float(row.get('inclination_degrees')),
                    orbit_data
                ))
                stored_count += 1
                
            except Exception as e:
                print(f"Error storing comet {row.get('designation', 'unknown')}: {e}")
                continue
        
        return stored_count

def get_comets_by_magnitude(max_h_magnitude: float, limit: int = 1000) -> List[sqlite3.Row]:
    """Retrieve comets filtered by H magnitude, ordered by brightness."""
    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT * FROM comets 
        WHERE magnitude_h <= ? AND magnitude_h IS NOT NULL
        ORDER BY magnitude_h ASC
        LIMIT ?
    """, (max_h_magnitude, limit))
    
    result = cursor.fetchall()
    cursor.close()
    return result

def store_comet_positions(comet_id: int, location_key: str, time_bucket: str,
                         observer_lat: float, observer_lon: float, observer_elevation: float,
                         position_data: List[Dict]) -> None:
    """Store computed comet positions for a location/time bucket."""
    with db_transaction() as conn:
        serialized_data = pickle.dumps(position_data)
        
        conn.execute("""
            INSERT OR REPLACE INTO comet_positions (
                comet_id, location_key, time_bucket,
                observer_lat, observer_lon, observer_elevation,
                computed_at, position_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(comet_id), str(location_key), str(time_bucket),
            float(observer_lat), float(observer_lon), float(observer_elevation),
            datetime.now(timezone.utc).isoformat(), serialized_data
        ))

def get_comet_positions(location_key: str, time_bucket: str, 
                       max_age_seconds: int = 49 * 3600) -> Optional[List[Dict]]:
    """Retrieve cached comet positions for location/time if fresh enough."""
    conn = get_db_connection()
    
    # Calculate cutoff time
    cutoff_time = datetime.now(timezone.utc).timestamp() - max_age_seconds
    
    cursor = conn.execute("""
        SELECT position_data FROM comet_positions
        WHERE location_key = ? AND time_bucket = ?
        AND strftime('%s', computed_at) > ?
        LIMIT 1
    """, (str(location_key), str(time_bucket), str(cutoff_time)))
    
    row = cursor.fetchone()
    cursor.close()
    
    if row and row['position_data']:
        return pickle.loads(row['position_data'])
    
    return None

def store_celestial_snapshot(location_key: str, time_bucket: str,
                            observer_lat: float, observer_lon: float, observer_elevation: float,
                            snapshot_data: Dict) -> None:
    """Store computed celestial snapshot for a location/time bucket."""
    with db_transaction() as conn:
        serialized_data = pickle.dumps(snapshot_data)
        
        conn.execute("""
            INSERT OR REPLACE INTO celestial_snapshots (
                location_key, time_bucket,
                observer_lat, observer_lon, observer_elevation,
                computed_at, snapshot_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            str(location_key), str(time_bucket),
            float(observer_lat), float(observer_lon), float(observer_elevation),
            datetime.now(timezone.utc).isoformat(), serialized_data
        ))

def get_celestial_snapshot(location_key: str, time_bucket: str, 
                          max_age_seconds: int = 49 * 3600) -> Optional[Dict]:
    """Retrieve cached celestial snapshot for location/time if fresh enough."""
    conn = get_db_connection()
    
    # Calculate cutoff time
    cutoff_time = datetime.now(timezone.utc).timestamp() - max_age_seconds
    
    cursor = conn.execute("""
        SELECT snapshot_data FROM celestial_snapshots
        WHERE location_key = ? AND time_bucket = ?
        AND strftime('%s', computed_at) > ?
        LIMIT 1
    """, (str(location_key), str(time_bucket), str(cutoff_time)))
    
    row = cursor.fetchone()
    cursor.close()
    
    if row and row['snapshot_data']:
        return pickle.loads(row['snapshot_data'])
    
    return None

def cleanup_old_positions(retention_days: int = 30) -> int:
    """Remove position cache entries older than retention period."""
    with db_transaction() as conn:
        cutoff_time = datetime.now(timezone.utc).timestamp() - (retention_days * 24 * 3600)
        
        # Clean asteroid positions
        cursor = conn.execute("""
            DELETE FROM asteroid_positions 
            WHERE strftime('%s', computed_at) < ?
        """, (str(cutoff_time),))
        
        deleted_count = cursor.rowcount
        
        # Clean comet positions
        cursor = conn.execute("""
            DELETE FROM comet_positions 
            WHERE strftime('%s', computed_at) < ?
        """, (str(cutoff_time),))
        
        deleted_count += cursor.rowcount
        
        # Clean celestial snapshots
        cursor = conn.execute("""
            DELETE FROM celestial_snapshots 
            WHERE strftime('%s', computed_at) < ?
        """, (str(cutoff_time),))
        
        deleted_count += cursor.rowcount
        
        return deleted_count

def get_database_stats() -> Dict[str, Any]:
    """Get database statistics for monitoring."""
    conn = get_db_connection()
    
    stats = {}
    
    # Count asteroids
    cursor = conn.execute("SELECT COUNT(*) as count FROM asteroids")
    stats['asteroids_count'] = cursor.fetchone()['count']
    cursor.close()
    
    # Count comets
    cursor = conn.execute("SELECT COUNT(*) as count FROM comets")
    stats['comets_count'] = cursor.fetchone()['count']
    cursor.close()
    
    # Count position cache entries
    cursor = conn.execute("SELECT COUNT(*) as count FROM asteroid_positions")
    stats['positions_count'] = cursor.fetchone()['count']
    cursor.close()
    
    cursor = conn.execute("SELECT COUNT(*) as count FROM comet_positions")
    stats['comet_positions_count'] = cursor.fetchone()['count']
    cursor.close()
    
    # Count celestial snapshots
    cursor = conn.execute("SELECT COUNT(*) as count FROM celestial_snapshots")
    stats['celestial_snapshots_count'] = cursor.fetchone()['count']
    cursor.close()
    
    # Database file size
    if os.path.exists(DB_PATH):
        stats['db_size_mb'] = os.path.getsize(DB_PATH) / (1024 * 1024)
    
    # Oldest and newest position cache entries
    cursor = conn.execute("""
        SELECT 
            MIN(computed_at) as oldest,
            MAX(computed_at) as newest
        FROM asteroid_positions
    """)
    row = cursor.fetchone()
    stats['cache_oldest'] = row['oldest']
    stats['cache_newest'] = row['newest']
    cursor.close()
    
    # Add connection counter for debugging
    with _connection_lock:
        stats['db_connections'] = _connection_counter
    
    return stats

def migrate_from_pickle_cache() -> Dict[str, int]:
    """Migrate existing pickle cache files to SQLite database."""
    migration_stats = {
        'dataframe_migrated': 0,
        'positions_migrated': 0,
        'errors': 0
    }
    
    # Migrate asteroid DataFrame if exists
    df_cache_file = 'cache/asteroids_dataframe.pkl'
    if os.path.exists(df_cache_file):
        try:
            import pandas as pd
            with open(df_cache_file, 'rb') as f:
                df = pickle.load(f)
            
            count = store_asteroid_dataframe(df)
            migration_stats['dataframe_migrated'] = count
            print(f"Migrated {count} asteroids from DataFrame cache")
            
        except Exception as e:
            print(f"Error migrating DataFrame cache: {e}")
            migration_stats['errors'] += 1
    
    # TODO: Migrate position cache files from cache/asteroids_v2/* structure
    # This would scan the directory structure and convert pickle files to DB entries
    
    return migration_stats


def close_db_connection():
    """Close the thread-local database connection if it exists."""
    if hasattr(_thread_local, 'connection') and _thread_local.connection is not None:
        try:
            _thread_local.connection.close()
            _thread_local.connection = None
        except Exception as e:
            print(f"Error closing database connection: {e}")
