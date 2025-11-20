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
    logger.info("Resolved location: lat=%.6f lon=%.6f elev=%.1f", resolved_lat, resolved_lon, resolved_elevation)
    return float(resolved_lat), float(resolved_lon), float(resolved_elevation)

def get_cache_data(cache_file: str, cache_ttl: int, use_postgres: bool = True, loc_key: str = None, time_bucket: str = None, postgres_getter=None):
    """
    Unified cache retrieval logic - PostgreSQL only.
    
    Args:
        cache_file: Ignored (legacy parameter)
        cache_ttl: Cache TTL in seconds
        use_postgres: Whether to try PostgreSQL cache
        loc_key: Location key for PostgreSQL cache
        time_bucket: Time bucket for PostgreSQL cache
        postgres_getter: Function to get data from PostgreSQL cache
        
    Returns:
        Cached data or None if not found/expired
    """
    # PostgreSQL cache only
    if use_postgres and postgres_getter and loc_key and time_bucket:
        try:
            cached_data = postgres_getter(loc_key, time_bucket, cache_ttl)
            if cached_data:
                return cached_data
        except Exception as e:
            print(f"PostgreSQL cache failed: {e}")
    
    return None

def store_cache_data(data: Any, cache_file: str, use_postgres: bool = True, loc_key: str = None, time_bucket: str = None, postgres_storer=None, **postgres_kwargs):
    """
    Unified cache storage logic - PostgreSQL only.
    
    Args:
        data: Data to cache
        cache_file: Ignored (legacy parameter)
        use_postgres: Whether to store in PostgreSQL cache
        loc_key: Location key for PostgreSQL cache
        time_bucket: Time bucket for PostgreSQL cache
        postgres_storer: Function to store data in PostgreSQL cache
        **postgres_kwargs: Additional arguments for PostgreSQL storer
    """
    # PostgreSQL cache only
    if use_postgres and postgres_storer and loc_key and time_bucket:
        try:
            postgres_storer(loc_key=loc_key, time_bucket=time_bucket, **postgres_kwargs)
        except Exception as e:
            print(f"PostgreSQL cache write failed: {e}")
