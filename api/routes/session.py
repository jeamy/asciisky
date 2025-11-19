import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from api.models import LocationPayload
from cache_utils import normalize_location, location_key
from db_utils import store_sunpath_year
from api.computation import compute_sunpath_year

router = APIRouter()


async def _precompute_sunpath_for_location(lat: float, lon: float, elevation: float) -> None:
    """Precompute yearly sunpath for the current year and store it in PostgreSQL.

    Runs compute_sunpath_year in a background thread and does not block the caller.
    """
    try:
        target_year = datetime.now(timezone.utc).year
        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        year_bucket = str(target_year)

        sunpath_data = await asyncio.to_thread(
            compute_sunpath_year,
            lat_norm,
            lon_norm,
            elev_norm,
            target_year,
        )

        store_sunpath_year(loc_key, year_bucket, lat_norm, lon_norm, elev_norm, sunpath_data)
    except Exception:
        # Precompute is best-effort and must never break the session endpoint
        return


@router.get("/session/location")
async def get_session_location(request: Request):
    loc = request.session.get("location")
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
    request.session["location"] = loc

    # Pre-compute sunpath data for the current year in the background
    # to ensure it's cached for the next page load.
    try:
        asyncio.create_task(
            _precompute_sunpath_for_location(
                loc["latitude"],
                loc["longitude"],
                loc["elevation"],
            )
        )
    except Exception:
        # If pre-computation fails, do not block the request.
        # The frontend will trigger computation on demand if needed.
        pass

    return {"ok": True, "location": loc}
