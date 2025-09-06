# Server-Side Session and Location Caching Plan

This plan defines how server-side sessions and per-location caches for comets and (bright) asteroids are implemented. The goal is to reuse identical results for the same locations within a time window and save computation time. The system uses a hybrid approach with SQLite as the primary storage and pickle files as fallback.

## Goals
- Separate, reusable datasets for each observer location and time window.
- Minimal changes to existing endpoints; frontend continues to provide location or uses session fallback.
- TTL-compatible (~6h) and stable against concurrency.

## Scope
- Comets (`comets.load_comets()`): cache per location and time bucket in SQLite and pickle (final list including Alt/Az, event times).
- Bright asteroids (`bright_asteroids.load_bright_asteroids()`): cache per location and time bucket in SQLite and pickle (final list).
- Planets (in `main.py`): cache in SQLite `celestial_snapshots` table with fallback to pickle files.
- Global DataFrame caches (MPC/MPCORB) remain unchanged globally (~6h) and location-independent, stored in both SQLite and pickle format.

## Cache Key Strategy
- Location normalization:
  - Latitude/Longitude: round to 4 decimal places (`~11 m`).
  - Elevation: round to 10 m.
  - Example string: `lat{lat:.4f}_lon{lon:.4f}_el{int(round(elev/10)*10)}`.
- Time bucket (UTC): 6-hour window matching the TTL.
  - Buckets: 00, 06, 12, 18 UTC.
  - Format: `YYYYMMDD_HH` (e.g., `20250830_18`).
- Result: same location in the same 6h bucket → same cache.

## Storage Layout

### SQLite Database (Primary)
- Database file: `cache/asciisky.db`
- Tables:
  - `asteroid_positions`: Keyed by (asteroid_id, location_key, time_bucket)
  - `comet_positions`: Keyed by (comet_id, location_key, time_bucket)
  - `celestial_snapshots`: Keyed by (location_key, time_bucket)

### Pickle Files (Fallback)
- Comets: `cache/bright_comets/<loc_key>/<bucket>.pkl`
- Asteroids: `cache/bright_asteroids/<loc_key>/<bucket>.pkl`
- Examples:
  - `cache/bright_comets/lat48.2082_lon16.3738_el170/20250830_18.pkl`
  - `cache/bright_asteroids/lat48.2082_lon16.3738_el170/20250830_18.pkl`

## TTL and Invalidation
- TTL: ~6h (consistent with existing global DataFrame caches).
- Reading: Cache considered "fresh" if file `mtime` < 6h old.
- Cleanup: periodically delete old bucket files (e.g., at startup and opportunistically every N requests).

## Concurrency and Atomic Writes

### SQLite (Primary)
- Database transactions with automatic rollback on error
- Thread-local connections with proper configuration
- PRAGMA settings for optimal concurrency

### Pickle Files (Fallback)
- Writing: always atomic (Tempfile + `os.replace`) to avoid race conditions
- Optional: File-based locks for very high parallelism

## API Integration (Backend)

### Database Integration
- `db_utils.py`:
  - Provides database connection and transaction management
  - Functions for storing and retrieving asteroid/comet data
  - Functions for caching computed positions

### Cache Integration
- `comets.py`:
  - Try SQLite first via `db_utils.get_comet_positions()`
  - Fall back to pickle cache if not found in database
  - Store results in both SQLite and pickle for backward compatibility
- `bright_asteroids.py`:
  - Try SQLite first via `db_utils.get_asteroid_positions()`
  - Fall back to pickle cache if not found in database
  - Store results in both SQLite and pickle for backward compatibility

### Session Management
- `main.py` (Sessions, optional but recommended):
  - Add SessionMiddleware (cookie-based)
  - Endpoints:
    - `GET /api/session/location` → returns stored session location
    - `POST /api/session/location` → sets session location
  - Existing endpoints (`/api/comets`, `/api/bright_asteroids`, `/api/celestial`):
    - Use location from query; if missing → session location as fallback; if no session → `settings.get_location()`

IMPORTANT (Frontend rule): Always maintain API endpoints centrally in `static/js/constants.js`.

## Frontend Integration (minimal)
- `static/js/constants.js`: add new session endpoints.
- `static/js/locationDialog.js`: `POST /api/session/location` on change.
- `static/js/skyManager.js` (or initializer): load `GET /api/session/location` at startup and set as default.
- Requests may continue to send explicit `lat/lon/elevation` parameters (override session fallback).

## Utility Module: `cache_utils.py`
Shared helpers for comets and asteroids.

```python
# cache_utils.py (Sketch)
from __future__ import annotations
import os, json, tempfile, time, hashlib
from datetime import datetime, timezone
from typing import Any, Optional

CACHE_ROOT = "cache"

def normalize_location(lat: float, lon: float, elev: float) -> str:
    lat_r = round(float(lat), 4)
    lon_r = round(float(lon), 4)
    el_r  = int(round(float(elev) / 10.0) * 10)
    return f"lat{lat_r:.4f}_lon{lon_r:.4f}_el{el_r}"

def time_bucket(now: Optional[datetime] = None, hours: int = 6) -> str:
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    base = now_utc.replace(minute=0, second=0, microsecond=0)
    h = (base.hour // hours) * hours
    return base.replace(hour=h).strftime("%Y%m%d_%H")

def cache_path(kind: str, loc_key: str, bucket: str) -> str:
    # kind ∈ {"bright_comets", "bright_asteroids"}
    dir_path = os.path.join(CACHE_ROOT, kind, loc_key)
    os.makedirs(dir_path, exist_ok=True)
    return os.path.join(dir_path, f"{bucket}.pkl")

def is_fresh(path: str, ttl_seconds: int) -> bool:
    try:
        age = time.time() - os.path.getmtime(path)
        return age >= 0 and age < ttl_seconds
    except FileNotFoundError:
        return False

def read_pickle_if_fresh(path: str, ttl_seconds: int) -> Optional[Any]:
    if is_fresh(path, ttl_seconds):
        import pickle
        with open(path, "rb") as f:
            return pickle.load(f)
    return None

def atomic_write_pickle(path: str, obj: Any) -> None:
    import pickle
    dir_name = os.path.dirname(path)
    os.makedirs(dir_name, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dir_name, delete=False) as tmp:
        pickle.dump(obj, tmp)
        tmp_path = tmp.name
    os.replace(tmp_path, path)  # atomic on same filesystem

def cleanup_cache(kind: str, max_age_hours: int = 24) -> int:
    """Removes old files; returns number of deleted files."""
    import glob
    cutoff = time.time() - max_age_hours * 3600
    root = os.path.join(CACHE_ROOT, kind)
    removed = 0
    for path in glob.glob(os.path.join(root, "**", "*.pkl"), recursive=True):
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except FileNotFoundError:
            pass
    return removed
```

## Implementation Steps
1. Add `db_utils.py` for SQLite database operations:
   - Create schema with tables for asteroids, comets, and position caches
   - Implement thread-safe connection management
   - Provide transaction support with automatic rollback

2. Add `cache_utils.py` (shared key/I/O functions for pickle fallback):
   - Implement location normalization and time bucketing
   - Provide atomic file operations
   - Support both SQLite and pickle cache paths

3. Update `comets.py` and `bright_asteroids.py`:
   - Try SQLite first via `db_utils` functions
   - Fall back to pickle cache via `cache_utils` functions
   - Store results in both SQLite and pickle for backward compatibility

4. Update `main.py` (optional Session):
   - Add `SessionMiddleware`, Secret Key from Env or constant
   - Implement `GET/POST /api/session/location`
   - In `/api/comets`, `/api/bright_asteroids`, `/api/celestial` location fallback to session

5. Frontend:
   - `static/js/constants.js`: add new session endpoints
   - `static/js/locationDialog.js`: `POST /api/session/location` on change
   - Initialization: `GET /api/session/location` as default (if no query location)

6. Update documentation: `README.md`, `doc/plan.md`, `doc/comets.md`, `doc/asteroids.md`, `doc/sqlite.md`, `doc/cache.md`

## Tests & Benchmarking
- Same `lat/lon/elev` + same bucket: second call must be cache hit (measuring end-to-end time << first call).
- Different location: cache miss, but global DataFrame cache used (faster than cold start).
- After TTL > 6h: cache miss (recalculation).
- Parallelism: simultaneous requests → no corrupt files, exactly one final cache file.

## Migration & Backward Compatibility
- On first access: 
  - If new path is missing, optionally read the previous global cache (`cache/bright_comet_cache.pkl` / `cache/bright_asteroid_cache.pkl`) once, then write under new schema.
  - Afterward, only use per-location/bucket.

## Configuration (Defaults)
- Location rounding: lat/lon 4 decimal places, elevation to 10 m
- Bucket: 6h (UTC), buckets at 00/06/12/18
- TTL: 6h
- Optional In-Memory LRU: 60-120s per location/bucket to save disk I/O
- SQLite configuration:
  - `ASTEROID_USE_SQLITE`: 1 (enabled)
  - `COMET_USE_SQLITE`: 1 (enabled)
  - `CELESTIAL_USE_SQLITE`: 1 (enabled)
  - Database PRAGMA settings:
    - `synchronous=NORMAL`: Balance safety/performance
    - `cache_size=10000`: 10MB cache
    - `temp_store=MEMORY`: Use RAM for temp tables

## Security & Privacy
- Session stores only location coordinates and optional name (no PII beyond that).
- Cookie-signed (no sensitive content in plain text required; server manages session store).

## Notes
- Alt/Az and event times depend on time; with 6h buckets, values can drift over the course of the bucket. This is consistent with current TTL behavior.
- Extension idea (later): RA/Dec-oriented caching and Alt/Az "reprojection" at response time, if finer accuracy is needed (more complex, but more accurate).
