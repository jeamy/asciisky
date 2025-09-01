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
- ASCII_SKY_RETENTION_DAYS: if set to a positive integer N, prune cache files older than N days
- ASCII_SKY_WORKER_RUN_ONCE: if set to "1", run a single sweep and exit
- TZ should be set in Docker to ensure local logging timestamps
"""
from __future__ import annotations

import os
import json
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple, Optional

# Local imports
import settings
import bright_asteroids
import comets
from cache_utils import (
    build_cache_path,
    normalize_location,
    location_key,
    atomic_write_pickle,
    CACHE_ROOT,
)

# Import compute function and Skyfield loading context from main
# This avoids duplicating celestial computation logic.
import main as webapp


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


def ensure_celestial(lat: float, lon: float, elevation: float, dt_utc: datetime) -> bool:
    """Ensure a celestial snapshot exists for this hour. Returns True if created."""
    path = build_cache_path("celestial", lat, lon, elevation, dt=dt_utc, bucket_hours=1)
    if os.path.exists(path):
        return False
    try:
        snapshot = webapp.compute_celestial_snapshot(lat, lon, elevation, dt_utc)
        atomic_write_pickle(path, snapshot)
        print(f"[celestial] wrote {path}")
        return True
    except Exception:
        print(f"[celestial] error for {lat},{lon},{elevation} at {dt_utc.isoformat()}")
        traceback.print_exc()
        return False


def ensure_asteroids(lat: float, lon: float, elevation: float, dt_utc: datetime) -> bool:
    """Ensure an asteroid list cache exists for this hour. Returns True if created."""
    path = build_cache_path("asteroids", lat, lon, elevation, dt=dt_utc, bucket_hours=bright_asteroids.ASTEROID_CACHE_BUCKET_HOURS)
    if os.path.exists(path):
        return False
    try:
        location = {"latitude": lat, "longitude": lon, "elevation": elevation}
        # Module will write its per-hour cache via atomic_write_pickle()
        _ = bright_asteroids.load_bright_asteroids(
            webapp.LOADER, webapp.ts, webapp.eph, location,
            max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE,
            use_cache=True, current_dt=dt_utc
        )
        print(f"[asteroids] wrote {path}")
        return True
    except Exception:
        print(f"[asteroids] error for {lat},{lon},{elevation} at {dt_utc.isoformat()}")
        traceback.print_exc()
        return False


def ensure_comets(lat: float, lon: float, elevation: float, dt_utc: datetime) -> bool:
    """Ensure a comet list cache exists for this hour. Returns True if created."""
    path = build_cache_path("comets", lat, lon, elevation, dt=dt_utc, bucket_hours=comets.COMET_CACHE_BUCKET_HOURS)
    if os.path.exists(path):
        return False
    try:
        location = {"latitude": lat, "longitude": lon, "elevation": elevation}
        _ = comets.load_comets(webapp.ts, webapp.eph, location, use_cache=True, current_dt=dt_utc)
        print(f"[comets] wrote {path}")
        return True
    except Exception:
        print(f"[comets] error for {lat},{lon},{elevation} at {dt_utc.isoformat()}")
        traceback.print_exc()
        return False


def precompute_sweep(kinds: List[str], horizon_hours: int) -> Tuple[int, int]:
    """Run one sweep over all locations and hours.
    Returns (created_count, checked_count).
    """
    locations = get_target_locations()
    if not locations:
        print("No locations configured; nothing to precompute.")
        return (0, 0)

    now = _now_utc()
    hours = iter_hours(now, horizon_hours)
    created = 0
    checked = 0

    print(f"Precompute sweep start: {len(locations)} locations, {len(hours)} hours, kinds={kinds}")

    for loc in locations:
        lat = float(loc["latitude"])
        lon = float(loc["longitude"])
        elevation = float(loc.get("elevation", 0.0))
        label = loc.get("name") or f"{lat:.4f},{lon:.4f},{elevation:.0f}m"
        for dt in hours:
            for kind in kinds:
                try:
                    if kind == "celestial":
                        checked += 1
                        if ensure_celestial(lat, lon, elevation, dt):
                            created += 1
                    elif kind == "asteroids":
                        checked += 1
                        if ensure_asteroids(lat, lon, elevation, dt):
                            created += 1
                    elif kind == "comets":
                        checked += 1
                        if ensure_comets(lat, lon, elevation, dt):
                            created += 1
                except Exception:
                    traceback.print_exc()
        print(f"  - done {label}")

    print(f"Precompute sweep complete: created={created}, checked={checked}")
    return created, checked


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
    now = _now_utc()
    cutoff = now - timedelta(days=int(retention_days))
    deleted = 0
    scanned = 0
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
    if retention_days and retention_days > 0:
        print(f"  retention_days={retention_days}")
    else:
        print("  retention_days=disabled")

    # Initial sweep immediately
    try:
        precompute_sweep(kinds, horizon_hours)
    except Exception:
        traceback.print_exc()

    # Initial prune
    try:
        if retention_days and retention_days > 0:
            prune_old_snapshots(retention_days)
    except Exception:
        traceback.print_exc()

    if run_once:
        print("Run once mode set; exiting.")
        return

    # Then loop hourly
    while True:
        try:
            sleep_s = seconds_until_next_hour()
            print(f"Sleeping {sleep_s}s until next hour...")
            time.sleep(sleep_s)
            precompute_sweep(kinds, horizon_hours)
            if retention_days and retention_days > 0:
                prune_old_snapshots(retention_days)
        except KeyboardInterrupt:
            print("Worker interrupted; exiting.")
            break
        except Exception:
            traceback.print_exc()
            # On errors, wait a minute before retry to avoid tight loop
            time.sleep(60)


if __name__ == "__main__":
    main()
