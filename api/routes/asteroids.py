import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

import bright_asteroids
from api.cache_interpolation import load_asteroids_with_interpolation
from api.helpers import get_location_params, parse_time_param, resolve_magnitude_filter
from cache_utils import time_bucket_utc
from config.interpolation_config import (
    get_interpolation_strategy,
    is_smart_interpolation_enabled,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def trigger_asteroid_worker(lat, lon, elevation, dt_utc):
    """Publish one deduplicated asteroid precompute task."""
    try:
        from api.rabbitmq.task_publisher import trigger_precompute_task

        await trigger_precompute_task(
            'asteroids',
            {'latitude': lat, 'longitude': lon, 'elevation': elevation},
            dt_utc.isoformat(),
            20.0,
            bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS,
        )
    except Exception:
        logger.exception("Failed to trigger asteroid worker")


@router.get("/bright_asteroids")
async def get_bright_asteroids(request: Request, background_tasks: BackgroundTasks, lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False, time: str | None = None, max_magnitude: float = None):
    """Get positions of the brightest minor planets (asteroids)."""
    try:
        lat, lon, elevation = get_location_params(request, lat, lon, elevation)

        if save_location:
            # GET requests are intentionally side-effect free.  Persist
            # locations through POST /api/session/location or user settings.
            logger.warning("Ignoring deprecated save_location query parameter on GET /bright_asteroids")

        # Magnitude-Filter aus user_settings oder Parameter verwenden
        if max_magnitude is None:
            max_magnitude = resolve_magnitude_filter(request, 'asteroidMaxMagnitude', bright_asteroids.MAX_APPARENT_MAGNITUDE)

        dt_utc = parse_time_param(time)
        
        # Feature Flag: Smart Interpolation aktivieren?
        user_id = request.session.get('user_id', 'anonymous')
        use_smart_interpolation = is_smart_interpolation_enabled(user_id)
        interpolation_strategy = get_interpolation_strategy(user_id)
        
        logger.info(f"User {user_id}: smart_interpolation={use_smart_interpolation}, strategy={interpolation_strategy.value}")
        
        # Cache-First Strategie mit asynchroner Berechnung
        try:
            logger.info(f"Checking cache for asteroids: lat={lat}, lon={lon}, time={dt_utc.isoformat()}")
            
            # Berechne Bucket-Zeit (gleiche Logik wie Worker!)
            bucket_dt = dt_utc.replace(minute=0, second=0, microsecond=0)
            bucket_key = time_bucket_utc(bucket_dt, bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS)
            
            # Wähle Interpolationsmethode basierend auf Feature Flags
            if use_smart_interpolation:
                from api.smart_interpolation import (
                    load_asteroids_with_smart_interpolation,
                )
                asteroid_list = await asyncio.to_thread(
                    load_asteroids_with_smart_interpolation,
                    lat, lon, elevation, dt_utc,
                    bucket_hours=bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS,
                    use_postgres=True
                )
            else:
                # Original nearest-bucket strategy
                asteroid_list = await asyncio.to_thread(
                    load_asteroids_with_interpolation,
                    lat, lon, elevation, dt_utc,
                    bucket_hours=bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS,
                    use_postgres=True
                )
            
            if isinstance(asteroid_list, list):
                logger.info(f"✅ Cache HIT for asteroids: {len(asteroid_list)} found")
            else:
                # The publisher obtains the persistent claim before publishing.
                # Do not create a separate API-only advisory-lock key here: it
                # cannot remain held across the background task and previously
                # made this branch appear protected although no lock was held.
                logger.warning(f"❌ Cache MISS - triggering asteroid worker for bucket {bucket_key}")
                background_tasks.add_task(trigger_asteroid_worker, lat, lon, elevation, bucket_dt)
                asteroid_list = []
        except Exception as e:
            logger.error(f"Failed to load asteroids from cache: {e}")
            # Triggere trotzdem Asteroid-Worker
            background_tasks.add_task(trigger_asteroid_worker, lat, lon, elevation, dt_utc)
            asteroid_list = []
        
        result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
        for asteroid in asteroid_list:
            if isinstance(asteroid, dict) and "name" in asteroid:
                # Magnitude-Filter anwenden (wichtig: load_bright_asteroids cached mit Mag 20, wir filtern hier)
                if asteroid.get("magnitude", 99) <= max_magnitude:
                    # Use name as key without index to avoid duplicate keys when order changes
                    result["bodies"][f"bright_asteroid_{asteroid['name']}"] = asteroid
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Add back /asteroids endpoint for backward compatibility
@router.get("/asteroids")
async def get_asteroids(request: Request, background_tasks: BackgroundTasks, lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False, time: str | None = None, max_magnitude: float = None):
    """Alias for /bright_asteroids endpoint for backward compatibility."""
    return await get_bright_asteroids(request, background_tasks, lat, lon, elevation, location_name, save_location, time, max_magnitude)
