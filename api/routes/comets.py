from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from api.helpers import parse_time_param
from api.computation import LOADER, ts, eph
from api.background import trigger_background_precompute_window
from api.cache_interpolation import load_comets_with_interpolation
import comets
import settings
import os
import pickle
from cache_utils import build_cache_path, read_pickle_if_fresh, normalize_location, location_key, time_bucket_utc
from db_utils import get_comet_positions
import asyncio

router = APIRouter()

@router.get("/comets")
async def get_comets(request: Request, lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False, max_comets: int = 1000, time: Optional[str] = None):
    """Get comets with real MPC data and rise/set/transit times."""
    try:
        location_settings = settings.get_location()
        session_loc = request.session.get("location", {}) if hasattr(request, "session") else {}
        if lat is None: lat = session_loc.get("latitude", location_settings["latitude"])
        if lon is None: lon = session_loc.get("longitude", location_settings["longitude"])
        if elevation is None: elevation = session_loc.get("elevation", location_settings["elevation"])

        if save_location and lat is not None and lon is not None and elevation is not None:
            settings.set_location(lat, lon, elevation, location_name)

        dt_utc = parse_time_param(time)

        if time is not None:
            # Try loading with interpolation between cached buckets
            try:
                comet_list = load_comets_with_interpolation(
                    lat, lon, elevation, dt_utc,
                    bucket_hours=comets.COMET_CACHE_BUCKET_HOURS,
                    ttl_seconds=comets.COMET_CACHE_TTL_SECONDS,
                    use_sqlite=getattr(comets, 'COMET_USE_SQLITE', False),
                    disable_pickle=getattr(comets, 'DISABLE_PICKLE', False)
                )
                
                if isinstance(comet_list, list) and comet_list:
                    result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
                    for i, comet in enumerate(comet_list[:max_comets]):
                        if isinstance(comet, dict) and "name" in comet:
                            result["bodies"][f"comet_{i}_{comet['name']}"] = comet
                    return result
            except Exception as e:
                # Log error but continue to fallback
                print(f"Comet interpolation failed: {e}")

            # No cache available - trigger background computation and return empty result
            # Don't wait for computation (max 3 seconds would still be too long)
            asyncio.create_task(trigger_background_precompute_window(request.app, lat, lon, elevation, dt_utc, kinds=['asteroids','comets']))
            
            # Return empty result immediately - data will be available on next update
            result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
            return result

        location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        comet_list = await asyncio.to_thread(lambda: comets.load_comets(ts, eph, location_dict, max_comets=max_comets, current_dt=dt_utc))
        result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
        for i, comet in enumerate(comet_list):
            if isinstance(comet, dict) and "name" in comet:
                result["bodies"][f"comet_{i}_{comet['name']}"] = comet
        
        # Trigger background precompute for future hours even without time parameter
        asyncio.create_task(trigger_background_precompute_window(request.app, lat, lon, elevation, dt_utc, kinds=['celestial','asteroids','comets']))
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
