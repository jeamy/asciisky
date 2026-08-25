"""
Shared utilities for per-location and time-bucketed caching.
- Normalizes observer location (lat/lon to 4 decimals, elevation to nearest 10 m)
- Generates 6-hour UTC time buckets (00, 06, 12, 18)
- Location keys for PostgreSQL cache
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

DEFAULT_BUCKET_HOURS = 6
DEFAULT_TTL_SECONDS = 6 * 3600  # 6 hours


def normalize_location(lat: float, lon: float, elevation: float,
                        latlon_decimals: int = 4, elevation_step: int = 10) -> tuple[float, float, int]:
    """Round lat/lon to 4 decimals (~11 m) and elevation to next higher 10 m step.
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
    elev_n = int(math.ceil(elev_f / float(elevation_step)) * elevation_step)
    return lat_n, lon_n, elev_n


def location_key(lat: float, lon: float, elevation: float) -> str:
    """Build a stable key string from normalized location values.
    Example: 'lat+48.2082_lon+16.3738_el+0170'
    """
    return f"lat{lat:+.4f}_lon{lon:+.4f}_el{int(elevation):+05d}"


def time_bucket_utc(dt: datetime | None = None, bucket_hours: int = DEFAULT_BUCKET_HOURS) -> str:
    """Return a 6-hour UTC bucket label like 'YYYYMMDDTHH'. Aligns HH to 00/06/12/18.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)

    if isinstance(dt, (list, tuple)):
        dt = dt[0] if dt else datetime.now(timezone.utc)

    if not isinstance(dt, datetime):
        raise TypeError(f"time_bucket_utc expected datetime or sequence of datetimes, got {type(dt).__name__}")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    bucket_hour = (dt.hour // bucket_hours) * bucket_hours
    return f"{dt:%Y%m%d}T{bucket_hour:02d}"
