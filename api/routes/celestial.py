from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from api.helpers import parse_time_param, get_location_params, get_cache_data, store_cache_data
from api.computation import compute_celestial_snapshot, CELESTIAL_BODIES
from cache_utils import build_cache_path, normalize_location, location_key, time_bucket_utc
from api.background import trigger_background_precompute_window
import settings
import os

router = APIRouter()

CELESTIAL_USE_SQLITE = os.getenv('CELESTIAL_USE_SQLITE', 'true').lower() == 'true'
CELESTIAL_CACHE_BUCKET_HOURS = 1
CELESTIAL_CACHE_TTL_SECONDS = 49 * 3600

@router.get("/celestial")
async def get_celestial_objects(request: Request, lat: float = None, lon: float = None, elevation: float = None, time: Optional[str] = None):
    """Get positions of celestial objects."""
    try:
        lat, lon, elevation = get_location_params(request, lat, lon, elevation)
        dt_utc = parse_time_param(time)

        if time is not None:
            # Setup cache parameters
            lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
            loc_key = location_key(lat_norm, lon_norm, elev_norm)
            time_bucket = time_bucket_utc(dt_utc, CELESTIAL_CACHE_BUCKET_HOURS)
            cache_file = build_cache_path('celestial', lat, lon, elevation, dt=dt_utc, bucket_hours=CELESTIAL_CACHE_BUCKET_HOURS)
            
            # Try to get from cache
            if CELESTIAL_USE_SQLITE:
                from db_utils import get_celestial_snapshot
                sqlite_getter = get_celestial_snapshot
            else:
                sqlite_getter = None
                
            snapshot = get_cache_data(
                cache_file=cache_file,
                cache_ttl=CELESTIAL_CACHE_TTL_SECONDS,
                use_sqlite=CELESTIAL_USE_SQLITE,
                loc_key=loc_key,
                time_bucket=time_bucket,
                sqlite_getter=sqlite_getter
            )
            
            if isinstance(snapshot, dict) and "bodies" in snapshot:
                return snapshot

            # Generate new snapshot
            snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
            
            # Store in cache
            if CELESTIAL_USE_SQLITE:
                from db_utils import store_celestial_snapshot
                sqlite_storer = store_celestial_snapshot
            else:
                sqlite_storer = None
                
            store_cache_data(
                data=snapshot,
                cache_file=cache_file,
                use_sqlite=CELESTIAL_USE_SQLITE,
                loc_key=loc_key,
                time_bucket=time_bucket,
                sqlite_storer=sqlite_storer,
                lat=lat, lon=lon, elevation=elevation
            )
            
            await trigger_background_precompute_window(request.app, lat, lon, elevation, dt_utc, kinds=['celestial','asteroids','comets'])
            return snapshot

        # No time parameter - generate fresh snapshot
        snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
        cache_file = build_cache_path('celestial', lat, lon, elevation, dt=dt_utc, bucket_hours=CELESTIAL_CACHE_BUCKET_HOURS)
        store_cache_data(data=snapshot, cache_file=cache_file)
        return snapshot
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/celestial/{body_id}")
async def get_celestial_object(body_id: str, request: Request, lat: float = None, lon: float = None, elevation: float = None, time: Optional[str] = None):
    """Get position of a specific celestial object."""
    try:
        if body_id not in CELESTIAL_BODIES:
            raise HTTPException(status_code=404, detail=f"Celestial body '{body_id}' not found")

        lat, lon, elevation = get_location_params(request, lat, lon, elevation)
        dt_utc = parse_time_param(time)

        if time is not None:
            # Setup cache parameters
            lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
            loc_key = location_key(lat_norm, lon_norm, elev_norm)
            time_bucket = time_bucket_utc(dt_utc, CELESTIAL_CACHE_BUCKET_HOURS)
            cache_file = build_cache_path('celestial', lat, lon, elevation, dt=dt_utc, bucket_hours=CELESTIAL_CACHE_BUCKET_HOURS)
            
            # Try to get from cache
            if CELESTIAL_USE_SQLITE:
                from db_utils import get_celestial_snapshot
                sqlite_getter = get_celestial_snapshot
            else:
                sqlite_getter = None
                
            snapshot = get_cache_data(
                cache_file=cache_file,
                cache_ttl=CELESTIAL_CACHE_TTL_SECONDS,
                use_sqlite=CELESTIAL_USE_SQLITE,
                loc_key=loc_key,
                time_bucket=time_bucket,
                sqlite_getter=sqlite_getter
            )
            
            if isinstance(snapshot, dict) and "bodies" in snapshot and body_id in snapshot["bodies"]:
                return {**snapshot["bodies"][body_id], "id": body_id}

            # Generate new snapshot
            snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
            
            # Store in cache
            if CELESTIAL_USE_SQLITE:
                from db_utils import store_celestial_snapshot
                sqlite_storer = store_celestial_snapshot
            else:
                sqlite_storer = None
                
            store_cache_data(
                data=snapshot,
                cache_file=cache_file,
                use_sqlite=CELESTIAL_USE_SQLITE,
                loc_key=loc_key,
                time_bucket=time_bucket,
                sqlite_storer=sqlite_storer,
                lat=lat, lon=lon, elevation=elevation
            )
            
            await trigger_background_precompute_window(request.app, lat, lon, elevation, dt_utc, kinds=['celestial','asteroids','comets'])
            if body_id in snapshot["bodies"]:
                return {**snapshot["bodies"][body_id], "id": body_id}
            else:
                raise HTTPException(status_code=500, detail=f"Snapshot missing body '{body_id}'")

        # No time parameter - generate fresh snapshot
        snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
        cache_file = build_cache_path('celestial', lat, lon, elevation, dt=dt_utc, bucket_hours=CELESTIAL_CACHE_BUCKET_HOURS)
        store_cache_data(data=snapshot, cache_file=cache_file)
        
        if body_id in snapshot["bodies"]:
            return {**snapshot["bodies"][body_id], "id": body_id}
        else:
            raise HTTPException(status_code=500, detail=f"Snapshot missing body '{body_id}'")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
