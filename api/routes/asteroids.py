from typing import Optional
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from api.helpers import parse_time_param, get_location_params
from api.cache_interpolation import load_asteroids_with_interpolation
from api.computation import LOADER, ts, eph
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


async def trigger_asteroid_worker(lat, lon, elevation, dt_utc):
    """
    Triggert Asteroid-Worker für On-Demand Berechnung
    
    Args:
        lat, lon, elevation: Location
        dt_utc: Zeit
    """
    try:
        import pika
        import json
        rabbitmq_url = os.environ.get('RABBITMQ_URL', 'amqp://admin:changeme@rabbitmq:5672/')
        logger.info(f"🚀 Triggering asteroid worker: url={rabbitmq_url}")
        
        def publish_task():
            try:
                logger.info(f"📡 Connecting to RabbitMQ...")
                params = pika.URLParameters(rabbitmq_url)
                connection = pika.BlockingConnection(params)
                channel = connection.channel()
                logger.info(f"✅ Connected to RabbitMQ")
                
                # Exchange deklarieren (MUSS existieren für basic_publish)
                channel.exchange_declare(
                    exchange='computation.direct',
                    exchange_type='direct',
                    durable=True
                )
                
                task_id = f"asteroid_{int(time.time())}_{uuid.uuid4().hex[:8]}"
                # Task-Daten
                task = {
                    'task_id': task_id,
                    'kind': 'asteroids',  # Required for unified_worker (plural!)
                    'location': {
                        'latitude': lat,
                        'longitude': lon,
                        'elevation': elevation
                    },
                    'time_bucket': dt_utc.isoformat(),
                    'magnitude': 20.0  # Max magnitude for asteroids
                }
                
                logger.info(f"📤 Publishing task: {task['task_id']}")
                
                # Publiziere an computation.direct Exchange mit routing_key compute.asteroid
                channel.basic_publish(
                    exchange='computation.direct',
                    routing_key='compute.asteroid',
                    body=json.dumps(task),
                    properties=pika.BasicProperties(
                        delivery_mode=2,  # persistent
                        priority=5
                    )
                )
                
                connection.close()
                logger.info(f"✅ Published asteroid task {task['task_id']} to asteroid.compute queue")
            except Exception as e:
                logger.error(f"❌ Error in publish_task: {e}", exc_info=True)
                raise
        
        await asyncio.to_thread(publish_task)
        
    except Exception as e:
        logger.error(f"❌ Failed to trigger asteroid worker: {e}", exc_info=True)


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
async def get_bright_asteroids(request: Request, background_tasks: BackgroundTasks, lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False, time: Optional[str] = None, max_magnitude: float = None):
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
        location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        
        # Feature Flag: RabbitMQ oder alte Architektur?
        user_id = request.session.get('user_id', 'anonymous')
        use_rabbitmq_flag = use_rabbitmq_for('asteroids', user_id)
        
        # Feature Flag: Smart Interpolation aktivieren?
        from config.interpolation_config import is_smart_interpolation_enabled, get_interpolation_strategy
        use_smart_interpolation = is_smart_interpolation_enabled(user_id)
        interpolation_strategy = get_interpolation_strategy(user_id)
        
        logger.info(f"User {user_id}: smart_interpolation={use_smart_interpolation}, strategy={interpolation_strategy.value}")
        
        # Cache-First Strategie mit asynchroner Berechnung
        try:
            logger.info(f"Checking cache for asteroids: lat={lat}, lon={lon}, time={dt_utc.isoformat()}")
            
            # Berechne Bucket-Zeit (gleiche Logik wie Worker!)
            from cache_utils import time_bucket_utc
            bucket_dt = dt_utc.replace(minute=0, second=0, microsecond=0)
            bucket_key = time_bucket_utc(bucket_dt, bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS)
            
            # Wähle Interpolationsmethode basierend auf Feature Flags
            if use_smart_interpolation:
                from api.smart_interpolation import load_asteroids_with_smart_interpolation
                asteroid_list = load_asteroids_with_smart_interpolation(
                    lat, lon, elevation, dt_utc,
                    bucket_hours=bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS,
                    ttl_seconds=bright_asteroids.ASTEROID_CACHE_TTL_SECONDS,
                    use_postgres=True
                )
            else:
                # Original nearest-bucket strategy
                asteroid_list = load_asteroids_with_interpolation(
                    lat, lon, elevation, dt_utc,
                    bucket_hours=bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS,
                    ttl_seconds=bright_asteroids.ASTEROID_CACHE_TTL_SECONDS,
                    use_postgres=True
                )
            
            if isinstance(asteroid_list, list) and asteroid_list:
                logger.info(f"✅ Cache HIT for asteroids: {len(asteroid_list)} found")
            else:
                # Cache-Miss: Prüfe ob Berechnung bereits läuft
                from cache_utils import normalize_location, location_key
                lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
                loc_key = location_key(lat_norm, lon_norm, elev_norm)
                
                computation_key = f"computing:asteroid:{loc_key}:{bucket_key}"
                
                # Prüfe ob bereits in Berechnung
                from db_utils import is_computation_in_progress, mark_computation_in_progress
                if is_computation_in_progress(computation_key):
                    logger.info(f"⏳ Computation already in progress for bucket {bucket_key}")
                    asteroid_list = []  # Warte auf laufende Berechnung
                else:
                    # Markiere als "in progress" und trigger Worker
                    mark_computation_in_progress(computation_key, ttl_seconds=300)  # 5 Min Timeout
                    logger.warning(f"❌ Cache MISS - triggering asteroid worker for bucket {bucket_key}")
                    # Starte Task als FastAPI Background Task (läuft NACH Response)
                    # Wichtig: Übergebe BUCKET-Zeit, nicht Request-Zeit!
                    background_tasks.add_task(trigger_asteroid_worker, lat, lon, elevation, bucket_dt)
                    asteroid_list = []  # Gib zurück was im Cache ist (leer)
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Add back /asteroids endpoint for backward compatibility
@router.get("/asteroids")
async def get_asteroids(request: Request, lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False, time: Optional[str] = None, max_magnitude: float = None):
    """Alias for /bright_asteroids endpoint for backward compatibility."""
    return await get_bright_asteroids(request, lat, lon, elevation, location_name, save_location, time, max_magnitude)
