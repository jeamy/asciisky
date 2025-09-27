"""
AsciiSky Precompute Worker
- Maintains per-hour cached snapshots for the next N hours (default 48 or env override)
- Kinds: celestial, asteroids, comets
- Sources locations from:
  * settings.get_location() (persisted user location)
  * optional env ASCII_SKY_PRECOMPUTE_LOCATIONS (JSON array or CSV "lat,lon,elev;...")
  * optional precompute_locations.json file at project root (JSON array)
  * existing cached locations under cache/<kind>/* (directory names 'lat±DD.DDDD_lon±DD.DDDD_el±DDDDD')
- Runs every hour (at top of hour) to keep a rolling window fresh by creating any
  missing per-hour cache files.
- Optional retention pruning deletes snapshots older than a configured number of days.

Environment variables:
- ASCII_SKY_PRECOMPUTE_HOURS: horizon in hours (default 48)
- ASCII_SKY_PRECOMPUTE_KINDS: comma-separated list of kinds to precompute
  (default: "celestial,asteroids,comets")
- ASCII_SKY_PRECOMPUTE_LOCATIONS: JSON array of objects with latitude/longitude/elevation
  or CSV string "lat,lon,elev;lat,lon,elev"
- ASCII_SKY_PRECOMPUTE_WORKERS: number of parallel workers for location processing (default 3)
- ASCII_SKY_ADAPTIVE_WORKERS: if set to "1", enable adaptive worker scaling based on system load
- ASCII_SKY_RETENTION_DAYS: if set to a positive integer N, prune cache files older than N days
- ASCII_SKY_WORKER_RUN_ONCE: if set to "1", run a single sweep and exit
- TZ should be set in Docker to ensure local logging timestamps
"""
from __future__ import annotations

import os
import json
import time
import traceback
import psutil
import gc
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# Local imports
import settings
import bright_asteroids
import comets
from api.computation import ts, eph
from cache_utils import (
    build_cache_path,
    normalize_location,
    location_key,
    atomic_write_pickle,
    CACHE_ROOT,
)
from db_utils import (
    store_asteroid_positions,
    get_asteroid_positions,
    get_database_stats,
    cleanup_old_positions,
    has_asteroid_positions,
    has_comet_positions,
)

# Skyfield objects are imported from api.computation


def _now_utc() -> datetime:
    dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_locations_env() -> List[Dict[str, float]]:
    """Parse locations from env ASCII_SKY_PRECOMPUTE_LOCATIONS.
    Accepts JSON array of objects or CSV string "lat,lon,elev;lat,lon,elev".
    """
    raw = os.environ.get("ASCII_SKY_PRECOMPUTE_LOCATIONS", "").strip()
    if not raw:
        return []
    # Try JSON first
    try:
        data = json.loads(raw)
        out: List[Dict[str, float]] = []
        if isinstance(data, list):
            for item in data:
                try:
                    out.append({
                        "latitude": float(item.get("latitude")),
                        "longitude": float(item.get("longitude")),
                        "elevation": float(item.get("elevation", 0.0)),
                        "name": item.get("name", "") or ""
                    })
                except Exception:
                    continue
        return [loc for loc in out if isinstance(loc.get("latitude"), float) and isinstance(loc.get("longitude"), float)]
    except Exception:
        pass
    # Fallback CSV format
    try:
        parts = [p.strip() for p in raw.split(";") if p.strip()]
        out = []
        for p in parts:
            fields = [f.strip() for f in p.split(",")]
            if len(fields) >= 2:
                lat = float(fields[0])
                lon = float(fields[1])
                elev = float(fields[2]) if len(fields) >= 3 else 0.0
                out.append({"latitude": lat, "longitude": lon, "elevation": elev})
        return out
    except Exception:
        return []


def _parse_locations_file() -> List[Dict[str, float]]:
    """Parse optional precompute_locations.json from project root."""
    path = os.path.join(os.getcwd(), "precompute_locations.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            data = json.load(f)
        out: List[Dict[str, float]] = []
        if isinstance(data, list):
            for item in data:
                try:
                    out.append({
                        "latitude": float(item.get("latitude")),
                        "longitude": float(item.get("longitude")),
                        "elevation": float(item.get("elevation", 0.0)),
                        "name": item.get("name", "") or ""
                    })
                except Exception:
                    continue
        return out
    except Exception:
        return []


def get_target_locations() -> List[Dict[str, Any]]:
    """Collect and de-duplicate target locations for precompute.
    Sources in order:
      1) persisted user location (settings.get_location())
      2) env/file configured lists
      3) all existing cached locations under cache/<kind>/*
    """
    locs: List[Dict[str, Any]] = []

    # 1) Persisted user location
    try:
        base = settings.get_location()
        if isinstance(base, dict) and "latitude" in base and "longitude" in base:
            locs.append({
                "latitude": float(base.get("latitude", 0.0)),
                "longitude": float(base.get("longitude", 0.0)),
                "elevation": float(base.get("elevation", 0.0)),
                "name": base.get("name", "") or ""
            })
    except Exception:
        pass

    # 2) Env/file locations
    for lst in (_parse_locations_env(), _parse_locations_file()):
        for item in lst:
            try:
                locs.append({
                    "latitude": float(item.get("latitude", 0.0)),
                    "longitude": float(item.get("longitude", 0.0)),
                    "elevation": float(item.get("elevation", 0.0)),
                    "name": item.get("name", "") or ""
                })
            except Exception:
                continue

    # 3) Cached locations from disk (cache/<kind>/*)
    try:
        for kind in ("celestial", "asteroids", "comets"):
            base_dir = os.path.join(CACHE_ROOT, kind)
            if not os.path.isdir(base_dir):
                continue
            for entry in os.listdir(base_dir):
                dir_path = os.path.join(base_dir, entry)
                if not os.path.isdir(dir_path):
                    continue
                # Expect entry like: 'lat+48.2082_lon+16.3738_el+0170'
                try:
                    parts = entry.split("_")
                    if len(parts) != 3:
                        continue
                    lat_s, lon_s, el_s = parts
                    if not (lat_s.startswith("lat") and lon_s.startswith("lon") and el_s.startswith("el")):
                        continue
                    lat = float(lat_s[3:])
                    lon = float(lon_s[3:])
                    elev = int(el_s[2:])  # signed integer with leading zeros
                    lat_n, lon_n, elev_n = normalize_location(lat, lon, float(elev))
                    locs.append({
                        "latitude": lat_n,
                        "longitude": lon_n,
                        "elevation": float(elev_n),
                        "name": ""
                    })
                except Exception:
                    continue
    except Exception:
        pass

    # Deduplicate by normalized cache key
    seen = set()
    unique: List[Dict[str, Any]] = []
    for loc in locs:
        lat_n, lon_n, elev_n = normalize_location(loc["latitude"], loc["longitude"], loc["elevation"])
        key = location_key(lat_n, lon_n, elev_n)
        if key not in seen:
            seen.add(key)
            unique.append({
                "latitude": lat_n,
                "longitude": lon_n,
                "elevation": float(elev_n),
                "name": loc.get("name", "")
            })
    return unique


def hour_floor(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.replace(minute=0, second=0, microsecond=0)


def iter_hours(start_utc: datetime, horizon_hours: int) -> List[datetime]:
    base = hour_floor(start_utc)
    return [base + timedelta(hours=i) for i in range(horizon_hours)]


def iter_hours_prioritized(start_utc: datetime, horizon_hours: int) -> Tuple[List[datetime], List[datetime]]:
    """Split hours into high priority (current + next 6h) and low priority (rest).
    Returns (high_priority_hours, low_priority_hours).
    """
    base = hour_floor(start_utc)
    all_hours = [base + timedelta(hours=i) for i in range(horizon_hours)]
    
    # High priority: current hour + next 6 hours (7 total)
    high_priority = all_hours[:7] if len(all_hours) >= 7 else all_hours
    low_priority = all_hours[7:] if len(all_hours) > 7 else []
    
    return high_priority, low_priority


def get_adaptive_worker_count(base_workers: int) -> int:
    """Calculate adaptive worker count based on system load.
    Returns worker count between 1 and max_workers.
    
    The worker count is always capped by ASCII_SKY_PRECOMPUTE_WORKERS,
    which serves as an absolute maximum.
    """
    # Ensure we never exceed the configured maximum
    try:
        max_workers = int(os.environ.get("ASCII_SKY_PRECOMPUTE_WORKERS", "3"))
    except Exception:
        max_workers = base_workers
        
    try:
        # Get CPU usage (average over 1 second)
        cpu_percent = psutil.cpu_percent(interval=1.0)
        # Get memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Reduce workers if system is under high load
        if cpu_percent > 80 or memory_percent > 85:
            return max(1, min(base_workers // 2, max_workers))
        elif cpu_percent > 60 or memory_percent > 70:
            return min(base_workers, max_workers)
        else:
            # System has capacity, can use more workers but never exceed max_workers
            return min(int(base_workers * 1.5), max_workers)
    except Exception:
        # Fallback to base workers if psutil fails, but still respect max_workers
        return min(base_workers, max_workers)


def ensure_celestial(lat: float, lon: float, elevation: float, dt_utc: datetime) -> bool:
    """Ensure a celestial snapshot exists for this hour. Returns True if created."""
    path = build_cache_path("celestial", lat, lon, elevation, dt=dt_utc, bucket_hours=1)
    if os.path.exists(path):
        return False
    try:
        from api.computation import compute_celestial_snapshot
        snapshot = compute_celestial_snapshot(lat, lon, elevation, dt_utc)
        atomic_write_pickle(path, snapshot)
        print(f"[celestial] wrote {path}")
        return True
    except Exception:
        print(f"[celestial] error for {lat},{lon},{elevation} at {dt_utc.isoformat()}")
        traceback.print_exc()
        return False


def ensure_asteroids(lat: float, lon: float, elevation: float, dt_utc: datetime) -> bool:
    """Ensure an asteroid list cache exists for this hour. Returns True if created."""
    from cache_utils import time_bucket_utc
    
    # Check both SQLite and pickle cache
    if bright_asteroids.ASTEROID_USE_SQLITE:
        # Check SQLite cache first via fast existence query
        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        time_bucket = time_bucket_utc(dt_utc, bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS)
        if has_asteroid_positions(loc_key, time_bucket, bright_asteroids.ASTEROID_CACHE_TTL_SECONDS):
            return False  # Already cached in SQLite
    
    # Check pickle cache as fallback (unless disabled)
    disable_pickle = os.environ.get("ASCII_SKY_DISABLE_PICKLE", "0").strip() == "1"
    path = build_cache_path("asteroids", lat, lon, elevation, dt=dt_utc, bucket_hours=bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS)
    if (not disable_pickle) and os.path.exists(path):
        return False
    
    try:
        location = {"latitude": lat, "longitude": lon, "elevation": elevation}
        # Module will write to both SQLite and pickle cache
        from api.computation import LOADER
        asteroid_list = bright_asteroids.load_bright_asteroids(
            LOADER, ts, eph, location,
            max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE,
            use_cache=True, current_dt=dt_utc
        )
        
        if bright_asteroids.ASTEROID_USE_SQLITE and asteroid_list:
            print(f"[asteroids] wrote SQLite cache for {loc_key}/{time_bucket} ({len(asteroid_list)} objects)")
        else:
            print(f"[asteroids] wrote pickle cache {path}")
        return True
    except Exception as e:
        print(f"[asteroids] error for {lat},{lon},{elevation} at {dt_utc.isoformat()}: {e}")
        traceback.print_exc()
        return False


def ensure_comets(lat: float, lon: float, elevation: float, dt_utc: datetime) -> bool:
    """Ensure a comet list cache exists for this hour. Returns True if created."""
    from cache_utils import time_bucket_utc
    
    # Check SQLite cache first if enabled
    if comets.COMET_USE_SQLITE:
        try:
            lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
            loc_key = location_key(lat_norm, lon_norm, elev_norm)
            time_bucket = time_bucket_utc(dt_utc, comets.COMET_CACHE_BUCKET_HOURS)
            if has_comet_positions(loc_key, time_bucket, comets.COMET_CACHE_TTL_SECONDS):
                return False  # Cache exists
        except Exception as e:
            print(f"[comets] SQLite cache check failed: {e}")
    
    # Check pickle cache as fallback (unless disabled)
    disable_pickle = os.environ.get("ASCII_SKY_DISABLE_PICKLE", "0").strip() == "1"
    path = build_cache_path("comets", lat, lon, elevation, dt=dt_utc, bucket_hours=comets.COMET_CACHE_BUCKET_HOURS)
    if (not disable_pickle) and os.path.exists(path):
        return False
    
    try:
        location = {"latitude": lat, "longitude": lon, "elevation": elevation}
        comet_list = comets.load_comets(ts, eph, location, use_cache=True, current_dt=dt_utc)
        
        if comets.COMET_USE_SQLITE:
            print(f"[comets] wrote SQLite cache for {loc_key}/{time_bucket} ({len(comet_list)} objects)")
        else:
            print(f"[comets] wrote {path}")
        return True
    except Exception:
        print(f"[comets] error for {lat},{lon},{elevation} at {dt_utc.isoformat()}")
        traceback.print_exc()
        return False


def _process_location_batch(loc: Dict[str, Any], hours: List[datetime], kinds: List[str], batch_size: int = 6) -> Tuple[int, int]:
    """Process all hours and kinds for a single location with batch optimization.
    Returns (created_count, checked_count) for this location.
    """
    lat = float(loc["latitude"])
    lon = float(loc["longitude"])
    elevation = float(loc.get("elevation", 0.0))
    label = loc.get("name") or f"{lat:.4f},{lon:.4f},{elevation:.0f}m"
    
    created = 0
    checked = 0
    
    # Group hours into batches for more efficient processing
    hour_batches = [hours[i:i + batch_size] for i in range(0, len(hours), batch_size)]
    
    try:
        for batch_idx, hour_batch in enumerate(hour_batches):
            for kind in kinds:
                # Check which hours in this batch need processing
                hours_to_process = []
                for dt in hour_batch:
                    if kind == "celestial":
                        path = build_cache_path("celestial", lat, lon, elevation, dt=dt, bucket_hours=1)
                    elif kind == "asteroids":
                        path = build_cache_path("asteroids", lat, lon, elevation, dt=dt, bucket_hours=bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS)
                    elif kind == "comets":
                        path = build_cache_path("comets", lat, lon, elevation, dt=dt, bucket_hours=comets.COMET_CACHE_BUCKET_HOURS)
                    else:
                        continue
                        
                    checked += 1
                    if not os.path.exists(path):
                        hours_to_process.append(dt)
                
                # Process all missing hours for this kind in batch
                if hours_to_process:
                    try:
                        if kind == "celestial":
                            for dt in hours_to_process:
                                if ensure_celestial(lat, lon, elevation, dt):
                                    created += 1
                        elif kind == "asteroids":
                            # For asteroids/comets, we still process individually due to their caching logic
                            for dt in hours_to_process:
                                if ensure_asteroids(lat, lon, elevation, dt):
                                    created += 1
                        elif kind == "comets":
                            for dt in hours_to_process:
                                if ensure_comets(lat, lon, elevation, dt):
                                    created += 1
                    except Exception:
                        print(f"[{kind}] batch error for {label} (batch {batch_idx + 1})")
                        traceback.print_exc()
                        
                # Explicitly clean up memory after each kind
                gc.collect()
    except Exception as e:
        print(f"Error processing location {label}: {e}")
        traceback.print_exc()
    finally:
        # Clean up database connections
        from db_utils import close_db_connection
        close_db_connection()
    
    print(f"  - done {label} (created={created}, checked={checked})")
    return created, checked


def precompute_sweep_prioritized(kinds: List[str], horizon_hours: int, base_workers: int = 3, use_adaptive: bool = True) -> Tuple[int, int]:
    """Run prioritized sweep with adaptive workers and batch processing.
    Returns (created_count, checked_count).
    """
    locations = get_target_locations()
    if not locations:
        print("No locations configured; nothing to precompute.")
        return (0, 0)

    now = _now_utc()
    high_priority_hours, low_priority_hours = iter_hours_prioritized(now, horizon_hours)
    
    # Adaptive worker count based on system load
    if use_adaptive:
        workers = get_adaptive_worker_count(base_workers)
        print(f"Adaptive workers: {workers} (base: {base_workers})")
    else:
        workers = base_workers
    
    total_created = 0
    total_checked = 0

    print(f"Precompute sweep start: {len(locations)} locations, {len(high_priority_hours)}+{len(low_priority_hours)} hours, kinds={kinds}")

    try:
        # Process high priority hours first (current + next 6h)
        if high_priority_hours:
            print(f"Processing HIGH PRIORITY hours ({len(high_priority_hours)}h) with {workers} workers...")
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_location = {
                    executor.submit(_process_location_batch, loc, high_priority_hours, kinds, 3): loc
                    for loc in locations
                }
                
                for future in as_completed(future_to_location):
                    loc = future_to_location[future]
                    try:
                        created, checked = future.result()
                        total_created += created
                        total_checked += checked
                    except Exception:
                        label = loc.get("name") or f"{loc['latitude']:.4f},{loc['longitude']:.4f}"
                        print(f"[ERROR] Failed to process high priority for location {label}")
                        traceback.print_exc()
            
            # Force garbage collection after high priority batch
            gc.collect()

        # Process low priority hours with potentially fewer workers
        if low_priority_hours:
            low_workers = max(1, workers // 2)  # Use fewer workers for low priority
            print(f"Processing LOW PRIORITY hours ({len(low_priority_hours)}h) with {low_workers} workers...")
            with ThreadPoolExecutor(max_workers=low_workers) as executor:
                future_to_location = {
                    executor.submit(_process_location_batch, loc, low_priority_hours, kinds, 12): loc
                    for loc in locations
                }
                
                for future in as_completed(future_to_location):
                    loc = future_to_location[future]
                    try:
                        created, checked = future.result()
                        total_created += created
                        total_checked += checked
                    except Exception:
                        label = loc.get("name") or f"{loc['latitude']:.4f},{loc['longitude']:.4f}"
                        print(f"[ERROR] Failed to process low priority for location {label}")
                        traceback.print_exc()
            
            # Force garbage collection after low priority batch
            gc.collect()
    except Exception as e:
        print(f"Error in precompute sweep: {e}")
        traceback.print_exc()
    finally:
        # Clean up any remaining database connections
        from db_utils import close_db_connection
        close_db_connection()

    print(f"Precompute sweep complete: created={total_created}, checked={total_checked}")
    return total_created, total_checked


def precompute_sweep(kinds: List[str], horizon_hours: int, max_workers: int = 3) -> Tuple[int, int]:
    """Legacy wrapper for backward compatibility. Uses prioritized sweep."""
    return precompute_sweep_prioritized(kinds, horizon_hours, max_workers, use_adaptive=True)


def _parse_bucket_label(label: str) -> Optional[datetime]:
    """Parse 'YYYYMMDDTHH' into UTC-aware datetime or None."""
    try:
        dt = datetime.strptime(label, "%Y%m%dT%H")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def prune_old_snapshots(retention_days: int) -> Tuple[int, int]:
    """Delete cache files older than retention_days.
    Returns (deleted_files, scanned_files).
    """
    if retention_days is None or retention_days <= 0:
        return (0, 0)
    
    deleted = 0
    scanned = 0
    
    # Prune SQLite database positions
    try:
        db_deleted = cleanup_old_positions(retention_days)
        print(f"[prune] SQLite: deleted {db_deleted} old position entries")
        deleted += db_deleted
    except Exception as e:
        print(f"[prune] SQLite cleanup error: {e}")
    
    # Prune pickle cache files
    now = _now_utc()
    cutoff = now - timedelta(days=int(retention_days))
    try:
        for kind in ("celestial", "asteroids", "comets"):
            base_dir = os.path.join(CACHE_ROOT, kind)
            if not os.path.isdir(base_dir):
                continue
            for loc_entry in os.listdir(base_dir):
                loc_dir = os.path.join(base_dir, loc_entry)
                if not os.path.isdir(loc_dir):
                    continue
                for fn in os.listdir(loc_dir):
                    if not fn.endswith(".pkl"):
                        continue
                    scanned += 1
                    label = fn[:-4]
                    dt = _parse_bucket_label(label)
                    if dt is None:
                        continue
                    if dt < cutoff:
                        fpath = os.path.join(loc_dir, fn)
                        try:
                            os.remove(fpath)
                            deleted += 1
                        except Exception:
                            traceback.print_exc()
                # Remove empty location directories
                try:
                    if not os.listdir(loc_dir):
                        os.rmdir(loc_dir)
                except Exception:
                    pass
            # Remove empty kind directory
            try:
                if not os.listdir(base_dir):
                    os.rmdir(base_dir)
            except Exception:
                pass
    except Exception:
        traceback.print_exc()
    print(f"Retention prune: days={retention_days}, deleted={deleted}, scanned={scanned}")
    return deleted, scanned


def seconds_until_next_hour(now: Optional[datetime] = None) -> int:
    if now is None:
        now = _now_utc()
    next_hour = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    delta = (next_hour - now).total_seconds()
    # Keep a small buffer
    return max(1, int(delta))


def main() -> None:
    kinds_env = os.environ.get("ASCII_SKY_PRECOMPUTE_KINDS", "celestial,asteroids,comets").strip()
    kinds = [k.strip() for k in kinds_env.split(",") if k.strip()]
    try:
        horizon_hours = int(os.environ.get("ASCII_SKY_PRECOMPUTE_HOURS", "144"))
    except Exception:
        horizon_hours = 144
    try:
        max_workers = int(os.environ.get("ASCII_SKY_PRECOMPUTE_WORKERS", "3"))
        max_workers = max(1, min(max_workers, 8))  # Clamp between 1-8
    except Exception:
        max_workers = 3
    
    adaptive_workers = os.environ.get("ASCII_SKY_ADAPTIVE_WORKERS", "1").strip() == "1"
    
    # Optional retention
    try:
        retention_days_env = os.environ.get("ASCII_SKY_RETENTION_DAYS", "").strip()
        retention_days = int(retention_days_env) if retention_days_env else 0
    except Exception:
        retention_days = 0

    run_once = os.environ.get("ASCII_SKY_WORKER_RUN_ONCE", "").strip() == "1"

    print("AsciiSky precompute worker starting...")
    print(f"  kinds={kinds}")
    print(f"  horizon_hours={horizon_hours}")
    print(f"  max_workers={max_workers}")
    print(f"  adaptive_workers={adaptive_workers}")
    
    # Print database statistics if SQLite is enabled
    if bright_asteroids.ASTEROID_USE_SQLITE:
        try:
            db_stats = get_database_stats()
            print(
                "  SQLite database: "
                f"{db_stats.get('asteroids_count', 0)} asteroids, "
                f"{db_stats.get('comets_count', 0)} comets"
            )
            print(
                "                   "
                f"{db_stats.get('positions_count', 0)} asteroid positions, "
                f"{db_stats.get('comet_positions_count', 0)} comet positions"
            )
            if db_stats.get('db_size_mb'):
                print(f"  Database size: {db_stats['db_size_mb']:.1f} MB")
            if db_stats.get('db_connections'):
                print(f"  Database connections: {db_stats['db_connections']}")
        except Exception as e:
            print(f"  SQLite database status: error ({e})")
    if retention_days and retention_days > 0:
        print(f"  retention_days={retention_days}")
    else:
        print("  retention_days=disabled")

    # Ensure orbital element sources are fresh before computing
    try:
        # Forces weekly refresh check and rebuilds comet dataframe cache
        comets.load_comet_dataframe(use_cache=False)
    except Exception:
        traceback.print_exc()
    try:
        if bright_asteroids.should_update_mpcorb_file():
            updated = bright_asteroids.download_mpcorb_file()
            if not updated:
                print("Warning: MPCORB download reported failure; continuing with existing file")
        # Drop stale asteroid dataframe cache so it will be rebuilt on demand
        if os.path.exists(bright_asteroids.ASTEROID_DF_CACHE_FILE):
            try:
                os.remove(bright_asteroids.ASTEROID_DF_CACHE_FILE)
                print(f"Removed stale asteroid dataframe cache {bright_asteroids.ASTEROID_DF_CACHE_FILE}")
            except Exception as cache_err:
                print(f"Warning: could not remove asteroid dataframe cache: {cache_err}")
    except Exception:
        traceback.print_exc()

    # Initial sweep immediately
    try:
        precompute_sweep_prioritized(kinds, horizon_hours, max_workers, adaptive_workers)
        # Force garbage collection after sweep
        gc.collect()
    except Exception:
        traceback.print_exc()

    # Initial prune
    try:
        if retention_days and retention_days > 0:
            prune_old_snapshots(retention_days)
            # Force garbage collection after prune
            gc.collect()
    except Exception:
        traceback.print_exc()

    if run_once:
        print("Run once mode set; exiting.")
        # Final cleanup
        from db_utils import close_db_connection
        close_db_connection()
        return

    # Then loop hourly
    while True:
        try:
            # Close database connections before sleeping
            from db_utils import close_db_connection
            close_db_connection()
            
            sleep_s = seconds_until_next_hour()
            print(f"Sleeping {sleep_s}s until next hour...")
            time.sleep(sleep_s)
            
            # Run sweep
            precompute_sweep_prioritized(kinds, horizon_hours, max_workers, adaptive_workers)
            gc.collect()
            
            # Run prune if enabled
            if retention_days and retention_days > 0:
                prune_old_snapshots(retention_days)
                gc.collect()
                
        except KeyboardInterrupt:
            print("Worker interrupted; exiting.")
            # Final cleanup
            from db_utils import close_db_connection
            close_db_connection()
            break
        except Exception:
            traceback.print_exc()
            # On errors, wait a minute before retry to avoid tight loop
            time.sleep(60)


if __name__ == "__main__":
    main()
