import os
import json
import asyncio
import subprocess
import sys
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI

from cache_utils import build_cache_path, atomic_write_pickle, normalize_location, location_key, time_bucket_utc
from api.computation import compute_celestial_snapshot, LOADER, ts, eph
import bright_asteroids
import comets

CELESTIAL_USE_SQLITE = os.getenv('CELESTIAL_USE_SQLITE', 'true').lower() == 'true'
CELESTIAL_CACHE_BUCKET_HOURS = 1
CELESTIAL_CACHE_TTL_SECONDS = 49 * 3600

def _hour_floor(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.replace(minute=0, second=0, microsecond=0)

def ensure_celestial_cache(lat: float, lon: float, elevation: float, dt_utc: datetime):
    """Ensure celestial cache exists for given location/time."""
    try:
        if CELESTIAL_USE_SQLITE:
            lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
            loc_key = location_key(lat_norm, lon_norm, elev_norm)
            time_bucket = time_bucket_utc(dt_utc, CELESTIAL_CACHE_BUCKET_HOURS)

            try:
                from db_utils import get_celestial_snapshot
                cached_snapshot = get_celestial_snapshot(loc_key, time_bucket, CELESTIAL_CACHE_TTL_SECONDS)
                if cached_snapshot:
                    return
            except Exception as e:
                print(f"[bg] SQLite celestial cache check failed: {e}")

        cache_file = build_cache_path('celestial', lat, lon, elevation, dt=dt_utc, bucket_hours=CELESTIAL_CACHE_BUCKET_HOURS)
        if not os.path.exists(cache_file):
            snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)

            if CELESTIAL_USE_SQLITE:
                try:
                    from db_utils import store_celestial_snapshot
                    store_celestial_snapshot(loc_key, time_bucket, lat, lon, elevation, snapshot)
                except Exception as e:
                    print(f"[bg] Failed to store celestial snapshot in SQLite: {e}")

            atomic_write_pickle(cache_file, snapshot)
    except Exception:
        print(f"[bg] celestial ensure failed for {lat},{lon},{elevation} @ {dt_utc.isoformat()}")
        traceback.print_exc()

def _ensure_asteroids_cache(lat: float, lon: float, elevation: float, dt_utc: datetime) -> bool:
    """Ensure asteroid cache exists. Returns True if cache was already present, False if generated."""
    try:
        if bright_asteroids.ASTEROID_USE_SQLITE:
            from cache_utils import normalize_location, location_key, time_bucket_utc
            from db_utils import get_asteroid_positions
            lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
            loc_key = location_key(lat_norm, lon_norm, elev_norm)
            time_bucket = time_bucket_utc(dt_utc, bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS)
            cached_positions = get_asteroid_positions(loc_key, time_bucket, bright_asteroids.ASTEROID_CACHE_TTL_SECONDS)
            if cached_positions:
                return True

        location = {"latitude": lat, "longitude": lon, "elevation": elevation}
        _ = bright_asteroids.load_bright_asteroids(
            LOADER, ts, eph, location,
            max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE,
            use_cache=True, current_dt=dt_utc
        )
        return False
    except Exception:
        print(f"[bg] asteroids ensure failed for {lat},{lon},{elevation} @ {dt_utc.isoformat()}")
        traceback.print_exc()
        return False

def _ensure_comets_cache(lat: float, lon: float, elevation: float, dt_utc: datetime) -> bool:
    """Ensure comet cache exists. Returns True if cache was already present, False if generated."""
    try:
        if comets.COMET_USE_SQLITE:
            from cache_utils import normalize_location, location_key, time_bucket_utc
            from db_utils import get_comet_positions
            lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
            loc_key = location_key(lat_norm, lon_norm, elev_norm)
            time_bucket = time_bucket_utc(dt_utc, comets.COMET_CACHE_BUCKET_HOURS)
            cached_positions = get_comet_positions(loc_key, time_bucket, comets.COMET_CACHE_TTL_SECONDS)
            if cached_positions:
                return True

        location = {"latitude": lat, "longitude": lon, "elevation": elevation}
        _ = comets.load_comets(ts, eph, location, use_cache=True, current_dt=dt_utc)
        return False
    except Exception:
        print(f"[bg] comets ensure failed for {lat},{lon},{elevation} @ {dt_utc.isoformat()}")
        traceback.print_exc()
        return False

async def trigger_background_precompute_window(app: FastAPI, lat: float, lon: float, elevation: float, dt_utc: datetime, kinds: list[str]) -> None:
    """Kick off background precompute for a 48h window relative to dt_utc."""
    try:
        # Prüfe, ob bereits ein ähnlicher Task in den letzten 5 Minuten gestartet wurde
        if hasattr(app, 'precompute_tasks') and hasattr(app, 'last_precompute_check'):
            # Koordinaten normalisieren für Vergleich
            from cache_utils import normalize_location
            lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
            loc_key = f"{lat_norm:.4f},{lon_norm:.4f},{elev_norm:.1f}"
            
            now = datetime.now(timezone.utc)
            last_check_time = getattr(app, 'last_precompute_check', {}).get(loc_key)
            
            # Wenn für diesen Standort innerhalb der letzten 5 Minuten bereits ein Task gestartet wurde, überspringen
            if last_check_time and (now - last_check_time).total_seconds() < 300:  # 5 Minuten
                print(f"[bg] Skipping duplicate task for {loc_key}, last started {(now - last_check_time).total_seconds():.1f}s ago")
                return
        
        # Initialisiere die Tracking-Attribute, falls sie noch nicht existieren
        if not hasattr(app, 'precompute_tasks'):
            app.precompute_tasks = {}
        if not hasattr(app, 'last_precompute_check'):
            app.last_precompute_check = {}
        
        # Aktualisiere den Zeitstempel für diesen Standort
        from cache_utils import normalize_location
        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = f"{lat_norm:.4f},{lon_norm:.4f},{elev_norm:.1f}"
        app.last_precompute_check[loc_key] = datetime.now(timezone.utc)
        
        horizon_hours = int(os.environ.get("ASCII_SKY_PRECOMPUTE_HOURS", "48"))
        now_utc = datetime.now(timezone.utc)
        base = _hour_floor(dt_utc)
        forward = base >= _hour_floor(now_utc)

        task_id = f"window_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        task_data = {
            'task_id': task_id, 'lat': lat, 'lon': lon, 'elevation': elevation,
            'start_dt_utc': (base if forward else base - timedelta(hours=horizon_hours-1)).isoformat(),
            'end_dt_utc': (base + timedelta(hours=horizon_hours-1) if forward else base).isoformat(),
            'kinds': kinds
        }

        task_file = f"cache/task_{task_id}.json"
        os.makedirs(os.path.dirname(task_file), exist_ok=True)
        with open(task_file, 'w') as f:
            json.dump(task_data, f)

        try:
            worker_script = os.path.join(os.getcwd(), 'precompute_task_worker.py')
            process = subprocess.Popen([sys.executable, worker_script, task_file], cwd=os.getcwd(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            print(f"Started background window worker process for task {task_id} (PID: {process.pid})")

            if not hasattr(app, 'precompute_tasks'):
                app.precompute_tasks = {}
            app.precompute_tasks[task_id] = {
                'id': task_id,
                'status': 'starting',
                'start_time': datetime.now(timezone.utc).isoformat(),
                'worker_process': True,
                'worker_pid': process.pid
            }
        except Exception as e:
            print(f"Failed to start background window worker: {e}")
            traceback.print_exc()
    except Exception:
        print("[bg] trigger failed")
        traceback.print_exc()

async def trigger_background_precompute_range(app: FastAPI, lat: float, lon: float, elevation: float, start_dt_utc: datetime, end_dt_utc: datetime, kinds: list[str]) -> dict:
    """Kick off background precompute for a custom date range."""
    try:
        if start_dt_utc.tzinfo is None: start_dt_utc = start_dt_utc.replace(tzinfo=timezone.utc)
        if end_dt_utc.tzinfo is None: end_dt_utc = end_dt_utc.replace(tzinfo=timezone.utc)

        start_dt_utc, end_dt_utc = _hour_floor(start_dt_utc), _hour_floor(end_dt_utc)
        if start_dt_utc > end_dt_utc: start_dt_utc, end_dt_utc = end_dt_utc, start_dt_utc

        delta_hours = int((end_dt_utc - start_dt_utc).total_seconds() / 3600) + 1
        task_id = f"precompute_{int(time.time())}_{delta_hours}h"

        if not hasattr(app, 'precompute_tasks'):
            app.precompute_tasks = {}

        app.precompute_tasks[task_id] = {
            'id': task_id, 'status': 'starting', 'start_time': datetime.now(timezone.utc).isoformat(),
            'location': {'lat': lat, 'lon': lon, 'elevation': elevation},
            'date_range': {'start': start_dt_utc.isoformat(), 'end': end_dt_utc.isoformat()},
            'hours_total': delta_hours, 'hours_completed': 0, 'percent_complete': 0, 'worker_process': True
        }

        task_data = {
            'task_id': task_id, 'lat': lat, 'lon': lon, 'elevation': elevation,
            'start_dt_utc': start_dt_utc.isoformat(), 'end_dt_utc': end_dt_utc.isoformat(), 'kinds': kinds
        }

        task_file = f"cache/task_{task_id}.json"
        os.makedirs(os.path.dirname(task_file), exist_ok=True)
        with open(task_file, 'w') as f:
            json.dump(task_data, f)

        try:
            worker_script = os.path.join(os.getcwd(), 'precompute_task_worker.py')
            process = subprocess.Popen([sys.executable, worker_script, task_file], cwd=os.getcwd(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            print(f"Started background worker process for task {task_id} (PID: {process.pid})")
            app.precompute_tasks[task_id]['worker_pid'] = process.pid
        except Exception as e:
            print(f"Failed to start background worker: {e}")
            traceback.print_exc()

        return {'task_id': task_id, 'status': 'started', 'message': f'Background precompute started for {delta_hours} hours', 'hours_total': delta_hours}
    except Exception as e:
        print("Error starting background precompute range")
        traceback.print_exc()
        return {'error': str(e), 'status': 'failed to start'}
