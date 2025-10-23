# Planets: Positions, Magnitudes, and Event Times

This document explains how ASCII Sky computes positions, magnitudes, and event times for the Sun, Moon, and planets.

## Overview

- Bodies: Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune
- Time: `dt_utc` resolved from optional `time` query param (ISO 8601; supports trailing `Z` or TZ offset). Defaults to current UTC. `t = ts.from_datetime(dt_utc)`
- Observer: topocentric Earth location using `wgs84.latlon(lat, lon, elevation_m)`
- Output: altitude, azimuth, Earth-center distance (AU), and magnitude, plus rise/set/transit times
- API: `/api/planets` (all bodies)

Backend implementation: see `api/routes/planets.py` function `get_planets()`.
Note: Planets are computed **synchronously** (no RabbitMQ workers), as they are fast to calculate.

## Geometry and Distances

- Observer: `observer = eph['earth'] + wgs84.latlon(lat, lon, elevation_m=elevation)`
- Position: `astrometric = observer.at(t).observe(body)`; `apparent = astrometric.apparent()`
- Topocentric coordinates: `alt, az, _ = apparent.altaz()`
- Distance (AU): computed from Earth’s center to the body
  - `earth_center = eph['earth'].at(t)`
  - `earth_distance = earth_center.observe(body).distance().au`

Note: Distance is geocentric in AU; altitude/azimuth are topocentric.

## Magnitude Models

- Sun: fixed value `-26.74`
- Moon: phase-based heuristic
  - Phase angle from Skyfield: `almanac.moon_phase(eph, t).radians`
  - Magnitude formula: `M = -12.7 + 2.5 * log10(0.5 * (1 - cos(phase_angle)))`
  - Guard against invalid `log10(0)` by clamping the phase factor; fallback `-12.7` when zero
- Mercury–Saturn: Skyfield’s `planetary_magnitude(astrometric)`
  - If the call fails, static fallbacks are used:
    - Mercury 0.23, Venus -4.14, Mars 1.66, Jupiter -2.2, Saturn 0.46
- Uranus, Neptune: static magnitudes 5.7 and 7.8

Returned magnitudes are floats. They are not user-configurable.

## Rise, Set, and Transit Times

Times are returned as local `HH:MM` strings. The frontend appends localized labels (e.g., “Uhr”).

- Rise/Set window:
  - `/api/celestial`: search over a 48-hour window starting at UTC midnight of the simulated day using `almanac.risings_and_settings()` and `almanac.find_discrete()`
  - `/api/celestial/{body}`: same 48-hour window anchored at the simulated day’s UTC midnight
- Transit (culmination):
  - `/api/celestial`: approximated as the midpoint between rise and set when both exist; otherwise fall back to “now + 12h”
  - `/api/celestial/{body}`: same midpoint approach when possible; otherwise an estimate (+6h or +18h) based on whether altitude is rising or falling

Note: Unlike asteroids/comets (which use `almanac.meridian_transits()`), planetary transit is approximated from rise/set times.

## Output Shape

- `/api/celestial` returns:
  - `time`: ISO datetime (UTC)
  - `location`: `{ latitude, longitude, elevation }`
  - `bodies`: map keyed by body name with entries:
    - `name`, `symbol`
    - `altitude`, `azimuth` (deg)
    - `distance` (AU, geocentric)
    - `magnitude` (float)
    - `visible`: always true
    - `rise_time`, `set_time`, `transit_time` (strings or null)
- `/api/celestial/{body}` returns the body entry above, plus for the Moon:
  - `phase`: 0..1
  - `phase_name`: a coarse phase label (e.g., `new_moon`, `full_moon`)

## Endpoint Summary

- `GET /api/planets?lat=<deg>&lon=<deg>&elevation=<m>&time=<ISO8601>` (optional `time`)

Example:

```
GET /api/planets?lat=48.2082&lon=16.3738&elevation=171&time=2025-01-15T21:30:00Z
```

## Frontend Integration

- Endpoints are centralized in `static/js/constants.js` per project convention.
- The frontend treats all bodies as visible and overlays labels/time information accordingly.

## Caching

- Planet/Sun/Moon calculations run on demand and are not cached server-side.
