"""
Nearest-bucket cache loading for asteroid and comet positions.

Positions are precomputed per location and UTC bucket.  A request is served
from the bucket closest to the requested instant; the following bucket is
only accepted when it lies at most ``MAX_FUTURE_HOURS`` ahead.  Positions are
never interpolated between buckets (that produced inconsistent rise/set data).
"""
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from cache_utils import location_key, normalize_location, time_bucket_utc

logger = logging.getLogger(__name__)

# How far ahead a following bucket may lie when the current one is missing.
MAX_FUTURE_HOURS = 1.0


def surrounding_buckets(dt: datetime, bucket_hours: int = 1) -> tuple[datetime, datetime, float]:
    """Return the bucket containing ``dt``, the next bucket and the position between them (0..1)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    bucket1 = dt.replace(hour=(dt.hour // bucket_hours) * bucket_hours, minute=0, second=0, microsecond=0)
    bucket2 = bucket1 + timedelta(hours=bucket_hours)
    total = (bucket2 - bucket1).total_seconds()
    factor = (dt - bucket1).total_seconds() / total if total > 0 else 0.0
    return bucket1, bucket2, max(0.0, min(1.0, factor))


def _load_bucket_generic(
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    loader_func: Callable,
) -> list[dict[str, Any]] | None:
    """Load one bucket; ``[]`` is a valid cached result, ``None`` a miss."""
    lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
    loc_key = location_key(lat_norm, lon_norm, elev_norm)
    bucket = time_bucket_utc(dt_utc, bucket_hours)
    try:
        positions = loader_func(loc_key, bucket)
        if isinstance(positions, list):
            return positions
    except (OSError, ValueError):
        logger.exception("Could not load cached position bucket %s", bucket)
    return None


def load_nearest_bucket(
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    loader_func: Callable,
) -> list[dict[str, Any]] | None:
    """Return the cached list of the bucket nearest to ``dt_utc`` or ``None``."""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    bucket1_dt, bucket2_dt, factor = surrounding_buckets(dt_utc, bucket_hours)

    list1 = _load_bucket_generic(lat, lon, elevation, bucket1_dt, bucket_hours, loader_func)
    # The following bucket is only needed when it is nearer or the first is missing.
    list2 = None
    if list1 is None or factor >= 0.5:
        list2 = _load_bucket_generic(lat, lon, elevation, bucket2_dt, bucket_hours, loader_func)

    if list1 is not None and list2 is not None:
        return list2 if factor >= 0.5 else list1
    if list1 is not None:
        return list1
    if list2 is not None:
        ahead_hours = (bucket2_dt - dt_utc).total_seconds() / 3600
        if ahead_hours <= MAX_FUTURE_HOURS:
            return list2
    return None

