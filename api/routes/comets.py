from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from api.helpers import parse_time_param
from api.cache_interpolation import load_comets_with_interpolation
import comets
import settings
import os
from cache_utils import normalize_location, location_key, time_bucket_utc
from db_utils import get_comet_positions
import asyncio
import logging
import uuid
import time
from datetime import datetime, timedelta

# RabbitMQ Integration
from config.feature_flags import use_rabbitmq_for
from api.rabbitmq.task_publisher import get_task_publisher

logger = logging.getLogger(__name__)

router = APIRouter()


async def trigger_rabbitmq_precompute_comets(lat, lon, elevation, dt_utc, hours_radius=12):
    """Triggert RabbitMQ Background Tasks für Comet Precompute"""
    try:
        publisher = get_task_publisher()
        if not publisher:
            logger.warning("TaskPublisher not available")
            return
        
        location = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        tasks = []
        
        for hour_offset in range(-hours_radius, hours_radius + 1):
            time_bucket = dt_utc + timedelta(hours=hour_offset)
            tasks.append({
                'kind': 'comets',
                'location': location,
                'time_bucket': time_bucket.isoformat(),
                'magnitude': 14.0,
                'priority': 5
            })
        
        await asyncio.to_thread(publisher.publish_batch, tasks)
        logger.info(f"Published {len(tasks)} comet precompute tasks")
    except Exception as e:
        logger.error(f"Failed to trigger comet precompute: {e}")


async def compute_comets_rabbitmq(location_dict, dt_utc, max_magnitude):
    """
    Berechnet Kometen über RabbitMQ (neue Architektur)
    
    Args:
        location_dict: {'latitude': float, 'longitude': float, 'elevation': float}
        dt_utc: datetime object
        max_magnitude: float
        
    Returns:
        Liste von Kometen-Daten
    """
    client = get_rabbitmq_client()
    if not client:
        raise Exception("RabbitMQ client not available")
    
    task_id = f"comet_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    
    request_data = {
        'task_id': task_id,
        'location': location_dict,
        'time_bucket': dt_utc.isoformat(),
        'magnitude': max_magnitude
    }
    
    logger.info(f"Sending comet computation to RabbitMQ: {task_id}")
    
    # Synchroner RPC-Call mit Timeout
    result = await asyncio.to_thread(
        client.call,
        'compute.comet',
        request_data,
        timeout=settings.RABBITMQ_TIMEOUT
    )
    
    if result and 'comets' in result:
        logger.info(f"Received {len(result['comets'])} comets from RabbitMQ")
        return result['comets']
    else:
        raise Exception("Invalid response from RabbitMQ worker")


async def compute_comets_old(location_dict, dt_utc, max_comets):
    """
    Berechnet Kometen mit alter Architektur (Fallback)
    
    Args:
        location_dict: {'latitude': float, 'longitude': float, 'elevation': float}
        dt_utc: datetime object
        max_comets: int
        
    Returns:
        Liste von Kometen-Daten
    """
    return await asyncio.to_thread(
        lambda: comets.load_comets(ts, eph, location_dict, max_comets=max_comets, current_dt=dt_utc)
    )

@router.get("/comets")
async def get_comets(request: Request, lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False, max_comets: int = 1000, time: Optional[str] = None, max_magnitude: float = None):
    """Get comets with real MPC data and rise/set/transit times."""
    try:
        location_settings = settings.get_location()
        session_loc = request.session.get("location", {}) if hasattr(request, "session") else {}
        if lat is None: lat = session_loc.get("latitude", location_settings["latitude"])
        if lon is None: lon = session_loc.get("longitude", location_settings["longitude"])
        if elevation is None: elevation = session_loc.get("elevation", location_settings["elevation"])

        if save_location and lat is not None and lon is not None and elevation is not None:
            settings.set_location(lat, lon, elevation, location_name)

        # Magnitude-Filter aus user_settings oder Parameter verwenden
        if max_magnitude is None:
            filters = settings.get_magnitude_filters()
            max_magnitude = filters.get("cometMaxMagnitude", comets.MAX_APPARENT_MAGNITUDE)

        dt_utc = parse_time_param(time)
        location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        
        # Feature Flag: RabbitMQ oder alte Architektur?
        user_id = request.session.get('user_id', 'anonymous')
        use_rabbitmq_flag = use_rabbitmq_for('comets', user_id)
        
        # Bei RabbitMQ: Cache-First + Background Tasks
        if use_rabbitmq_flag:
            logger.info(f"Using RabbitMQ architecture for comets: lat={lat}, lon={lon}")
            try:
                comet_list = load_comets_with_interpolation(
                    lat, lon, elevation, dt_utc,
                    bucket_hours=comets.COMET_CACHE_BUCKET_HOURS,
                    ttl_seconds=comets.COMET_CACHE_TTL_SECONDS,
                    use_sqlite=getattr(comets, 'COMET_USE_SQLITE', False)
                )
                
                if isinstance(comet_list, list) and comet_list:
                    logger.info(f"Cache hit for comets: {len(comet_list)} found")
                else:
                    logger.info("Cache miss - triggering RabbitMQ background task")
                    asyncio.create_task(trigger_rabbitmq_precompute_comets(
                        lat, lon, elevation, dt_utc, hours_radius=12
                    ))
                    comet_list = []
            except Exception as e:
                logger.warning(f"Cache read failed: {e}")
                asyncio.create_task(trigger_rabbitmq_precompute_comets(
                    lat, lon, elevation, dt_utc, hours_radius=12
                ))
                comet_list = []
        else:
            # RabbitMQ deaktiviert - sollte nicht passieren
            logger.warning(f"RabbitMQ disabled for comets - returning empty")
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
