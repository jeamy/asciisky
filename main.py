"""
AsciiSky - ASCII Art Celestial Position Tracker
"""
import asyncio
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import FileResponse, RedirectResponse

# Import routers from the new modules
from api.routes import (
    admin_users,
    asteroids,
    auth,
    celestial,
    comets,
    config,
    filters,
    interpolation_admin,
    messier,
    session,
    user_settings,
    zodiac,
)
from api.routes.auth import _get_user_by_id, _session_clear_user
from db_utils import database_identity, database_target


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.precompute_tasks = {}
    print(f"AsciiSky web PostgreSQL target: {database_target()}", flush=True)
    try:
        print(f"AsciiSky web actual PostgreSQL server: {database_identity()}", flush=True)
    except Exception as exc:
        print(f"AsciiSky web PostgreSQL identity unavailable: {exc}", flush=True)
    yield
    # Shutdown (nothing to clean up currently)

# Initialize FastAPI app
app = FastAPI(
    title="AsciiSky API",
    description="API for ASCII art representation of the night sky.",
    lifespan=lifespan
)

# Add session middleware
SESSION_SECRET = os.environ.get("ASCII_SKY_SESSION_SECRET")
if not SESSION_SECRET:
    if os.environ.get("ASCII_SKY_ENV", "development").lower() in {"production", "prod"}:
        raise RuntimeError("ASCII_SKY_SESSION_SECRET must be set in production")
    # Never fall back to a public, predictable signing key.  Development
    # sessions intentionally expire on process restart when no secret is set.
    SESSION_SECRET = secrets.token_urlsafe(48)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax")

# Development favors immediate iteration; production keeps static assets in the
# browser cache and revalidates them periodically.
_development_mode = os.environ.get("ASCII_SKY_ENV", "development").lower() not in {"production", "prod"}
@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    try:
        path = request.url.path or ""
        if path.startswith("/static/") and path.endswith((".js", ".css")):
            if _development_mode:
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
            else:
                response.headers["Cache-Control"] = "public, max-age=300, must-revalidate"
    except Exception:
        pass
    return response

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(session.router, prefix="/api", tags=["session"])
app.include_router(celestial.router, prefix="/api", tags=["celestial"])
app.include_router(asteroids.router, prefix="/api", tags=["asteroids"])
app.include_router(comets.router, prefix="/api", tags=["comets"])
app.include_router(zodiac.router, prefix="/api", tags=["zodiac"])
app.include_router(messier.router, prefix="/api", tags=["messier"])
app.include_router(config.router, prefix="/api", tags=["config"])
app.include_router(filters.router, prefix="/api", tags=["filters"])
app.include_router(user_settings.router, prefix="/api", tags=["user_settings"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(admin_users.router, prefix="/api", tags=["admin-users"])
app.include_router(interpolation_admin.router, prefix="/api", tags=["interpolation-admin"])

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def read_root(request: Request):
    """Render the main page."""
    return FileResponse("templates/index.html")


def _require_admin_page(request: Request) -> dict | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    try:
        user = _get_user_by_id(int(user_id))
    except (TypeError, ValueError):
        user = None
    if not user or not user.get("is_active", False):
        _session_clear_user(request)
        return None
    if not user.get("is_admin", False):
        request.session["user_is_admin"] = False
        return None
    request.session["user_is_admin"] = True
    return user


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_page(request: Request):
    """Render the admin user management page (admins only)."""
    user = await asyncio.to_thread(_require_admin_page, request)
    if not user:
        return RedirectResponse("/", status_code=302)

    return FileResponse("templates/admin.html")

if __name__ == "__main__":
    import uvicorn
    # The port is hardcoded to 8000. If you have issues with zombie processes,
    # you might need to change this or kill the process.
    uvicorn.run(app, host="0.0.0.0", port=8000)
