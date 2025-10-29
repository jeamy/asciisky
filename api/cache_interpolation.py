"""
Cache loading with interpolation support for asteroids and comets.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import logging
from cache_utils import normalize_location, location_key, time_bucket_utc
from db_utils import get_asteroid_positions, get_comet_positions
from api.interpolation import get_interpolation_buckets, interpolate_object_list

logger = logging.getLogger(__name__)


def load_asteroids_with_interpolation(
    lat: float,
    lon: float, 
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    ttl_seconds: int,
    use_postgres: bool = True
) -> Optional[List[Dict[str, Any]]]:
    """
    Load asteroid positions with interpolation between cached buckets.
    
    Args:
        lat: Latitude
        lon: Longitude
        elevation: Elevation in meters
        dt_utc: Target datetime (UTC)
        bucket_hours: Cache bucket size in hours
        ttl_seconds: Cache TTL in seconds
        use_postgres: Whether to use PostgreSQL backend
    
    Returns:
        List of interpolated asteroid dictionaries, or None if no cache available
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    
    # Get surrounding buckets and interpolation factor
    bucket1_dt, bucket2_dt, factor = get_interpolation_buckets(dt_utc, bucket_hours)
    
    # Load data for both buckets (PostgreSQL only)
    list1 = _load_asteroid_bucket(lat, lon, elevation, bucket1_dt, bucket_hours, ttl_seconds, use_postgres)
    list2 = _load_asteroid_bucket(lat, lon, elevation, bucket2_dt, bucket_hours, ttl_seconds, use_postgres)
    
    logger.info(f"Asteroid buckets for {dt_utc.isoformat()}: bucket1={bucket1_dt.isoformat()} ({'found' if list1 else 'missing'}), bucket2={bucket2_dt.isoformat()} ({'found' if list2 else 'missing'}), factor={factor:.3f}")
    
    # DISABLED INTERPOLATION - Using exact buckets only to avoid position inconsistencies
    # If we have both buckets, prefer the closer one instead of interpolation
    if list1 and list2:
        # Choose the bucket closer to the requested time
        if factor < 0.5:
            logger.info(f"Using bucket1 (closer): {bucket1_dt.isoformat()}")
            return list1
        else:
            logger.info(f"Using bucket2 (closer): {bucket2_dt.isoformat()}")
            return list2
    
    # If only one bucket available, use it
    if list1:
        logger.info(f"Using only available bucket1: {bucket1_dt.isoformat()}")
        return list1
    
    if list2:
        # Check if bucket2 is not too far in the future
        time_diff_hours = (bucket2_dt - dt_utc).total_seconds() / 3600
        if time_diff_hours <= 1.0:  # Max 1 hour in future
            logger.info(f"Using bucket2 (within 1h): {bucket2_dt.isoformat()}")
            return list2
        else:
            logger.warning(f"Bucket2 too far in future ({time_diff_hours:.1f}h), returning None")
            return None
    
    # No buckets available
    return None


def load_comets_with_interpolation(
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    ttl_seconds: int,
    use_postgres: bool = True
) -> Optional[List[Dict[str, Any]]]:
    """
    Load comet positions with interpolation between cached buckets.
    
    Args:
        lat: Latitude
        lon: Longitude
        elevation: Elevation in meters
        dt_utc: Target datetime (UTC)
        bucket_hours: Cache bucket size in hours
        ttl_seconds: Cache TTL in seconds
        use_postgres: Whether to use PostgreSQL backend
    
    Returns:
        List of interpolated comet dictionaries, or None if no cache available
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    
    # Get surrounding buckets and interpolation factor
    bucket1_dt, bucket2_dt, factor = get_interpolation_buckets(dt_utc, bucket_hours)
    
    # Load data for both buckets (PostgreSQL only)
    list1 = _load_comet_bucket(lat, lon, elevation, bucket1_dt, bucket_hours, ttl_seconds, use_postgres)
    list2 = _load_comet_bucket(lat, lon, elevation, bucket2_dt, bucket_hours, ttl_seconds, use_postgres)
    
    logger.info(f"Comet buckets for {dt_utc.isoformat()}: bucket1={bucket1_dt.isoformat()} ({'found' if list1 else 'missing'}), bucket2={bucket2_dt.isoformat()} ({'found' if list2 else 'missing'}), factor={factor:.3f}")
    
    # DISABLED INTERPOLATION - Using exact buckets only to avoid position inconsistencies
    # If we have both buckets, prefer the closer one instead of interpolation
    if list1 and list2:
        # Choose the bucket closer to the requested time
        if factor < 0.5:
            logger.info(f"Using bucket1 (closer): {bucket1_dt.isoformat()}")
            return list1
        else:
            logger.info(f"Using bucket2 (closer): {bucket2_dt.isoformat()}")
            return list2
    
    # If only one bucket available, use it
    if list1:
        logger.info(f"Using only available bucket1: {bucket1_dt.isoformat()}")
        return list1
    
    if list2:
        # Check if bucket2 is not too far in the future
        time_diff_hours = (bucket2_dt - dt_utc).total_seconds() / 3600
        if time_diff_hours <= 1.0:  # Max 1 hour in future
            logger.info(f"Using bucket2 (within 1h): {bucket2_dt.isoformat()}")
            return list2
        else:
            logger.warning(f"Bucket2 too far in future ({time_diff_hours:.1f}h), returning None")
            return None
    
    # No buckets available
    return None


def _load_asteroid_bucket(
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    ttl_seconds: int,
    use_postgres: bool
) -> Optional[List[Dict[str, Any]]]:
    """Load asteroid data for a single time bucket from PostgreSQL."""
    lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
    loc_key = location_key(lat_norm, lon_norm, elev_norm)
    bucket = time_bucket_utc(dt_utc, bucket_hours)
    
    # PostgreSQL only
    if use_postgres:
        try:
            positions = get_asteroid_positions(loc_key, bucket, ttl_seconds)
            if isinstance(positions, list) and positions:
                return positions
        except Exception:
            pass
    
    return None


def _load_comet_bucket(
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    ttl_seconds: int,
    use_postgres: bool
) -> Optional[List[Dict[str, Any]]]:
    """Load comet data for a single time bucket from PostgreSQL."""
    lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
    loc_key = location_key(lat_norm, lon_norm, elev_norm)
    bucket = time_bucket_utc(dt_utc, bucket_hours)
    
    # PostgreSQL only
    if use_postgres:
        try:
            positions = get_comet_positions(loc_key, bucket, ttl_seconds)
            if isinstance(positions, list) and positions:
                return positions
        except Exception:
            pass
    
    return None
