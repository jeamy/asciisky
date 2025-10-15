"""
AsciiSky - ASCII Art Celestial Position Tracker
"""
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Import routers from the new modules
from api.routes import session, celestial, asteroids, comets, cache, config, zodiac, filters

# Initialize FastAPI app
app = FastAPI(
    title="AsciiSky API",
    description="API for ASCII art representation of the night sky."
)

# Add session middleware
SESSION_SECRET = os.environ.get("ASCII_SKY_SESSION_SECRET", "dev-secret-please-change")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax")

# Prevent stale JS/CSS in browsers during rapid iteration: disable caching for static modules
@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    try:
        path = request.url.path or ""
        if path.startswith("/static/") and (path.endswith(".js") or path.endswith(".css")):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
    except Exception:
        pass
    return response

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Global dict to store info about running and completed precompute tasks
app.precompute_tasks = {}

# Include routers
app.include_router(session.router, prefix="/api", tags=["session"])
app.include_router(celestial.router, prefix="/api", tags=["celestial"])
app.include_router(asteroids.router, prefix="/api", tags=["asteroids"])
app.include_router(comets.router, prefix="/api", tags=["comets"])
app.include_router(zodiac.router, prefix="/api", tags=["zodiac"])
app.include_router(cache.router, prefix="/api", tags=["cache"])
app.include_router(config.router, prefix="/api", tags=["config"])
app.include_router(filters.router, prefix="/api", tags=["filters"])

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def read_root(request: Request):
    """Render the main page."""
    return FileResponse("templates/index.html")

if __name__ == "__main__":
    import uvicorn
    # The port is hardcoded to 8000. If you have issues with zombie processes,
    # you might need to change this or kill the process.
    uvicorn.run(app, host="0.0.0.0", port=8000)
