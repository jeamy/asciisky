# Comets: Position and Magnitude Pipeline

This document explains how ASCII Sky computes positions and brightness for comets using real MPC data, and how filtering and event times are determined.

## Overview

- Source data: MPC comet orbital elements (downloaded once and cached locally).
- Orbits: Constructed per row with Skyfield `mpc.comet_orbit()`.
- Geometry: Positions are computed topocentrically from an Earth observer with the composite target `sun + orbit`.
- Apparent magnitude: Estimated using the M1/k1 photometric model:
  - V = M1 + 5 log10(Δ) + 2.5·k1·log10(r) (with k1 interpreted as exponent n)
- Filtering: Two-stage filtering for performance and relevance.
  - Prefilter by absolute parameters: require M1 and k1, and M1 ≤ 14.0
  - Final filter by estimated apparent magnitude: V ≤ 10.0
- Rise/Set/Transit: Computed with Skyfield almanac over a two-day window, selecting the best local-day transit.
- Caching: DataFrame and final bright list are cached to speed up subsequent calls.
- API: `GET /api/comets` with optional `max_comets` parameter.

Backend entrypoint: `comets.load_comets()`.

## Data Loading and Normalization

- The loader reads from a local cached copy `cache/CometEls.txt` if available; otherwise it downloads from MPC and saves it there.
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

Cache: standardized DataFrame is stored in `cache/comets_dataframe.pkl` with a 6h validity.

## Geometry and Distances

For each candidate comet row:

- Time: `t = ts.now()` (UTC)
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

Two-stage filtering is applied to reduce heavy computations:

1. Prefilter by photometric parameters:
   - Require `M1` and `k1` present and `M1 <= 14.0`.
   - Process intrinsically brighter comets first (sort by `M1`).
2. Apparent magnitude filter:
   - After computing V, keep comets with `V <= 10.0`.

Processing stops after collecting up to `max_comets` items.
- Default in `comets.load_comets()`: 5000
- Default for the API query param in `main.py`: 1000

Note: The frontend no longer exposes user-set magnitude filters. These backend thresholds exist only to limit work and return relevant objects.

## Rise, Set, and Transit Times

For each comet that passes filtering:

- Window: 48h starting at UTC midnight of the current day.
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

- MPC raw copy: `cache/CometEls.txt` (download-once cache of MPC elements)
- DataFrame cache: `cache/comets_dataframe.pkl` (6h validity)
- Bright comet list cache: `cache/bright_comet_cache.pkl` (final filtered list, ~6h validity; not keyed by location)

## Endpoint

- `GET /api/comets?lat=<deg>&lon=<deg>&elevation=<m>&max_comets=<N>`
  - Returns a JSON object with `time`, `location`, and `bodies`.
  - `max_comets` limits how many candidates are processed/returned (default 1000 at the API layer).

## Frontend Integration

- Endpoints are centralized in `static/js/constants.js`.
- Comets use the symbol "☄️" and type "comet". Label overlays for bright comets are controlled via:
  - `CONFIG.LABELS.ENABLE_BRIGHT_COMET_LABELS`
  - `CONFIG.LABELS.BRIGHT_COMET_MAG_THRESHOLD`
- Label filtering only affects display overlays, not backend data loading.
