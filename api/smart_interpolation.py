"""
Smart Interpolation Framework for Asteroids and Comets
======================================================

Provides adaptive interpolation with on-demand computation fallbacks.
Replaces the disabled interpolation in cache_interpolation.py with
a robust solution that handles missing buckets gracefully.

Features:
- Adaptive interpolation strategies based on bucket availability
- On-demand bucket computation for missing data
- Astronomical corrections for horizon events and magnitude smoothing
- Smart caching of computed buckets
- Comprehensive error handling and logging
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum

# Existing imports
from cache_utils import normalize_location, location_key, time_bucket_utc
from db_utils import get_asteroid_positions, get_comet_positions, store_asteroid_positions, store_comet_positions
from api.interpolation import get_interpolation_buckets, interpolate_object_list
import bright_asteroids
import comets
from api.computation import LOADER, ts, eph

logger = logging.getLogger(__name__)


class InterpolationStrategy(Enum):
    """Available interpolation strategies"""
    NEAREST_BUCKET = "nearest_bucket"      # Current fallback strategy
    SMART_INTERPOLATION = "smart_interpolation"  # New adaptive strategy
    ON_DEMAND_ONLY = "on_demand_only"      # Compute everything on demand


class SmartInterpolationConfig:
    """Configuration for smart interpolation"""
    
    def __init__(self):
        self.enabled = os.getenv('ENABLE_SMART_INTERPOLATION', 'false').lower() == 'true'
        self.on_demand_enabled = os.getenv('INTERPOLATION_ON_DEMAND', 'true').lower() == 'true'
        self.max_future_hours = float(os.getenv('INTERPOLATION_MAX_FUTURE_HOURS', '2.0'))
        self.cache_computed = os.getenv('INTERPOLATION_CACHE_COMPUTED', 'true').lower() == 'true'
        self.strategy = InterpolationStrategy(os.getenv('INTERPOLATION_STRATEGY', 'smart_interpolation'))
        
        logger.info(f"Smart Interpolation Config: enabled={self.enabled}, "
                   f"on_demand={self.on_demand_enabled}, "
                   f"max_future_hours={self.max_future_hours}, "
                   f"strategy={self.strategy.value}")


# Global configuration instance
_config = SmartInterpolationConfig()


def load_asteroids_with_smart_interpolation(
    lat: float,
    lon: float, 
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int = 1,
    ttl_seconds: int = 86400,
    use_postgres: bool = True
) -> Optional[List[Dict[str, Any]]]:
    """
    Load asteroid positions with smart interpolation.
    
    Args:
        lat: Latitude
        lon: Longitude
        elevation: Elevation in meters
        dt_utc: Target datetime (UTC)
        bucket_hours: Cache bucket size in hours
        ttl_seconds: Cache TTL in seconds
        use_postgres: Whether to use PostgreSQL backend
    
    Returns:
        List of interpolated asteroid dictionaries, or None if no data available
    """
    if not _config.enabled:
        # Fallback to original nearest-bucket strategy
        return _load_with_nearest_bucket_asteroids(lat, lon, elevation, dt_utc, bucket_hours, ttl_seconds, use_postgres)
    
    return _load_with_smart_interpolation(
        'asteroids', lat, lon, elevation, dt_utc, bucket_hours, ttl_seconds, use_postgres
    )


def load_comets_with_smart_interpolation(
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int = 1,
    ttl_seconds: int = 86400,
    use_postgres: bool = True
) -> Optional[List[Dict[str, Any]]]:
    """
    Load comet positions with smart interpolation.
    
    Args:
        lat: Latitude
        lon: Longitude
        elevation: Elevation in meters
        dt_utc: Target datetime (UTC)
        bucket_hours: Cache bucket size in hours
        ttl_seconds: Cache TTL in seconds
        use_postgres: Whether to use PostgreSQL backend
    
    Returns:
        List of interpolated comet dictionaries, or None if no data available
    """
    if not _config.enabled:
        # Fallback to original nearest-bucket strategy
        return _load_with_nearest_bucket_comets(lat, lon, elevation, dt_utc, bucket_hours, ttl_seconds, use_postgres)
    
    return _load_with_smart_interpolation(
        'comets', lat, lon, elevation, dt_utc, bucket_hours, ttl_seconds, use_postgres
    )


def _load_with_smart_interpolation(
    object_type: str,
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    ttl_seconds: int,
    use_postgres: bool
) -> Optional[List[Dict[str, Any]]]:
    """
    Core smart interpolation logic with adaptive strategies.
    
    Args:
        object_type: 'asteroids' or 'comets'
        lat, lon, elevation: Location parameters
        dt_utc: Target datetime
        bucket_hours: Cache bucket size
        ttl_seconds: Cache TTL
        use_postgres: Use PostgreSQL backend
    
    Returns:
        Interpolated object list or None
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    
    # Get surrounding buckets and interpolation factor
    bucket1_dt, bucket2_dt, factor = get_interpolation_buckets(dt_utc, bucket_hours)
    
    logger.info(f"Smart interpolation for {object_type} at {dt_utc.isoformat()}: "
               f"bucket1={bucket1_dt.isoformat()}, bucket2={bucket2_dt.isoformat()}, factor={factor:.3f}")
    
    # Load data for both buckets
    list1 = _load_bucket(object_type, lat, lon, elevation, bucket1_dt, bucket_hours, ttl_seconds, use_postgres)
    list2 = _load_bucket(object_type, lat, lon, elevation, bucket2_dt, bucket_hours, ttl_seconds, use_postgres)
    
    # Apply adaptive strategy based on bucket availability
    if _config.strategy == InterpolationStrategy.SMART_INTERPOLATION:
        return _apply_smart_strategy(object_type, lat, lon, elevation, dt_utc, 
                                    bucket1_dt, bucket2_dt, factor, list1, list2)
    elif _config.strategy == InterpolationStrategy.ON_DEMAND_ONLY:
        return _apply_on_demand_strategy(object_type, lat, lon, elevation, dt_utc,
                                        bucket1_dt, bucket2_dt, factor)
    else:
        # Fallback to nearest bucket
        return _apply_nearest_bucket_strategy(list1, list2, factor, bucket2_dt, dt_utc)


def _apply_smart_strategy(
    object_type: str,
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket1_dt: datetime,
    bucket2_dt: datetime,
    factor: float,
    list1: Optional[List[Dict[str, Any]]],
    list2: Optional[List[Dict[str, Any]]]
) -> Optional[List[Dict[str, Any]]]:
    """
    Apply smart interpolation strategy with on-demand computation.
    """
    
    # Case 1: Both buckets available → True interpolation
    if list1 and list2:
        logger.info(f"Both buckets available for {object_type} → performing smart interpolation")
        return _interpolate_objects_smart(object_type, list1, list2, factor, dt_utc, lat, lon, elevation)
    
    # Case 2: Only previous bucket available → Compute future bucket on-demand
    if list1 and not list2 and _config.on_demand_enabled:
        logger.info(f"Only previous bucket available for {object_type} → computing future bucket on-demand")
        list2 = _compute_bucket_on_demand(object_type, lat, lon, elevation, bucket2_dt)
        if list2:
            if _config.cache_computed:
                _store_bucket(object_type, lat, lon, elevation, bucket2_dt, list2)
            return _interpolate_objects_smart(object_type, list1, list2, factor, dt_utc, lat, lon, elevation)
        logger.warning(f"On-demand computation failed for {object_type} future bucket, using previous bucket")
        return list1
    
    # Case 3: Only future bucket available → Compute previous bucket on-demand
    if not list1 and list2 and _config.on_demand_enabled:
        logger.info(f"Only future bucket available for {object_type} → computing previous bucket on-demand")
        list1 = _compute_bucket_on_demand(object_type, lat, lon, elevation, bucket1_dt)
        if list1:
            if _config.cache_computed:
                _store_bucket(object_type, lat, lon, elevation, bucket1_dt, list1)
            return _interpolate_objects_smart(object_type, list1, list2, factor, dt_utc, lat, lon, elevation)
        
        # Fallback: Check if future bucket is within acceptable time range
        time_diff_hours = (bucket2_dt - dt_utc).total_seconds() / 3600
        if time_diff_hours <= _config.max_future_hours:
            logger.info(f"Using future bucket for {object_type} (within {time_diff_hours:.1f}h limit)")
            return list2
        else:
            logger.warning(f"Future bucket too far ahead for {object_type} ({time_diff_hours:.1f}h > {_config.max_future_hours}h)")
            return None
    
    # Case 4: No buckets available → Compute both on-demand
    if not list1 and not list2 and _config.on_demand_enabled:
        logger.info(f"No buckets available for {object_type} → computing both on-demand")
        list1 = _compute_bucket_on_demand(object_type, lat, lon, elevation, bucket1_dt)
        list2 = _compute_bucket_on_demand(object_type, lat, lon, elevation, bucket2_dt)
        
        if list1 and list2:
            if _config.cache_computed:
                _store_bucket(object_type, lat, lon, elevation, bucket1_dt, list1)
                _store_bucket(object_type, lat, lon, elevation, bucket2_dt, list2)
            return _interpolate_objects_smart(object_type, list1, list2, factor, dt_utc, lat, lon, elevation)
        
        # Return whatever we could compute
        return list1 or list2 or None
    
    # Default fallback
    logger.warning(f"No strategy applicable for {object_type}, returning None")
    return None


def _apply_on_demand_strategy(
    object_type: str,
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket1_dt: datetime,
    bucket2_dt: datetime,
    factor: float
) -> Optional[List[Dict[str, Any]]]:
    """
    Apply on-demand only strategy (compute everything fresh).
    """
    logger.info(f"Applying on-demand only strategy for {object_type}")
    
    # Compute both buckets fresh
    list1 = _compute_bucket_on_demand(object_type, lat, lon, elevation, bucket1_dt)
    list2 = _compute_bucket_on_demand(object_type, lat, lon, elevation, bucket2_dt)
    
    if list1 and list2:
        if _config.cache_computed:
            _store_bucket(object_type, lat, lon, elevation, bucket1_dt, list1)
            _store_bucket(object_type, lat, lon, elevation, bucket2_dt, list2)
        return _interpolate_objects_smart(object_type, list1, list2, factor, dt_utc, lat, lon, elevation)
    
    return list1 or list2 or None


def _apply_nearest_bucket_strategy(
    list1: Optional[List[Dict[str, Any]]],
    list2: Optional[List[Dict[str, Any]]],
    factor: float,
    bucket2_dt: datetime,
    dt_utc: datetime
) -> Optional[List[Dict[str, Any]]]:
    """
    Apply original nearest bucket strategy (current behavior).
    """
    # If we have both buckets, prefer the closer one instead of interpolation
    if list1 and list2:
        if factor < 0.5:
            logger.info(f"Using bucket1 (closer): factor={factor:.3f}")
            return list1
        else:
            logger.info(f"Using bucket2 (closer): factor={factor:.3f}")
            return list2
    
    # If only one bucket available, use it
    if list1:
        logger.info(f"Using only available bucket1")
        return list1
    
    if list2:
        # Check if bucket2 is not too far in the future
        time_diff_hours = (bucket2_dt - dt_utc).total_seconds() / 3600
        if time_diff_hours <= _config.max_future_hours:
            logger.info(f"Using bucket2 (within {time_diff_hours:.1f}h)")
            return list2
        else:
            logger.warning(f"Bucket2 too far in future ({time_diff_hours:.1f}h), returning None")
            return None
    
    # No buckets available
    return None


def _load_bucket(
    object_type: str,
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    ttl_seconds: int,
    use_postgres: bool
) -> Optional[List[Dict[str, Any]]]:
    """Load object data for a single time bucket from PostgreSQL."""
    lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
    loc_key = location_key(lat_norm, lon_norm, elev_norm)
    bucket = time_bucket_utc(dt_utc, bucket_hours)
    
    # PostgreSQL only
    if use_postgres:
        try:
            if object_type == 'asteroids':
                positions = get_asteroid_positions(loc_key, bucket, ttl_seconds)
            else:
                positions = get_comet_positions(loc_key, bucket, ttl_seconds)
            
            if isinstance(positions, list) and positions:
                return positions
        except Exception as e:
            logger.error(f"Error loading {object_type} bucket {bucket}: {e}")
    
    return None


def _compute_bucket_on_demand(
    object_type: str,
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime
) -> Optional[List[Dict[str, Any]]]:
    """
    Compute missing bucket on-demand.
    """
    try:
        logger.info(f"Computing {object_type} bucket on-demand for {dt_utc.isoformat()}")
        
        location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        
        if object_type == 'asteroids':
            objects = bright_asteroids.load_bright_asteroids(
                LOADER, ts, eph, location_dict,
                max_magnitude=20.0,
                current_dt=dt_utc
            )
        else:  # comets
            objects = comets.load_comets(
                ts, eph, location_dict,
                max_comets=1000,
                current_dt=dt_utc
            )
        
        logger.info(f"On-demand computation completed: {len(objects) if objects else 0} {object_type}")
        return objects if objects else []
        
    except Exception as e:
        logger.error(f"On-demand {object_type} computation failed: {e}")
        return None


def _store_bucket(
    object_type: str,
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    objects: List[Dict[str, Any]]
) -> None:
    """
    Store computed bucket in cache.
    """
    try:
        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        bucket = time_bucket_utc(dt_utc, 1)
        
        if object_type == 'asteroids':
            store_asteroid_positions(0, loc_key, bucket, lat_norm, lon_norm, elev_norm, objects)
        else:
            store_comet_positions(0, loc_key, bucket, lat_norm, lon_norm, elev_norm, objects)
        
        logger.info(f"Cached {len(objects)} {object_type} for bucket {bucket}")
        
    except Exception as e:
        logger.error(f"Failed to cache {object_type} bucket: {e}")


def _interpolate_objects_smart(
    object_type: str,
    list1: List[Dict[str, Any]],
    list2: List[Dict[str, Any]],
    factor: float,
    target_dt: datetime,
    lat: float = 0.0,
    lon: float = 0.0,
    elevation: float = 0.0
) -> List[Dict[str, Any]]:
    """
    Perform smart interpolation with astronomical corrections.
    """
    try:
        # Base interpolation
        interpolated = interpolate_object_list(list1, list2, factor)
        
        # Apply astronomical corrections with location
        location = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        corrected = []
        for obj in interpolated:
            corrected_obj = _apply_astronomical_corrections(obj, list1, list2, factor, target_dt, location)
            corrected.append(corrected_obj)
        
        logger.info(f"Smart interpolation completed for {object_type}: {len(corrected)} objects")
        return corrected
        
    except Exception as e:
        logger.error(f"Smart interpolation failed for {object_type}: {e}")
        # Fallback to basic interpolation
        return interpolate_object_list(list1, list2, factor)


def _apply_astronomical_corrections(
    obj: Dict[str, Any],
    list1: List[Dict[str, Any]],
    list2: List[Dict[str, Any]],
    factor: float,
    target_dt: datetime,
    location: Dict[str, float]
) -> Dict[str, Any]:
    """
    Apply astronomical corrections to interpolated object.
    Uses the dedicated astronomical_corrections module.
    """
    try:
        from api.astronomical_corrections import apply_astronomical_corrections
        
        result = apply_astronomical_corrections(obj, list1, list2, factor, target_dt, location)
        return result.corrected_object
        
    except Exception as e:
        logger.error(f"Astronomical corrections failed for {obj.get('name')}: {e}")
        # Fallback: return uncorrected object
        return obj


# Removed duplicate functions - now using astronomical_corrections module:
# - _is_horizon_crossing() → use astronomical_corrections.py
# - _correct_horizon_crossing() → use astronomical_corrections.py
# - _smooth_magnitude_interpolation() → use astronomical_corrections.py
# - _find_object_by_name() → use astronomical_corrections.py


def _load_with_nearest_bucket_asteroids(
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    ttl_seconds: int,
    use_postgres: bool
) -> Optional[List[Dict[str, Any]]]:
    """Fallback to original nearest bucket strategy for asteroids."""
    # Import here to avoid circular imports
    from api.cache_interpolation import load_asteroids_with_interpolation
    return load_asteroids_with_interpolation(lat, lon, elevation, dt_utc, bucket_hours, ttl_seconds, use_postgres)


def _load_with_nearest_bucket_comets(
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    ttl_seconds: int,
    use_postgres: bool
) -> Optional[List[Dict[str, Any]]]:
    """Fallback to original nearest bucket strategy for comets."""
    # Import here to avoid circular imports
    from api.cache_interpolation import load_comets_with_interpolation
    return load_comets_with_interpolation(lat, lon, elevation, dt_utc, bucket_hours, ttl_seconds, use_postgres)


def get_interpolation_config() -> SmartInterpolationConfig:
    """Get current interpolation configuration."""
    return _config


def reload_interpolation_config():
    """Reload interpolation configuration from environment."""
    global _config
    _config = SmartInterpolationConfig()
    logger.info(f"Smart interpolation config reloaded: {_config.strategy.value}")
