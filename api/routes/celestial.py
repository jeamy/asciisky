from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from api.helpers import parse_time_param
from api.computation import compute_celestial_snapshot, CELESTIAL_BODIES
from cache_utils import build_cache_path, read_pickle_if_fresh, atomic_write_pickle, normalize_location, location_key, time_bucket_utc
from api.background import trigger_background_precompute_window
import settings
import os
import pickle

router = APIRouter()

CELESTIAL_USE_SQLITE = os.getenv('CELESTIAL_USE_SQLITE', 'true').lower() == 'true'
CELESTIAL_CACHE_BUCKET_HOURS = 1
CELESTIAL_CACHE_TTL_SECONDS = 49 * 3600

@router.get("/celestial")
async def get_celestial_objects(request: Request, lat: float = None, lon: float = None, elevation: float = None, time: Optional[str] = None):
    """Get positions of celestial objects."""
    try:
        location_settings = settings.get_location()
        session_loc = request.session.get("location", {}) if hasattr(request, "session") else {}
        if lat is None: lat = session_loc.get("latitude", location_settings["latitude"])
        if lon is None: lon = session_loc.get("longitude", location_settings["longitude"])
        if elevation is None: elevation = session_loc.get("elevation", location_settings["elevation"])

        dt_utc = parse_time_param(time)

        if time is not None:
            if CELESTIAL_USE_SQLITE:
                try:
                    from db_utils import get_celestial_snapshot
                    lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
                    loc_key = location_key(lat_norm, lon_norm, elev_norm)
                    time_bucket = time_bucket_utc(dt_utc, CELESTIAL_CACHE_BUCKET_HOURS)
                    snapshot = get_celestial_snapshot(loc_key, time_bucket, CELESTIAL_CACHE_TTL_SECONDS)
                    if isinstance(snapshot, dict) and "bodies" in snapshot:
                        return snapshot
                except Exception as e:
                    print(f"SQLite celestial cache failed: {e}")

            cache_file = build_cache_path('celestial', lat, lon, elevation, dt=dt_utc, bucket_hours=CELESTIAL_CACHE_BUCKET_HOURS)
            snapshot = read_pickle_if_fresh(cache_file, CELESTIAL_CACHE_TTL_SECONDS)
            if snapshot is None and os.path.exists(cache_file):
                with open(cache_file, 'rb') as f:
                    snapshot = pickle.load(f)
            if isinstance(snapshot, dict) and "bodies" in snapshot:
                return snapshot

            snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
            if CELESTIAL_USE_SQLITE:
                try:
                    from db_utils import store_celestial_snapshot
                    store_celestial_snapshot(loc_key, time_bucket, lat, lon, elevation, snapshot)
                except Exception as e:
                    print(f"Failed to store celestial snapshot in SQLite: {e}")
            try:
                atomic_write_pickle(cache_file, snapshot)
            except Exception: pass
            await trigger_background_precompute_window(request.app, lat, lon, elevation, dt_utc, kinds=['celestial','asteroids','comets'])
            return snapshot

        snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
        try:
            cache_file = build_cache_path('celestial', lat, lon, elevation, dt=dt_utc, bucket_hours=CELESTIAL_CACHE_BUCKET_HOURS)
            atomic_write_pickle(cache_file, snapshot)
        except Exception: pass
        return snapshot
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/celestial/{body_id}")
async def get_celestial_object(body_id: str, request: Request, lat: float = None, lon: float = None, elevation: float = None, time: Optional[str] = None):
    """Get position of a specific celestial object."""
    try:
        if body_id not in CELESTIAL_BODIES:
            raise HTTPException(status_code=404, detail=f"Celestial body '{body_id}' not found")

        location_settings = settings.get_location()
        session_loc = request.session.get("location", {}) if hasattr(request, "session") else {}
        if lat is None: lat = session_loc.get("latitude", location_settings["latitude"])
        if lon is None: lon = session_loc.get("longitude", location_settings["longitude"])
        if elevation is None: elevation = session_loc.get("elevation", location_settings["elevation"])

        dt_utc = parse_time_param(time)

        if time is not None:
            if CELESTIAL_USE_SQLITE:
                try:
                    from db_utils import get_celestial_snapshot
                    lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
                    loc_key = location_key(lat_norm, lon_norm, elev_norm)
                    time_bucket = time_bucket_utc(dt_utc, CELESTIAL_CACHE_BUCKET_HOURS)
                    snapshot = get_celestial_snapshot(loc_key, time_bucket, CELESTIAL_CACHE_TTL_SECONDS)
                    if isinstance(snapshot, dict) and "bodies" in snapshot and body_id in snapshot["bodies"]:
                        return {**snapshot["bodies"][body_id], "id": body_id}
                except Exception as e:
                    print(f"SQLite celestial cache failed: {e}")

            cache_file = build_cache_path('celestial', lat, lon, elevation, dt=dt_utc, bucket_hours=CELESTIAL_CACHE_BUCKET_HOURS)
            snapshot = read_pickle_if_fresh(cache_file, CELESTIAL_CACHE_TTL_SECONDS)
            if snapshot is None and os.path.exists(cache_file):
                with open(cache_file, 'rb') as f:
                    snapshot = pickle.load(f)
            if isinstance(snapshot, dict) and "bodies" in snapshot and body_id in snapshot["bodies"]:
                return {**snapshot["bodies"][body_id], "id": body_id}

            snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
            # ... (caching logic as above)
            await trigger_background_precompute_window(request.app, lat, lon, elevation, dt_utc, kinds=['celestial','asteroids','comets'])
            if body_id in snapshot["bodies"]:
                return {**snapshot["bodies"][body_id], "id": body_id}
            else:
                raise HTTPException(status_code=500, detail=f"Snapshot missing body '{body_id}'")

        snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
        # ... (caching logic as above)
        if body_id in snapshot["bodies"]:
            return {**snapshot["bodies"][body_id], "id": body_id}
        else:
            raise HTTPException(status_code=500, detail=f"Snapshot missing body '{body_id}'")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
