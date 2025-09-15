import os
import json
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from api.models import PrecomputeRangeRequest
from api.helpers import get_location_from_request, parse_time_param
from api.background import trigger_background_precompute_range, _hour_floor
from cache_utils import normalize_location, location_key, CACHE_ROOT, build_cache_path, read_pickle_if_fresh, time_bucket_utc
import settings
import bright_asteroids
import comets
from datetime import datetime, timedelta, timezone

router = APIRouter()

@router.post("/precompute_range")
async def precompute_range(request: Request, body: PrecomputeRangeRequest):
    """Trigger background precomputation of celestial data for a date range."""
    try:
        location = await get_location_from_request(request, body.lat, body.lon, body.elevation)
        if not location:
            return JSONResponse(status_code=400, content={'error': 'Invalid location'})

        lat, lon, elevation = location['latitude'], location['longitude'], location['elevation']

        start_dt = parse_time_param(body.start_date)
        end_dt = parse_time_param(body.end_date)

        result = await trigger_background_precompute_range(request.app, lat, lon, elevation, start_dt, end_dt, kinds=['celestial', 'asteroids', 'comets'])
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})

@router.get("/precompute_range/{task_id}")
async def get_precompute_status(request: Request, task_id: str):
    """Get status of a background precompute task by its ID."""
    try:
        if not hasattr(request.app, 'precompute_tasks') or task_id not in request.app.precompute_tasks:
            return JSONResponse(status_code=404, content={'error': f'Task {task_id} not found'})

        task_info = request.app.precompute_tasks[task_id].copy()

        if task_info.get('worker_process'):
            status_file = f"cache/task_status_{task_id}.json"
            if os.path.exists(status_file):
                with open(status_file, 'r') as f:
                    worker_status = json.load(f)
                task_info.update(worker_status)

        return task_info
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})

@router.get("/cache_status")
async def get_cache_status(request: Request, loc_key: Optional[str] = None, lat: Optional[float] = None, lon: Optional[float] = None, elevation: Optional[float] = None):
    """Report status of the precomputed cache system."""
    try:
        time = request.query_params.get('time')
        kinds = [k.strip() for k in os.environ.get("ASCII_SKY_PRECOMPUTE_KINDS", "celestial,asteroids,comets").split(",") if k.strip()]
        horizon_hours = int(os.environ.get("ASCII_SKY_PRECOMPUTE_HOURS", "48"))

        dt_utc = parse_time_param(time)
        window_start = _hour_floor(dt_utc)
        window_end = window_start + timedelta(hours=horizon_hours)

        requested = None
        if loc_key:
            try:
                parts = loc_key.split("_")
                if len(parts) == 3 and parts[0].startswith("lat") and parts[1].startswith("lon") and parts[2].startswith("el"):
                    lat_s, lon_s, el_s = parts[0][3:], parts[1][3:], parts[2][2:]
                    lat_v, lon_v, elev_v = float(lat_s), float(lon_s), float(int(el_s))
                    lat_n, lon_n, elev_n = normalize_location(lat_v, lon_v, elev_v)
                    requested = {"latitude": lat_n, "longitude": lon_n, "elevation": elev_n, "name": "", "loc_key": loc_key}
            except Exception:
                requested = None

        if requested is None and (lat is not None and lon is not None):
            try:
                elev_in = float(elevation) if elevation is not None else 0.0
                lat_n, lon_n, elev_n = normalize_location(float(lat), float(lon), elev_in)
                key = location_key(lat_n, lon_n, elev_n)
                requested = {"latitude": lat_n, "longitude": lon_n, "elevation": elev_n, "name": "", "loc_key": key}
            except Exception:
                requested = None

        dedup = {}
        if requested is not None:
            dedup[requested["loc_key"]] = {k: v for k, v in requested.items() if k != 'loc_key'}
        else:
            targets = []
            try:
                from precompute_worker import get_target_locations as _get_targets
                targets = _get_targets() or []
            except Exception:
                pass
            if not targets:
                try:
                    base = settings.get_location()
                    if isinstance(base, dict) and "latitude" in base and "longitude" in base:
                        targets = [{**base}]
                except Exception:
                    pass
            for loc in targets:
                try:
                    lat_n, lon_n, elev_n = normalize_location(loc.get("latitude", 0.0), loc.get("longitude", 0.0), loc.get("elevation", 0.0))
                    key = location_key(lat_n, lon_n, elev_n)
                    dedup[key] = {"latitude": lat_n, "longitude": lon_n, "elevation": elev_n, "name": loc.get("name", "")}
                except Exception:
                    continue

        def _parse_bucket(label: str) -> Optional[datetime]:
            try:
                return datetime.strptime(label, "%Y%m%dT%H").replace(tzinfo=timezone.utc)
            except Exception:
                return None

        try:
            from db_utils import get_database_stats
            db_stats = get_database_stats()
        except Exception:
            db_stats = {}

        totals = {k: 0 for k in kinds}
        locations_out = []
        for loc_key_str, loc_data in dedup.items():
            counts, earliest, latest = {}, {}, {}
            for kind in kinds:
                counts[kind] = 0
                earliest[kind] = None
                latest[kind] = None
                
                # Scan cache directory for this kind and location
                cache_dir = os.path.join(CACHE_ROOT, kind, loc_key_str)
                if os.path.exists(cache_dir):
                    try:
                        bucket_files = [f for f in os.listdir(cache_dir) if f.endswith('.pkl')]
                        counts[kind] = len(bucket_files)
                        totals[kind] += counts[kind]
                        
                        if bucket_files:
                            # Parse bucket timestamps to find earliest/latest
                            bucket_times = []
                            for bucket_file in bucket_files:
                                bucket_name = bucket_file.replace('.pkl', '')
                                bucket_dt = _parse_bucket(bucket_name)
                                if bucket_dt:
                                    bucket_times.append(bucket_dt)
                            
                            if bucket_times:
                                bucket_times.sort()
                                earliest[kind] = bucket_times[0].isoformat()
                                latest[kind] = bucket_times[-1].isoformat()
                    except Exception as e:
                        print(f"Error scanning cache for {kind}/{loc_key_str}: {e}")
                        
            locations_out.append({**loc_data, "loc_key": loc_key_str, "counts": counts, "earliest": earliest, "latest": latest})

        max_precompute_hours = int(os.environ.get("ASCII_SKY_MAX_PRECOMPUTE_HOURS", "168"))

        return {
            "now_utc": dt_utc.isoformat(), "precompute_horizon_hours": horizon_hours,
            "max_precompute_hours": max_precompute_hours, "window": {"start": window_start.isoformat(), "end": window_end.isoformat()},
            "kinds": kinds, "locations": locations_out, "totals": totals, "database": db_stats,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cache_availability")
async def get_cache_availability(request: Request, lat: Optional[float] = None, lon: Optional[float] = None, elevation: Optional[float] = None):
    """Return availability booleans for the current bucket for celestial/asteroids/comets.
    The decision respects SQLite (if enabled) and pickle cache TTLs.
    """
    try:
        # Resolve location from session or params
        from api.helpers import get_location_from_request
        location = await get_location_from_request(request, lat, lon, elevation)
        if not location:
            return JSONResponse(status_code=400, content={"error": "Invalid location"})

        lat_v, lon_v, elev_v = location["latitude"], location["longitude"], location["elevation"]
        lat_n, lon_n, elev_n = normalize_location(lat_v, lon_v, elev_v)
        key = location_key(lat_n, lon_n, elev_n)

        # Determine current bucket
        time_param = request.query_params.get('time')
        from api.helpers import parse_time_param
        dt_utc = parse_time_param(time_param)

        # Celestial constants (aligned with routes)
        CELESTIAL_CACHE_BUCKET_HOURS = 1
        CELESTIAL_CACHE_TTL_SECONDS = 49 * 3600

        available = {"celestial": False, "asteroids": False, "comets": False}

        # Celestial availability
        try:
            use_sqlite = os.getenv('CELESTIAL_USE_SQLITE', 'true').lower() == 'true'
            bucket = time_bucket_utc(dt_utc, CELESTIAL_CACHE_BUCKET_HOURS)
            if use_sqlite:
                try:
                    from db_utils import get_celestial_snapshot
                    if get_celestial_snapshot(key, bucket, CELESTIAL_CACHE_TTL_SECONDS):
                        available["celestial"] = True
                except Exception:
                    pass
            if not available["celestial"]:
                path = build_cache_path('celestial', lat_v, lon_v, elev_v, dt=dt_utc, bucket_hours=CELESTIAL_CACHE_BUCKET_HOURS)
                if read_pickle_if_fresh(path, CELESTIAL_CACHE_TTL_SECONDS) is not None:
                    available["celestial"] = True
        except Exception:
            pass

        # Asteroids availability
        try:
            import bright_asteroids
            bucket = time_bucket_utc(dt_utc, bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS)
            if getattr(bright_asteroids, 'ASTEROID_USE_SQLITE', False):
                try:
                    from db_utils import get_asteroid_positions
                    if get_asteroid_positions(key, bucket, bright_asteroids.ASTEROID_CACHE_TTL_SECONDS):
                        available["asteroids"] = True
                except Exception:
                    pass
            if not available["asteroids"]:
                path = build_cache_path('asteroids', lat_v, lon_v, elev_v, dt=dt_utc, bucket_hours=bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS)
                if read_pickle_if_fresh(path, bright_asteroids.ASTEROID_CACHE_TTL_SECONDS) is not None:
                    available["asteroids"] = True
        except Exception:
            pass

        # Comets availability
        try:
            import comets
            bucket = time_bucket_utc(dt_utc, comets.COMET_CACHE_BUCKET_HOURS)
            if getattr(comets, 'COMET_USE_SQLITE', False):
                try:
                    from db_utils import get_comet_positions
                    if get_comet_positions(key, bucket, comets.COMET_CACHE_TTL_SECONDS):
                        available["comets"] = True
                except Exception:
                    pass
            if not available["comets"]:
                path = build_cache_path('comets', lat_v, lon_v, elev_v, dt=dt_utc, bucket_hours=comets.COMET_CACHE_BUCKET_HOURS)
                if read_pickle_if_fresh(path, comets.COMET_CACHE_TTL_SECONDS) is not None:
                    available["comets"] = True
        except Exception:
            pass

        return {"location": {"lat": lat_n, "lon": lon_n, "elevation": elev_n, "loc_key": key}, "time": dt_utc.isoformat(), "available": available}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/precompute_window")
async def precompute_window(request: Request):
    """Trigger background precompute for a forward/backward window around the given time.
    Request body JSON: { lat, lon, elevation, kinds?: list[str] | comma string, time?: ISO8601 }
    Falls back to environment kinds and current time if not provided.
    """
    try:
        payload = await request.json()
        lat = float(payload.get('lat'))
        lon = float(payload.get('lon'))
        elevation = float(payload.get('elevation', 0.0))
        kinds_raw = payload.get('kinds')
        time_str = payload.get('time')

        if lat is None or lon is None:
            return JSONResponse(status_code=400, content={'error': 'lat/lon are required'})

        if isinstance(kinds_raw, list):
            kinds = [str(k).strip() for k in kinds_raw if str(k).strip()]
        elif isinstance(kinds_raw, str):
            kinds = [k.strip() for k in kinds_raw.split(',') if k.strip()]
        else:
            kinds = [k.strip() for k in os.environ.get("ASCII_SKY_PRECOMPUTE_KINDS", "celestial,asteroids,comets").split(',') if k.strip()]

        # Parse time param (defaults to now if None)
        dt_utc = parse_time_param(time_str)

        # Trigger background window precompute (guarded inside)
        from api.background import trigger_background_precompute_window
        await trigger_background_precompute_window(request.app, lat, lon, elevation, dt_utc, kinds=kinds)

        return { 'status': 'started', 'message': 'Background precompute window triggered', 'kinds': kinds, 'time': dt_utc.isoformat() }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
