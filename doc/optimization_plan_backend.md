# Backend Optimization Plan

This document outlines incremental backend optimizations for AsciiSky that keep the current precompute-first architecture intact, avoid any demo/fallback data, and remain fully Docker-compatible. Changes focus on lowering latency in cache-miss scenarios, cutting I/O, and improving compute efficiency.

## Goals

- Maintain the stable precompute pipeline (SQLite + pickle as needed) and automatic background window generation.
- Reduce latency spikes during on-demand fallbacks in API routes.
- Minimize redundant compute work (especially comet orbit builds and event times).
- Keep everything running inside Docker; no local installs.
- No demo/fallback data at any point.

## Quick Wins (Phase 1)

- Offload heavy computations in async routes to background threads
  - Files: `api/routes/comets.py`, `api/routes/asteroids.py`
  - Change: Wrap calls to `comets.load_comets(...)` and `bright_asteroids.load_bright_asteroids(...)` in `await asyncio.to_thread(...)` to avoid blocking the event loop on cache misses.

- Enforce strict TTL on pickle cache reads (no stale disk fallbacks)
  - Files: `api/routes/comets.py`, `api/routes/asteroids.py`
  - Change: Remove the "if file exists, then read anyway" branch after `read_pickle_if_fresh(...)` returns None. Always respect TTL.

- LRU cache for comet orbit building
  - File: `comets.py`
  - Change: Introduce a small in-process LRU cache for `mpc.comet_orbit(...)` keyed by essential orbital elements to reduce repeated orbit constructions across calls.

- Limit rise/set/transit calculations for comets to top-N
  - File: `comets.py`
  - Change: Compute rise/set/transit only for the first N bright comets (configurable). Others get `null` for event times, saving CPU in heavy scenes.

- Use wgs84 consistently for observer location in comets
  - File: `comets.py`
  - Change: Replace `Topos` with `wgs84.latlon` to match `api/computation.py` and keep code consistent with current Skyfield usage.

## Configuration

- ASCII_SKY_COMET_EVENTS_MAX (default: 50)
  - Limits how many comet event-time calculations (rise/set/transit) are performed per response.

Existing environment variables remain unchanged (e.g., magnitude thresholds, precompute window/workers, retention days). Endpoints continue to be centralized in `static/js/constants.js`.

## Rollout Plan

1) Implement quick wins (Phase 1) and deploy to development.
2) Verify:
   - No event loop blocking under cache-miss load.
   - Comet API latency improved when many candidates exist.
   - No stale pickle reads occur; SQLite path remains primary.
3) Benchmark typical usage (panning/time jumps) and precompute sweeps.
4) If desired, proceed with Phase 2 refinements (DB exists-check methods, optional disabling of pickle writes when SQLite is enabled, additional observability timers).

## Notes & Constraints

- Docker environment only; no local installs required.
- No demo/fallback data anywhere.
- Frontend endpoints remain unchanged and centralized in `static/js/constants.js`.
- Magnitude thresholds remain sourced from environment variables.
