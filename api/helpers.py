from datetime import datetime, timezone
from typing import Optional, Tuple

from fastapi import Request
import settings as app_settings

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
    # Get defaults from settings and session
    location_settings = app_settings.get_location()
    session_loc = request.session.get("location", {}) if hasattr(request, "session") else {}
    
    # Resolve parameters with priority order
    resolved_lat = lat if lat is not None else session_loc.get("latitude", location_settings["latitude"])
    resolved_lon = lon if lon is not None else session_loc.get("longitude", location_settings["longitude"])  
    resolved_elevation = elevation if elevation is not None else session_loc.get("elevation", location_settings["elevation"])
    return float(resolved_lat), float(resolved_lon), float(resolved_elevation)


def resolve_magnitude_filter(request: Request, filter_key: str, default: float) -> float:
    """
    Resolve magnitude filter value: DB for logged-in users, file for anonymous.
    
    Args:
        request: FastAPI request (for session user_id)
        filter_key: e.g. 'asteroidMaxMagnitude' or 'cometMaxMagnitude'
        default: fallback magnitude if no filter is stored
        
    Returns: resolved max magnitude as float
    """
    user_id = request.session.get('user_id') if hasattr(request, 'session') else None
    if user_id:
        try:
            from api.routes.filters import get_user_filters_from_db
            filters = get_user_filters_from_db(user_id)
            if filters:
                return float(filters.get(filter_key, default))
        except Exception:
            pass
    filters = app_settings.get_magnitude_filters()
    return float(filters.get(filter_key, default))

