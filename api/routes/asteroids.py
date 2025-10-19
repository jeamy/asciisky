from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from api.helpers import parse_time_param, get_location_params
from api.cache_interpolation import load_asteroids_with_interpolation
import bright_asteroids
import settings
import asyncio
import os
import time
import uuid
import logging
from datetime import datetime, timedelta
from cache_utils import normalize_location, location_key, time_bucket_utc
from db_utils import get_asteroid_positions

# RabbitMQ Integration (für Migration)
from config.feature_flags import use_rabbitmq_for
from api.rabbitmq.task_publisher import get_task_publisher

logger = logging.getLogger(__name__)

router = APIRouter()


async def trigger_rabbitmq_precompute(lat, lon, elevation, dt_utc, kinds=['asteroids'], hours_radius=12):
    """
    Triggert RabbitMQ Background Tasks für Precompute
    
    Args:
        lat, lon, elevation: Location
        dt_utc: Zentrale Zeit
        kinds: Liste von Typen ('asteroids', 'comets', etc.)
        hours_radius: Radius in Stunden um dt_utc
    """
    try:
        publisher = get_task_publisher()
        if not publisher:
            logger.warning("TaskPublisher not available, skipping RabbitMQ precompute")
            return
        
        location = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        
        # Erstelle Tasks für Zeitfenster (±hours_radius)
        tasks = []
        for hour_offset in range(-hours_radius, hours_radius + 1):
            time_bucket = dt_utc + timedelta(hours=hour_offset)
            time_bucket_str = time_bucket.isoformat()
            
            for kind in kinds:
                # Magnitude basierend auf Kind
                magnitude = 20.0 if kind == 'asteroids' else 14.0 if kind == 'comets' else None
                
                tasks.append({
                    'kind': kind,
                    'location': location,
                    'time_bucket': time_bucket_str,
                    'magnitude': magnitude,
                    'priority': 5  # Normal priority
                })
        
        # Publiziere Tasks als Batch
        await asyncio.to_thread(publisher.publish_batch, tasks)
        logger.info(f"Published {len(tasks)} precompute tasks to RabbitMQ")
        
    except Exception as e:
        logger.error(f"Failed to trigger RabbitMQ precompute: {e}")


async def compute_asteroids_rabbitmq(location_dict, dt_utc, max_magnitude):
    """
    Berechnet Asteroiden über RabbitMQ (neue Architektur)
    
    Args:
        location_dict: {'latitude': float, 'longitude': float, 'elevation': float}
        dt_utc: datetime object
        max_magnitude: float
        
    Returns:
        Liste von Asteroiden-Daten
    """
    client = get_rabbitmq_client()
    if client is None:
        raise ConnectionError("RabbitMQ client not available")
    
    request_data = {
        'task_id': f"asteroid_{int(time.time())}_{uuid.uuid4().hex[:8]}",
        'type': 'asteroid',
        'location': location_dict,
        'time_bucket': dt_utc.isoformat(),
        'magnitude': max_magnitude
    }
    
    # RPC Call mit Timeout
    result = await asyncio.to_thread(
        client.call,
        queue='asteroid',
        request=request_data,
        priority=10,
        timeout=settings.RABBITMQ_TIMEOUT
    )
    
    return result.get('asteroids', [])


async def compute_asteroids_old(location_dict, dt_utc, max_magnitude):
    """
    Berechnet Asteroiden mit alter Architektur (Fallback)
    
    Args:
        location_dict: {'latitude': float, 'longitude': float, 'elevation': float}
        dt_utc: datetime object
        max_magnitude: float
        
    Returns:
        Liste von Asteroiden-Daten
    """
    return await asyncio.to_thread(
        lambda: bright_asteroids.load_bright_asteroids(
            LOADER, ts, eph, location_dict,
            max_magnitude=max_magnitude,
            current_dt=dt_utc
        )
    )


@router.get("/bright_asteroids")
async def get_bright_asteroids(request: Request, lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False, time: Optional[str] = None, max_magnitude: float = None):
    """Get positions of the brightest minor planets (asteroids)."""
    try:
        lat, lon, elevation = get_location_params(request, lat, lon, elevation)

        if save_location and lat is not None and lon is not None and elevation is not None:
            settings.set_location(lat, lon, elevation, location_name)

        # Magnitude-Filter aus user_settings oder Parameter verwenden
        if max_magnitude is None:
            filters = settings.get_magnitude_filters()
            max_magnitude = filters.get("asteroidMaxMagnitude", bright_asteroids.MAX_APPARENT_MAGNITUDE)

        dt_utc = parse_time_param(time)

        if time is not None:
            # Try loading with interpolation between cached buckets
            try:
                asteroid_list = load_asteroids_with_interpolation(
                    lat, lon, elevation, dt_utc,
                    bucket_hours=bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS,
                    ttl_seconds=bright_asteroids.ASTEROID_CACHE_TTL_SECONDS,
                    use_sqlite=getattr(bright_asteroids, 'ASTEROID_USE_SQLITE', False)
                )
                
                if isinstance(asteroid_list, list) and asteroid_list:
                    result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
                    for asteroid in asteroid_list:
                        if isinstance(asteroid, dict) and "name" in asteroid:
                            # Magnitude-Filter anwenden
                            if asteroid.get("magnitude", 99) <= max_magnitude:
                                # Use name as key without index to avoid duplicate keys when order changes
                                result["bodies"][f"bright_asteroid_{asteroid['name']}"] = asteroid
                    return result
            except Exception as e:
                # Log error but continue to fallback
                print(f"Interpolation failed: {e}")

            # No cache available - RabbitMQ will handle this
            # Return empty result immediately - data will appear on next poll (60s)
            result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
            return result

        location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        
        # Feature Flag: RabbitMQ oder alte Architektur?
        user_id = request.session.get('user_id', 'anonymous')
        use_rabbitmq_flag = use_rabbitmq_for('asteroids', user_id)
        
        # Bei RabbitMQ: Versuche aus Cache zu lesen, triggere Background Task wenn leer
        if use_rabbitmq_flag:
            logger.info(f"Using RabbitMQ architecture: lat={lat}, lon={lon}")
            
            # Versuche aus Cache zu lesen (wie Legacy)
            try:
                bright_asteroid_list = load_asteroids_with_interpolation(
                    lat, lon, elevation, dt_utc,
                    bucket_hours=bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS,
                    ttl_seconds=bright_asteroids.ASTEROID_CACHE_TTL_SECONDS,
                    use_sqlite=getattr(bright_asteroids, 'ASTEROID_USE_SQLITE', False)
                )
                
                if isinstance(bright_asteroid_list, list) and bright_asteroid_list:
                    # Cache Hit! Daten vorhanden
                    logger.info(f"Cache hit for asteroids: {len(bright_asteroid_list)} found")
                else:
                    # Cache Miss! Trigger Background Task
                    logger.info("Cache miss - triggering RabbitMQ background task")
                    asyncio.create_task(trigger_rabbitmq_precompute(
                        lat, lon, elevation, dt_utc, kinds=['asteroids'], hours_radius=12
                    ))
                    bright_asteroid_list = []  # Leere Liste
                    
            except Exception as e:
                logger.warning(f"Cache read failed: {e}")
                # Trigger Background Task
                asyncio.create_task(trigger_rabbitmq_precompute(
                    lat, lon, elevation, dt_utc, kinds=['asteroids'], hours_radius=12
                ))
                bright_asteroid_list = []  # Leere Liste
        else:
            # RabbitMQ deaktiviert - sollte nicht passieren
            logger.warning(f"RabbitMQ disabled for asteroids - returning empty")
            bright_asteroid_list = []
        
        result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
        for asteroid in bright_asteroid_list:
            if isinstance(asteroid, dict) and "name" in asteroid:
                # Magnitude-Filter anwenden (wichtig: load_bright_asteroids cached mit Mag 20, wir filtern hier)
                if asteroid.get("magnitude", 99) <= max_magnitude:
                    # Use name as key without index to avoid duplicate keys when order changes
                    result["bodies"][f"bright_asteroid_{asteroid['name']}"] = asteroid
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Add back /asteroids endpoint for backward compatibility
@router.get("/asteroids")
async def get_asteroids(request: Request, lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False, time: Optional[str] = None, max_magnitude: float = None):
    """Alias for /bright_asteroids endpoint for backward compatibility."""
    return await get_bright_asteroids(request, lat, lon, elevation, location_name, save_location, time, max_magnitude)
