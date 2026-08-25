import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

import comets
from api.cache_interpolation import load_comets_with_interpolation
from api.helpers import (
    get_location_params,
    parse_time_param,
    resolve_magnitude_filter,
    trigger_small_body_worker,
)
from cache_utils import time_bucket_utc
from config.interpolation_config import (
    get_interpolation_strategy,
    is_smart_interpolation_enabled,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def trigger_comet_worker(lat, lon, elevation, dt_utc):
    """Publish one deduplicated comet precompute task."""
    await trigger_small_body_worker(
        'comets',
        lat,
        lon,
        elevation,
        dt_utc,
        14.0,
        comets.COMET_CACHE_BUCKET_HOURS,
        logger,
    )


@router.get("/comets")
async def get_comets(request: Request, background_tasks: BackgroundTasks, lat: float = None, lon: float = None, elevation: float = None, time: str | None = None, max_magnitude: float = None):
    """Get comets with real MPC data and rise/set/transit times."""
    try:
        lat, lon, elevation = get_location_params(request, lat, lon, elevation)

        # Magnitude-Filter aus user_settings oder Parameter verwenden
        if max_magnitude is None:
            max_magnitude = resolve_magnitude_filter(request, 'cometMaxMagnitude', comets.MAX_APPARENT_MAGNITUDE)

        dt_utc = parse_time_param(time)
        
        # Feature Flag: Smart Interpolation aktivieren?
        user_id = request.session.get('user_id', 'anonymous')
        use_smart_interpolation = is_smart_interpolation_enabled(user_id)
        interpolation_strategy = get_interpolation_strategy(user_id)
        
        logger.info(f"User {user_id}: smart_interpolation={use_smart_interpolation}, strategy={interpolation_strategy.value}")
        
        # Cache-First Strategie mit asynchroner Berechnung
        try:
            logger.info(f"Checking cache for comets: lat={lat}, lon={lon}, time={dt_utc.isoformat()}")
            
            # Berechne Bucket-Zeit (gleiche Logik wie Worker!)
            bucket_dt = dt_utc.replace(minute=0, second=0, microsecond=0)
            bucket_key = time_bucket_utc(bucket_dt, comets.COMET_CACHE_BUCKET_HOURS)
            
            # Wähle Interpolationsmethode basierend auf Feature Flags
            if use_smart_interpolation:
                from api.smart_interpolation import load_comets_with_smart_interpolation
                comet_list = await asyncio.to_thread(
                    load_comets_with_smart_interpolation,
                    lat, lon, elevation, dt_utc,
                    bucket_hours=comets.COMET_CACHE_BUCKET_HOURS,
                    use_postgres=True
                )
            else:
                # Original nearest-bucket strategy
                comet_list = await asyncio.to_thread(
                    load_comets_with_interpolation,
                    lat, lon, elevation, dt_utc,
                    bucket_hours=comets.COMET_CACHE_BUCKET_HOURS,
                    use_postgres=True
                )
            
            if isinstance(comet_list, list):
                logger.info(f"✅ Cache HIT for comets: {len(comet_list)} found")
            else:
                # The publisher obtains the persistent claim before publishing.
                # A transient API-only advisory lock cannot safely cover this
                # background task and is intentionally not used here.
                logger.warning(f"❌ Cache MISS - triggering comet worker for bucket {bucket_key}")
                background_tasks.add_task(trigger_comet_worker, lat, lon, elevation, bucket_dt)
                comet_list = []
        except Exception as e:
            logger.error(f"Failed to load comets from cache: {e}")
            # Triggere trotzdem Comet-Worker
            background_tasks.add_task(trigger_comet_worker, lat, lon, elevation, dt_utc)
            comet_list = []
        
        result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
        count = 0
        for comet in comet_list:
            if isinstance(comet, dict) and "name" in comet:
                # Magnitude-Filter anwenden
                if comet.get("magnitude", 99) <= max_magnitude:
                    result["bodies"][f"comet_{count}_{comet['name']}"] = comet
                    count += 1
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
