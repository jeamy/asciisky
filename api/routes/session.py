from datetime import datetime, timezone

from fastapi import APIRouter, Request
from api.models import LocationPayload
from api.rabbitmq.task_publisher import get_task_publisher

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
        publisher = get_task_publisher()
        if publisher is not None:
            current_year = datetime.now(timezone.utc).year
            publisher.publish_sunpath_task(
                {
                    "latitude": loc["latitude"],
                    "longitude": loc["longitude"],
                    "elevation": loc["elevation"],
                    "name": loc.get("name", ""),
                },
                current_year,
                priority=9,
            )
    except Exception:
        # If pre-computation fails, do not block the request.
        # The frontend will trigger it on demand if needed.
        pass

    return {"ok": True, "location": loc}
