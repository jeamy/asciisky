from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from api.helpers import parse_time_param, get_location_params
from api.computation import LOADER, ts, eph
from api.background import trigger_background_precompute_window
from api.cache_interpolation import load_asteroids_with_interpolation
import bright_asteroids
import settings
import asyncio
import os
import pickle
from cache_utils import build_cache_path, read_pickle_if_fresh, normalize_location, location_key, time_bucket_utc
from db_utils import get_asteroid_positions

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
            # Try loading with interpolation between cached buckets
            try:
                asteroid_list = load_asteroids_with_interpolation(
                    lat, lon, elevation, dt_utc,
                    bucket_hours=bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS,
                    ttl_seconds=bright_asteroids.ASTEROID_CACHE_TTL_SECONDS,
                    use_sqlite=getattr(bright_asteroids, 'ASTEROID_USE_SQLITE', False),
                    disable_pickle=getattr(bright_asteroids, 'DISABLE_PICKLE', False)
                )
                
                if isinstance(asteroid_list, list) and asteroid_list:
                    result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
                    for i, asteroid in enumerate(asteroid_list):
                        if isinstance(asteroid, dict) and "name" in asteroid:
                            result["bodies"][f"bright_asteroid_{i}_{asteroid['name']}"] = asteroid
                    return result
            except Exception as e:
                # Log error but continue to fallback
                print(f"Interpolation failed: {e}")

            # No cache available - trigger background computation and return empty result
            # Don't wait for computation (max 3 seconds would still be too long)
            asyncio.create_task(trigger_background_precompute_window(request.app, lat, lon, elevation, dt_utc, kinds=['asteroids','comets']))
            
            # Return empty result immediately - data will be available on next update
            result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
            return result

        location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        bright_asteroid_list = await asyncio.to_thread(lambda: bright_asteroids.load_bright_asteroids(LOADER, ts, eph, location_dict, max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE, current_dt=dt_utc))
        result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
        for i, asteroid in enumerate(bright_asteroid_list):
            if isinstance(asteroid, dict) and "name" in asteroid:
                result["bodies"][f"bright_asteroid_{i}_{asteroid['name']}"] = asteroid
        
        # Trigger background precompute for future hours even without time parameter
        asyncio.create_task(trigger_background_precompute_window(request.app, lat, lon, elevation, dt_utc, kinds=['celestial','asteroids','comets']))
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Add back /asteroids endpoint for backward compatibility
@router.get("/asteroids")
async def get_asteroids(request: Request, lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False, time: Optional[str] = None):
    """Alias for /bright_asteroids endpoint for backward compatibility."""
    return await get_bright_asteroids(request, lat, lon, elevation, location_name, save_location, time)
