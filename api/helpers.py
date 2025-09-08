from datetime import datetime, timezone
from typing import Dict, Any, Optional

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
