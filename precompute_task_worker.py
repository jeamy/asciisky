#!/usr/bin/env python3
"""
Separater Worker-Prozess für Precompute-Tasks
Läuft komplett isoliert vom Hauptprozess um Blockierungen zu vermeiden
"""
import os
import sys
import json
import pickle
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import settings
import bright_asteroids
import comets
from cache_utils import build_cache_path, read_pickle_if_fresh, atomic_write_pickle, CACHE_ROOT, normalize_location, location_key, time_bucket_utc
import main as webapp
import traceback

# Import database utilities if available
try:
    from db_utils import get_celestial_snapshot, store_celestial_snapshot, get_asteroid_positions, get_comet_positions
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

def _hour_floor(dt):
    """Round datetime down to the nearest hour"""
    return dt.replace(minute=0, second=0, microsecond=0)

def ensure_celestial_cache(lat, lon, elevation, dts_utc):
    """Ensure celestial cache exists for a list of datetimes."""
    for dt_utc in dts_utc:
        path = build_cache_path("celestial", lat, lon, elevation, dt=dt_utc, bucket_hours=1)
        if os.path.exists(path):
            continue

        try:
            snapshot = webapp.compute_celestial_snapshot(lat, lon, elevation, dt_utc)
            atomic_write_pickle(path, snapshot)
        except Exception:
            print(f"[worker] ERROR: Failed to generate celestial cache for {lat}, {lon} at {dt_utc}")
            traceback.print_exc()

def _ensure_asteroids_cache(lat, lon, elevation, dts_utc):
    """Ensure asteroid cache exists for a list of datetimes."""
    for dt_utc in dts_utc:
        if DB_AVAILABLE and bright_asteroids.ASTEROID_USE_SQLITE:
            lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
            loc_key = location_key(lat_norm, lon_norm, elev_norm)
            time_bucket = time_bucket_utc(dt_utc, bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS)
            if get_asteroid_positions(loc_key, time_bucket):
                continue

        path = build_cache_path("asteroids", lat, lon, elevation, dt=dt_utc, bucket_hours=bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS)
        if os.path.exists(path):
            continue

        try:
            from skyfield.api import wgs84
            observer_location = wgs84.latlon(lat, lon, elevation_m=elevation)
            bright_asteroids.load_bright_asteroids(
                webapp.LOADER, webapp.ts, webapp.eph, observer_location, current_dt=dt_utc
            )
        except Exception as e:
            print(f"[worker] Error generating asteroid cache: {e}")

def _ensure_comets_cache(lat, lon, elevation, dts_utc):
    """Ensure comet cache exists for a list of datetimes."""
    for dt_utc in dts_utc:
        if DB_AVAILABLE and comets.COMET_USE_SQLITE:
            lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
            loc_key = location_key(lat_norm, lon_norm, elev_norm)
            time_bucket = time_bucket_utc(dt_utc, comets.COMET_CACHE_BUCKET_HOURS)
            if get_comet_positions(loc_key, time_bucket):
                continue

        path = build_cache_path("comets", lat, lon, elevation, dt=dt_utc, bucket_hours=comets.COMET_CACHE_BUCKET_HOURS)
        if os.path.exists(path):
            continue

        try:
            from skyfield.api import wgs84
            observer_location = wgs84.latlon(lat, lon, elevation_m=elevation)
            comets.load_comets(
                webapp.ts, webapp.eph, observer_location, current_dt=dt_utc
            )
        except Exception as e:
            print(f"[worker] Error generating comet cache: {e}")

def update_task_status(task_id, status_update):
    """Update task status in shared file"""
    status_file = f"cache/task_status_{task_id}.json"
    try:
        # Read existing status
        if os.path.exists(status_file):
            with open(status_file, 'r') as f:
                status = json.load(f)
        else:
            status = {'id': task_id, 'status': 'starting'}
        
        # Update with new data
        status.update(status_update)
        status['last_updated'] = datetime.now(timezone.utc).isoformat()
        
        # Write atomically
        temp_file = f"{status_file}.tmp"
        with open(temp_file, 'w') as f:
            json.dump(status, f)
        os.replace(temp_file, status_file)
        
    except Exception as e:
        print(f"[worker] Error updating task status: {e}")

def cleanup_task_files(task_id, task_file):
    """Clean up both task and status files for a completed/failed task"""
    files_to_remove = [
        task_file,  # cache/task_{task_id}.json
        f"cache/task_status_{task_id}.json"  # Status file
    ]
    
    for file_path in files_to_remove:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"[worker] Removed: {file_path}")
            except Exception as e:
                print(f"[worker] Failed to remove {file_path}: {e}")

def process_precompute_task(task_file):
    """Process a precompute task from task file"""
    try:
        with open(task_file, 'r') as f:
            task_data = json.load(f)

        task_id = task_data['task_id']
        lat, lon, elevation = task_data['lat'], task_data['lon'], task_data['elevation']
        start_dt_utc = datetime.fromisoformat(task_data['start_dt_utc'])
        end_dt_utc = datetime.fromisoformat(task_data['end_dt_utc'])
        kinds = task_data['kinds']

        print(f"[worker] Starting task {task_id} for {lat}, {lon}, {start_dt_utc} to {end_dt_utc}")

        update_task_status(task_id, {'status': 'running', 'start_time': datetime.now(timezone.utc).isoformat()})

        # Generate a prioritized list of hours to process
        now_hour = _hour_floor(datetime.now(timezone.utc))
        all_hours = [start_dt_utc + timedelta(hours=i) for i in range(int((end_dt_utc - start_dt_utc).total_seconds() / 3600) + 1)]
        
        hours_to_process = sorted(all_hours, key=lambda dt: (
            dt != now_hour,  # Current hour first
            dt < now_hour,   # Then future hours
            abs((dt - now_hour).total_seconds()) # Then by proximity to now
        ))

        total_hours = len(hours_to_process)
        hours_completed = 0
        
        # Process kind by kind for better batching
        for kind_idx, kind in enumerate(kinds):
            print(f"[worker] Processing kind: {kind} ({kind_idx+1}/{len(kinds)})")
            
            if kind == 'celestial':
                ensure_celestial_cache(lat, lon, elevation, hours_to_process)
            elif kind == 'asteroids':
                _ensure_asteroids_cache(lat, lon, elevation, hours_to_process)
            elif kind == 'comets':
                _ensure_comets_cache(lat, lon, elevation, hours_to_process)
            
            # Update progress after each kind is processed
            hours_completed += total_hours # This is not quite right, but a placeholder
            percent_complete = round(((kind_idx + 1) / len(kinds)) * 100, 1)
            update_task_status(task_id, {
                'percent_complete': percent_complete,
                'current_kind': kind,
            })
            print(f"[worker] Progress: {percent_complete}%")

        
        # Mark as completed
        update_task_status(task_id, {
            'status': 'completed',
            'end_time': datetime.now(timezone.utc).isoformat()
        })
        
        print(f"[worker] Task {task_id} completed successfully")
        
        # Clean up both task and status files
        cleanup_task_files(task_id, task_file)
        print(f"[worker] Cleaned up files for task {task_id}")
            
    except Exception as e:
        print(f"[worker] Error in task {task_id}: {e}")
        import traceback
        traceback.print_exc()
        
        # Mark as error
        update_task_status(task_id, {
            'status': 'error',
            'error': str(e),
            'end_time': datetime.now(timezone.utc).isoformat()
        })
        
        # Clean up task files even on error (after status update)
        cleanup_task_files(task_id, task_file)
        print(f"[worker] Cleaned up files for failed task {task_id}")

def main():
    if len(sys.argv) != 2:
        print("Usage: precompute_task_worker.py <task_file>")
        sys.exit(1)
    
    task_file = sys.argv[1]
    if not os.path.exists(task_file):
        print(f"Task file not found: {task_file}")
        sys.exit(1)
    
    process_precompute_task(task_file)

if __name__ == "__main__":
    main()
