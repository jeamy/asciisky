"""
Cache loading with interpolation support for asteroids and comets.
"""
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from api.interpolation import get_interpolation_buckets
from cache_utils import location_key, normalize_location, time_bucket_utc
from db_utils import get_asteroid_positions, get_comet_positions

logger = logging.getLogger(__name__)


def _load_bucket_generic(
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    use_postgres: bool,
    loader_func: Callable
) -> list[dict[str, Any]] | None:
    """Generic bucket loader for asteroids or comets."""
    if not use_postgres:
        return None
    
    lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
    loc_key = location_key(lat_norm, lon_norm, elev_norm)
    bucket = time_bucket_utc(dt_utc, bucket_hours)
    
    try:
        # Position buckets are immutable.  The DB loaders deliberately accept
        # only location and bucket; TTL belongs to dataset management, not to
        # a position lookup.
        positions = loader_func(loc_key, bucket)
        if isinstance(positions, list):
            # An empty list is a valid cached result (no visible objects), not
            # a cache miss.
            return positions
    except (OSError, ValueError):
        logger.exception("Could not load cached position bucket %s", bucket)
    
    return None


def _load_with_interpolation_generic(
    lat: float,
    lon: float, 
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    use_postgres: bool,
    loader_func: Callable,
    object_type: str
) -> list[dict[str, Any]] | None:
    """
    Generic cache loader with bucket selection logic.
    
    Args:
        lat: Latitude
        lon: Longitude
        elevation: Elevation in meters
        dt_utc: Target datetime (UTC)
        bucket_hours: Cache bucket size in hours
        use_postgres: Whether to use PostgreSQL backend
        loader_func: Function to load data (get_asteroid_positions or get_comet_positions)
        object_type: "asteroid" or "comet" for logging
    
    Returns:
        List of object dictionaries, or None if no cache available
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    
    # Get surrounding buckets and interpolation factor
    bucket1_dt, bucket2_dt, factor = get_interpolation_buckets(dt_utc, bucket_hours)
    
    # Optimization: Load bucket2 only if needed
    # If factor < 0.5, we'll use bucket1 anyway, so skip bucket2
    list1 = _load_bucket_generic(lat, lon, elevation, bucket1_dt, bucket_hours, use_postgres, loader_func)
    
    # Only load bucket2 if bucket1 is missing OR factor >= 0.5
    list2 = None
    if list1 is None or factor >= 0.5:
        list2 = _load_bucket_generic(lat, lon, elevation, bucket2_dt, bucket_hours, use_postgres, loader_func)
    
    # Reduce logging verbosity - only log at debug level
    logger.debug(f"{object_type.capitalize()} buckets for {dt_utc.isoformat()}: bucket1={bucket1_dt.isoformat()} ({'found' if list1 is not None else 'missing'}), bucket2={bucket2_dt.isoformat()} ({'found' if list2 is not None else 'missing'}), factor={factor:.3f}")
    
    # DISABLED INTERPOLATION - Using exact buckets only to avoid position inconsistencies
    # If we have both buckets, prefer the closer one instead of interpolation
    if list1 is not None and list2 is not None:
        # Choose the bucket closer to the requested time
        if factor < 0.5:
            logger.debug(f"Using bucket1 (closer): {bucket1_dt.isoformat()}")
            return list1
        else:
            logger.debug(f"Using bucket2 (closer): {bucket2_dt.isoformat()}")
            return list2
    
    # If only one bucket available, use it
    if list1 is not None:
        logger.debug(f"Using only available bucket1: {bucket1_dt.isoformat()}")
        return list1
    
    if list2 is not None:
        # Check if bucket2 is not too far in the future
        time_diff_hours = (bucket2_dt - dt_utc).total_seconds() / 3600
        if time_diff_hours <= 1.0:  # Max 1 hour in future
            logger.debug(f"Using bucket2 (within 1h): {bucket2_dt.isoformat()}")
            return list2
        else:
            logger.debug(f"Bucket2 too far in future ({time_diff_hours:.1f}h), returning None")
            return None
    
    # No buckets available
    return None


def load_asteroids_with_interpolation(
    lat: float,
    lon: float, 
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    use_postgres: bool = True
) -> list[dict[str, Any]] | None:
    """
    Load asteroid positions with interpolation between cached buckets.
    
    Args:
        lat: Latitude
        lon: Longitude
        elevation: Elevation in meters
        dt_utc: Target datetime (UTC)
        bucket_hours: Cache bucket size in hours
        use_postgres: Whether to use PostgreSQL backend
    
    Returns:
        List of interpolated asteroid dictionaries, or None if no cache available
    """
    return _load_with_interpolation_generic(
        lat, lon, elevation, dt_utc, bucket_hours,
        use_postgres, get_asteroid_positions, "asteroid"
    )


def load_comets_with_interpolation(
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    use_postgres: bool = True
) -> list[dict[str, Any]] | None:
    """
    Load comet positions with interpolation between cached buckets.
    
    Args:
        lat: Latitude
        lon: Longitude
        elevation: Elevation in meters
        dt_utc: Target datetime (UTC)
        bucket_hours: Cache bucket size in hours
        use_postgres: Whether to use PostgreSQL backend
    
    Returns:
        List of interpolated comet dictionaries, or None if no cache available
    """
    return _load_with_interpolation_generic(
        lat, lon, elevation, dt_utc, bucket_hours,
        use_postgres, get_comet_positions, "comet"
    )
