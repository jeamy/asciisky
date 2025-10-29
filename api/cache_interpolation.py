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
    
    # If we have both buckets, interpolate
    if list1 and list2:
        return interpolate_object_list(list1, list2, factor)
    
    # If only one bucket available:
    if list1 and not list2:
        # Use past bucket - this is safe
        return list1
    
    if list2 and not list1:
        # list1 (past) missing but list2 (future) exists
        # Try to find earlier buckets (up to 6 hours back)
        for hours_back in range(2, 7):
            fallback_bucket_dt = bucket1_dt - timedelta(hours=hours_back * bucket_hours)
            fallback_list = _load_asteroid_bucket(lat, lon, elevation, fallback_bucket_dt, bucket_hours, ttl_seconds, use_postgres)
            if fallback_list:
                # Found an earlier bucket - use it with list2 for interpolation
                logger.info(f"Using fallback bucket for asteroids: {fallback_bucket_dt.isoformat()} + {bucket2_dt.isoformat()}")
                # Calculate new interpolation factor
                total_seconds = (bucket2_dt - fallback_bucket_dt).total_seconds()
                elapsed_seconds = (dt_utc - fallback_bucket_dt).total_seconds()
                new_factor = elapsed_seconds / total_seconds if total_seconds > 0 else 0.0
                new_factor = max(0.0, min(1.0, new_factor))
                return interpolate_object_list(fallback_list, list2, new_factor)
        
        # No earlier bucket found - log warning and use list2
        logger.warning(f"Using future bucket for asteroids (no past data): requested {dt_utc.isoformat()}, using {bucket2_dt.isoformat()}")
        return list2
    
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
    
    # If we have both buckets, interpolate
    if list1 and list2:
        return interpolate_object_list(list1, list2, factor)
    
    # If only one bucket available:
    if list1 and not list2:
        # Use past bucket - this is safe
        return list1
    
    if list2 and not list1:
        # list1 (past) missing but list2 (future) exists
        # Try to find earlier buckets (up to 6 hours back)
        for hours_back in range(2, 7):
            fallback_bucket_dt = bucket1_dt - timedelta(hours=hours_back * bucket_hours)
            fallback_list = _load_comet_bucket(lat, lon, elevation, fallback_bucket_dt, bucket_hours, ttl_seconds, use_postgres)
            if fallback_list:
                # Found an earlier bucket - use it with list2 for interpolation
                logger.info(f"Using fallback bucket for comets: {fallback_bucket_dt.isoformat()} + {bucket2_dt.isoformat()}")
                # Calculate new interpolation factor
                total_seconds = (bucket2_dt - fallback_bucket_dt).total_seconds()
                elapsed_seconds = (dt_utc - fallback_bucket_dt).total_seconds()
                new_factor = elapsed_seconds / total_seconds if total_seconds > 0 else 0.0
                new_factor = max(0.0, min(1.0, new_factor))
                return interpolate_object_list(fallback_list, list2, new_factor)
        
        # No earlier bucket found - log warning and use list2
        logger.warning(f"Using future bucket for comets (no past data): requested {dt_utc.isoformat()}, using {bucket2_dt.isoformat()}")
        return list2
    
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
