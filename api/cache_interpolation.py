"""
Cache loading with interpolation support for asteroids and comets.
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from cache_utils import normalize_location, location_key, time_bucket_utc, build_cache_path, read_pickle_if_fresh
from db_utils import get_asteroid_positions, get_comet_positions
from api.interpolation import get_interpolation_buckets, interpolate_object_list


def load_asteroids_with_interpolation(
    lat: float,
    lon: float, 
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    ttl_seconds: int,
    use_sqlite: bool = True,
    disable_pickle: bool = False
) -> Optional[List[Dict[str, Any]]]:
    """
    Load asteroid positions with interpolation between cached buckets.
    
    Args:
        lat, lon, elevation: Observer location
        dt_utc: Target datetime (timezone-aware)
        bucket_hours: Cache bucket size in hours
        ttl_seconds: Cache TTL in seconds
        use_sqlite: Whether to use SQLite backend
        disable_pickle: Whether to disable pickle cache
    
    Returns:
        List of interpolated asteroid dictionaries, or None if no cache available
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    
    # Get surrounding buckets and interpolation factor
    bucket1_dt, bucket2_dt, factor = get_interpolation_buckets(dt_utc, bucket_hours)
    
    # Load data for both buckets
    list1 = _load_asteroid_bucket(lat, lon, elevation, bucket1_dt, bucket_hours, ttl_seconds, use_sqlite, disable_pickle)
    list2 = _load_asteroid_bucket(lat, lon, elevation, bucket2_dt, bucket_hours, ttl_seconds, use_sqlite, disable_pickle)
    
    # If we have both buckets, interpolate
    if list1 and list2:
        return interpolate_object_list(list1, list2, factor)
    
    # Otherwise return whichever bucket we have (or None)
    return list1 or list2


def load_comets_with_interpolation(
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    ttl_seconds: int,
    use_sqlite: bool = True,
    disable_pickle: bool = False
) -> Optional[List[Dict[str, Any]]]:
    """
    Load comet positions with interpolation between cached buckets.
    
    Args:
        lat, lon, elevation: Observer location
        dt_utc: Target datetime (timezone-aware)
        bucket_hours: Cache bucket size in hours
        ttl_seconds: Cache TTL in seconds
        use_sqlite: Whether to use SQLite backend
        disable_pickle: Whether to disable pickle cache
    
    Returns:
        List of interpolated comet dictionaries, or None if no cache available
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    
    # Get surrounding buckets and interpolation factor
    bucket1_dt, bucket2_dt, factor = get_interpolation_buckets(dt_utc, bucket_hours)
    
    # Load data for both buckets
    list1 = _load_comet_bucket(lat, lon, elevation, bucket1_dt, bucket_hours, ttl_seconds, use_sqlite, disable_pickle)
    list2 = _load_comet_bucket(lat, lon, elevation, bucket2_dt, bucket_hours, ttl_seconds, use_sqlite, disable_pickle)
    
    # If we have both buckets, interpolate
    if list1 and list2:
        return interpolate_object_list(list1, list2, factor)
    
    # Otherwise return whichever bucket we have (or None)
    return list1 or list2


def _load_asteroid_bucket(
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    ttl_seconds: int,
    use_sqlite: bool,
    disable_pickle: bool
) -> Optional[List[Dict[str, Any]]]:
    """Load asteroid data for a single time bucket."""
    lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
    loc_key = location_key(lat_norm, lon_norm, elev_norm)
    bucket = time_bucket_utc(dt_utc, bucket_hours)
    
    # Try SQLite first
    if use_sqlite:
        try:
            positions = get_asteroid_positions(loc_key, bucket, ttl_seconds)
            if isinstance(positions, list) and positions:
                return positions
        except Exception:
            pass
    
    # Try pickle cache
    if not disable_pickle:
        try:
            cache_file = build_cache_path('asteroids', lat, lon, elevation, dt=dt_utc, bucket_hours=bucket_hours)
            positions = read_pickle_if_fresh(cache_file, ttl_seconds)
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
    use_sqlite: bool,
    disable_pickle: bool
) -> Optional[List[Dict[str, Any]]]:
    """Load comet data for a single time bucket."""
    lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
    loc_key = location_key(lat_norm, lon_norm, elev_norm)
    bucket = time_bucket_utc(dt_utc, bucket_hours)
    
    # Try SQLite first
    if use_sqlite:
        try:
            positions = get_comet_positions(loc_key, bucket, ttl_seconds)
            if isinstance(positions, list) and positions:
                return positions
        except Exception:
            pass
    
    # Try pickle cache
    if not disable_pickle:
        try:
            cache_file = build_cache_path('comets', lat, lon, elevation, dt=dt_utc, bucket_hours=bucket_hours)
            positions = read_pickle_if_fresh(cache_file, ttl_seconds)
            if isinstance(positions, list) and positions:
                return positions
        except Exception:
            pass
    
    return None
