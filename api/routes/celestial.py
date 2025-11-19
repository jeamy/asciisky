from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from api.helpers import parse_time_param, get_location_params
from api.computation import compute_celestial_snapshot, CELESTIAL_BODIES, compute_sunpath_year
from cache_utils import normalize_location, location_key
from db_utils import get_sunpath_year as get_cached_sunpath_year, store_sunpath_year
from api.rabbitmq.task_publisher import get_task_publisher

router = APIRouter()

@router.get("/celestial")
async def get_celestial_objects(request: Request, lat: float = None, lon: float = None, elevation: float = None, time: Optional[str] = None):
    """Get positions of celestial objects. Always computed in real-time."""
    try:
        lat, lon, elevation = get_location_params(request, lat, lon, elevation)
        dt_utc = parse_time_param(time)
        
        # Always compute fresh - no caching for celestial objects
        snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
        
        # No background tasks needed - celestial is always computed fresh
        return snapshot
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

 
@router.get("/celestial/sunpath")
async def get_sunpath_year(request: Request, lat: float = None, lon: float = None, elevation: float = None, year: int = None, time: Optional[str] = None):
    """Return sunrise/sunset curve for a full year at the given or session location.

    The result contains one entry per calendar day with local sunrise/sunset and day length
    in hours, suitable for plotting as a curve.
    """
    try:
        lat, lon, elevation = get_location_params(request, lat, lon, elevation)
        dt_utc = parse_time_param(time)
        target_year = year or dt_utc.year

        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        year_bucket = str(target_year)

        # Force re-computation if nocache=1 is present
        if "nocache" in request.query_params:
            pass
        else:
            cached = get_cached_sunpath_year(loc_key, year_bucket)
            if cached is not None:
                return cached

        # Data is not in cache or nocache=1, compute it now
        sunpath_data = compute_sunpath_year(lat_norm, lon_norm, elev_norm, target_year)

        # Store in cache for future requests
        store_sunpath_year(loc_key, year_bucket, sunpath_data)

        return sunpath_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/celestial/{body_id}")
async def get_celestial_object(body_id: str, request: Request, lat: float = None, lon: float = None, elevation: float = None, time: Optional[str] = None):
    """Get position of a specific celestial object. Always computed in real-time."""
    try:
        if body_id not in CELESTIAL_BODIES:
            raise HTTPException(status_code=404, detail=f"Celestial body '{body_id}' not found")

        lat, lon, elevation = get_location_params(request, lat, lon, elevation)
        dt_utc = parse_time_param(time)
        
        # Always compute fresh - no caching for celestial objects
        snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
        
        # No background tasks needed - celestial is always computed fresh
        if body_id in snapshot["bodies"]:
            return {**snapshot["bodies"][body_id], "id": body_id}
        else:
            raise HTTPException(status_code=500, detail=f"Snapshot missing body '{body_id}'")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
