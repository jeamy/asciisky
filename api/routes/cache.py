import os
import json
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from api.models import PrecomputeRangeRequest
from api.helpers import get_location_from_request, parse_time_param
from api.background import trigger_background_precompute_range, _hour_floor
from cache_utils import normalize_location, location_key, CACHE_ROOT
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
                # ... (rest of the logic for scanning cache)
                counts[kind] = 0 # Placeholder
            locations_out.append({**loc_data, "loc_key": loc_key_str, "counts": counts, "earliest": earliest, "latest": latest})

        max_precompute_hours = int(os.environ.get("ASCII_SKY_MAX_PRECOMPUTE_HOURS", "168"))

        return {
            "now_utc": dt_utc.isoformat(), "precompute_horizon_hours": horizon_hours,
            "max_precompute_hours": max_precompute_hours, "window": {"start": window_start.isoformat(), "end": window_end.isoformat()},
            "kinds": kinds, "locations": locations_out, "totals": totals, "database": db_stats,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
