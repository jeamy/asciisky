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

# Import database utilities if available
try:
    from db_utils import get_celestial_snapshot, store_celestial_snapshot
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

def _hour_floor(dt):
    """Round datetime down to the nearest hour"""
    return dt.replace(minute=0, second=0, microsecond=0)

def ensure_celestial_cache(lat, lon, elevation, dt_utc):
    """Ensure celestial cache exists for given location and time"""
    try:
        # Import the computation module
        from api.computation import compute_celestial_snapshot, ts, eph
        
        # Check if cache already exists
        cache_file = build_cache_path('celestial', lat, lon, elevation, dt=dt_utc, bucket_hours=1)
        if os.path.exists(cache_file):
            print(f"[worker] Celestial cache exists for {lat}, {lon} at {dt_utc}")
            return True
            
        # Generate celestial snapshot
        print(f"[worker] Generating celestial cache for {lat}, {lon} at {dt_utc}")
        snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
        
        # Store in cache
        atomic_write_pickle(cache_file, snapshot)
        print(f"[worker] Stored celestial cache: {cache_file}")
        
        # Also store in database if available
        if DB_AVAILABLE:
            try:
                from cache_utils import normalize_location, location_key, time_bucket_utc
                lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
                loc_key = location_key(lat_norm, lon_norm, elev_norm)
                time_bucket = time_bucket_utc(dt_utc, 1)  # 1 hour buckets
                store_celestial_snapshot(loc_key, time_bucket, lat, lon, elevation, snapshot)
                print(f"[worker] Stored celestial snapshot in database")
            except Exception as e:
                print(f"[worker] Failed to store celestial snapshot in database: {e}")
        
        return True
    except Exception as e:
        print(f"[worker] Error generating celestial cache: {e}")
        import traceback
        traceback.print_exc()
        return False

def _ensure_asteroids_cache(lat, lon, elevation, dt_utc):
    """Ensure asteroid cache exists for given location and time"""
    try:
        # Import skyfield objects from the computation module
        from api.computation import LOADER, ts, eph
        
        # Create location dict as expected by load_bright_asteroids
        location = {"latitude": lat, "longitude": lon, "elevation": elevation}

        result = bright_asteroids.load_bright_asteroids(
            LOADER, ts, eph, location,
            max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE,
            use_cache=True, current_dt=dt_utc
        )
        return result is not None
    except Exception as e:
        print(f"[worker] Error generating asteroid cache: {e}")
        import traceback
        traceback.print_exc()
        return False

def _ensure_comets_cache(lat, lon, elevation, dt_utc):
    """Ensure comet cache exists for given location and time"""
    try:
        # Import skyfield objects from the computation module
        from api.computation import ts, eph
        
        # Create location dict as expected by load_comets
        location = {"latitude": lat, "longitude": lon, "elevation": elevation}

        result = comets.load_comets(ts, eph, location, use_cache=True, current_dt=dt_utc)
        return result is not None
    except Exception as e:
        print(f"[worker] Error generating comet cache: {e}")
        import traceback
        traceback.print_exc()
        return False

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
    import gc
    
    try:
        # Load task data
        with open(task_file, 'r') as f:
            task_data = json.load(f)

        task_id = task_data['task_id']
        lat = task_data['lat']
        lon = task_data['lon']
        elevation = task_data['elevation']
        start_dt_utc = datetime.fromisoformat(task_data['start_dt_utc'])
        end_dt_utc = datetime.fromisoformat(task_data['end_dt_utc'])
        kinds = task_data['kinds']

        print(f"[worker] Starting task {task_id}")
        print(f"[worker] Location: {lat}, {lon}, {elevation}")
        print(f"[worker] Time range: {start_dt_utc} to {end_dt_utc}")
        print(f"[worker] Kinds: {kinds}")

        # Update status to running
        update_task_status(task_id, {
            'status': 'running',
            'start_time': datetime.now(timezone.utc).isoformat()
        })

        # Calculate total hours
        delta_hours = int((end_dt_utc - start_dt_utc).total_seconds() / 3600) + 1

        # Strategische Prioritätsliste: aktuelles Datum zuerst, dann Zukunft, dann Vergangenheit
        now_utc = datetime.now(timezone.utc)
        now_hour = _hour_floor(now_utc)

        # Erstelle prioritätsbasierte Liste der zu berechnenden Stunden
        hours_to_process = []

        # 1. Priorität: Aktuelle Stunde (falls im Bereich)
        if start_dt_utc <= now_hour <= end_dt_utc:
            hours_to_process.append(now_hour)
            print(f"[worker] Priority 1: Current hour {now_hour.isoformat()}")

        # 2. Priorität: Zukunft (nächste Stunden nach jetzt)
        future_hours = []
        current_dt = now_hour + timedelta(hours=1)
        while current_dt <= end_dt_utc:
            if current_dt not in hours_to_process:
                future_hours.append(current_dt)
            current_dt += timedelta(hours=1)

        # Sortiere Zukunft chronologisch (nächste Stunden zuerst)
        future_hours.sort()
        hours_to_process.extend(future_hours)
        print(f"[worker] Priority 2: Future hours ({len(future_hours)} hours)")

        # 3. Priorität: Vergangenheit (Stunden vor jetzt)
        past_hours = []
        current_dt = now_hour - timedelta(hours=1)
        while current_dt >= start_dt_utc:
            if current_dt not in hours_to_process:
                past_hours.append(current_dt)
            current_dt -= timedelta(hours=1)

        # Sortiere Vergangenheit umgekehrt chronologisch (neueste zuerst)
        past_hours.sort(reverse=True)
        hours_to_process.extend(past_hours)
        print(f"[worker] Priority 3: Past hours ({len(past_hours)} hours)")

        # Falls aktueller Zeitpunkt außerhalb des Bereichs liegt, normale chronologische Reihenfolge
        if not (start_dt_utc <= now_hour <= end_dt_utc):
            hours_to_process = []
            current_dt = start_dt_utc
            while current_dt <= end_dt_utc:
                hours_to_process.append(current_dt)
                current_dt += timedelta(hours=1)
            print(f"[worker] Current time outside range, using chronological order")

        hours_completed = 0
        hours_skipped = 0
        
        # Verarbeite Stunden in prioritätsbasierter Reihenfolge
        for process_dt in hours_to_process:
            hour_had_cache = True  # Track if all kinds had cache for this hour

            for k in kinds:
                kind_had_cache = False

                if k == 'celestial':
                    cache_existed = ensure_celestial_cache(lat, lon, elevation, process_dt)
                    if cache_existed:
                        kind_had_cache = True
                        print(f"[worker] celestial cache exists for {process_dt.isoformat()}")
                    else:
                        print(f"[worker] generated celestial cache for {process_dt.isoformat()}")
                elif k == 'asteroids':
                    cache_existed = _ensure_asteroids_cache(lat, lon, elevation, process_dt)
                    if cache_existed:
                        kind_had_cache = True
                        print(f"[worker] asteroid cache exists for {process_dt.isoformat()}")
                    else:
                        print(f"[worker] generated asteroid cache for {process_dt.isoformat()}")
                elif k == 'comets':
                    cache_existed = _ensure_comets_cache(lat, lon, elevation, process_dt)
                    if cache_existed:
                        kind_had_cache = True
                        print(f"[worker] comet cache exists for {process_dt.isoformat()}")
                    else:
                        print(f"[worker] generated comet cache for {process_dt.isoformat()}")

                if not kind_had_cache:
                    hour_had_cache = False
            
            # Count all processed hours, but track skipped separately
            hours_completed += 1
            if hour_had_cache:
                hours_skipped += 1
            
            # GC every 20 hours to prevent memory buildup
            if hours_completed % 20 == 0:
                gc.collect()
            
            # Update progress
            percent_complete = round((hours_completed / delta_hours) * 100, 1)
            update_task_status(task_id, {
                'hours_completed': hours_completed,
                'hours_skipped': hours_skipped,
                'percent_complete': percent_complete,
                'current_processing': process_dt.isoformat()
            })

            print(f"[worker] Progress: {hours_completed}/{delta_hours} ({percent_complete}%)")
        
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
    finally:
        # Final cleanup: close database connections and force GC
        try:
            from db_utils import close_db_connection
            close_db_connection()
            gc.collect()
        except Exception as cleanup_err:
            print(f"[worker] Cleanup warning: {cleanup_err}")

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
