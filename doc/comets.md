# Comets: Position and Magnitude Pipeline

This document explains how ASCII Sky computes positions and brightness for comets using real MPC data, and how caching and filtering are handled.

## Overview

- Source data: MPC comet orbital elements (downloaded once and cached locally).
- Orbits: Constructed per row with Skyfield `mpc.comet_orbit()`.
- Geometry: Positions are computed topocentrically from an Earth observer with the composite target `sun + orbit`.
  - Center handling: we build `orbit = mpc.comet_orbit(row, ts, ...)` and then:
    - If `orbit.center != 0` (i.e., Sun-centered), we set `target = sun + orbit` to shift to the Solar System Barycenter.
    - Else (`center == 0`), we use `target = orbit` (already barycentric).
    - All observations and almanac calls use `target`.
- Apparent magnitude: Estimated using the M1/k1 photometric model:
  - V = M1 + 5 log10(Δ) + 2.5·k1·log10(r) (with k1 interpreted as exponent n)
- Filtering: User-configurable magnitude filter is applied in the API layer; workers compute and store unfiltered positions up to magnitude 20.0.
  - Prefilter for worker workload is still applied (e.g., require M1 and sort by intrinsic brightness), but final selection by apparent magnitude is performed in the API route based on user settings.
- Rise/Set/Transit: Computed with Skyfield almanac over a two-day window, selecting the best local-day transit.
  - Functions `risings_and_settings(eph, target, topos)` and `meridian_transits(eph, target, topos)` are used with the `target` defined above.
- Caching: a filesystem cache is used for the raw DataFrame (elements), and PostgreSQL is used for computed positions. Final lists are filtered at API time per request.
- API: `GET /api/comets` with optional `max_comets` parameter.

Backend entrypoint: `comets.load_comets()`.
API endpoint: `/api/comets` (see `api/routes/comets.py`).
Worker: `workers/comet_worker.py` (RabbitMQ-based async computation).
Cache:
- Filesystem DataFrame cache: `comet_dataframe.pkl` under `DATA_DIR`.
- PostgreSQL position cache: `cached_positions` table.

## Data Loading and Normalization

- The loader downloads MPC comet elements when needed and stores the standardized DataFrame on the filesystem (`comet_dataframe.pkl`) as a pickled blob.
- Parsing: `skyfield.data.mpc.load_comets_dataframe()` → Pandas DataFrame.
- Standardization (`_standardize_comet_df()`):
  - Keep the latest row per `designation` (by `reference`), preferring rows with valid `e` and `q`.
  - Normalize/alias element columns:
    - `i` from `inclination_degrees` → `i`/`incl`
    - `om`/`node` from `longitude_of_ascending_node_degrees`
    - `w`/`peri` from `argument_of_perihelion_degrees`
    - Photometry: `M1` from `magnitude_g`, `k1` from `magnitude_k` (if present)
  - Coerce numeric columns to floats.
  - Drop rows missing essentials `e` and `q`.
  - Require at least one valid time reference among `epoch_tt`, `Tp`, or a complete Y/M/D for epoch or perihelion.
  - Index by `designation`.

Cache: standardized DataFrame is stored on the filesystem with a TTL of 31 days.

## Geometry and Distances

For each candidate comet row:

- Time: `dt_utc` resolved from optional `time` query param (ISO 8601; supports trailing `Z` or TZ offset). Defaults to current UTC. `t = ts.from_datetime(dt_utc)`
- Observer: `topos = Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=elevation)`
  - `observer = eph['earth'] + topos`
- Target: composite `sun + orbit` (avoids center errors and matches almanac routines)
  - `astrometric = observer.at(t).observe(sun + orbit)`
- Distances:
  - Observer distance Δ (AU): `delta = astrometric.distance().au`
  - Heliocentric distance r (AU): `r = sun.at(t).observe(sun + orbit).distance().au`

## Apparent Magnitude (M1/k1)

We estimate the total apparent magnitude V using the model:

- V = M1 + 5 log10(Δ) + 2.5·k1·log10(r)

Interpretation:

- We treat `k1` as the brightness exponent `n` and multiply by 2.5 in magnitude space.

Where:

- M1, k1: comet photometric parameters from MPC (k1 interpreted as exponent n)
- r: heliocentric distance in AU
- Δ: observer (topocentric) distance in AU

Implementation: see `comets.py` in the computation block before event times.

## Selection by Brightness

Two-stage filtering is applied to reduce heavy computations while keeping caches reusable:

1. Prefilter by photometric parameters (in `load_comets`):
   - Require `M1` to be present and `M1 <= MAX_ABSOLUTE_MAGNITUDE` (see `comets.MAX_ABSOLUTE_MAGNITUDE`, default 18.0).
   - Process intrinsically brighter comets first (DataFrame is sorted by `M1`).
2. Apparent magnitude cache limit (in `_compute_comets_vectorized`):
   - After computing apparent magnitudes vectorized for all candidates, keep comets with `V <= 20.0`.
   - Sort by apparent brightness and take up to `max_comets` entries.

Processing stops after collecting up to `max_comets` items.
- Default in `comets.load_comets()`: `MAX_COMETS_DEFAULT = 1000`.
- Default for the API query param in `api/routes/comets.py`: 1000.

Note: User magnitude filters are applied **only** in the API route (`/api/comets`) using
`settings.get_magnitude_filters()` and do not affect the underlying caches.

## Rise, Set, and Transit Times

For each comet that passes filtering:

- Window: 48h starting at UTC midnight of the simulated day.
- Rise/Set: `almanac.risings_and_settings(eph, sun + orbit, topos)` and `almanac.find_discrete(...)`
- Transit: `almanac.meridian_transits(eph, sun + orbit, topos)` and `almanac.find_discrete(...)`
  - Choose the upper transit (highest altitude) that occurs on the current local day; if none, pick the best candidate.
- Time formatting: returned as local `HH:MM` strings (backend formats; frontend appends localized suffixes as needed).

## Output Shape

Each comet entry returned by `load_comets()` includes:

- `name`: comet name or designation
- `symbol`: "☄️"
- `type`: "comet"
- `ra`, `dec`: right ascension (deg) and declination (deg)
- `altitude`, `azimuth`: topocentric coordinates (deg)
- `distance`: observer distance Δ (AU, rounded)
- `magnitude`: apparent V (rounded to 0.1 mag)
- `rise_time`, `set_time`, `transit_time`: strings or null

## Caching

- Filesystem DataFrame cache
  - File: `comet_dataframe.pkl` under `DATA_DIR`.
  - Written by `db_utils.store_comet_dataframe()` and read via
    `db_utils.get_comet_dataframe()` / `comets.load_comet_dataframe()`.
  - TTL: 31 days (`COMET_DF_CACHE_TTL_SECONDS`).
- PostgreSQL position cache (table `cached_positions`)
  - Key: `(object_type='comet', location_key, time_bucket)`.
  - Stores computed positions as pickled, unfiltered lists (all objects up to
    about mag 20.0).
  - TTL: Unlimited (positions for a specific hour are immutable).
  
Filtering is not part of the caches. The API route applies the user magnitude
filter from `user_settings.json` (see `/api/filters`). Workers always compute
using a magnitude limit up to about 20.0 and store unfiltered results.

## Endpoint

- `GET /api/comets?lat=<deg>&lon=<deg>&elevation=<m>&max_comets=<N>&time=<ISO8601>` (optional `time`)
  - Returns a JSON object with `time`, `location`, and `bodies`.
  - The API applies the current user magnitude filter from `user_settings.json` (defaults can be set via environment variables; see README).
  - `max_comets` limits how many candidates are processed/returned (default 1000 at the API layer).
  - `time` is an optional ISO 8601 UTC timestamp (e.g., `2025-01-15T21:30:00Z` or `2025-01-15T21:30:00+00:00`). When provided, all calculations and event windows use the simulated timestamp and day.

Example:

```
GET /api/comets?lat=48.2082&lon=16.3738&elevation=171&time=2025-01-15T21:30:00Z
```

## Frontend Integration

- Endpoints are centralized in `static/js/constants.js`.
- Comets use the symbol "☄️" and type "comet". Label overlays for bright comets are controlled via:
  - `CONFIG.LABELS.ENABLE_BRIGHT_COMET_LABELS`
  - `CONFIG.LABELS.BRIGHT_COMET_MAG_THRESHOLD`
- Label filtering only affects display overlays, not backend data loading.

## Related architecture docs

- [API Request Flow](ARCHITECTURE_FLOW_API.md)
- [Cache Strategy](ARCHITECTURE_CACHE.md)
- [Database Schema](ARCHITECTURE_DATABASE.md)
