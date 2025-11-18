from fastapi import APIRouter, Request, BackgroundTasks
from datetime import datetime, timezone
from api.models import LocationPayload
from cache_utils import normalize_location, location_key
from db_utils import get_sunpath_year as get_cached_sunpath_year, store_sunpath_year
from api.computation import compute_sunpath_year

router = APIRouter()

@router.get("/session/location")
async def get_session_location(request: Request):
    loc = request.session.get("location")
    return {"location": loc}


def _precompute_sunpath_for_location(lat: float, lon: float, elevation: float) -> None:
    """Background task: precompute and cache yearly sunpath for current year."""
    try:
        now_utc = datetime.now(timezone.utc)
        year = now_utc.year

        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        year_bucket = str(year)

        cached = get_cached_sunpath_year(loc_key, year_bucket)
        if cached is not None:
            return

        result = compute_sunpath_year(lat, lon, elevation, year)
        try:
            store_sunpath_year(loc_key, year_bucket, lat, lon, elevation, result)
        except Exception:
            # Cache-Fehler im Hintergrund ignorieren
            pass
    except Exception:
        # Hintergrundfehler nicht nach außen durchreichen
        return


@router.post("/session/location")
async def set_session_location(payload: LocationPayload, request: Request, background_tasks: BackgroundTasks):
    loc = {
        "latitude": float(payload.latitude),
        "longitude": float(payload.longitude),
        "elevation": float(payload.elevation),
    }
    if payload.name:
        loc["name"] = payload.name
    request.session["location"] = loc

    # Precompute yearly sunpath for this location in the background
    background_tasks.add_task(
        _precompute_sunpath_for_location,
        loc["latitude"],
        loc["longitude"],
        loc["elevation"],
    )

    return {"ok": True, "location": loc}
