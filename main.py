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
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
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
from cache_utils import build_cache_path, read_pickle_if_fresh, atomic_write_pickle

# Initialisiere FastAPI
app = FastAPI(title="AsciiSky API", description="API für die ASCII-Darstellung des Sternenhimmels")
SESSION_SECRET = os.environ.get("ASCII_SKY_SESSION_SECRET", "dev-secret-please-change")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax")

# Statische Dateien und Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# API-Endpunkte
API_ENDPOINT_CELESTIAL = "/api/celestial"
API_ENDPOINT_ASTEROIDS = "/api/asteroids"
API_ENDPOINT_COMETS = "/api/comets"
API_ENDPOINT_BRIGHT_ASTEROIDS = "/api/bright_asteroids"

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
    'asteroid': '•',
    'comet': '☄️'
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
                    import math
                    moon_phase = almanac.moon_phase(eph, t)
                    moon_phase_angle = float(moon_phase.radians)
                    phase_factor = 0.5 * (1 - math.cos(moon_phase_angle))
                    phase_percent = (1 - phase_factor * 2) * 100
                    if phase_percent < 0:
                        phase_percent = 0
                    if phase_percent > 100:
                        phase_percent = 100
                    if phase_percent < 5:
                        phase_name = "new_moon"
                    elif phase_percent < 45:
                        phase_name = "waxing_crescent"
                    elif phase_percent < 55:
                        phase_name = "first_quarter"
                    elif phase_percent < 95:
                        phase_name = "waxing_gibbous"
                    elif phase_percent < 100:
                        phase_name = "full_moon"
                    elif phase_percent < 145:
                        phase_name = "waning_gibbous"
                    elif phase_percent < 155:
                        phase_name = "last_quarter"
                    else:
                        phase_name = "waning_crescent"
                    body_entry["phase"] = phase_percent / 100
                    body_entry["phase_name"] = phase_name
                except Exception:
                    pass

            result["bodies"][name] = body_entry
        except Exception as e:
            print(f"Error calculating position for {name}: {str(e)}")
            continue

    return result

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

        # If a simulated time was provided, read from cache only (ignore TTL if necessary)
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
            # Fallback placeholder while worker prepares snapshot
            return {
                "time": dt_utc.isoformat(),
                "location": {"latitude": lat, "longitude": lon, "elevation": elevation},
                "bodies": {},
                "loading": True
            }

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

        # Simulated time -> cache-only
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
            # Placeholder while worker prepares snapshot
            return {
                "id": body_id,
                "name": body_id,
                "symbol": BODY_SYMBOLS.get(body_id, "?"),
                "visible": True,
                "loading": True
            }

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

        # Simulated time -> cache-only
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
            return {
                "time": dt_utc.isoformat(),
                "location": {"latitude": lat, "longitude": lon, "elevation": elevation},
                "bodies": {},
                "loading": True
            }

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

        # Simulated time -> cache-only
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
            return {
                "time": dt_utc.isoformat(),
                "location": {"latitude": lat, "longitude": lon, "elevation": elevation},
                "max_magnitude": max_magnitude,
                "bodies": {},
                "loading": True
            }

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

        # Simulated time -> cache-only
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
            return {
                "time": dt_utc.isoformat(),
                "location": {"latitude": lat, "longitude": lon, "elevation": elevation},
                "bodies": {},
                "loading": True
            }

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
