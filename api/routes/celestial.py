import asyncio
import logging
import time as monotonic_time

from fastapi import APIRouter, HTTPException, Request

from api.computation import (
    CELESTIAL_BODIES,
    compute_celestial_snapshot,
    compute_sunpath_year,
)
from api.helpers import get_location_params, parse_time_param
from cache_utils import location_key, normalize_location
from db_utils import get_sunpath_year as get_cached_sunpath_year
from db_utils import store_sunpath_year

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/celestial")
async def get_celestial_objects(request: Request, lat: float = None, lon: float = None, elevation: float = None, time: str | None = None):
    """Positions of the Sun, Moon and planets; rise/set/transit are cached per local day."""
    try:
        lat, lon, elevation = get_location_params(request, lat, lon, elevation)
        dt_utc = parse_time_param(time)
        return await asyncio.to_thread(compute_celestial_snapshot, lat, lon, elevation, dt_utc)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Celestial request failed")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/celestial/sunpath")
async def get_sunpath_year(request: Request, lat: float = None, lon: float = None, elevation: float = None, year: int = None, time: str | None = None):
    """Sunrise/sunset curve for a full year at the given or session location.

    One entry per calendar day with local sunrise/sunset, transit, twilight and
    day length; cached per location and year.
    """
    try:
        lat, lon, elevation = get_location_params(request, lat, lon, elevation)
        dt_utc = parse_time_param(time)
        target_year = year or dt_utc.year

        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        year_bucket = str(target_year)

        try:
            cached = await asyncio.to_thread(get_cached_sunpath_year, loc_key, year_bucket)
        except Exception:
            # Like storing below, the cache is best-effort: compute without it.
            logger.warning("Could not read cached sunpath for loc_key=%s year=%s", loc_key, year_bucket, exc_info=True)
            cached = None
        if cached is not None:
            logger.debug("Sunpath cache HIT for loc_key=%s year=%s", loc_key, year_bucket)
            return cached

        started = monotonic_time.monotonic()
        sunpath_data = await asyncio.to_thread(
            compute_sunpath_year, lat_norm, lon_norm, elev_norm, target_year,
        )
        logger.info(
            "Sunpath computed for loc_key=%s year=%s in %.2fs (points=%d)",
            loc_key, year_bucket, monotonic_time.monotonic() - started, len(sunpath_data["points"]),
        )

        try:
            await asyncio.to_thread(
                store_sunpath_year, loc_key, year_bucket, lat_norm, lon_norm, elev_norm, sunpath_data,
            )
        except Exception:
            # Caching is best-effort; the computed result is still returned.
            logger.warning("Could not store sunpath for loc_key=%s year=%s", loc_key, year_bucket, exc_info=True)

        return sunpath_data
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error while handling sunpath request")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/celestial/{body_id}")
async def get_celestial_object(body_id: str, request: Request, lat: float = None, lon: float = None, elevation: float = None, time: str | None = None):
    """Position of one solar system body (computes only that body)."""
    if body_id not in CELESTIAL_BODIES:
        raise HTTPException(status_code=404, detail=f"Celestial body '{body_id}' not found")
    try:
        lat, lon, elevation = get_location_params(request, lat, lon, elevation)
        dt_utc = parse_time_param(time)
        snapshot = await asyncio.to_thread(
            compute_celestial_snapshot, lat, lon, elevation, dt_utc, body_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Celestial body request failed")
        raise HTTPException(status_code=500, detail="Internal server error") from e
    body = snapshot["bodies"].get(body_id)
    if body is None:
        raise HTTPException(status_code=500, detail=f"Could not compute '{body_id}'")
    return {**body, "id": body_id}
