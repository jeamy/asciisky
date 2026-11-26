"""
API routes for magnitude filter settings
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
import settings
from api.models import MagnitudeFilters
from api.routes.auth import _get_user_by_id, _session_clear_user

router = APIRouter()
logger = logging.getLogger(__name__)

def get_user_filters_from_db(user_id: int) -> dict | None:
    """Load magnitude filters from database for a specific user"""
    try:
        from db_utils import get_user_settings as db_get_user_settings

        settings_obj = db_get_user_settings(int(user_id))
        if not settings_obj:
            return None

        filters = settings_obj.get("filters")
        if isinstance(filters, dict):
            return filters
        return None
    except Exception as e:
        logger.warning("Error loading user filters from DB: %s", e)
        return None


def save_user_filters_to_db(user_id: int, filters: dict) -> bool:
    """Save magnitude filters to database for a specific user"""
    try:
        from db_utils import (
            get_user_settings as db_get_user_settings,
        )
        from db_utils import (
            save_user_settings as db_save_user_settings,
        )

        current_settings = db_get_user_settings(int(user_id)) or {}
        if not isinstance(current_settings, dict):
            current_settings = {}

        # Merge filters into the existing settings JSON structure
        merged_settings = dict(current_settings)
        merged_settings["filters"] = filters

        db_save_user_settings(int(user_id), merged_settings)
        return True
    except Exception as e:
        logger.warning("Error saving user filters to DB: %s", e)
        return False


def _resolve_session_user_id(request: Request) -> int | None:
    """Return a live, active user id, or None for an anonymous request.

    Stale or disabled sessions are cleared and raise 401.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    try:
        user = _get_user_by_id(int(user_id))
    except (TypeError, ValueError):
        user = None
    if not user or not user.get("is_active", False):
        _session_clear_user(request)
        raise HTTPException(status_code=401, detail="Session user no longer exists")
    return int(user["id"])


SESSION_FILTERS_KEY = "filters"


def session_filters(request: Request) -> dict | None:
    """Filters an anonymous visitor chose; they live in that visitor's session only."""
    filters = request.session.get(SESSION_FILTERS_KEY) if hasattr(request, "session") else None
    return filters if isinstance(filters, dict) else None


def _get_filters_sync(request: Request) -> dict:
    """Blocking body of GET /filters (session/DB lookup + optional file read)."""
    user_id = _resolve_session_user_id(request)

    if user_id is not None:
        filters = get_user_filters_from_db(user_id)
        if filters:
            return {"success": True, "filters": filters, "source": "database"}
    else:
        filters = session_filters(request)
        if filters:
            return {"success": True, "filters": {**settings.get_magnitude_filters(), **filters}, "source": "session"}

    return {"success": True, "filters": settings.get_magnitude_filters(), "source": "defaults"}


def _set_filters_sync(request: Request, filters: MagnitudeFilters) -> dict:
    """Blocking body of POST /filters.

    Signed-in users store their filters in the database.  Anonymous visitors
    keep theirs in their own session: the server-wide defaults in
    ``cache/user_settings.json`` are never written by a request.
    """
    user_id = _resolve_session_user_id(request)

    if user_id is not None:
        base = get_user_filters_from_db(user_id) or settings.get_default_magnitude_filters()
    else:
        base = {**settings.get_magnitude_filters(), **(session_filters(request) or {})}

    updated_filters = dict(base)
    if filters.asteroidMaxMagnitude is not None:
        updated_filters["asteroidMaxMagnitude"] = float(filters.asteroidMaxMagnitude)
    if filters.cometMaxMagnitude is not None:
        updated_filters["cometMaxMagnitude"] = float(filters.cometMaxMagnitude)

    if user_id is not None:
        if not save_user_filters_to_db(user_id, updated_filters):
            raise HTTPException(status_code=500, detail="Failed to save filters to database")
        storage = "database"
    else:
        request.session[SESSION_FILTERS_KEY] = updated_filters
        storage = "session"

    # Filtering happens per request on unfiltered buckets: no cache invalidation.
    return {"success": True, "filters": updated_filters, "cache_invalidated": False, "storage": storage}


@router.get("/filters")
async def get_filters(request: Request):
    """Get current magnitude filter settings"""
    try:
        return await asyncio.to_thread(_get_filters_sync, request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/filters")
async def set_filters(filters: MagnitudeFilters, request: Request):
    """Set magnitude filter settings for this user or session."""
    try:
        return await asyncio.to_thread(_set_filters_sync, request, filters)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
