import asyncio
import copy
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from psycopg.errors import ForeignKeyViolation
from pydantic import BaseModel, Field

from api.models import LocationPayload, MagnitudeFilters
from api.routes.auth import _get_user_by_id, _session_clear_user
from db_utils import get_user_settings as db_get_user_settings
from db_utils import save_user_settings as db_save_user_settings
from settings import DEFAULT_SETTINGS, get_default_magnitude_filters

logger = logging.getLogger(__name__)

router = APIRouter()


class UserSettingsModel(BaseModel):
    """Settings a signed-in user may store.

    ``location`` and ``filters`` are validated because the precompute
    coordinator reads every stored location (an unchecked value would break
    its query for all users).
    """
    location: LocationPayload | None = None
    display: dict[str, Any] | None = None
    simTime: dict[str, Any] | None = None
    filters: MagnitudeFilters | None = None
    theme: str | None = Field(default=None, max_length=20)
    language: str | None = Field(default=None, max_length=5)
    options: dict[str, Any] | None = None


def _default_user_settings() -> dict[str, Any]:
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
        # No centerAz here: the page derives it from an older horizontalShift
        # when a stored record has no centerAz yet.
        "display": {
            "viewMode": "horizon",
        },
        "simTime": {
            "offsetMinutes": 0,
        },
        "filters": copy.deepcopy(base_filters),
        "theme": "green",
        "language": "de",
        "options": {"showConstellations": False},
    }


def _merge_settings(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Shallow merge with simple nested-dict support for known sections."""
    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            nested = dict(result[key])
            nested.update(value)
            result[key] = nested
        else:
            result[key] = value
    return result


def _require_authenticated_user(request: Request) -> int:
    """Return a live user id or clear a stale/disabled session and raise 401."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        user = _get_user_by_id(int(user_id))
    except (TypeError, ValueError):
        user = None
    if not user or not user.get("is_active", True):
        _session_clear_user(request)
        raise HTTPException(status_code=401, detail="Session user no longer exists")
    return int(user["id"])


def _load_settings_sync(request: Request) -> dict[str, Any]:
    user_id = _require_authenticated_user(request)
    stored = db_get_user_settings(user_id)
    if stored is None:
        return _default_user_settings()
    return _merge_settings(_default_user_settings(), stored)


def _save_settings_sync(request: Request, incoming: dict[str, Any]) -> dict[str, Any]:
    user_id = _require_authenticated_user(request)
    current = db_get_user_settings(user_id) or {}
    final_settings = _merge_settings(_merge_settings(_default_user_settings(), current), incoming)
    try:
        db_save_user_settings(user_id, final_settings)
    except ForeignKeyViolation:
        # The user may have been deleted after session validation.
        _session_clear_user(request)
        raise HTTPException(status_code=401, detail="Session user no longer exists") from None
    return final_settings


@router.get("/user/settings")
async def get_user_settings(request: Request) -> dict[str, Any]:
    """Return the settings of the signed-in user (401 for anonymous callers)."""
    try:
        return await asyncio.to_thread(_load_settings_sync, request)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Loading user settings failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/user/settings")
async def update_user_settings(payload: UserSettingsModel, request: Request) -> dict[str, Any]:
    """Upsert the signed-in user's settings; omitted fields keep their values."""
    incoming = payload.model_dump(exclude_unset=True)
    try:
        return await asyncio.to_thread(_save_settings_sync, request, incoming)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Saving user settings failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
