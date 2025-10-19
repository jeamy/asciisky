# Migration Plan: From Precomputation to Runtime Ephemerides

This plan describes how to migrate AsciiSky from custom-range precomputation of object positions to a runtime ephemerides model (compute positions on demand from orbital elements), inspired by Stellarium/KStars.

## Goals

- Compute positions on demand from MPC elements (no range precompute).
- Keep persistent storage minimal (elements + small indices in PostgreSQL).
- Ensure smooth UX (panning/zooming/time steps) via small in-memory session caches only.
- Preserve Docker-only environment; no local installs. Dependencies are already in the container (e.g., Skyfield).
- No demo/fallback data; always use real data.
- Centralize frontend API endpoints in `static/js/constants.js`.

## Current State (Summary)

- Precomputation UI allows custom date-range precompute; results stored in PostgreSQL + pickle files.
- Frontend can request precomputed availability and use cached results.
- Magnitude thresholds and other settings via environment variables.

## Target Architecture

- Persistent: only orbital elements and small metadata in PostgreSQL.
- Runtime: positions computed per request/time/location.
- Session caches (memory):
  - Active object set (recently visible/bright).
  - Small result cache keyed by (rounded_time, location_bucket, object_id).
  - Optional label/layout cache for frontend.
- No disk-based precompute of time ranges.

## Phased Migration

### Phase 0 — Feature Flags (safe landing)
- Add environment flags:
  - `ASCII_SKY_RUNTIME_EPHEMERIS=true|false` (default: false initially)
  - `ASCII_SKY_DISABLE_PRECOMPUTE_UI=true|false` (default: false initially)
- Backend honors flags to switch code path; frontend hides precompute UI when disabled.

### Phase 1 — Backend Runtime Endpoint(s)
- Ensure APIs compute positions from elements on demand. Typical endpoints:
  - `/api/asteroids?lat=..&lon=..&elevation=..&time=ISO&mag_max=..&limit=..`
  - `/api/comets?...` (M1/k1)
  - `/api/celestial?...` (planets/moon)
- Internals:
  - Shared pipeline: propagate → transform → magnitude → filter.
  - Batch compute with capped object counts (Top-N by expected brightness).
  - Small in-process cache for (time_bucket, location_bucket, object_id).
- Keep endpoints’ base URLs centralized in `static/js/constants.js` (per project rule).

### Phase 2 — Frontend Switch (behind flags)
- When `ASCII_SKY_RUNTIME_EPHEMERIS=true`, frontend:
  - Stops invoking precompute UI/actions.
  - Requests data only for the current sim time and visible set.
  - Maintains frame-throttled redraws; applies FOV/horizon/magnitude filters client-side if needed.
- Respect language/i18n; keep labels minimal.

### Phase 3 — Deprecate Disk Precompute
- Announce deprecation in README and docs.
- Stop writing new pickle caches and precompute tables when runtime mode is on.
- Provide a maintenance command (documented) to clean old caches (within Docker volume). Do not auto-delete.

### Phase 4 — Performance & Quality
- Benchmarks on typical hardware:
  - cold start response times
  - steady-state panning @ 1×/2×/4× zoom
  - object count scaling (e.g., 100/500/2000 candidates)
- Tune thresholds (env vars) and limits.
- Add logging/timing around hot paths (guarded by debug flag).

### Phase 5 — Remove Legacy
- After bake-in period and positive metrics, default `ASCII_SKY_RUNTIME_EPHEMERIS=true`.
- Hide precompute UI by default; remove code paths and doc sections.

## API and Config Changes

- Add flags:
  - `ASCII_SKY_RUNTIME_EPHEMERIS`
  - `ASCII_SKY_DISABLE_PRECOMPUTE_UI`
- Keep existing magnitude env vars:
  - `ASCII_SKY_ASTEROID_MAX_ABSOLUTE_MAG`
  - `ASCII_SKY_ASTEROID_MAX_APPARENT_MAG`
  - `ASCII_SKY_COMET_MAX_ABSOLUTE_MAG`
  - `ASCII_SKY_COMET_MAX_APPARENT_MAG`
- Ensure `/api/config` exposes the above so the frontend can adapt.
- Frontend endpoints remain centralized in `static/js/constants.js`.

## Database Changes

- Retain tables for elements and small indices.
- Deprecate/remove precomputed time-bucket tables once legacy is removed.
- No need for pickle caches in runtime mode; document clean-up.
- Update `doc/sqlite.md` to reflect the leaner schema (follow-up task).

## Testing & Rollout

- Unit tests: element propagation, transforms, magnitude models.
- Integration tests: API responses for fixed (time, location) with known bodies.
- Performance tests: response time under typical loads.
- UI/E2E sanity: panning, zoom, time jumps, i18n labels.
- Rollout plan:
  1) Land behind feature flag in main; disabled by default.
  2) Enable in dev/staging; compare metrics vs precompute.
  3) Enable by default; keep legacy code for one release as fallback.
  4) Remove legacy.

## Risks & Mitigations

- Performance regressions on low-end machines → stronger magnitude/FOV culling, Top-N cap.
- Accuracy concerns over long time spans → ensure element epochs are recent; refresh elements regularly.
- Memory usage from session cache → cap sizes, short TTLs.

## Timeline (suggested)

- Week 1: Implement flags and backend runtime endpoints; basic cache.
- Week 2: Frontend integration behind flag; initial benchmarks; fix hotspots.
- Week 3: Enable by default; documentation updates; deprecate legacy paths.
- Week 4: Remove legacy code and precompute UI; finalize docs.
