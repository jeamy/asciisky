"""
PostgreSQL database utilities for AsciiSky astronomical data caching.
Provides efficient storage and retrieval of asteroid orbital data and computed positions.
Multi-host compatible.
"""
import hashlib
import json
import logging
import os
import pickle
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

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


def database_target() -> str:
    """Non-sensitive configured database target for diagnostics."""
    return f"{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB} user={POSTGRES_USER}"


def database_identity() -> str:
    """Return the actual PostgreSQL server identity reached by this process."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT current_database() AS database,
                       inet_server_addr()::text AS server_addr,
                       inet_server_port() AS server_port,
                       pg_postmaster_start_time()::text AS server_started
            """)
            row = cursor.fetchone()
        conn.commit()
        return (
            f"{row['server_addr']}:{row['server_port']}/{row['database']} "
            f"started={row['server_started']}"
        )
    except Exception:
        conn.rollback()
        raise

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

def _store_dataframe(filename: str, df_pickle: bytes) -> str:
    """Atomically replace a source dataframe so workers never read a partial file."""
    from data_paths import DATA_DIR, ensure_data_dirs
    ensure_data_dirs()
    cache_file = os.path.join(DATA_DIR, filename)
    fd, temporary_path = tempfile.mkstemp(prefix=f".{filename}-", suffix=".tmp", dir=DATA_DIR)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(df_pickle)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary_path, cache_file)
    except OSError:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise
    return cache_file


def store_asteroid_dataframe(df_pickle: bytes) -> None:
    """Store asteroid DataFrame in the filesystem using an atomic replace."""
    cache_file = _store_dataframe('asteroid_dataframe.pkl', df_pickle)

    logger.info(f"Stored asteroid DataFrame in filesystem: {cache_file} ({len(df_pickle) / 1024 / 1024:.1f} MB)")

def get_asteroid_dataframe(max_age_seconds: int = 49 * 3600) -> bytes | None:
    """Retrieve cached asteroid DataFrame from FILESYSTEM (not PostgreSQL)."""
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

def _store_positions(
    object_type: str,
    object_id: int,
    location_key: str,
    time_bucket: str,
    observer_lat: float,
    observer_lon: float,
    observer_elevation: float,
    position_data: list[dict],
) -> None:
    """Store one immutable position bucket for a supported minor-body type."""
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
            DO UPDATE SET
                observer_lat = EXCLUDED.observer_lat,
                observer_lon = EXCLUDED.observer_lon,
                observer_elevation = EXCLUDED.observer_elevation,
                computed_at = EXCLUDED.computed_at,
                position_data = EXCLUDED.position_data
        """, (
            object_type, object_id, location_key, time_bucket,
            observer_lat, observer_lon, observer_elevation,
            datetime.now(timezone.utc), serialized_data
        ))

def _get_positions(object_type: str, location_key: str, time_bucket: str) -> list[dict] | None:
    """Retrieve an immutable minor-body position bucket, including ``[]``."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Positions for a specific time_bucket are immutable - no TTL needed!
        cursor.execute("""
            SELECT position_data FROM cached_positions
            WHERE object_type = %s
              AND location_key = %s
              AND time_bucket = %s
            ORDER BY computed_at DESC LIMIT 1
        """, (object_type, location_key, time_bucket))

        row = cursor.fetchone()
        if row and row['position_data']:
            return pickle.loads(bytes(row['position_data']))
        return None
    except Exception:
        conn.rollback()
        raise
    finally:
        if not conn.closed:
            conn.commit()


def store_asteroid_positions(
    asteroid_id: int, location_key: str, time_bucket: str,
    observer_lat: float, observer_lon: float, observer_elevation: float,
    position_data: list[dict],
) -> None:
    _store_positions(
        "asteroid", asteroid_id, location_key, time_bucket,
        observer_lat, observer_lon, observer_elevation, position_data,
    )


def get_asteroid_positions(location_key: str, time_bucket: str) -> list[dict] | None:
    return _get_positions("asteroid", location_key, time_bucket)

# ===== Sunpath Functions =====

def store_sunpath_year(location_key: str, year_bucket: str,
                        observer_lat: float, observer_lon: float, observer_elevation: float,
                        sunpath_data: dict[str, Any]) -> None:
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
                      max_age_seconds: int = None) -> dict[str, Any] | None:
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
        if not conn.closed:
            conn.commit()

# ===== Comet Functions =====

def store_comet_dataframe(df_pickle: bytes) -> None:
    """Store comet DataFrame in the filesystem using an atomic replace."""
    cache_file = _store_dataframe('comet_dataframe.pkl', df_pickle)

    logger.info(f"Stored comet DataFrame in filesystem: {cache_file} ({len(df_pickle) / 1024 / 1024:.1f} MB)")

def get_comet_dataframe(max_age_seconds: int = 49 * 3600) -> bytes | None:
    """Retrieve cached comet DataFrame from FILESYSTEM (not PostgreSQL)."""
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

def store_comet_positions(
    comet_id: int, location_key: str, time_bucket: str,
    observer_lat: float, observer_lon: float, observer_elevation: float,
    position_data: list[dict],
) -> None:
    _store_positions(
        "comet", comet_id, location_key, time_bucket,
        observer_lat, observer_lon, observer_elevation, position_data,
    )


def get_comet_positions(location_key: str, time_bucket: str) -> list[dict] | None:
    return _get_positions("comet", location_key, time_bucket)

# ===== Cache Maintenance Functions =====

def cleanup_cached_positions(retention_days: int, object_types: list[str] | None = None) -> int:
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


def invalidate_cached_positions(object_types: list[str]) -> int:
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


def claim_precompute_task(task_key: str, ttl_seconds: int = 86400) -> bool:
    """Atomically reserve a precompute key across coordinator processes.

    Expired claims can be replaced, covering publisher crashes without keeping
    a separate cleanup daemon.
    """
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO precompute_task_claims (task_key, claimed_at, expires_at)
            VALUES (%s, NOW(), NOW() + (%s * INTERVAL '1 second'))
            ON CONFLICT (task_key) DO UPDATE
            SET claimed_at = EXCLUDED.claimed_at,
                expires_at = EXCLUDED.expires_at
            WHERE precompute_task_claims.expires_at <= NOW()
            RETURNING task_key
        """, (task_key, max(1, int(ttl_seconds))))
        return cursor.fetchone() is not None


def release_precompute_task(task_key: str) -> None:
    """Release a persistent precompute publication claim."""
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM precompute_task_claims WHERE task_key = %s
        """, (task_key,))

def get_database_stats() -> dict:
    """Get database statistics (asteroid/comet DataFrame availability from filesystem)."""
    from data_paths import DATA_DIR

    asteroid_file = os.path.join(DATA_DIR, 'asteroid_dataframe.pkl')
    comet_file = os.path.join(DATA_DIR, 'comet_dataframe.pkl')

    asteroid_count = 0
    comet_count = 0

    if os.path.exists(asteroid_file):
        try:
            file_age = time.time() - os.path.getmtime(asteroid_file)
            if file_age <= 49 * 3600:
                with open(asteroid_file, 'rb') as f:
                    df = pickle.loads(f.read())
                asteroid_count = len(df) if df is not None else 0
        except Exception:
            pass

    if os.path.exists(comet_file):
        try:
            file_age = time.time() - os.path.getmtime(comet_file)
            if file_age <= 49 * 3600:
                with open(comet_file, 'rb') as f:
                    df = pickle.loads(f.read())
                comet_count = len(df) if df is not None else 0
        except Exception:
            pass

    return {
        'asteroids_count': asteroid_count,
        'comets_count': comet_count
    }

# ===== User Settings Functions =====

def get_user_settings(user_id: int) -> dict[str, Any] | None:
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
    except Exception:
        conn.rollback()
        raise
    finally:
        if not conn.closed:
            conn.commit()


def save_user_settings(user_id: int, settings: dict[str, Any]) -> None:
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


def get_all_user_locations() -> list[dict[str, Any]]:
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

        locations: list[dict[str, Any]] = []
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
    except Exception:
        conn.rollback()
        raise
    finally:
        if not conn.closed:
            conn.commit()

# ===== Computation Lock Functions =====

def _advisory_lock_id(computation_key: str) -> int:
    """Generate a stable, process-independent advisory lock ID from a string key."""
    h = hashlib.md5(computation_key.encode('utf-8')).digest()
    return int.from_bytes(h[:4], 'big') & 0x7FFFFFFF


@contextmanager
def computation_lock(computation_key: str, wait_seconds: float = 5.0):
    """Acquire a session advisory lock with a bounded database-side wait.

    PostgreSQL advisory locks do not have a TTL.  Task claims provide the
    durable expiry mechanism; this lock solely serializes overlapping worker
    DB operations.  A bounded wait prevents a stalled peer from blocking a
    consumer indefinitely.
    """
    conn = get_db_connection()
    lock_id = _advisory_lock_id(computation_key)

    try:
        cursor = conn.cursor()
        # ``lock_timeout`` applies to the following blocking lock statement.
        timeout_ms = max(1, int(wait_seconds * 1000))
        cursor.execute("SET LOCAL lock_timeout = %s", (f"{timeout_ms}ms",))
        cursor.execute("SELECT pg_advisory_lock(%s)", (lock_id,))

        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
            conn.commit()
        except Exception:
            conn.rollback()

# Advisory locks are explicitly released above and also disappear when a
# thread-local connection is eventually closed.
