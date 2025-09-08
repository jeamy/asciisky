from fastapi import APIRouter, Request
from api.models import LocationPayload

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
    return {"ok": True, "location": loc}
