from typing import Optional
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from api.helpers import parse_time_param, get_location_params, resolve_magnitude_filter
from api.cache_interpolation import load_comets_with_interpolation
from api.computation import ts, eph
from config.interpolation_config import is_smart_interpolation_enabled, get_interpolation_strategy
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
                    'type': 'precompute',
                    'kind': 'comets',  # Required for unified_worker (plural!)
                    'location': {
                        'latitude': lat,
                        'longitude': lon,
                        'elevation': elevation
                    },
                    'time_bucket': dt_utc.isoformat(),
                    'magnitude': 14.0  # Max magnitude for comets
                }
                
                logger.info(f"📤 Publishing task: {task['task_id']}")
                from db_utils import claim_precompute_task, release_precompute_task
                from workers.worker_utils import precompute_task_key
                key = precompute_task_key(task)
                if not claim_precompute_task(key):
                    logger.info("Equivalent comet task already queued: %s", key)
                    connection.close()
                    return
                
                # Publiziere an computation.direct Exchange mit routing_key compute.comet
                # On-Demand Tasks für aktuellen Standort/Zeitpunkt mit höchster Priorität
                channel.basic_publish(
                    exchange='computation.direct',
                    routing_key='compute.comet',
                    body=json.dumps(task),
                    properties=pika.BasicProperties(
                        delivery_mode=2,  # persistent
                        priority=10,
                        message_id=key,
                    )
                )
                
                connection.close()
                logger.info(f"✅ Published comet task {task['task_id']} to comet.compute queue")
            except Exception as e:
                if 'key' in locals():
                    try:
                        release_precompute_task(key)
                    except Exception:
                        logger.exception("Could not release comet task claim")
                logger.error(f"❌ Error in publish_task: {e}", exc_info=True)
                raise
        
        await asyncio.to_thread(publish_task)
        
    except Exception as e:
        logger.error(f"❌ Failed to trigger comet worker: {e}", exc_info=True)


@router.get("/comets")
async def get_comets(request: Request, background_tasks: BackgroundTasks, lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False, time: Optional[str] = None, max_magnitude: float = None):
    """Get comets with real MPC data and rise/set/transit times."""
    try:
        lat, lon, elevation = get_location_params(request, lat, lon, elevation)

        if save_location and lat is not None and lon is not None and elevation is not None:
            settings.set_location(lat, lon, elevation, location_name)

        # Magnitude-Filter aus user_settings oder Parameter verwenden
        if max_magnitude is None:
            max_magnitude = resolve_magnitude_filter(request, 'cometMaxMagnitude', comets.MAX_APPARENT_MAGNITUDE)

        dt_utc = parse_time_param(time)
        location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        
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
                lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
                loc_key = location_key(lat_norm, lon_norm, elev_norm)
                
                computation_key = f"computing:comet:{loc_key}:{bucket_key}"
                
                # Prüfe ob bereits in Berechnung
                from db_utils import is_computation_in_progress, computation_lock  # noqa: PLC0415
                if is_computation_in_progress(computation_key):
                    logger.info(f"⏳ Computation already in progress for bucket {bucket_key}")
                    comet_list = []  # Warte auf laufende Berechnung
                else:
                    # Markiere als "in progress" und trigger Worker
                    computation_lock(computation_key, ttl_seconds=300)  # 5 Min Timeout
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
