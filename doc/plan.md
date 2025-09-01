# ASCII Sky - Development Plan

## Features Implemented

1. **ASCII Horizon Line**
   - ✅ Created a dynamic horizon line using ASCII characters
   - ✅ Added cardinal directions (N, O, S, W)
   - ✅ Adjusted line dynamically based on object position

2. **Celestial Object Positioning**
   - ✅ Calculated correct position for celestial objects in the ASCII sky
   - ✅ Showed object position relative to horizon
   - ✅ Handled objects below the horizon
   - ✅ Added special symbols for objects below the horizon

3. **Interactive Menu**
   - ✅ Created an object selection menu for celestial objects
   - ✅ Included Sun, Moon, and planets
   - ✅ Added object information on selection

4. **Object Information Dialog**
   - ✅ Displayed detailed information when an object is selected
   - ✅ Showed current position, distance, and other relevant data
   - ✅ Added rise, set, and transit times for all celestial objects
   - ✅ Included closable dialog with X button

## Recent Improvements

### Backend (Python/FastAPI)
- ✅ Added API endpoints for celestial objects
- ✅ Implemented constants for API endpoints and astronomical values
- ✅ Fixed serialization issues with celestial body data
- ✅ Improved error handling for missing celestial bodies
- ✅ Added calculation of rise, set, and transit times for all celestial objects
- ✅ Modified visibility logic to always show objects below the horizon
- ✅ Implemented bright asteroids pipeline with IAU H–G magnitude model
  - Use `mpc.mpcorb_orbit()` and observe `sun + orbit` from an Earth `Topos`
  - Compute heliocentric distance r, observer distance Δ, phase angle α
  - Apply H–G magnitude: `V = H + 5 log10(rΔ) − 2.5 log10((1−G)Φ1 + GΦ2)`
  - Two-stage filtering: `MAX_ABSOLUTE_MAGNITUDE (H)` and `MAX_APPARENT_MAGNITUDE (V)`
  - Rise/Set/Transit via `almanac` with `sun + orbit` and `Topos`
  - Transit selection: choose the upper transit (highest altitude) on the current local day
  - Time formatting: backend returns plain local "HH:MM" strings (no localized suffix)

 - ✅ Implemented comets pipeline with real MPC data and M1/k1 photometric model
   - Load MPC elements, build orbits with `mpc.comet_orbit()`; compute topocentric alt/az
   - Apparent magnitude: `V = M1 + 5 log10(Δ) + k1 log10(r)`
   - Filtering: prefilter `M1 ≤ 14.0`; final filter `V ≤ 10.0`; optional `max_comets` parameter
   - Event times: risings/settings + transit over 48h; select highest-altitude transit; local "HH:MM"
   - Caching: DataFrame (~6h TTL) and bright comet list (~6h TTL) under `cache/`
   - API: `GET /api/comets` (centralized in `static/js/constants.js`)

 - ✅ Completed planet, Sun, Moon magnitude models and endpoints
   - Sun fixed −26.74; Moon phase-based heuristic
   - Mercury–Saturn via `planetary_magnitude` (fallbacks); Uranus/Neptune fixed
   - Endpoints: `GET /api/celestial` and `GET /api/celestial/{body}`
   - See `doc/planets.md`

### Frontend (JavaScript)
- ✅ Centralized constants in constants.js
- ✅ Fixed recursion bug in skyRenderer.js
- ✅ Improved rendering performance
- ✅ Added proper symbol mapping for celestial objects
- ✅ Enhanced object dialog with rise, set, and transit times
- ✅ Improved positioning of objects below the horizon
- ✅ Implemented internationalization (i18n) with German as default language
- ✅ Improved multi-object dialog with minimalist design and better spacing
- ✅ Moved dialog CSS to external file for better maintainability
- ✅ Added loading indicator while fetching bright asteroids
- ✅ Simplified asteroid display names (strip numeric designations like "(4) Vesta")
- ✅ Deduplicate objects by normalized name key to avoid duplicates in dialogs
- ✅ Centralized time labeling with `buildTimeLabel()` to avoid duplicated "Uhr"

### Code Organization
- ✅ Moved all constants to constants.js
- ✅ Created separate modules for different functionality
- ✅ Added documentation and comments

## Ongoing Tasks

### Backend
- [ ] Implement time-based simulation controls
- [ ] Optional: Standardize logging across backend modules and set default level to INFO
- [ ] 48h‑Vorberechnung im Hintergrund, stündlich rollierend (siehe Abschnitt „Hintergrund‑Vorberechnung für Simulation“)

### Frontend
- [ ] Add responsive design for different screen sizes
- [ ] Implement animation for object movement
- [ ] Add search functionality for celestial objects
- [ ] Gate console logging behind a debug flag in `skyRenderer.js`/`settings.js`
- [ ] Persist last-selected object and restore on load
- [ ] Test comet labels and tune label thresholds if needed (labels only)

## Hintergrund‑Vorberechnung für Simulation (48h, stündlich)

- __Ziele__
  - Simulierte Ansichten werden ausschließlich aus dem Cache bedient (keine On‑Demand‑Berechnung).
  - Antwortzeiten stabil und kurz, keine langen Rechenzeiten im Request‑Pfad.

- __Umfang__
  - Alle vorhandenen/konfigurierten Orte (z. B. Liste in `config/locations.json` oder bestehende gespeicherte Orte).
  - Daten für: Planeten/Sonne/Mond, helle Asteroiden, Kometen (inkl. Labels und Auf/Unter/Transit‑Zeiten).

- __Zeit‑Raster__
  - Stündliche Samples für die nächsten 48 Stunden (UTC‑Stundenbuckets, z. B. `YYYYMMDDTHH`).
  - Job läuft jede volle Stunde und schiebt das 48h‑Fenster rollierend weiter.

- __Cache/Storage__
  - Persistente Dateien unter `cache/` pro Ort und Stunde, z. B. `cache/{kind}/{lat}_{lon}_{elev}/YYYYMMDDTHH.pkl`.
  - TTL ≥ 49h oder keine TTL; separater Cleanup für Daten älter als 72h.
  - API‑Endpoints für Simulation lesen ausschließlich aus diesem Cache.

- __Orchestrierung__
  - Stündlicher Worker (separater Docker‑Service oder In‑Process‑Scheduler).
  - Retry/Fehlerstrategie, Logging/Metriken; Start leicht versetzt zur vollen Stunde, um Race‑Conditions zu vermeiden.
  - Konfigurierbare Standortliste; initial alle bestehenden Orte.

- __Fallbacks__
  - Falls ein Snapshot fehlt: optional nächstgelegene Stunde verwenden oder 202/503 zurückgeben (kein On‑Demand‑Rechnen).

### UI/UX
- [ ] Improve ASCII art for different objects
- [ ] Add help/instructions panel
- [ ] Create user preferences for display options

## Technical Considerations
- Using Skyfield for accurate astronomical calculations
- Docker for consistent deployment environment
- Centralized constants for better maintainability
- Optimized rendering to prevent recursion issues
- H–G magnitude implementation and asteroid selection documented in `doc/asteroids.md`
 - Comet brightness uses M1/k1 model with thresholds `M1 ≤ 14.0` and `V ≤ 10.0`
 - Caching under `cache/`: comet DataFrame (~6h TTL), bright comet list (~6h TTL)
 - API endpoints are centralized in `static/js/constants.js`

## Comets Pipeline (Implemented)

1. Data source and caching
   - Load MPC comet orbital elements via `skyfield.data.mpc.load_comets_dataframe()`
   - Cache raw MPC file and standardized DataFrame under `cache/` (DataFrame TTL ~6h)
   - Cache the final bright comet list separately (TTL ~6h) for fast responses

2. Orbit and geometry
   - Build comet orbits with `mpc.comet_orbit(row, ts, GM_SUN)`
   - Compute topocentric alt/az from the observer `eph['earth'] + wgs84.latlon(...)`
   - Distances: observer distance Δ (AU) and heliocentric distance r (AU)

3. Photometric model and filtering
   - Use the M1/k1 model: `V = M1 + 5 log10(Δ) + k1 log10(r)`
   - Prefilter by absolute magnitude `M1 ≤ 14.0`
   - Final filter by apparent magnitude `V ≤ 10.0`
   - Optional: limit payload with `max_comets` query parameter

4. Event times
   - Compute rise, set, and transit over a 48-hour window using Skyfield almanac
   - Select events for the current local day and choose the highest-altitude transit
   - Format times as local "HH:MM"; frontend applies localized labels

5. API
   - Endpoint: `GET /api/comets?max_comets=<N>`
   - Returns a list with: `name`, `symbol` (☄️), `type` ("comet"), `ra`, `dec`, `altitude`, `azimuth`, `distance`, `magnitude`, `rise_time`, `set_time`, `transit_time`

6. Frontend integration
   - Endpoints centralized in `static/js/constants.js`
   - Label control via `CONFIG.LABELS.ENABLE_BRIGHT_COMET_LABELS` and `BRIGHT_COMET_MAG_THRESHOLD`
   - Magnitude filtering is backend-internal; UI labels are controlled separately

7. Documentation
   - See `doc/comets.md` for details; `README.md` updated with caching and endpoint notes

8. Testing
   - Sanity-check a sample comet against external ephemerides
   - UI test/tune label thresholds; verify timing across timezones
