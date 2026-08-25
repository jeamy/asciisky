import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from api.computation import compute_sunpath_year
from api.models import LocationPayload
from cache_utils import location_key, normalize_location
from db_utils import (
    claim_precompute_task,
    get_sunpath_year,
    release_precompute_task,
    store_sunpath_year,
)
from timezone_utils import get_timezone_name
from workers.worker_utils import precompute_task_key

router = APIRouter()
logger = logging.getLogger(__name__)


async def _precompute_sunpath_for_location(
    lat: float, lon: float, elevation: float, task_key: str
) -> None:
    """Precompute yearly sunpath for the current year and store it in PostgreSQL.

    Runs compute_sunpath_year in a background thread and does not block the caller.
    """
    try:
        target_year = datetime.now(timezone.utc).year
        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        year_bucket = str(target_year)

        cached = await asyncio.to_thread(get_sunpath_year, loc_key, year_bucket)
        if cached is not None:
            return

        sunpath_data = await asyncio.to_thread(
            compute_sunpath_year,
            lat_norm,
            lon_norm,
            elev_norm,
            target_year,
        )

        await asyncio.to_thread(
            store_sunpath_year,
            loc_key,
            year_bucket,
            lat_norm,
            lon_norm,
            elev_norm,
            sunpath_data,
        )
    except Exception:
        logger.exception("Sunpath precompute failed")
    finally:
        await asyncio.to_thread(release_precompute_task, task_key)


@router.get("/session/location")
async def get_session_location(request: Request):
    loc = request.session.get("location")
    try:
        if isinstance(loc, dict) and "timezone" not in loc:
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            if lat is not None and lon is not None:
                loc = {**loc, "timezone": get_timezone_name(float(lat), float(lon))}
                request.session["location"] = loc
    except Exception:
        pass
    return {"location": loc}


@router.post("/session/location")
async def set_session_location(payload: LocationPayload, request: Request):
    loc = {
        "latitude": float(payload.latitude),
        "longitude": float(payload.longitude),
        "elevation": float(payload.elevation),
    }
    if payload.name:
        loc["name"] = payload.name

    try:
        loc["timezone"] = get_timezone_name(loc["latitude"], loc["longitude"])
    except Exception:
        loc["timezone"] = "UTC"
    request.session["location"] = loc

    # Pre-compute sunpath data only if no cache/task for this location/year
    # exists.  Persistent claims also deduplicate across API processes.
    try:
        target_year = datetime.now(timezone.utc).year
        lat_norm, lon_norm, elev_norm = normalize_location(
            loc["latitude"], loc["longitude"], loc["elevation"]
        )
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        if await asyncio.to_thread(get_sunpath_year, loc_key, str(target_year)) is None:
            task = {
                "type": "precompute",
                "kind": "sunpath",
                "location": {"latitude": lat_norm, "longitude": lon_norm, "elevation": elev_norm},
                "time_bucket": datetime(target_year, 1, 1, tzinfo=timezone.utc).isoformat(),
            }
            task_key = precompute_task_key(task)
            if await asyncio.to_thread(claim_precompute_task, task_key):
                background = asyncio.create_task(
                    _precompute_sunpath_for_location(
                        loc["latitude"], loc["longitude"], loc["elevation"], task_key
                    )
                )
                request.app.state.precompute_tasks[task_key] = background
                background.add_done_callback(
                    lambda _task: request.app.state.precompute_tasks.pop(task_key, None)
                )
    except Exception:
        # This optimization must not make the location update fail.
        logger.exception("Could not schedule sunpath precompute")

    return {"ok": True, "location": loc}
