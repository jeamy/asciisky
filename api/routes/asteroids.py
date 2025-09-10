from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from api.helpers import parse_time_param, get_location_params
from api.computation import LOADER, ts, eph
from api.background import trigger_background_precompute_window
import bright_asteroids
import settings
import asyncio

router = APIRouter()

@router.get("/bright_asteroids")
async def get_bright_asteroids(request: Request, lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False, time: Optional[str] = None):
    """Get positions of the brightest minor planets (asteroids)."""
    try:
        lat, lon, elevation = get_location_params(request, lat, lon, elevation)

        if save_location and lat is not None and lon is not None and elevation is not None:
            settings.set_location(lat, lon, elevation, location_name)

        dt_utc = parse_time_param(time)

        if time is not None:
            cache_file = build_cache_path('asteroids', lat, lon, elevation, dt=dt_utc, bucket_hours=bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS)
            asteroid_list = read_pickle_if_fresh(cache_file, bright_asteroids.ASTEROID_CACHE_TTL_SECONDS)
            if asteroid_list is None and os.path.exists(cache_file):
                with open(cache_file, 'rb') as f:
                    asteroid_list = pickle.load(f)

            if isinstance(asteroid_list, list):
                result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
                for i, asteroid in enumerate(asteroid_list):
                    if isinstance(asteroid, dict) and "name" in asteroid:
                        result["bodies"][f"bright_asteroid_{i}_{asteroid['name']}"] = asteroid
                return result

            location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
            bright_asteroid_list = bright_asteroids.load_bright_asteroids(LOADER, ts, eph, location_dict, max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE, use_cache=True, current_dt=dt_utc)
            result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
            for i, asteroid in enumerate(bright_asteroid_list):
                if isinstance(asteroid, dict) and "name" in asteroid:
                    result["bodies"][f"bright_asteroid_{i}_{asteroid['name']}"] = asteroid

            asyncio.create_task(trigger_background_precompute_window(request.app, lat, lon, elevation, dt_utc, kinds=['celestial','asteroids','comets']))
            return result

        location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        bright_asteroid_list = bright_asteroids.load_bright_asteroids(LOADER, ts, eph, location_dict, max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE, current_dt=dt_utc)
        result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
        for i, asteroid in enumerate(bright_asteroid_list):
            if isinstance(asteroid, dict) and "name" in asteroid:
                result["bodies"][f"bright_asteroid_{i}_{asteroid['name']}"] = asteroid
        
        # Trigger background precompute for future hours even without time parameter
        asyncio.create_task(trigger_background_precompute_window(request.app, lat, lon, elevation, dt_utc, kinds=['celestial','asteroids','comets']))
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Removed redundant /asteroids endpoint - use /bright_asteroids instead
