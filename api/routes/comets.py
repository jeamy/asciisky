from typing import Optional
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from api.helpers import parse_time_param
from api.cache_interpolation import load_comets_with_interpolation
from api.computation import ts, eph
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


async def trigger_comet_worker(lat, lon, elevation, dt_utc):
    """
    Triggert Comet-Worker für On-Demand Berechnung
    
    Args:
        lat, lon, elevation: Location
        dt_utc: Zeit
    """
    try:
        import pika
        import json
        rabbitmq_url = os.environ.get('RABBITMQ_URL', 'amqp://admin:changeme@rabbitmq:5672/')
        logger.info(f"🚀 Triggering comet worker: url={rabbitmq_url}")
        
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
                
                task_id = f"comet_{int(time.time())}_{uuid.uuid4().hex[:8]}"
                # Task-Daten
                task = {
                    'task_id': task_id,
                    'kind': 'comet',  # Required for unified_worker
                    'location': {
                        'latitude': lat,
                        'longitude': lon,
                        'elevation': elevation
                    },
                    'time_bucket': dt_utc.isoformat(),
                    'magnitude': 14.0  # Max magnitude for comets
                }
                
                logger.info(f"📤 Publishing task: {task['task_id']}")
                
                # Publiziere an computation.direct Exchange mit routing_key compute.comet
                channel.basic_publish(
                    exchange='computation.direct',
                    routing_key='compute.comet',
                    body=json.dumps(task),
                    properties=pika.BasicProperties(
                        delivery_mode=2,  # persistent
                        priority=5
                    )
                )
                
                connection.close()
                logger.info(f"✅ Published comet task {task['task_id']} to comet.compute queue")
            except Exception as e:
                logger.error(f"❌ Error in publish_task: {e}", exc_info=True)
                raise
        
        await asyncio.to_thread(publish_task)
        
    except Exception as e:
        logger.error(f"❌ Failed to trigger comet worker: {e}", exc_info=True)


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
async def get_comets(request: Request, background_tasks: BackgroundTasks, lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False, max_comets: int = 1000, time: Optional[str] = None, max_magnitude: float = None):
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
        
        # Feature Flag: Smart Interpolation aktivieren?
        from config.interpolation_config import is_smart_interpolation_enabled, get_interpolation_strategy
        use_smart_interpolation = is_smart_interpolation_enabled(user_id)
        interpolation_strategy = get_interpolation_strategy(user_id)
        
        logger.info(f"User {user_id}: smart_interpolation={use_smart_interpolation}, strategy={interpolation_strategy.value}")
        
        # Cache-First Strategie mit asynchroner Berechnung
        try:
            logger.info(f"Checking cache for comets: lat={lat}, lon={lon}, time={dt_utc.isoformat()}")
            
            # Berechne Bucket-Zeit (gleiche Logik wie Worker!)
            from cache_utils import time_bucket_utc
            bucket_dt = dt_utc.replace(minute=0, second=0, microsecond=0)
            bucket_key = time_bucket_utc(bucket_dt, comets.COMET_CACHE_BUCKET_HOURS)
            
            # Wähle Interpolationsmethode basierend auf Feature Flags
            if use_smart_interpolation:
                from api.smart_interpolation import load_comets_with_smart_interpolation
                comet_list = load_comets_with_smart_interpolation(
                    lat, lon, elevation, dt_utc,
                    bucket_hours=comets.COMET_CACHE_BUCKET_HOURS,
                    ttl_seconds=comets.COMET_CACHE_TTL_SECONDS,
                    use_postgres=True
                )
            else:
                # Original nearest-bucket strategy
                comet_list = load_comets_with_interpolation(
                    lat, lon, elevation, dt_utc,
                    bucket_hours=comets.COMET_CACHE_BUCKET_HOURS,
                    ttl_seconds=comets.COMET_CACHE_TTL_SECONDS,
                    use_postgres=True
                )
            
            if isinstance(comet_list, list) and comet_list:
                logger.info(f"✅ Cache HIT for comets: {len(comet_list)} found")
            else:
                # Cache-Miss: Prüfe ob Berechnung bereits läuft
                from cache_utils import normalize_location, location_key
                lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
                loc_key = location_key(lat_norm, lon_norm, elev_norm)
                
                computation_key = f"computing:comet:{loc_key}:{bucket_key}"
                
                # Prüfe ob bereits in Berechnung
                from db_utils import is_computation_in_progress, mark_computation_in_progress
                if is_computation_in_progress(computation_key):
                    logger.info(f"⏳ Computation already in progress for bucket {bucket_key}")
                    comet_list = []  # Warte auf laufende Berechnung
                else:
                    # Markiere als "in progress" und trigger Worker
                    mark_computation_in_progress(computation_key, ttl_seconds=300)  # 5 Min Timeout
                    logger.warning(f"❌ Cache MISS - triggering comet worker for bucket {bucket_key}")
                    # Starte Task als FastAPI Background Task (läuft NACH Response)
                    # Wichtig: Übergebe BUCKET-Zeit, nicht Request-Zeit!
                    background_tasks.add_task(trigger_comet_worker, lat, lon, elevation, bucket_dt)
                    comet_list = []  # Gib zurück was im Cache ist (leer)
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
