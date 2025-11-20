from typing import Optional
from datetime import datetime, timezone
import asyncio
import logging

from fastapi import APIRouter, Request, HTTPException
from api.helpers import parse_time_param, get_location_params
from api.computation import compute_celestial_snapshot, CELESTIAL_BODIES, compute_sunpath_year
from cache_utils import normalize_location, location_key
from db_utils import get_sunpath_year as get_cached_sunpath_year, store_sunpath_year

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/celestial")
async def get_celestial_objects(request: Request, lat: float = None, lon: float = None, elevation: float = None, time: Optional[str] = None):
    """Get positions of celestial objects. Always computed in real-time."""
    try:
        lat, lon, elevation = get_location_params(request, lat, lon, elevation)
        dt_utc = parse_time_param(time)
        
        # Always compute fresh - no caching for celestial objects
        logger.info("Celestial request: lat=%.6f lon=%.6f elev=%.1f time=%s", lat, lon, elevation, dt_utc)
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
        logger.info("Sunpath request: lat=%.6f lon=%.6f elev=%.1f", lat, lon, elevation)
        dt_utc = parse_time_param(time)
        logger.info("Sunpath request: time=%s", dt_utc)
        target_year = year or dt_utc.year
        logger.info("Sunpath request: year=%s", target_year)

        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        logger.info("Sunpath request: lat=%.6f lon=%.6f elev=%.1f (norm=%.4f,%.4f,%d)", lat, lon, elevation, lat_norm, lon_norm, elev_norm)
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        logger.info("Sunpath request: loc_key=%s", loc_key)
        year_bucket = str(target_year)
        logger.info("Sunpath request: year_bucket=%s", year_bucket)

        nocache = "nocache" in request.query_params
        logger.info(
            "Sunpath request: lat=%.6f lon=%.6f elev=%.1f (norm=%.4f,%.4f,%d) year=%s loc_key=%s nocache=%s",
            lat,
            lon,
            elevation,
            lat_norm,
            lon_norm,
            elev_norm,
            year_bucket,
            loc_key,
            nocache,
        )

        # Respect nocache flag for debugging, otherwise prefer cached data
        if nocache:
            cached = None
        else:
            cached = get_cached_sunpath_year(loc_key, year_bucket)

        if cached is not None:
            logger.info("Sunpath cache HIT for loc_key=%s year=%s", loc_key, year_bucket)
            return cached

        logger.info("Sunpath cache MISS for loc_key=%s year=%s - starting computation", loc_key, year_bucket)

        start_ts = datetime.now(timezone.utc)

        # Compute sunpath directly in a background thread to avoid blocking the event loop
        sunpath_data = await asyncio.to_thread(
            compute_sunpath_year,
            lat_norm,
            lon_norm,
            elev_norm,
            target_year,
        )

        end_ts = datetime.now(timezone.utc)
        duration = (end_ts - start_ts).total_seconds()
        try:
            points_len = len(sunpath_data.get("points", [])) if isinstance(sunpath_data, dict) else None
        except Exception:
            points_len = None
        logger.info(
            "Sunpath computation DONE for loc_key=%s year=%s in %.2fs (points=%s)",
            loc_key,
            year_bucket,
            duration,
            points_len,
        )

        try:
            store_sunpath_year(loc_key, year_bucket, lat_norm, lon_norm, elev_norm, sunpath_data)
        except Exception:
            # Caching is best-effort; computation result is still returned
            pass

        return sunpath_data
    except Exception as e:
        logger.exception("Error while handling sunpath request: %s", e)
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
