from typing import Any, Dict, Optional

import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from settings import DEFAULT_SETTINGS, get_default_magnitude_filters
from db_utils import get_user_settings as db_get_user_settings, save_user_settings as db_save_user_settings


logger = logging.getLogger(__name__)

router = APIRouter()


class UserSettingsModel(BaseModel):
    location: Optional[Dict[str, Any]] = None
    display: Optional[Dict[str, Any]] = None
    simTime: Optional[Dict[str, Any]] = None
    filters: Optional[Dict[str, Any]] = None
    theme: Optional[str] = None
    language: Optional[str] = None
    options: Optional[Dict[str, Any]] = None


def _default_user_settings() -> Dict[str, Any]:
    """Base defaults matching the structure of SettingsManager.settings."""
    base_location = DEFAULT_SETTINGS.get("location", {})
    base_filters = DEFAULT_SETTINGS.get("filters") or get_default_magnitude_filters()

    return {
        "location": {
            "latitude": float(base_location.get("latitude", 48.2082)),
            "longitude": float(base_location.get("longitude", 16.3738)),
            "elevation": float(base_location.get("elevation", 171.0)),
            "name": base_location.get("name", "Wien"),
        },
        "display": {
            "horizontalShift": 0,
        },
        "simTime": {
            "enabled": False,
            "offsetMinutes": 0,
        },
        "filters": base_filters,
        "theme": "green",
        "language": "de",
        "options": {},
    }


def _merge_settings(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow merge with simple nested-dict support for known sections."""
    result: Dict[str, Any] = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            nested = dict(result[key])
            nested.update(value)
            result[key] = nested
        else:
            result[key] = value
    return result


@router.get("/user/settings")
async def get_user_settings(request: Request) -> Dict[str, Any]:
    """Return settings JSON for the currently authenticated user.

    The user_id is taken from the session; unauthenticated callers receive 401.
    """
    user_id = request.session.get("user_id")
    logger.info("GET /user/settings user_id=%s", user_id)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        stored = db_get_user_settings(int(user_id))
        logger.info("GET /user/settings user_id=%s stored_exists=%s", user_id, stored is not None)
        if stored is None:
            return _default_user_settings()
        return _merge_settings(_default_user_settings(), stored)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/user/settings")
async def update_user_settings(
    payload: UserSettingsModel,
    request: Request,
) -> Dict[str, Any]:
    """Upsert settings JSON for the currently authenticated user.

    The request body corresponds to the structure of SettingsManager.settings.
    Partial updates are allowed; missing fields fall back to existing values or
    defaults.
    """
    user_id = request.session.get("user_id")
    logger.info("PUT /user/settings user_id=%s", user_id)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        current = db_get_user_settings(int(user_id)) or {}
        incoming = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
        logger.info("PUT /user/settings user_id=%s incoming=%s current=%s", user_id, incoming, current)
        merged_current = _merge_settings(_default_user_settings(), current)
        final_settings = _merge_settings(merged_current, incoming)
        db_save_user_settings(int(user_id), final_settings)
        logger.info("PUT /user/settings user_id=%s saved", user_id)
        return final_settings
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(exc))
