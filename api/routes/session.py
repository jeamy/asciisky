from fastapi import APIRouter, Request, BackgroundTasks
from datetime import datetime, timezone
from api.models import LocationPayload
from api.rabbitmq.task_publisher import get_task_publisher

router = APIRouter()

@router.get("/session/location")
async def get_session_location(request: Request):
    loc = request.session.get("location")
    return {"location": loc}


def _enqueue_sunpath_precompute(lat: float, lon: float, elevation: float) -> None:
    """Background task: enqueue yearly sunpath computation via RabbitMQ.

    Die eigentliche Berechnung findet im Unified Worker statt und wird in
    PostgreSQL gecached. Dieser Task soll nur die Queue befüllen und darf
    den Webserver nicht blockieren.
    """
    try:
        now_utc = datetime.now(timezone.utc)
        year = now_utc.year

        publisher = get_task_publisher()
        if not publisher:
            return

        location = {
            "latitude": float(lat),
            "longitude": float(lon),
            "elevation": float(elevation),
        }

        publisher.publish_sunpath_task(location, year, priority=10)
    except Exception:
        # Fehler beim Enqueue sollen die Session-Location nicht blockieren
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

    # Enqueue yearly sunpath computation for this location in the background
    background_tasks.add_task(
        _enqueue_sunpath_precompute,
        loc["latitude"],
        loc["longitude"],
        loc["elevation"],
    )

    return {"ok": True, "location": loc}
