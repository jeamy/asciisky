"""
Interpolation utilities for asteroid and comet positions.
Provides linear interpolation between cached hourly snapshots.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import math


def interpolate_position(pos1: Dict[str, Any], pos2: Dict[str, Any], factor: float) -> Dict[str, Any]:
    """
    Linear interpolation between two position dictionaries.
    
    Args:
        pos1: First position (earlier time)
        pos2: Second position (later time)
        factor: Interpolation factor (0.0 = pos1, 1.0 = pos2)
    
    Returns:
        Interpolated position dictionary
    """
    result = pos1.copy()
    
    # Interpolate numeric fields
    numeric_fields = ['altitude', 'azimuth', 'distance', 'magnitude', 'ra', 'dec']
    for field in numeric_fields:
        if field in pos1 and field in pos2:
            val1 = pos1[field]
            val2 = pos2[field]
            if val1 is not None and val2 is not None:
                # Special handling for azimuth (circular interpolation)
                if field == 'azimuth':
                    result[field] = interpolate_azimuth(val1, val2, factor)
                else:
                    result[field] = val1 + (val2 - val1) * factor
    
    # Keep string fields from pos1 (name, rise/set times, etc.)
    # These don't interpolate meaningfully
    
    # Ensure type and symbol are preserved (prefer pos2 if pos1 doesn't have them)
    if 'type' not in result or result['type'] is None:
        if 'type' in pos2 and pos2['type'] is not None:
            result['type'] = pos2['type']
    if 'symbol' not in result or result['symbol'] is None:
        if 'symbol' in pos2 and pos2['symbol'] is not None:
            result['symbol'] = pos2['symbol']
    
    return result


def interpolate_azimuth(az1: float, az2: float, factor: float) -> float:
    """
    Circular interpolation for azimuth angles (0-360 degrees).
    Handles wrap-around at 0/360 boundary.
    """
    # Normalize to 0-360
    az1 = az1 % 360
    az2 = az2 % 360
    
    # Calculate shortest angular distance
    diff = az2 - az1
    if diff > 180:
        diff -= 360
    elif diff < -180:
        diff += 360
    
    result = (az1 + diff * factor) % 360
    return result


def interpolate_object_list(
    list1: List[Dict[str, Any]], 
    list2: List[Dict[str, Any]], 
    factor: float
) -> List[Dict[str, Any]]:
    """
    Interpolate between two lists of celestial objects.
    Matches objects by name and interpolates their positions.
    
    Args:
        list1: First object list (earlier time)
        list2: Second object list (later time)
        factor: Interpolation factor (0.0 = list1, 1.0 = list2)
    
    Returns:
        List of interpolated objects
    """
    if not list1 or not list2:
        # If either list is empty, return the non-empty one or empty list
        return list1 or list2 or []
    
    # Create lookup by name for list2
    list2_by_name = {obj.get('name'): obj for obj in list2 if 'name' in obj}
    
    result = []
    for obj1 in list1:
        name = obj1.get('name')
        if not name:
            continue
        
        obj2 = list2_by_name.get(name)
        if obj2:
            # Both objects exist - interpolate
            result.append(interpolate_position(obj1, obj2, factor))
        else:
            # Object only in list1 - include as-is
            result.append(obj1.copy())
    
    # Add objects that only exist in list2
    list1_names = {obj.get('name') for obj in list1 if 'name' in obj}
    for obj2 in list2:
        name = obj2.get('name')
        if name and name not in list1_names:
            result.append(obj2.copy())
    
    return result


def get_interpolation_buckets(dt: datetime, bucket_hours: int = 1) -> tuple[datetime, datetime, float]:
    """
    Get the two surrounding time buckets and interpolation factor for a given datetime.
    
    Args:
        dt: Target datetime (must be timezone-aware)
        bucket_hours: Bucket size in hours (default: 1)
    
    Returns:
        Tuple of (bucket1_dt, bucket2_dt, interpolation_factor)
        where factor is 0.0 at bucket1 and 1.0 at bucket2
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Calculate bucket1 (floor to bucket_hours)
    bucket1_hour = (dt.hour // bucket_hours) * bucket_hours
    bucket1 = dt.replace(hour=bucket1_hour, minute=0, second=0, microsecond=0)
    
    # Calculate bucket2 (next bucket)
    bucket2 = bucket1 + timedelta(hours=bucket_hours)
    
    # Calculate interpolation factor
    total_seconds = (bucket2 - bucket1).total_seconds()
    elapsed_seconds = (dt - bucket1).total_seconds()
    factor = elapsed_seconds / total_seconds if total_seconds > 0 else 0.0
    
    # Clamp factor to [0, 1]
    factor = max(0.0, min(1.0, factor))
    
    return bucket1, bucket2, factor
