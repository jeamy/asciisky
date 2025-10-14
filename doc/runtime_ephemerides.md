# Runtime Ephemerides and Caching Strategy

This document explains how AsciiSky should compute positions for small bodies (asteroids/comets) at runtime, inspired by Stellarium and KStars. The key idea is to keep only the orbital elements on disk and compute positions "on the fly" for the current time, location, and view, instead of precomputing large ranges.

## Principles

- Use real orbital element data (MPCORB for asteroids, MPC Comet Elements for comets). No demo/fallback data.
- Compute positions at request time from elements using efficient algorithms.
- Filter aggressively (magnitude thresholds, horizon/FOV) to keep the number of computed objects small per frame.
- Cache minimally and intelligently (in-memory during a session), but do not rely on large time-range precomputations.
- Keep the Docker environment as the execution target; all dependencies (e.g., Skyfield) are available in the container.

## Data Sources

- Asteroids: MPCORB (Minor Planet Center)
- Comets: MPC Comet Elements (M1/k1)
- Planets/Moon: analytical models (e.g., VSOP87/ELP) or library equivalents

AsciiSky stores the raw elements (and parsed forms) in the cache/ directory and/or SQLite, with reasonable TTLs for comets. API endpoints are centralized in `static/js/constants.js` per project conventions.

## Computation Pipeline (Runtime)

For a given observing site (lat, lon, elevation) and time t:

1) Element propagation
- From the element epoch to time t: solve Kepler's equation to obtain state at t
- Heliocentric coordinates → transform to geocentric, apply light-time correction if needed

2) Coordinate transforms
- Ecliptic → Equatorial, apply precession/nutation/aberration (library-provided)
- Geocentric → Topocentric for the observing site
- Convert to Alt/Az

3) Apparent magnitude
- Asteroids: IAU H,G or H,G1,G2 model
- Comets: M1,k1 model

4) Visibility/selection filters
- Magnitude threshold (configurable via env)
- Object subset (top-N by brightness or curated list)
- Horizon/FOV culling

5) Output
- Minimal structure per object: { id, name, alt, az, ra, dec, mag, distance, rise/set/transit if requested }

## Session Caches (In-Memory)

- Active object set
  - Maintain a list of objects that were recently visible/bright enough.
  - Update incrementally as time pans forward/backward.

- Result cache (small, time-bucketed)
  - Keyed by: (rounded_time, location_bucket, object_id)
  - Rounded_time: e.g. to nearest 1–5 minutes for small bodies; reduces recomputation within a pan/drag session.
  - Evict on location/time changes or size limits.

- Label/layout cache
  - Keep computed label positions and connection segments per frame for smoother UI redraws.

No large-range precompute is necessary. The above caches are transient and kept in memory only. SQLite remains the primary persistent store for raw elements and small auxiliary indices.

## Performance Notes

- Filter early: magnitude threshold and initial horizon/FOV culling before full transforms.
- Use fast solvers (Newton) for Kepler's equation; limit iterations.
- Batch computations per object type to reduce overhead.
- Consider update cadence per object class (e.g., very faint objects update less often).

## Configuration

- Magnitude thresholds via environment variables:
  - `ASCII_SKY_ASTEROID_MAX_ABSOLUTE_MAG` (default: 12.0)
  - `ASCII_SKY_ASTEROID_MAX_APPARENT_MAG` (default: 10.0)
  - `ASCII_SKY_COMET_MAX_ABSOLUTE_MAG` (default: 18.0)
  - `ASCII_SKY_COMET_MAX_APPARENT_MAG` (default: 14.0)
- Feature flags (for rollout, see migration plan):
  - `ASCII_SKY_RUNTIME_EPHEMERIS` (enable runtime computation)
  - `ASCII_SKY_DISABLE_PRECOMPUTE_UI` (hide precompute UI)

## Frontend Integration

- Endpoints in `static/js/constants.js`.
- The frontend should request only what is currently needed (visible objects, current time), and append `?time=<ISO8601>` when sim time is active.
- Keep UI responsive with frame-throttling for pans/zooms.

## Docker Environment

- No local installs; everything runs inside Docker.
- Skyfield and other dependencies are bundled in the container and used by the backend APIs.
