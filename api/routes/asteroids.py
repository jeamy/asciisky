from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from api.helpers import parse_time_param, get_location_params
from api.computation import LOADER, ts, eph
from api.background import trigger_background_precompute_spot
from api.cache_interpolation import load_asteroids_with_interpolation
import bright_asteroids
import settings
import asyncio
import os
import pickle
import time
import uuid
import logging
from cache_utils import build_cache_path, read_pickle_if_fresh, normalize_location, location_key, time_bucket_utc
from db_utils import get_asteroid_positions

# RabbitMQ Integration (für Migration)
from config.feature_flags import use_rabbitmq_for

logger = logging.getLogger(__name__)

# Lazy init für RabbitMQ Client
_rabbitmq_client = None

def get_rabbitmq_client():
    """Lazy initialization von RabbitMQ Client"""
    global _rabbitmq_client
    if _rabbitmq_client is None and settings.RABBITMQ_ENABLED:
        try:
            from api.rabbitmq.rpc_client import RabbitMQRPCClient
            _rabbitmq_client = RabbitMQRPCClient(settings.RABBITMQ_URL)
            logger.info("RabbitMQ client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize RabbitMQ client: {e}")
            _rabbitmq_client = None
    return _rabbitmq_client

router = APIRouter()


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
                    use_sqlite=getattr(bright_asteroids, 'ASTEROID_USE_SQLITE', False),
                    disable_pickle=getattr(bright_asteroids, 'DISABLE_PICKLE', False)
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

            # No cache available - trigger spot computation (±12h around requested time)
            # This is much faster than full 30-day window
            print(f"No cache for asteroids at {dt_utc.isoformat()}, triggering spot computation (±12h)...")
            
            # Trigger spot precompute for ±12 hours around requested time
            asyncio.create_task(trigger_background_precompute_spot(request.app, lat, lon, elevation, dt_utc, kinds=['asteroids','comets'], hours_radius=12))
            
            # Return empty result immediately - data will appear on next poll (60s)
            result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
            return result

        location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        
        # Feature Flag: RabbitMQ oder alte Architektur?
        user_id = request.session.get('user_id', None)
        use_rabbitmq = use_rabbitmq_for('asteroids', user_id)
        
        if use_rabbitmq:
            logger.info(f"Using RabbitMQ for asteroids: lat={lat}, lon={lon}")
            try:
                bright_asteroid_list = await compute_asteroids_rabbitmq(
                    location_dict, dt_utc, max_magnitude
                )
            except Exception as e:
                logger.error(f"RabbitMQ error: {e}")
                # Fallback zur alten Architektur
                if settings.FALLBACK_TO_OLD_ON_ERROR:
                    logger.warning("Falling back to old architecture")
                    bright_asteroid_list = await compute_asteroids_old(
                        location_dict, dt_utc, max_magnitude
                    )
                else:
                    raise HTTPException(status_code=503, detail="Service temporarily unavailable")
        else:
            logger.info(f"Using old architecture for asteroids: lat={lat}, lon={lon}")
            bright_asteroid_list = await compute_asteroids_old(
                location_dict, dt_utc, max_magnitude
            )
        
        result = {"time": dt_utc.isoformat(), "location": {"latitude": lat, "longitude": lon, "elevation": elevation}, "bodies": {}}
        for asteroid in bright_asteroid_list:
            if isinstance(asteroid, dict) and "name" in asteroid:
                # Magnitude-Filter anwenden (wichtig: load_bright_asteroids cached mit Mag 20, wir filtern hier)
                if asteroid.get("magnitude", 99) <= max_magnitude:
                    # Use name as key without index to avoid duplicate keys when order changes
                    result["bodies"][f"bright_asteroid_{asteroid['name']}"] = asteroid
        
        # Trigger background precompute for future hours even without time parameter
        if not use_rabbitmq:  # Nur bei alter Architektur
            asyncio.create_task(trigger_background_precompute_spot(request.app, lat, lon, elevation, dt_utc, kinds=['asteroids','comets'], hours_radius=12))
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Add back /asteroids endpoint for backward compatibility
@router.get("/asteroids")
async def get_asteroids(request: Request, lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False, time: Optional[str] = None, max_magnitude: float = None):
    """Alias for /bright_asteroids endpoint for backward compatibility."""
    return await get_bright_asteroids(request, lat, lon, elevation, location_name, save_location, time, max_magnitude)
