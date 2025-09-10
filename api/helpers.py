from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

from fastapi import Request

async def get_location_from_request(request: Request, lat: float = None, lon: float = None, elevation: float = None) -> Dict[str, Any]:
    """
    Get location data from query params, session, or settings file.
    Priority: query params > session > settings file

    Returns a dict with latitude, longitude, elevation, and optional name.
    """
    try:
        # 1. Try query parameters first
        if lat is not None and lon is not None:
            return {
                "latitude": float(lat),
                "longitude": float(lon),
                "elevation": float(elevation if elevation is not None else 0.0),
                "name": ""
            }

        # 2. Try session
        session = request.session
        if "location" in session:
            try:
                loc = session["location"]
                if isinstance(loc, dict) and "latitude" in loc and "longitude" in loc:
                    return {
                        "latitude": float(loc["latitude"]),
                        "longitude": float(loc["longitude"]),
                        "elevation": float(loc.get("elevation", 0.0)),
                        "name": loc.get("name", "")
                    }
            except Exception:
                pass

        # 3. Fall back to settings file
        import settings as app_settings
        loc = app_settings.get_location()
        if loc and "latitude" in loc and "longitude" in loc:
            return {
                "latitude": float(loc["latitude"]),
                "longitude": float(loc["longitude"]),
                "elevation": float(loc.get("elevation", 0.0)),
                "name": loc.get("name", "")
            }

        # 4. Default to Vienna if all else fails
        return {
            "latitude": 48.2082,
            "longitude": 16.3738,
            "elevation": 171.0,
            "name": "Vienna"
        }
    except Exception as e:
        print(f"Error getting location: {str(e)}")
        return None

def parse_time_param(time_str: Optional[str]) -> datetime:
    """Helper: parse optional ISO 8601 datetime string (supports 'Z') into UTC-aware datetime"""
    if not time_str:
        return datetime.now(timezone.utc)
    try:
        s = time_str.strip()
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        # Fallback to current UTC on parse errors
        return datetime.now(timezone.utc)

def get_location_params(request: Request, lat: float = None, lon: float = None, elevation: float = None) -> Tuple[float, float, float]:
    """
    Unified location parameter resolution for all endpoints.
    Priority: query params > session > settings file
    
    Returns: (latitude, longitude, elevation) as floats
    """
    import settings
    
    # Get defaults from settings and session
    location_settings = settings.get_location()
    session_loc = request.session.get("location", {}) if hasattr(request, "session") else {}
    
    # Resolve parameters with priority order
    resolved_lat = lat if lat is not None else session_loc.get("latitude", location_settings["latitude"])
    resolved_lon = lon if lon is not None else session_loc.get("longitude", location_settings["longitude"])  
    resolved_elevation = elevation if elevation is not None else session_loc.get("elevation", location_settings["elevation"])
    
    return float(resolved_lat), float(resolved_lon), float(resolved_elevation)

def get_cache_data(cache_file: str, cache_ttl: int, use_sqlite: bool = False, loc_key: str = None, time_bucket: str = None, sqlite_getter=None):
    """
    Unified cache retrieval logic for all endpoints.
    
    Args:
        cache_file: Path to pickle cache file
        cache_ttl: Cache TTL in seconds
        use_sqlite: Whether to try SQLite cache first
        loc_key: Location key for SQLite cache
        time_bucket: Time bucket for SQLite cache
        sqlite_getter: Function to get data from SQLite cache
    
    Returns:
        Cached data or None if not found/expired
    """
    import os
    import pickle
    from cache_utils import read_pickle_if_fresh
    
    # Try SQLite cache first if enabled
    if use_sqlite and sqlite_getter and loc_key and time_bucket:
        try:
            cached_data = sqlite_getter(loc_key, time_bucket, cache_ttl)
            if cached_data:
                return cached_data
        except Exception as e:
            print(f"SQLite cache failed: {e}")
    
    # Try pickle cache
    cached_data = read_pickle_if_fresh(cache_file, cache_ttl)
    if cached_data is not None:
        return cached_data
        
    # Fallback to loading expired pickle cache
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass
    
    return None

def store_cache_data(data: Any, cache_file: str, use_sqlite: bool = False, loc_key: str = None, time_bucket: str = None, sqlite_storer=None, **sqlite_kwargs):
    """
    Unified cache storage logic for all endpoints.
    
    Args:
        data: Data to cache
        cache_file: Path to pickle cache file
        use_sqlite: Whether to store in SQLite cache
        loc_key: Location key for SQLite cache
        time_bucket: Time bucket for SQLite cache
        sqlite_storer: Function to store data in SQLite cache
        **sqlite_kwargs: Additional arguments for SQLite storer
    """
    from cache_utils import atomic_write_pickle
    
    # Store in SQLite if enabled
    if use_sqlite and sqlite_storer and loc_key and time_bucket:
        try:
            sqlite_storer(loc_key, time_bucket, **sqlite_kwargs, data)
        except Exception as e:
            print(f"Failed to store in SQLite cache: {e}")
    
    # Store in pickle cache
    try:
        atomic_write_pickle(cache_file, data)
    except Exception:
        pass
