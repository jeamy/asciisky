"""Asteroid and comet routes.

Both serve precomputed position buckets (cache first); on a miss they publish
one deduplicated precompute task and answer with an empty list, which the
frontend fills on its next refresh.  Buckets are computed up to the module's
``CACHE_MAX_MAGNITUDE``; each request is filtered to the caller's limit here.
"""
import asyncio
import logging
from dataclasses import dataclass
from types import ModuleType

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

import bright_asteroids
import comets
from api.cache_interpolation import load_nearest_bucket
from api.helpers import (
    get_location_params,
    parse_time_param,
    resolve_magnitude_filter,
    trigger_small_body_worker,
)
from db_utils import get_asteroid_positions, get_comet_positions

logger = logging.getLogger(__name__)

router = APIRouter()


@dataclass(frozen=True)
class SmallBodyKind:
    kind: str              # task kind for the worker
    key_prefix: str        # prefix of the body keys in the response
    filter_key: str        # user filter field
    module: ModuleType     # bright_asteroids or comets
    bucket_hours: int
    loader: object         # DB loader for one bucket


ASTEROIDS = SmallBodyKind(
    'asteroids', 'bright_asteroid_', 'asteroidMaxMagnitude', bright_asteroids,
    bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS, get_asteroid_positions,
)
COMETS = SmallBodyKind(
    'comets', 'comet_', 'cometMaxMagnitude', comets,
    comets.COMET_CACHE_BUCKET_HOURS, get_comet_positions,
)


async def _small_body_response(
    spec: SmallBodyKind,
    request: Request,
    background_tasks: BackgroundTasks,
    lat: float | None,
    lon: float | None,
    elevation: float | None,
    time: str | None,
    max_magnitude: float | None,
) -> dict:
    lat, lon, elevation = get_location_params(request, lat, lon, elevation)
    dt_utc = parse_time_param(time)
    if max_magnitude is None:
        # The user's filter may come from PostgreSQL: keep it off the event loop.
        max_magnitude = await asyncio.to_thread(
            resolve_magnitude_filter, request, spec.filter_key, spec.module.MAX_APPARENT_MAGNITUDE,
        )

    bucket_dt = dt_utc.replace(minute=0, second=0, microsecond=0)
    try:
        bodies = await asyncio.to_thread(
            load_nearest_bucket, lat, lon, elevation, dt_utc, spec.bucket_hours, spec.loader,
        )
    except Exception:
        logger.exception("Failed to load %s from cache", spec.kind)
        bodies = None

    if bodies is None:
        # The publisher takes a persistent claim, so concurrent misses publish once.
        background_tasks.add_task(
            trigger_small_body_worker, spec.kind, lat, lon, elevation, bucket_dt,
            spec.module.CACHE_MAX_MAGNITUDE, spec.bucket_hours, logger,
        )
        bodies = []

    result = {
        "time": dt_utc.isoformat(),
        "location": {"latitude": lat, "longitude": lon, "elevation": elevation},
        "bodies": {},
    }
    for body in bodies:
        if not isinstance(body, dict) or "name" not in body:
            continue
        magnitude = body.get("magnitude")
        if magnitude is not None and magnitude <= max_magnitude:
            # The name alone keys the body, so a key survives a changed order.
            result["bodies"][f"{spec.key_prefix}{body['name']}"] = body
    return result


@router.get("/bright_asteroids")
async def get_bright_asteroids(request: Request, background_tasks: BackgroundTasks, lat: float = None, lon: float = None, elevation: float = None, time: str | None = None, max_magnitude: float = None):
    """Positions of the brightest minor planets (asteroids)."""
    try:
        return await _small_body_response(ASTEROIDS, request, background_tasks, lat, lon, elevation, time, max_magnitude)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Asteroid request failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/comets")
async def get_comets(request: Request, background_tasks: BackgroundTasks, lat: float = None, lon: float = None, elevation: float = None, time: str | None = None, max_magnitude: float = None):
    """Comets with MPC data and rise/set/transit times."""
    try:
        return await _small_body_response(COMETS, request, background_tasks, lat, lon, elevation, time, max_magnitude)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Comet request failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
