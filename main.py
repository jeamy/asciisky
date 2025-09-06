"""
AsciiSky - ASCII Art Himmelsdarstellung
"""
import os
import json
import pickle
import time
import gzip
import urllib.request
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from types import SimpleNamespace

import numpy as np
import pandas as pd
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from skyfield import almanac
from skyfield.api import load, wgs84, Star, Topos, Loader
from skyfield.data import hipparcos, mpc
from skyfield.magnitudelib import planetary_magnitude
from starlette.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

import settings
import bright_asteroids
import comets
from timezone_utils import get_tzinfo
from cache_utils import build_cache_path, read_pickle_if_fresh, atomic_write_pickle, CACHE_ROOT, normalize_location, location_key

# Initialisiere FastAPI
app = FastAPI(title="AsciiSky API", description="API für die ASCII-Darstellung des Sternenhimmels")
SESSION_SECRET = os.environ.get("ASCII_SKY_SESSION_SECRET", "dev-secret-please-change")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax")

# Helper function to get location from request, query params, or settings
async def get_location_from_request(request: Request, lat: float = None, lon: float = None, elevation: float = None) -> Dict[str, Any]:
    """
    Get location data from query params, session, or settings file.
    Priority: query params > session > settings file
    
    Returns a dict with latitude, longitude, elevation, and optional name.
    """
    try:
        # 1. Try query parameters first
        if lat is not None and lon is not None:
            return {
                "latitude": float(lat),
                "longitude": float(lon),
                "elevation": float(elevation if elevation is not None else 0.0),
                "name": ""
            }
        
        # 2. Try session
        session = request.session
        if "location" in session:
            try:
                loc = session["location"]
                if isinstance(loc, dict) and "latitude" in loc and "longitude" in loc:
                    return {
                        "latitude": float(loc["latitude"]),
                        "longitude": float(loc["longitude"]),
                        "elevation": float(loc.get("elevation", 0.0)),
                        "name": loc.get("name", "")
                    }
            except Exception:
                pass
        
        # 3. Fall back to settings file
        import settings as app_settings
        loc = app_settings.get_location()
        if loc and "latitude" in loc and "longitude" in loc:
            return {
                "latitude": float(loc["latitude"]),
                "longitude": float(loc["longitude"]),
                "elevation": float(loc.get("elevation", 0.0)),
                "name": loc.get("name", "")
            }
        
        # 4. Default to Vienna if all else fails
        return {
            "latitude": 48.2082,
            "longitude": 16.3738,
            "elevation": 171.0,
            "name": "Vienna"
        }
    except Exception as e:
        print(f"Error getting location: {str(e)}")
        return None

# Statische Dateien und Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# API-Endpunkte
API_ENDPOINT_CELESTIAL = "/api/celestial"
API_ENDPOINT_ASTEROIDS = "/api/asteroids"
API_ENDPOINT_COMETS = "/api/comets"
API_ENDPOINT_BRIGHT_ASTEROIDS = "/api/bright_asteroids"
API_ENDPOINT_CACHE_STATUS = "/api/cache_status"
API_ENDPOINT_PRECOMPUTE_RANGE = "/api/precompute_range"

# Cache settings for precomputed celestial snapshots
CELESTIAL_CACHE_BUCKET_HOURS = 1
CELESTIAL_CACHE_TTL_SECONDS = 49 * 3600

# Lade Skyfield-Daten (use local Loader to avoid network download)
LOADER = Loader('.')
ts = LOADER.timescale()
eph = LOADER('de421.bsp')  # Ephemeris-Datei

# Planeten und andere Himmelskörper
CELESTIAL_BODIES = {
    'sun': eph['sun'],
    'moon': eph['moon'],
    'mercury': eph['mercury'],
    'venus': eph['venus'],
    'mars': eph['mars'],
    'jupiter': eph['jupiter barycenter'],
    'saturn': eph['saturn barycenter'],
    'uranus': eph['uranus barycenter'],
    'neptune': eph['neptune barycenter']
}

# Symbole für Himmelskörper
BODY_SYMBOLS = {
    'sun': '☀️',
    'moon': '🌙',
    'mercury': '☿',
    'venus': '♀',
    'mars': '♂',
    'jupiter': '♃',
    'saturn': '♄',
    'uranus': '♅',
    'neptune': '♆',
    'comet': '☄️',  # Unicode U+2604 (Komet)
    'asteroid': '⚸'  # Unicode U+26B8 (Asteroid)
}

# Compute planetary snapshot for a given location and time (UTC)
def compute_celestial_snapshot(lat: float, lon: float, elevation: float, dt_utc: datetime) -> dict:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    # Determine observer timezone from coordinates
    tz = get_tzinfo(lat, lon)
    t = ts.from_datetime(dt_utc)
    location = wgs84.latlon(lat, lon, elevation_m=elevation)
    observer = eph['earth'] + location

    result = {
        "time": dt_utc.isoformat(),
        "location": {"latitude": lat, "longitude": lon, "elevation": elevation},
        "bodies": {},
        "loading": False
    }

    for name, body in CELESTIAL_BODIES.items():
        try:
            astrometric = observer.at(t).observe(body)
            apparent = astrometric.apparent()
            alt, az, distance = apparent.altaz()

            # Entfernung vom Erdmittelpunkt in AU
            earth_center = eph['earth'].at(t)
            earth_to_body = earth_center.observe(body)
            earth_distance = earth_to_body.distance().au

            # Magnitude
            if name == 'sun':
                mag = -26.74
            elif name == 'moon':
                moon_phase = almanac.moon_phase(eph, t)
                moon_phase_angle = float(moon_phase.radians)
                import math
                phase_factor = 0.5 * (1 - math.cos(moon_phase_angle))
                mag = -12.7 + 2.5 * math.log10(phase_factor) if phase_factor > 0 else -12.7
            elif name in ['mercury', 'venus', 'mars', 'jupiter', 'saturn']:
                try:
                    mag = planetary_magnitude(astrometric)
                except Exception:
                    mag = {
                        'mercury': 0.23,
                        'venus': -4.14,
                        'mars': 1.66,
                        'jupiter': -2.2,
                        'saturn': 0.46
                    }.get(name, 0)
            else:
                mag = {
                    'uranus': 5.7,
                    'neptune': 7.8
                }.get(name, 0)

            # Rise/Set window: next 48h from UTC midnight of simulated day
            try:
                f = almanac.risings_and_settings(eph, body, location)
                start_time = ts.utc(dt_utc.replace(hour=0, minute=0, second=0, microsecond=0))
                end_time = ts.utc(start_time.utc_datetime() + timedelta(days=2))
                times, events = almanac.find_discrete(start_time, end_time, f)
                rise_time = None
                set_time = None
                for ti, event in zip(times, events):
                    utc_time = ti.utc_datetime().replace(tzinfo=timezone.utc)
                    local_time = utc_time.astimezone(tz)
                    formatted_time = local_time.strftime('%H:%M')
                    if event == 1:
                        rise_time = formatted_time
                    else:
                        set_time = formatted_time
                # Transit time: midpoint or estimate
                transit_time = None
                try:
                    if rise_time and set_time:
                        now = dt_utc.astimezone(tz)
                        today = now.date()
                        rise_dt = datetime.strptime(rise_time, '%H:%M').replace(year=today.year, month=today.month, day=today.day, tzinfo=tz)
                        set_dt = datetime.strptime(set_time, '%H:%M').replace(year=today.year, month=today.month, day=today.day, tzinfo=tz)
                        if set_dt < rise_dt:
                            set_dt += timedelta(days=1)
                        transit_dt = rise_dt + (set_dt - rise_dt) / 2
                        transit_time = transit_dt.strftime('%H:%M')
                    else:
                        transit_dt = dt_utc.astimezone(tz) + timedelta(hours=12)
                        transit_time = transit_dt.strftime('%H:%M')
                except Exception:
                    transit_time = None
            except Exception:
                rise_time = None
                set_time = None
                transit_time = None

            body_entry = {
                "name": name,
                "symbol": BODY_SYMBOLS.get(name, "?"),
                "altitude": float(alt.degrees),
                "azimuth": float(az.degrees),
                "distance": float(earth_distance),
                "magnitude": float(mag),
                "visible": True,
                "transit_time": transit_time,
                "rise_time": rise_time,
                "set_time": set_time
            }

            # Moon phase details
            if name == 'moon':
                try:
                    # Verwende Skyfield's eingebaute fraction_illuminated Methode
                    illumination = astrometric.fraction_illuminated(eph['sun'])
                    
                    # Berechne Phasenwinkel für Phasennamen
                    moon_phase = almanac.moon_phase(eph, t)
                    phase_degrees = float(moon_phase.degrees)
                    
                    # Bestimme Phasenname basierend auf dem Phasenwinkel (0-360°)
                    # 0° = Neumond, 90° = Erstes Viertel, 180° = Vollmond, 270° = Letztes Viertel
                    # 0°-180° = zunehmend (waxing), 180°-360° = abnehmend (waning)
                    if phase_degrees < 22.5 or phase_degrees >= 337.5:
                        phase_name = "new_moon"
                    elif phase_degrees < 67.5:
                        phase_name = "waxing_crescent"
                    elif phase_degrees < 112.5:
                        phase_name = "first_quarter"
                    elif phase_degrees < 177.5:
                        phase_name = "waxing_gibbous"
                    elif phase_degrees < 182.5:
                        phase_name = "full_moon"
                    elif phase_degrees < 247.5:
                        phase_name = "waning_gibbous"
                    elif phase_degrees < 292.5:
                        phase_name = "last_quarter"
                    else:
                        phase_name = "waning_crescent"
                    
                    body_entry["phase"] = illumination
                    body_entry["phase_name"] = phase_name
                except Exception:
                    pass

            result["bodies"][name] = body_entry
        except Exception as e:
            print(f"Error calculating position for {name}: {str(e)}")
            continue

    return result

# Internal helper: ensure caches and spawn background precompute window for a location
def _hour_floor(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.replace(minute=0, second=0, microsecond=0)

def _ensure_celestial_cache(lat: float, lon: float, elevation: float, dt_utc: datetime) -> None:
    try:
        cache_file = build_cache_path('celestial', lat, lon, elevation, dt=dt_utc, bucket_hours=CELESTIAL_CACHE_BUCKET_HOURS)
        if not os.path.exists(cache_file):
            snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
            atomic_write_pickle(cache_file, snapshot)
    except Exception:
        print(f"[bg] celestial ensure failed for {lat},{lon},{elevation} @ {dt_utc.isoformat()}")
        import traceback; traceback.print_exc()

def _ensure_asteroids_cache(lat: float, lon: float, elevation: float, dt_utc: datetime) -> None:
    try:
        location = {"latitude": lat, "longitude": lon, "elevation": elevation}
        # Module writes its cache when use_cache=True
        _ = bright_asteroids.load_bright_asteroids(
            LOADER, ts, eph, location,
            max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE,
            use_cache=True, current_dt=dt_utc
        )
    except Exception:
        print(f"[bg] asteroids ensure failed for {lat},{lon},{elevation} @ {dt_utc.isoformat()}")
        import traceback; traceback.print_exc()

def _ensure_comets_cache(lat: float, lon: float, elevation: float, dt_utc: datetime) -> None:
    try:
        location = {"latitude": lat, "longitude": lon, "elevation": elevation}
        _ = comets.load_comets(ts, eph, location, use_cache=True, current_dt=dt_utc)
    except Exception:
        print(f"[bg] comets ensure failed for {lat},{lon},{elevation} @ {dt_utc.isoformat()}")
        import traceback; traceback.print_exc()

async def trigger_background_precompute_window(lat: float, lon: float, elevation: float, dt_utc: datetime, kinds: list[str]) -> None:
    """Kick off background precompute for a 48h window relative to dt_utc.
    Forward if dt_utc >= now, otherwise backward 48h.
    """
    try:
        try:
            horizon_hours = int(os.environ.get("ASCII_SKY_PRECOMPUTE_HOURS", "48"))
        except Exception:
            horizon_hours = 48
        now_utc = datetime.now(timezone.utc)
        base = _hour_floor(dt_utc)
        forward = base >= _hour_floor(now_utc)

        def _do_work_sync():
            for i in range(horizon_hours):
                t = base + timedelta(hours=i) if forward else base - timedelta(hours=i)
                for k in kinds:
                    if k == 'celestial':
                        _ensure_celestial_cache(lat, lon, elevation, t)
                    elif k == 'asteroids':
                        _ensure_asteroids_cache(lat, lon, elevation, t)
                    elif k == 'comets':
                        _ensure_comets_cache(lat, lon, elevation, t)

        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _do_work_sync)
    except Exception:
        print("[bg] trigger failed")
        import traceback; traceback.print_exc()

async def trigger_background_precompute_range(lat: float, lon: float, elevation: float, start_dt_utc: datetime, end_dt_utc: datetime, kinds: list[str]) -> dict:
    """Kick off background precompute for a custom date range.
    Returns status information about the precompute task.
    """
    try:
        # Ensure both datetimes are UTC-aware
        if start_dt_utc.tzinfo is None:
            start_dt_utc = start_dt_utc.replace(tzinfo=timezone.utc)
        if end_dt_utc.tzinfo is None:
            end_dt_utc = end_dt_utc.replace(tzinfo=timezone.utc)
        
        # Normalize to hour boundaries
        start_dt_utc = _hour_floor(start_dt_utc)
        end_dt_utc = _hour_floor(end_dt_utc)
        
        # Ensure start is before end
        if start_dt_utc > end_dt_utc:
            start_dt_utc, end_dt_utc = end_dt_utc, start_dt_utc
        
        # Calculate number of hours to process
        delta_hours = int((end_dt_utc - start_dt_utc).total_seconds() / 3600) + 1
        
        # Cap at reasonable limit (default: 7 days = 168 hours)
        try:
            max_hours = int(os.environ.get("ASCII_SKY_MAX_PRECOMPUTE_HOURS", "168"))
        except Exception:
            max_hours = 168
            
        if delta_hours > max_hours:
            delta_hours = max_hours
            end_dt_utc = start_dt_utc + timedelta(hours=max_hours-1)
        
        # Create a unique ID for this precompute task
        task_id = f"precompute_{int(time.time())}_{delta_hours}h"
        
        # Store task info in a global dict for status checking
        if not hasattr(app, 'precompute_tasks'):
            app.precompute_tasks = {}
        
        app.precompute_tasks[task_id] = {
            'id': task_id,
            'status': 'starting',
            'start_time': datetime.now(timezone.utc),
            'location': {'lat': lat, 'lon': lon, 'elevation': elevation},
            'date_range': {'start': start_dt_utc.isoformat(), 'end': end_dt_utc.isoformat()},
            'hours_total': delta_hours,
            'hours_completed': 0,
            'percent_complete': 0
        }
        
        # Define a synchronous function for the background task
        def _do_work_sync():
            try:
                app.precompute_tasks[task_id]['status'] = 'running'
                
                current_dt = start_dt_utc
                hours_completed = 0
                
                while current_dt <= end_dt_utc:
                    for k in kinds:
                        if k == 'celestial':
                            _ensure_celestial_cache(lat, lon, elevation, current_dt)
                        elif k == 'asteroids':
                            _ensure_asteroids_cache(lat, lon, elevation, current_dt)
                        elif k == 'comets':
                            _ensure_comets_cache(lat, lon, elevation, current_dt)
                    
                    current_dt += timedelta(hours=1)
                    hours_completed += 1
                    
                    # Update progress
                    app.precompute_tasks[task_id]['hours_completed'] = hours_completed
                    app.precompute_tasks[task_id]['percent_complete'] = int((hours_completed / delta_hours) * 100)
                
                app.precompute_tasks[task_id]['status'] = 'completed'
                app.precompute_tasks[task_id]['end_time'] = datetime.now(timezone.utc)
                
            except Exception as e:
                app.precompute_tasks[task_id]['status'] = 'error'
                app.precompute_tasks[task_id]['error'] = str(e)
                print(f"Error in background precompute range task {task_id}")
                import traceback; traceback.print_exc()

        # Start the background task
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _do_work_sync)
        
        return {
            'task_id': task_id,
            'status': 'started',
            'message': f'Background precompute started for {delta_hours} hours from {start_dt_utc.isoformat()} to {end_dt_utc.isoformat()}',
            'hours_total': delta_hours
        }
        
    except Exception as e:
        print("Error starting background precompute range")
        import traceback; traceback.print_exc()
        return {'error': str(e), 'status': 'failed to start'}

# Helper: parse optional ISO 8601 datetime string (supports 'Z') into UTC-aware datetime
def parse_time_param(time_str: Optional[str]) -> datetime:
    if not time_str:
        return datetime.now(timezone.utc)
    try:
        s = time_str.strip()
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        # Fallback to current UTC on parse errors
        return datetime.now(timezone.utc)

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Render the main page."""
    return FileResponse("templates/index.html")

# Session models and endpoints
class LocationPayload(BaseModel):
    latitude: float
    longitude: float
    elevation: float
    name: Optional[str] = None

@app.get("/api/session/location")
async def get_session_location(request: Request):
    loc = request.session.get("location")
    return {"location": loc}

@app.post("/api/session/location")
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

@app.get(API_ENDPOINT_CELESTIAL)
async def get_celestial_objects(request: Request, lat: float = None, lon: float = None, elevation: float = None, time: Optional[str] = None):
    """Get positions of celestial objects.
    Simulated time (time param provided): serve strictly from precomputed cache; do NOT compute on-demand.
    Real-time (no time param): compute on-demand and write to cache.
    """
    try:
        # Standortdaten: query params -> session -> settings
        location_settings = settings.get_location()
        session_loc = request.session.get("location", {}) if hasattr(request, "session") else {}
        if lat is None:
            lat = session_loc.get("latitude", location_settings["latitude"])
        if lon is None:
            lon = session_loc.get("longitude", location_settings["longitude"])
        if elevation is None:
            elevation = session_loc.get("elevation", location_settings["elevation"])

        dt_utc = parse_time_param(time)

        # If a simulated time was provided, prefer cache; on miss, compute now and trigger background precompute
        if time is not None:
            cache_file = build_cache_path('celestial', lat, lon, elevation, dt=dt_utc, bucket_hours=CELESTIAL_CACHE_BUCKET_HOURS)
            # Try fresh cache first, then fall back to any existing snapshot (old files are retained)
            snapshot = read_pickle_if_fresh(cache_file, CELESTIAL_CACHE_TTL_SECONDS)
            if snapshot is None:
                try:
                    if os.path.exists(cache_file):
                        with open(cache_file, 'rb') as f:
                            snapshot = pickle.load(f)
                except Exception:
                    snapshot = None
            if isinstance(snapshot, dict) and "bodies" in snapshot:
                return snapshot
            # Compute on-demand and store, then trigger background precompute window
            snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
            try:
                atomic_write_pickle(cache_file, snapshot)
            except Exception:
                pass
            try:
                asyncio.create_task(trigger_background_precompute_window(lat, lon, elevation, dt_utc, kinds=['celestial','asteroids','comets']))
            except Exception:
                pass
            return snapshot

        # Real-time: compute and store
        snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
        try:
            cache_file = build_cache_path('celestial', lat, lon, elevation, dt=dt_utc, bucket_hours=CELESTIAL_CACHE_BUCKET_HOURS)
            atomic_write_pickle(cache_file, snapshot)
        except Exception:
            pass
        return snapshot
    except Exception as e:
        print(f"Error in get_celestial_objects: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get(f"{API_ENDPOINT_CELESTIAL}/{{body_id}}")
async def get_celestial_object(body_id: str, request: Request, lat: float = None, lon: float = None, elevation: float = None, time: Optional[str] = None):
    """Get position of a specific celestial object.
    Simulated time: read object from precomputed full snapshot cache.
    Real-time: compute full snapshot on-demand and return the object.
    """
    try:
        if body_id not in CELESTIAL_BODIES:
            raise HTTPException(status_code=404, detail=f"Celestial body '{body_id}' not found")

        # Standortdaten
        location_settings = settings.get_location()
        session_loc = request.session.get("location", {}) if hasattr(request, "session") else {}
        if lat is None:
            lat = session_loc.get("latitude", location_settings["latitude"])
        if lon is None:
            lon = session_loc.get("longitude", location_settings["longitude"])
        if elevation is None:
            elevation = session_loc.get("elevation", location_settings["elevation"])

        dt_utc = parse_time_param(time)

        # Simulated time -> prefer cache; on miss compute and trigger background precompute
        if time is not None:
            cache_file = build_cache_path('celestial', lat, lon, elevation, dt=dt_utc, bucket_hours=CELESTIAL_CACHE_BUCKET_HOURS)
            snapshot = read_pickle_if_fresh(cache_file, CELESTIAL_CACHE_TTL_SECONDS)
            if snapshot is None:
                try:
                    if os.path.exists(cache_file):
                        with open(cache_file, 'rb') as f:
                            snapshot = pickle.load(f)
                except Exception:
                    snapshot = None
            if isinstance(snapshot, dict) and isinstance(snapshot.get("bodies"), dict):
                body = snapshot["bodies"].get(body_id)
                if isinstance(body, dict):
                    body_out = body.copy()
                    body_out["id"] = body_id
                    return body_out
            # Compute on-demand and store, then trigger background precompute window
            snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
            try:
                atomic_write_pickle(cache_file, snapshot)
            except Exception:
                pass
            try:
                asyncio.create_task(trigger_background_precompute_window(lat, lon, elevation, dt_utc, kinds=['celestial','asteroids','comets']))
            except Exception:
                pass
            body = snapshot["bodies"].get(body_id)
            if isinstance(body, dict):
                body_out = body.copy()
                body_out["id"] = body_id
                return body_out
            else:
                raise HTTPException(status_code=500, detail=f"Snapshot missing body '{body_id}'")

        # Real-time compute
        snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
        try:
            cache_file = build_cache_path('celestial', lat, lon, elevation, dt=dt_utc, bucket_hours=CELESTIAL_CACHE_BUCKET_HOURS)
            atomic_write_pickle(cache_file, snapshot)
        except Exception:
            pass
        body = snapshot["bodies"].get(body_id)
        if isinstance(body, dict):
            body_out = body.copy()
            body_out["id"] = body_id
            return body_out
        else:
            raise HTTPException(status_code=500, detail=f"Snapshot missing body '{body_id}'")
    except Exception as e:
        print(f"Error in get_celestial_object: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get(API_ENDPOINT_BRIGHT_ASTEROIDS)
async def get_bright_asteroids(request: Request, lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False, time: Optional[str] = None):
    """Get positions of the brightest minor planets (asteroids)."""
    try:
        # Hole Standortdaten: query params -> session -> settings
        location_settings = settings.get_location()
        session_loc = request.session.get("location", {}) if hasattr(request, "session") else {}
        if lat is None:
            lat = session_loc.get("latitude", location_settings["latitude"])
        if lon is None:
            lon = session_loc.get("longitude", location_settings["longitude"])
        if elevation is None:
            elevation = session_loc.get("elevation", location_settings["elevation"])
        
        # Speichere die Standortdaten, wenn gewünscht
        if save_location and lat is not None and lon is not None and elevation is not None:
            settings.set_location(lat, lon, elevation, location_name)
            print(f"Saved location settings: lat={lat}, lon={lon}, elevation={elevation}, name={location_name}")
        
        dt_utc = parse_time_param(time)

        # Simulated time -> prefer cache; on miss compute and trigger background precompute
        if time is not None:
            cache_file = build_cache_path('asteroids', lat, lon, elevation, dt=dt_utc, bucket_hours=bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS)
            asteroid_list = None
            try:
                # Prefer fresh, but accept any existing snapshot (old files kept)
                asteroid_list = read_pickle_if_fresh(cache_file, bright_asteroids.ASTEROID_CACHE_TTL_SECONDS)
                if asteroid_list is None and os.path.exists(cache_file):
                    with open(cache_file, 'rb') as f:
                        asteroid_list = pickle.load(f)
            except Exception:
                asteroid_list = None
            if isinstance(asteroid_list, list):
                result = {
                    "time": dt_utc.isoformat(),
                    "location": {"latitude": lat, "longitude": lon, "elevation": elevation},
                    "bodies": {},
                    "loading": False
                }
                for i, asteroid in enumerate(asteroid_list):
                    if isinstance(asteroid, dict) and "name" in asteroid:
                        key = f"bright_asteroid_{i}_{asteroid['name']}"
                        result["bodies"][key] = asteroid
                return result
            # Compute on-demand and store, then trigger background precompute window
            location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
            bright_asteroid_list = bright_asteroids.load_bright_asteroids(
                LOADER, ts, eph, location_dict,
                max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE,
                use_cache=True, current_dt=dt_utc
            )
            result = {
                "time": dt_utc.isoformat(),
                "location": {"latitude": lat, "longitude": lon, "elevation": elevation},
                "bodies": {},
                "loading": False
            }
            for i, asteroid in enumerate(bright_asteroid_list):
                if isinstance(asteroid, dict) and "name" in asteroid:
                    key = f"bright_asteroid_{i}_{asteroid['name']}"
                    result["bodies"][key] = asteroid
            try:
                asyncio.create_task(trigger_background_precompute_window(lat, lon, elevation, dt_utc, kinds=['celestial','asteroids','comets']))
            except Exception:
                pass
            return result

        # Real-time -> compute and store via module
        loader = Loader('.')
        location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        bright_asteroid_list = bright_asteroids.load_bright_asteroids(
            loader, ts, eph, location_dict, max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE, current_dt=dt_utc
        )

        result = {
            "time": dt_utc.isoformat(),
            "location": {"latitude": lat, "longitude": lon, "elevation": elevation},
            "bodies": {},
            "loading": False
        }
        for i, asteroid in enumerate(bright_asteroid_list):
            if isinstance(asteroid, dict) and "name" in asteroid:
                key = f"bright_asteroid_{i}_{asteroid['name']}"
                result["bodies"][key] = asteroid
        return result
        
    except Exception as e:
        print(f"Error in get_bright_asteroids: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get(API_ENDPOINT_ASTEROIDS)
async def get_asteroids(request: Request, lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False, time: Optional[str] = None):
    """Get visible asteroids.
    Simulated time: serve strictly from cache; Real-time: compute on-demand.
    """
    try:
        # Verwende den Wert aus bright_asteroids.py
        max_magnitude = bright_asteroids.MAX_APPARENT_MAGNITUDE
        
        # Hole Standortdaten: query params -> session -> settings
        location_settings = settings.get_location()
        session_loc = request.session.get("location", {}) if hasattr(request, "session") else {}
        if lat is None:
            lat = session_loc.get("latitude", location_settings["latitude"])
        if lon is None:
            lon = session_loc.get("longitude", location_settings["longitude"])
        if elevation is None:
            elevation = session_loc.get("elevation", location_settings["elevation"]) 
        
        # Speichere die Standortdaten, wenn gewünscht
        if save_location and lat is not None and lon is not None and elevation is not None:
            settings.set_location(lat, lon, elevation, location_name)
            print(f"Saved location settings: lat={lat}, lon={lon}, elevation={elevation}, name={location_name}")
        
        dt_utc = parse_time_param(time)

        # Simulated time -> prefer cache; on miss compute and trigger background precompute
        if time is not None:
            cache_file = build_cache_path('asteroids', lat, lon, elevation, dt=dt_utc, bucket_hours=bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS)
            asteroid_list = None
            try:
                asteroid_list = read_pickle_if_fresh(cache_file, bright_asteroids.ASTEROID_CACHE_TTL_SECONDS)
                if asteroid_list is None and os.path.exists(cache_file):
                    with open(cache_file, 'rb') as f:
                        asteroid_list = pickle.load(f)
            except Exception:
                asteroid_list = None
            if isinstance(asteroid_list, list):
                result = {
                    "time": dt_utc.isoformat(),
                    "location": {"latitude": lat, "longitude": lon, "elevation": elevation},
                    "max_magnitude": max_magnitude,
                    "bodies": {},
                    "loading": False
                }
                for i, asteroid in enumerate(asteroid_list):
                    if isinstance(asteroid, dict) and "name" in asteroid:
                        key = f"asteroid_{i}_{asteroid['name']}"
                        result["bodies"][key] = asteroid
                print(f"Returning {len(result['bodies'])} asteroids (cache)")
                return result
            # Compute on-demand and store, then trigger background precompute window
            location = {"latitude": lat, "longitude": lon, "elevation": elevation}
            asteroid_list = bright_asteroids.load_bright_asteroids(
                LOADER, ts, eph, location,
                max_magnitude=max_magnitude,
                use_cache=True, current_dt=dt_utc
            )
            result = {
                "time": dt_utc.isoformat(),
                "location": {"latitude": lat, "longitude": lon, "elevation": elevation},
                "max_magnitude": max_magnitude,
                "bodies": {},
                "loading": False
            }
            for i, asteroid in enumerate(asteroid_list):
                if isinstance(asteroid, dict) and "name" in asteroid:
                    key = f"asteroid_{i}_{asteroid['name']}"
                    result["bodies"][key] = asteroid
            print(f"Returning {len(result['bodies'])} asteroids (simulated compute)")
            try:
                asyncio.create_task(trigger_background_precompute_window(lat, lon, elevation, dt_utc, kinds=['celestial','asteroids','comets']))
            except Exception:
                pass
            return result

        # Real-time -> compute via module
        location = {"latitude": lat, "longitude": lon, "elevation": elevation}
        asteroid_list = bright_asteroids.load_bright_asteroids(load, ts, eph, location, max_magnitude=max_magnitude, current_dt=dt_utc)
        result = {
            "time": dt_utc.isoformat(),
            "location": {"latitude": lat, "longitude": lon, "elevation": elevation},
            "max_magnitude": max_magnitude,
            "bodies": {},
            "loading": False
        }
        for i, asteroid in enumerate(asteroid_list):
            if isinstance(asteroid, dict) and "name" in asteroid:
                key = f"asteroid_{i}_{asteroid['name']}"
                result["bodies"][key] = asteroid
        print(f"Returning {len(result['bodies'])} asteroids")
        return result
        
    except Exception as e:
        print(f"Error in get_asteroids: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get(API_ENDPOINT_COMETS)
async def get_comets(request: Request, lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False, max_comets: int = 1000, time: Optional[str] = None):
    """Get comets with real MPC data and rise/set/transit times.
    Simulated time: serve strictly from cache; Real-time: compute on-demand.
    Supports optional 'max_comets' to cap returned comets.
    """
    try:
        # Hole Standortdaten: query params -> session -> settings
        location_settings = settings.get_location()
        session_loc = request.session.get("location", {}) if hasattr(request, "session") else {}
        if lat is None:
            lat = session_loc.get("latitude", location_settings["latitude"])
        if lon is None:
            lon = session_loc.get("longitude", location_settings["longitude"])
        if elevation is None:
            elevation = session_loc.get("elevation", location_settings["elevation"]) 

        # Speichere die Standortdaten, wenn gewünscht
        if save_location and lat is not None and lon is not None and elevation is not None:
            settings.set_location(lat, lon, elevation, location_name)
            print(f"Saved location settings: lat={lat}, lon={lon}, elevation={elevation}, name={location_name}")

        # Resolve simulated/current UTC time
        dt_utc = parse_time_param(time)

        # Simulated time -> prefer cache; on miss compute and trigger background precompute
        if time is not None:
            cache_file = build_cache_path('comets', lat, lon, elevation, dt=dt_utc, bucket_hours=comets.COMET_CACHE_BUCKET_HOURS)
            comet_list = None
            try:
                comet_list = read_pickle_if_fresh(cache_file, comets.COMET_CACHE_TTL_SECONDS)
                if comet_list is None and os.path.exists(cache_file):
                    with open(cache_file, 'rb') as f:
                        comet_list = pickle.load(f)
            except Exception:
                comet_list = None
            if isinstance(comet_list, list):
                result = {
                    "time": dt_utc.isoformat(),
                    "location": {"latitude": lat, "longitude": lon, "elevation": elevation},
                    "bodies": {},
                    "loading": False
                }
                for i, comet in enumerate(comet_list[:max_comets]):
                    if isinstance(comet, dict) and "name" in comet:
                        key = f"comet_{i}_{comet['name']}"
                        result["bodies"][key] = comet
                print(f"Returning {len(result['bodies'])} comets (cache)")
                return result
            # Compute on-demand and store, then trigger background precompute window
            location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
            comet_list = comets.load_comets(ts, eph, location_dict, max_comets=max_comets, use_cache=True, current_dt=dt_utc)
            result = {
                "time": dt_utc.isoformat(),
                "location": {"latitude": lat, "longitude": lon, "elevation": elevation},
                "bodies": {},
                "loading": False
            }
            for i, comet in enumerate(comet_list[:max_comets]):
                if isinstance(comet, dict) and "name" in comet:
                    key = f"comet_{i}_{comet['name']}"
                    result["bodies"][key] = comet
            print(f"Returning {len(result['bodies'])} comets (simulated compute)")
            try:
                asyncio.create_task(trigger_background_precompute_window(lat, lon, elevation, dt_utc, kinds=['celestial','asteroids','comets']))
            except Exception:
                pass
            return result

        # Real-time -> compute and store via module
        location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        comet_list = comets.load_comets(ts, eph, location_dict, max_comets=max_comets, current_dt=dt_utc)

        result = {
            "time": dt_utc.isoformat(),
            "location": {"latitude": lat, "longitude": lon, "elevation": elevation},
            "bodies": {},
            "loading": False
        }
        for i, comet in enumerate(comet_list):
            if isinstance(comet, dict) and "name" in comet:
                key = f"comet_{i}_{comet['name']}"
                result["bodies"][key] = comet
        print(f"Returning {len(result['bodies'])} comets")
        return result

    except Exception as e:
        print(f"Error in get_comets: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Request body model for precompute range
class PrecomputeRangeRequest(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    elevation: Optional[float] = None
    start_date: str
    end_date: str

# Precompute range API endpoint
@app.post(API_ENDPOINT_PRECOMPUTE_RANGE)
async def precompute_range(request: Request, body: PrecomputeRangeRequest):
    """Trigger background precomputation of celestial data for a date range.
    
    Parameters:
    - lat, lon, elevation: Location coordinates
    - start_date: ISO 8601 date string for start of range
    - end_date: ISO 8601 date string for end of range
    
    Returns status information about the precompute task.
    """
    try:
        # Get location data from request body or session/settings
        location = await get_location_from_request(request, body.lat, body.lon, body.elevation)
        if not location:
            return JSONResponse(status_code=400, content={'error': 'Invalid location'})
        
        lat = location['latitude']
        lon = location['longitude']
        elevation = location['elevation']
        
        # Parse date strings
        try:
            start_dt = parse_time_param(body.start_date)
            end_dt = parse_time_param(body.end_date)
        except Exception as e:
            return JSONResponse(status_code=400, content={'error': f'Invalid date format: {str(e)}'})
        
        print(f"Precomputing cache for range: {body.start_date} to {body.end_date}")
        print(f"Location: {lat}, {lon}, {elevation}")
        
        
        # Trigger background precomputation
        result = await trigger_background_precompute_range(
            lat, lon, elevation, start_dt, end_dt, 
            kinds=['celestial', 'asteroids', 'comets']
        )
        
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})

# Get precompute task status
@app.get(API_ENDPOINT_PRECOMPUTE_RANGE + "/{task_id}")
async def get_precompute_status(task_id: str):
    """Get status of a background precompute task by its ID.
    
    Returns the current status, progress, and other details of the task.
    """
    try:
        if not hasattr(app, 'precompute_tasks'):
            return JSONResponse(status_code=404, content={'error': 'No precompute tasks found'})
        
        if task_id not in app.precompute_tasks:
            return JSONResponse(status_code=404, content={'error': f'Task {task_id} not found'})
        
        return app.precompute_tasks[task_id]
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})

# Cache status API endpoint
@app.get(API_ENDPOINT_CACHE_STATUS)
async def get_cache_status(request: Request, loc_key: Optional[str] = None, lat: Optional[float] = None, lon: Optional[float] = None, elevation: Optional[float] = None):
    """Report status of the precomputed cache system.
    Returns targeted locations, configured kinds, horizon, current window, and counts of
    cached files per kind and location within the current rolling window.
    """
    try:
        # Get time parameter (optional)
        time = request.query_params.get('time')
        
        kinds_env = os.environ.get("ASCII_SKY_PRECOMPUTE_KINDS", "celestial,asteroids,comets").strip()
        kinds = [k.strip() for k in kinds_env.split(",") if k.strip()]
        try:
            horizon_hours = int(os.environ.get("ASCII_SKY_PRECOMPUTE_HOURS", "48"))
        except Exception:
            horizon_hours = 48

        # Time window anchored to simulated or current UTC time
        dt_utc = parse_time_param(time)
        now_utc = dt_utc
        window_start = _hour_floor(dt_utc)
        window_end = window_start + timedelta(hours=horizon_hours)

        # Determine if a specific location was requested via query params
        requested = None  # dict with keys: latitude, longitude, elevation, name, loc_key
        if loc_key:
            try:
                parts = loc_key.split("_")
                if len(parts) == 3 and parts[0].startswith("lat") and parts[1].startswith("lon") and parts[2].startswith("el"):
                    lat_s = parts[0][3:]
                    lon_s = parts[1][3:]
                    el_s = parts[2][2:]
                    lat_v = float(lat_s)
                    lon_v = float(lon_s)
                    elev_v = float(int(el_s))  # stored as signed integer with leading zeros
                    lat_n, lon_n, elev_n = normalize_location(lat_v, lon_v, elev_v)
                    requested = {
                        "latitude": float(lat_n),
                        "longitude": float(lon_n),
                        "elevation": float(elev_n),
                        "name": "",
                        "loc_key": loc_key,
                    }
            except Exception:
                requested = None

        if requested is None and (lat is not None and lon is not None):
            try:
                elev_in = float(elevation) if elevation is not None else 0.0
                lat_n, lon_n, elev_n = normalize_location(float(lat), float(lon), elev_in)
                key = location_key(lat_n, lon_n, elev_n)
                requested = {
                    "latitude": float(lat_n),
                    "longitude": float(lon_n),
                    "elevation": float(elev_n),
                    "name": "",
                    "loc_key": key,
                }
            except Exception:
                requested = None

        dedup = {}
        if requested is not None:
            dedup[requested["loc_key"]] = {
                "latitude": requested["latitude"],
                "longitude": requested["longitude"],
                "elevation": requested["elevation"],
                "name": requested.get("name", ""),
            }
        else:
            # Get target locations (lazy import to avoid circular import)
            targets = []
            try:
                try:
                    from precompute_worker import get_target_locations as _get_targets  # type: ignore
                except Exception:
                    _get_targets = None
                if _get_targets is not None:
                    try:
                        targets = _get_targets() or []
                    except Exception:
                        targets = []
            except Exception:
                targets = []
            # Fallback: include persisted user location if targets empty
            if not targets:
                try:
                    base = settings.get_location()
                    if isinstance(base, dict) and "latitude" in base and "longitude" in base:
                        targets = [{
                            "latitude": float(base.get("latitude", 0.0)),
                            "longitude": float(base.get("longitude", 0.0)),
                            "elevation": float(base.get("elevation", 0.0)),
                            "name": base.get("name", "") or ""
                        }]
                except Exception:
                    targets = []

            # De-duplicate by normalized cache location key
            for loc in targets:
                try:
                    lat_n, lon_n, elev_n = normalize_location(loc.get("latitude", 0.0), loc.get("longitude", 0.0), loc.get("elevation", 0.0))
                    key = location_key(lat_n, lon_n, elev_n)
                    dedup[key] = {
                        "latitude": float(lat_n),
                        "longitude": float(lon_n),
                        "elevation": float(elev_n),
                        "name": loc.get("name", "") or "",
                    }
                except Exception:
                    continue

        # Helper to parse bucket label 'YYYYMMDDTHH' to UTC-aware datetime
        def _parse_bucket(label: str) -> Optional[datetime]:
            try:
                dt = datetime.strptime(label, "%Y%m%dT%H")
                return dt.replace(tzinfo=timezone.utc)
            except Exception:
                return None

        # Scan counts per location/kind
        totals = {k: 0 for k in kinds}
        locations_out = []
        for loc_key, loc in dedup.items():
            counts = {}
            earliest = {}
            latest = {}
            for kind in kinds:
                try:
                    base_dir = os.path.join(CACHE_ROOT, kind, loc_key)
                    bucket_dts = []
                    if os.path.isdir(base_dir):
                        for fn in os.listdir(base_dir):
                            if not fn.endswith(".pkl"):
                                continue
                            label = fn[:-4]
                            dt = _parse_bucket(label)
                            if dt is not None:
                                bucket_dts.append(dt)
                    # Earliest/latest overall for this location/kind
                    if bucket_dts:
                        earliest[kind] = min(bucket_dts).isoformat()
                        latest[kind] = max(bucket_dts).isoformat()
                    else:
                        earliest[kind] = None
                        latest[kind] = None
                    # Count within current window
                    count_window = sum(1 for dt in bucket_dts if (dt >= window_start and dt < window_end))
                    counts[kind] = int(count_window)
                    totals[kind] = totals.get(kind, 0) + int(count_window)
                except Exception:
                    counts[kind] = 0
                    earliest[kind] = None
                    latest[kind] = None
            locations_out.append({
                **loc,
                "loc_key": loc_key,
                "counts": counts,
                "earliest": earliest,
                "latest": latest,
            })

        return {
            "now_utc": now_utc.isoformat(),
            "precompute_horizon_hours": horizon_hours,
            "window": {
                "start": window_start.isoformat(),
                "end": window_end.isoformat(),
            },
            "kinds": kinds,
            "locations": locations_out,
            "totals": totals,
        }
    except Exception as e:
        print(f"Error in get_cache_status: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
