import os
import json
import asyncio
import subprocess
import sys
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI

from cache_utils import build_cache_path, atomic_write_pickle, normalize_location, location_key, time_bucket_utc
from api.computation import compute_celestial_snapshot, LOADER, ts, eph
import bright_asteroids
import psutil
import comets

CELESTIAL_USE_SQLITE = os.getenv('CELESTIAL_USE_SQLITE', 'true').lower() == 'true'
CELESTIAL_CACHE_BUCKET_HOURS = 1
CELESTIAL_CACHE_TTL_SECONDS = 49 * 3600
BG_TASK_COOLDOWN_SECONDS = int(os.environ.get('ASCII_SKY_BG_TASK_COOLDOWN_MINUTES', '5')) * 60
MAX_WINDOW_WORKERS = int(os.environ.get('ASCII_SKY_MAX_WINDOW_WORKERS', '1'))

def _hour_floor(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.replace(minute=0, second=0, microsecond=0)


def _has_recent_window_task_for_loc(loc_key_str: str, max_age_seconds: int = BG_TASK_COOLDOWN_SECONDS) -> bool:
    """Check cache/ for any window task (status) that is running/starting and matches loc_key within TTL.
    This reads the paired task_*.json to compare normalized location. Returns True if such a task exists.
    """
    try:
        import glob
        now = datetime.now(timezone.utc)
        for status_path in glob.glob(os.path.join('cache', 'task_status_window_*.json')):
            try:
                with open(status_path, 'r') as sf:
                    sdata = json.load(sf)
                status = sdata.get('status', 'unknown')
                # Consider running/starting tasks that have been updated recently
                if status not in ('starting', 'running'):
                    continue
                last_ts_str = sdata.get('last_updated') or sdata.get('start_time')
                if not last_ts_str:
                    continue
                try:
                    last_ts = datetime.fromisoformat(last_ts_str)
                    if last_ts.tzinfo is None:
                        last_ts = last_ts.replace(tzinfo=timezone.utc)
                except Exception:
                    continue
                if (now - last_ts).total_seconds() > max_age_seconds:
                    continue

                # Load matching task file to compare location
                task_id = Path(status_path).stem.replace('task_status_', '')
                task_file = os.path.join('cache', f'task_{task_id}.json')
                if not os.path.exists(task_file):
                    continue
                with open(task_file, 'r') as tf:
                    tdata = json.load(tf)
                t_lat = float(tdata.get('lat', 0.0))
                t_lon = float(tdata.get('lon', 0.0))
                t_elev = float(tdata.get('elevation', 0.0))
                lat_n, lon_n, elev_n = normalize_location(t_lat, t_lon, t_elev)
                loc_key_cmp = f"{lat_n:.4f},{lon_n:.4f},{elev_n:.1f}"
                if loc_key_cmp == loc_key_str:
                    return True
            except Exception:
                # Ignore malformed files
                continue
    except Exception:
        pass
    return False


def _count_running_window_workers() -> int:
    """Return number of running precompute_task_worker.py processes.
    Uses psutil to scan current process list inside the container.
    """
    try:
        count = 0
        for proc in psutil.process_iter(attrs=['pid', 'name', 'cmdline']):
            try:
                cmd = proc.info.get('cmdline') or []
                if any('precompute_task_worker.py' in part for part in cmd):
                    count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return count
    except Exception:
        return 0

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
        # Init shared attributes
        if not hasattr(app, 'precompute_tasks'):
            app.precompute_tasks = {}
        if not hasattr(app, 'last_precompute_check'):
            app.last_precompute_check = {}
        if not hasattr(app, 'bg_task_lock'):
            import asyncio as _asyncio
            app.bg_task_lock = _asyncio.Lock()
        if not hasattr(app, 'window_worker_reservations'):
            app.window_worker_reservations = 0
        if not hasattr(app, 'active_window_tasks_by_loc'):
            app.active_window_tasks_by_loc = {}

        # Koordinaten normalisieren und Schlüssel bilden
        from cache_utils import normalize_location
        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = f"{lat_norm:.4f},{lon_norm:.4f},{elev_norm:.1f}"

        # Guard: vermeide Duplikate innerhalb von 5 Minuten (race-safe)
        async with app.bg_task_lock:
            now = datetime.now(timezone.utc)
            last_check_time = app.last_precompute_check.get(loc_key)
            if last_check_time and (now - last_check_time).total_seconds() < BG_TASK_COOLDOWN_SECONDS:
                print(f"[bg] Skipping duplicate task for {loc_key}, last started {(now - last_check_time).total_seconds():.1f}s ago")
                return
            # Zusätzlich: wenn bereits ein laufender/neuerer Window-Task existiert, überspringen
            if _has_recent_window_task_for_loc(loc_key, BG_TASK_COOLDOWN_SECONDS):
                print(f"[bg] Active/recent window task exists for {loc_key}; skipping new start")
                return
            # Prüfe zusätzlich auf in-flight Task für diesen Standort
            inflight = app.active_window_tasks_by_loc.get(loc_key)
            if inflight and inflight.get('status') == 'reserved':
                print(f"[bg] In-flight window task already reserved for {loc_key}; skipping new start")
                return
            # Kapazitätsgrenze für gleichzeitige Fenster-Worker beachten (inkl. Reservierungen)
            running = _count_running_window_workers()
            reserved = int(app.window_worker_reservations or 0)
            if (running + reserved) >= MAX_WINDOW_WORKERS:
                print(f"[bg] At capacity: {running + reserved}/{MAX_WINDOW_WORKERS} (incl. reservations); skipping new start for {loc_key}")
                return
            # Reserviere Slot sofort, um Rennen zu vermeiden
            app.window_worker_reservations += 1
            app.active_window_tasks_by_loc[loc_key] = {"status": "reserved", "reserved_at": now.isoformat()}
            app.last_precompute_check[loc_key] = now

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
            # Run task worker in the worker container instead of web container
            docker_cmd = [
                'docker', 'exec', '-d', 'asciisky-worker-1',
                'python', 'precompute_task_worker.py', task_file
            ]
            process = subprocess.Popen(docker_cmd, cwd=os.getcwd())
            print(f"Started background window worker in worker container for task {task_id} (docker exec PID: {process.pid})")

            if not hasattr(app, 'precompute_tasks'):
                app.precompute_tasks = {}
            app.precompute_tasks[task_id] = {
                'id': task_id,
                'status': 'starting',
                'start_time': datetime.now(timezone.utc).isoformat(),
                'worker_process': True,
                'worker_pid': process.pid
            }
            # Markiere Standort-Task als laufend
            async with app.bg_task_lock:
                app.active_window_tasks_by_loc[loc_key] = {
                    "status": "running",
                    "worker_pid": process.pid,
                    "task_id": task_id,
                    "started_at": datetime.now(timezone.utc).isoformat()
                }
        except Exception as e:
            print(f"Failed to start background window worker: {e}")
            traceback.print_exc()
        finally:
            # Reservierung freigeben
            try:
                async with app.bg_task_lock:
                    app.window_worker_reservations = max(0, int(app.window_worker_reservations or 0) - 1)
            except Exception:
                pass
    except Exception:
        print("[bg] trigger failed")
        traceback.print_exc()

async def trigger_background_precompute_range(app: FastAPI, lat: float, lon: float, elevation: float, start_dt_utc: datetime, end_dt_utc: datetime, kinds: list[str]) -> dict:
    """Kick off background precompute for a custom date range."""
    try:
        # Ensure shared guards exist
        if not hasattr(app, 'precompute_tasks'):
            app.precompute_tasks = {}
        if not hasattr(app, 'bg_task_lock'):
            import asyncio as _asyncio
            app.bg_task_lock = _asyncio.Lock()
        if not hasattr(app, 'window_worker_reservations'):
            app.window_worker_reservations = 0
        if not hasattr(app, 'active_range_tasks_by_loc'):
            app.active_range_tasks_by_loc = {}

        if start_dt_utc.tzinfo is None: start_dt_utc = start_dt_utc.replace(tzinfo=timezone.utc)
        if end_dt_utc.tzinfo is None: end_dt_utc = end_dt_utc.replace(tzinfo=timezone.utc)

        start_dt_utc, end_dt_utc = _hour_floor(start_dt_utc), _hour_floor(end_dt_utc)
        if start_dt_utc > end_dt_utc: start_dt_utc, end_dt_utc = end_dt_utc, start_dt_utc

        delta_hours = int((end_dt_utc - start_dt_utc).total_seconds() / 3600) + 1
        task_id = f"precompute_{int(time.time())}_{delta_hours}h"

        # Normalize location key (same format as window tasks)
        from cache_utils import normalize_location
        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = f"{lat_norm:.4f},{lon_norm:.4f},{elev_norm:.1f}"

        # Capacity and duplicate guards
        async with app.bg_task_lock:
            # If a range task is already running for this location, skip
            inflight = app.active_range_tasks_by_loc.get(loc_key)
            if inflight:
                return {'status': 'skipped', 'reason': 'inflight_for_location'}
            # Check capacity including reservations
            running = _count_running_window_workers()
            reserved = int(app.window_worker_reservations or 0)
            if (running + reserved) >= MAX_WINDOW_WORKERS:
                return {'status': 'skipped', 'reason': 'at_capacity', 'running': running, 'reserved': reserved}
            # Reserve slot and mark inflight
            app.window_worker_reservations += 1
            app.active_range_tasks_by_loc[loc_key] = {
                'status': 'reserved', 'reserved_at': datetime.now(timezone.utc).isoformat(),
                'hours_total': delta_hours
            }

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
            # Run task worker in the worker container instead of web container
            docker_cmd = [
                'docker', 'exec', '-d', 'asciisky-worker-1',
                'python', 'precompute_task_worker.py', task_file
            ]
            process = subprocess.Popen(docker_cmd, cwd=os.getcwd())
            print(f"Started background worker in worker container for task {task_id} (docker exec PID: {process.pid})")
            app.precompute_tasks[task_id]['worker_pid'] = process.pid
            # Mark running for this location
            async with app.bg_task_lock:
                app.active_range_tasks_by_loc[loc_key] = {
                    'status': 'running', 'task_id': task_id, 'worker_pid': process.pid,
                    'started_at': datetime.now(timezone.utc).isoformat(), 'hours_total': delta_hours
                }
        except Exception as e:
            print(f"Failed to start background worker: {e}")
            traceback.print_exc()
        finally:
            # Release reservation
            try:
                async with app.bg_task_lock:
                    app.window_worker_reservations = max(0, int(app.window_worker_reservations or 0) - 1)
            except Exception:
                pass

        return {'task_id': task_id, 'status': 'started', 'message': f'Background precompute started for {delta_hours} hours', 'hours_total': delta_hours}
    except Exception as e:
        print("Error starting background precompute range")
        traceback.print_exc()
        return {'error': str(e), 'status': 'failed to start'}
