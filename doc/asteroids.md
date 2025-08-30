# Bright Asteroids: Position and Magnitude Pipeline

This document explains how ASCII Sky computes positions and brightness for bright minor planets (asteroids) and how the magnitude-based selection works.

## Overview

- Source data: MPCORB (Minor Planet Center) orbital elements.
- Orbits: Constructed from MPCORB elements using Skyfield's `mpc.mpcorb_orbit()`.
- Geometry: Positions observed from a topocentric Earth observer (`Earth + Topos`).
- Distances and phase angle: Derived from Skyfield vectors.
- Apparent magnitude: Computed using the IAU H–G photometric model.
- Filtering: Two-stage filter by absolute magnitude (H) and apparent magnitude (V).
- Rise/Set/Transit: Computed with Skyfield almanac for the composite `sun + orbit` target and the observer `Topos`.

Backend entrypoint: `bright_asteroids.load_bright_asteroids()`.
API endpoint: `/api/bright_asteroids` (see `main.py`).

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
- Define time: `t = ts.now()` (UTC).
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
   - After computing `apparent_magnitude`, keep rows with `V <= MAX_APPARENT_MAGNITUDE` (default 12.0).

Results are sorted by apparent magnitude and returned.

## Rise, Set, and Transit Times

For the asteroids that pass filtering:

- Time window: start at local day 00:00 UTC for two days.
- Rise/Set: `almanac.risings_and_settings(eph, sun + orbit, topos)` then `almanac.find_discrete(...)`.
- Transit: `almanac.meridian_transits(eph, sun + orbit, topos)` then `almanac.find_discrete(...)`.
- Times are formatted into local HH:MM in the frontend; backend stores strings like `"12:34 Uhr"` or ISO when appropriate.

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

Frontend display: the UI simplifies display names by stripping numeric designations (e.g., "(4) Vesta" → "Vesta").

## Caching

- DataFrame cache: `cache/asteroids_dataframe.pkl` (parsed MPCORB).
- Bright asteroid list cache: `cache/bright_asteroid_cache.pkl` (final results).
- Default validity: 6 hours (see `CACHE_VALIDITY_HOURS`).

## Endpoint

- `GET /api/bright_asteroids?lat=<deg>&lon=<deg>&elevation=<m>`
  - Uses `MAX_APPARENT_MAGNITUDE` from `bright_asteroids.py` for filtering.
  - Responds with a JSON object containing `time`, `location`, and `bodies`.

## Notes and Tips

- If MPC data is large, first load may take time; the frontend shows a loading indicator.
- Ensure you always build the almanac functions with `sun + orbit` and the `Topos` observer to avoid center errors.
- You can adjust brightness thresholds in `bright_asteroids.py`:
  - `MAX_ABSOLUTE_MAGNITUDE` (H) and `MAX_APPARENT_MAGNITUDE` (V).
- Default `G` fallback of 0.15 is a common choice when the slope parameter is missing.
