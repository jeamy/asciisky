"""
Shared utilities for per-location and time-bucketed caching.
- Normalizes observer location (lat/lon to 4 decimals, elevation to nearest 10 m)
- Generates 6-hour UTC time buckets (00, 06, 12, 18)
- Builds cache file paths like cache/<kind>/<loc_key>/<bucket>.pkl
- Provides atomic pickle write and TTL-aware read helpers
"""
from __future__ import annotations

import os
import pickle
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

CACHE_ROOT = "cache"
DEFAULT_BUCKET_HOURS = 6
DEFAULT_TTL_SECONDS = 6 * 3600  # 6 hours


def normalize_location(lat: float, lon: float, elevation: float,
                        latlon_decimals: int = 4, elevation_step: int = 10) -> Tuple[float, float, int]:
    """Round lat/lon to 4 decimals (~11 m) and elevation to nearest 10 m.
    Returns (lat_norm, lon_norm, elev_norm_int).
    """
    try:
        lat_f = float(lat)
        lon_f = float(lon)
        elev_f = float(elevation)
    except Exception:
        lat_f, lon_f, elev_f = 0.0, 0.0, 0.0
    lat_n = round(lat_f, latlon_decimals)
    lon_n = round(lon_f, latlon_decimals)
    elev_n = int(round(elev_f / float(elevation_step)) * elevation_step)
    return lat_n, lon_n, elev_n


def location_key(lat: float, lon: float, elevation: float) -> str:
    """Build a stable key string from normalized location values.
    Example: 'lat+48.2082_lon+16.3738_el+0170'
    """
    return f"lat{lat:+.4f}_lon{lon:+.4f}_el{int(elevation):+05d}"


def time_bucket_utc(dt: Optional[datetime] = None, bucket_hours: int = DEFAULT_BUCKET_HOURS) -> str:
    """Return a 6-hour UTC bucket label like 'YYYYMMDDTHH'. Aligns HH to 00/06/12/18.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    bucket_hour = (dt.hour // bucket_hours) * bucket_hours
    return f"{dt:%Y%m%d}T{bucket_hour:02d}"


def cache_path(kind: str, loc_key: str, bucket: str) -> str:
    """Build cache path for a given kind ('comets' or 'asteroids'), location key, and bucket label."""
    return os.path.join(CACHE_ROOT, kind, loc_key, f"{bucket}.pkl")


def build_cache_path(kind: str, lat: float, lon: float, elevation: float,
                     dt: Optional[datetime] = None, bucket_hours: int = DEFAULT_BUCKET_HOURS) -> str:
    lat_n, lon_n, elev_n = normalize_location(lat, lon, elevation)
    loc_key = location_key(lat_n, lon_n, elev_n)
    bucket = time_bucket_utc(dt=dt, bucket_hours=bucket_hours)
    return cache_path(kind, loc_key, bucket)


def _is_fresh(path: str, max_age_seconds: int) -> bool:
    try:
        mtime = os.path.getmtime(path)
        age = datetime.now().timestamp() - mtime
        return age < max_age_seconds
    except Exception:
        return False


def read_pickle_if_fresh(path: str, max_age_seconds: int = DEFAULT_TTL_SECONDS) -> Optional[Any]:
    """Return unpickled object if file exists and is fresh according to TTL, else None."""
    if not os.path.exists(path):
        return None
    if not _is_fresh(path, max_age_seconds):
        return None
    try:
        with open(path, 'rb') as f:
            return pickle.load(f)
    except Exception:
        return None


def atomic_write_pickle(path: str, data: Any) -> None:
    """Atomically write pickle file by writing to a temp file and os.replace()."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp-{os.getpid()}-{int(datetime.now().timestamp())}"
    with open(tmp_path, 'wb') as f:
        pickle.dump(data, f)
    os.replace(tmp_path, path)
