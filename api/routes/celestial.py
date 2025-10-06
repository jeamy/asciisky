from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from api.helpers import parse_time_param, get_location_params
from api.computation import compute_celestial_snapshot, CELESTIAL_BODIES
from api.background import trigger_background_precompute_window

router = APIRouter()

@router.get("/celestial")
async def get_celestial_objects(request: Request, lat: float = None, lon: float = None, elevation: float = None, time: Optional[str] = None):
    """Get positions of celestial objects. Always computed in real-time."""
    try:
        lat, lon, elevation = get_location_params(request, lat, lon, elevation)
        dt_utc = parse_time_param(time)
        
        # Always compute fresh - no caching for celestial objects
        snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
        
        # Trigger background precompute for asteroids/comets only
        await trigger_background_precompute_window(request.app, lat, lon, elevation, dt_utc, kinds=['asteroids','comets'])
        
        return snapshot
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
        
        # Trigger background precompute for asteroids/comets only
        await trigger_background_precompute_window(request.app, lat, lon, elevation, dt_utc, kinds=['asteroids','comets'])
        
        if body_id in snapshot["bodies"]:
            return {**snapshot["bodies"][body_id], "id": body_id}
        else:
            raise HTTPException(status_code=500, detail=f"Snapshot missing body '{body_id}'")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
