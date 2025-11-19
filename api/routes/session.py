import asyncio
from fastapi import APIRouter, Request
from api.models import LocationPayload
from api.routes.celestial import get_sunpath_year

router = APIRouter()

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
        # Create a sub-request or call the function directly.
        # Running it as a background task ensures the session is updated immediately.
        asyncio.create_task(
            get_sunpath_year(
                request=request,
                lat=loc["latitude"],
                lon=loc["longitude"],
                elevation=loc["elevation"],
            )
        )
    except Exception:
        # If pre-computation fails, do not block the request.
        # The frontend will trigger it on demand if needed.
        pass

    return {"ok": True, "location": loc}
