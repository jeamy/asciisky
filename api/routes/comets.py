from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from api.helpers import parse_time_param
from api.computation import LOADER, ts, eph
from api.background import trigger_background_precompute_window
import comets
import settings
import os
import pickle
from cache_utils import build_cache_path, read_pickle_if_fresh
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
            cache_file = build_cache_path('comets', lat, lon, elevation, dt=dt_utc, bucket_hours=comets.COMET_CACHE_BUCKET_HOURS)
            comet_list = read_pickle_if_fresh(cache_file, comets.COMET_CACHE_TTL_SECONDS)
            if comet_list is None and os.path.exists(cache_file):
                with open(cache_file, 'rb') as f:
                    comet_list = pickle.load(f)

            if isinstance(comet_list, list):
                result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
                for i, comet in enumerate(comet_list[:max_comets]):
                    if isinstance(comet, dict) and "name" in comet:
                        result["bodies"][f"comet_{i}_{comet['name']}"] = comet
                return result

            location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
            comet_list = comets.load_comets(ts, eph, location_dict, max_comets=max_comets, use_cache=True, current_dt=dt_utc)
            result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
            for i, comet in enumerate(comet_list[:max_comets]):
                if isinstance(comet, dict) and "name" in comet:
                    result["bodies"][f"comet_{i}_{comet['name']}"] = comet

            asyncio.create_task(trigger_background_precompute_window(request.app, lat, lon, elevation, dt_utc, kinds=['celestial','asteroids','comets']))
            return result

        location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        comet_list = comets.load_comets(ts, eph, location_dict, max_comets=max_comets, current_dt=dt_utc)
        result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
        for i, comet in enumerate(comet_list):
            if isinstance(comet, dict) and "name" in comet:
                result["bodies"][f"comet_{i}_{comet['name']}"] = comet
        
        # Trigger background precompute for future hours even without time parameter
        asyncio.create_task(trigger_background_precompute_window(request.app, lat, lon, elevation, dt_utc, kinds=['celestial','asteroids','comets']))
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
