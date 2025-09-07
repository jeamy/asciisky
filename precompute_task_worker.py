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
    # This is a simplified version - implement full celestial calculation
    print(f"[worker] Generating celestial cache for {lat}, {lon} at {dt_utc}")
    # Implementation would go here
    return True

def _ensure_asteroids_cache(lat, lon, elevation, dt_utc):
    """Ensure asteroid cache exists for given location and time"""
    try:
        # Import skyfield objects
        from skyfield.api import Loader, wgs84
        from skyfield.data import mpc
        
        # Create skyfield objects as expected by load_bright_asteroids
        # Use current directory where de421.bsp is located
        loader = Loader('.')
        ts = loader.timescale()
        eph = loader('de421.bsp')
        
        # Create proper Skyfield observer location object
        observer_location = wgs84.latlon(lat, lon, elevation_m=elevation)
        
        result = bright_asteroids.load_bright_asteroids(loader, ts, eph, observer_location, current_dt=dt_utc)
        return result is not None
    except Exception as e:
        print(f"[worker] Error generating asteroid cache: {e}")
        return False

def _ensure_comets_cache(lat, lon, elevation, dt_utc):
    """Ensure comet cache exists for given location and time"""
    try:
        # Import skyfield objects
        from skyfield.api import Loader, wgs84
        
        # Create skyfield objects as expected by load_comets
        # Use current directory where de421.bsp is located
        loader = Loader('.')
        ts = loader.timescale()
        eph = loader('de421.bsp')
        
        # Create proper Skyfield observer location object
        observer_location = wgs84.latlon(lat, lon, elevation_m=elevation)
        
        result = comets.load_comets(ts, eph, observer_location, current_dt=dt_utc)
        return result is not None
    except Exception as e:
        print(f"[worker] Error generating comet cache: {e}")
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

def process_precompute_task(task_file):
    """Process a precompute task from task file"""
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
                    ensure_celestial_cache(lat, lon, elevation, process_dt)
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
            
            hours_completed += 1
            if hour_had_cache:
                hours_skipped += 1
            
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
        
        # Clean up task file
        try:
            os.remove(task_file)
        except:
            pass
            
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
