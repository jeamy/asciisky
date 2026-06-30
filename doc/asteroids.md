# Bright Asteroids: Position and Magnitude Pipeline

This document explains how ASCII Sky computes positions and brightness for bright minor planets (asteroids) and how caching and filtering work.

## Overview

- Source data: MPCORB (Minor Planet Center) orbital elements.
- Orbits: Constructed from MPCORB elements using Skyfield's `mpc.mpcorb_orbit()`.
- Geometry: Positions observed from a topocentric Earth observer (`Earth + Topos`).
- Distances and phase angle: Derived from Skyfield vectors.
- Apparent magnitude: Computed using the IAU H–G photometric model.
- Filtering: User-configurable magnitude filter applied in the API layer; workers compute/store unfiltered positions up to mag 20.0.
- Rise/Set/Transit: Computed with Skyfield almanac for the composite `sun + orbit` target and the observer `Topos`.

Backend entrypoint: `bright_asteroids.load_bright_asteroids()`.
API endpoint: `/api/bright_asteroids` (see `api/routes/asteroids.py`).
Worker: `workers/unified_worker.py` for on-demand work;
`workers/precompute_worker.py` is the dedicated precompute consumer.
Cache: PostgreSQL database (`cached_positions` table).

## Data Loading

1. If necessary, download `MPCORB.DAT.gz` (see constants in `bright_asteroids.py`).
2. Parse into a Pandas DataFrame via `skyfield.data.mpc.load_mpcorb_dataframe()`.
3. Basic cleanup:
   - Convert numeric columns (e.g., `magnitude_H`, `magnitude_G`, `semimajor_axis_au`, ...).
   - Fill missing slope parameter `G` with 0.15 (common default).
4. Prefilter by absolute magnitude H:
   - Keep rows with `magnitude_H < MAX_ABSOLUTE_MAGNITUDE` (default 12.0).

## Geometry and Distances

For each candidate asteroid row:

- Build a Keplerian orbit: `orbit = mpc.mpcorb_orbit(row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)`.
- Define time: `dt_utc` resolved from optional `time` query param (ISO 8601; supports trailing `Z` or TZ offset). Defaults to current UTC. `t = ts.from_datetime(dt_utc)`.
- Define observer:
  - `topos = Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=elevation)`
  - `observer = eph['earth'] + topos`
- Observe the asteroid as a barycentric target against the Sun:
  - `astrometric = observer.at(t).observe(sun + orbit)`
- Distances:
  - Observer distance Δ (AU): `delta = astrometric.distance().au`
  - Heliocentric distance r (AU): `r = sun.at(t).observe(sun + orbit).distance().au`
- Phase angle α (Sun–object–observer): `alpha_deg = astrometric.phase_angle(sun).degrees`

Important: Using `sun + orbit` avoids heliocentric-center errors and ensures almanac functions work.

## Apparent Magnitude (IAU H–G)

We compute apparent V magnitude using the IAU H–G model:

```
V = H + 5 log10(r Δ) − 2.5 log10((1 − G) Φ1 + G Φ2)
Φ1 = exp(−3.33 * tan(α/2)^0.63)
Φ2 = exp(−1.87 * tan(α/2)^1.22)
```

Implementation: `asteroid_apparent_magnitude(H, G, r, delta, phase_angle_deg)` in `bright_asteroids.py`.

- H: absolute magnitude from MPCORB (`magnitude_H`).
- G: slope parameter from MPCORB (`magnitude_G`, default 0.15).
- r: heliocentric distance (AU).
- Δ: observer (topocentric) distance (AU).
- α: phase angle in degrees.

## Selection by Brightness

Two-stage filtering:

1. H prefilter:
   - `MAX_ABSOLUTE_MAGNITUDE` (default 12.0) limits the dataset before heavy computations.
2. Apparent V filter:
   - After computing `apparent_magnitude`, keep rows with `V <= MAX_APPARENT_MAGNITUDE` (default 10.0).

Results are sorted by apparent magnitude and returned.

## Rise, Set, and Transit Times

For the asteroids that pass filtering:

- Window: 48h starting at UTC midnight of the simulated day.
- Rise/Set: `almanac.risings_and_settings(eph, sun + orbit, topos)` then `almanac.find_discrete(...)`.
- Transit: `almanac.meridian_transits(eph, sun + orbit, topos)` then `almanac.find_discrete(...)`.
- Transit selection: choose the upper transit (highest altitude) that occurs on the simulated local day to avoid ~12h offsets.
- Time formatting: backend returns plain local "HH:MM" strings (no localized suffix). The frontend appends the localized hour label via `buildTimeLabel()` (German: "Uhr", English: empty), ensuring it is added at most once.

## Output Shape

Each asteroid entry returned by `load_bright_asteroids()` includes:

- `name`: MPC designation (e.g., "(4) Vesta").
- `number`: MPC identifier as string.
- `magnitude`: apparent V (rounded to 0.1 mag).
- `ra`, `dec`: right ascension (deg) and declination (deg).
- `altitude`, `azimuth`: topocentric coordinates (deg).
- `distance`: observer distance Δ (AU, rounded).
- `rise_time`, `set_time`, `transit_time`: strings (or null if unavailable).
- `type`: "asteroid".
- `symbol`: "•".

Frontend display: the UI simplifies display names by stripping numeric designations (e.g., "(4) Vesta" → "Vesta"). Names are deduplicated using a normalized key to prevent duplicates in multi-object dialogs and click selection. Time labels are built with `buildTimeLabel()` to avoid duplicate suffixes.

## Caching

- DataFrame cache (filesystem)
  - File: `asteroid_dataframe.pkl` under `DATA_DIR`.
  - Written by `db_utils.store_asteroid_dataframe()` and read via
    `db_utils.get_asteroid_dataframe()` / `bright_asteroids.load_asteroid_dataframe()`.
  - Staleness window: ~49 hours (see `ASTEROID_DF_CACHE_TTL_SECONDS`).
- Position cache (PostgreSQL, table `cached_positions`)
  - Key: `(object_type='asteroid', location_key, time_bucket)`.
  - Stores computed positions as pickled, unfiltered lists (all objects up to
    about mag 20.0).
  - TTL: Unlimited (positions for a specific hour are immutable).

Filtering is not part of the caches. The API route applies the user magnitude
filter from `user_settings.json` (see `/api/filters`). Workers always compute
using `max_magnitude` up to about 20.0 and store unfiltered results. This makes
the caches reusable across different user filter settings.

## Endpoint

- `GET /api/bright_asteroids?lat=<deg>&lon=<deg>&elevation=<m>&time=<ISO8601>` (optional `time`)
  - API applies the current user magnitude filter from `user_settings.json` (defaults can be set via environment variables; see README)
  - Responds with a JSON object containing `time`, `location`, and `bodies`.
  - `time` is an optional ISO 8601 UTC timestamp (e.g., `2025-01-15T21:30:00Z`). When provided, all calculations and event windows use the simulated timestamp and day.

Example:

```
GET /api/bright_asteroids?lat=48.2082&lon=16.3738&elevation=171&time=2025-01-15T21:30:00Z
```

## Notes and Tips

- If MPC data is large, first load may take time; the frontend shows a loading indicator.
- Ensure you always build the almanac functions with `sun + orbit` and the `Topos` observer to avoid center errors.
- You can adjust brightness thresholds in `bright_asteroids.py`:
  - `MAX_ABSOLUTE_MAGNITUDE` (H) and `MAX_APPARENT_MAGNITUDE` (V).
- Default `G` fallback of 0.15 is a common choice when the slope parameter is missing.

## Related architecture docs

- [API Request Flow](ARCHITECTURE_FLOW_API.md)
- [Cache Strategy](ARCHITECTURE_CACHE.md)
- [Database Schema](ARCHITECTURE_DATABASE.md)

Last reviewed against the code: 2026-06-30.
