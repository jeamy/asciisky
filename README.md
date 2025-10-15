# ASCII Sky - Celestial Tracker

A web application that displays the current positions of celestial bodies (Sun, Moon, planets, asteroids, comets) in ASCII art.

## Features

- Real-time tracking of celestial bodies (altitude and azimuth)
- Display of objects above and below the horizon
- Current moon phase visualization
- Rise, set, and transit times for all celestial objects
- Interactive object selection with detailed information dialog
- Distance and magnitude information for all objects
- Bright asteroids (minor planets) with apparent magnitude filtering and rise/set/transit times
- Comets using real MPC data with M1/k1 magnitude model, positions, and rise/set/transit times
- **User-adjustable brightness filters** for asteroids and comets (magnitude 10-20)
  - Accessible via ⚙️ button under "Visible Objects"
  - Filters saved per user in `user_settings.json`
  - Automatic cache recalculation when filters change
- Constellation visualization with:
  - Interactive toggle to show/hide constellations
  - Constellation lines connecting major stars (using data from [constellationship.fab](https://github.com/Stellarium/stellarium/tree/master/skycultures/western))
  - Constellation names in the selected language
  - Smooth panning and zooming
- Auto-updates every 60 seconds
- Internationalization (i18n) with German as default language
- Simulated time controls (optional): view the sky at a chosen UTC time
  - Extended navigation controls: day back, hour back, reset to current time, hour forward, day forward
  - Clickable time display for entering any custom date and time
  - Frontend appends `?time=<ISO8601>` to API calls automatically when enabled
  - Automatic background precomputation for smooth time navigation
- Minimalist UI design with optimized space usage
- Horizontal navigation with arrow controls and mouse drag panning
- Labels for bright asteroids, comets, and constellations
- Responsive design with mobile/tablet support
- Desktop zoom functionality (1×, 2×, 4×) with vertical pan/scroll (desktop only, disabled on mobile devices)
- SQLite database backend for efficient data storage and retrieval
- Automatic nightly updates of asteroid and comet orbital data (2:00 AM)
- DB-first loading strategy for optimal performance (10x faster than file parsing)

## Prerequisites

- Docker and Docker Compose

## Running the Application

### Using Docker Compose (Recommended)

1. Clone this repository
2. Navigate to the project directory
3. Run the following command:
   ```bash
   docker-compose up --build
   ```
4. Open your browser and navigate to `http://localhost:8000`

### Docker Services

The application runs multiple services:

- **`web`** - FastAPI web server (port 8000)
- **`worker`** - Precompute worker for cache generation
- **`data_updater`** - Nightly data update service (runs at 2:00 AM)
- **`task_cleanup`** - Background task file cleanup service

All services restart automatically unless stopped.

### First Run and Data Management

- **First Startup**: The app automatically downloads and stores MPC orbital data in SQLite database
- **Daily Updates**: The `data_updater` service automatically downloads fresh data at 2:00 AM local time
- **Performance**: After initial setup, all data loads from database (10x faster than file parsing)

- Cache Precomputation
  - Precomputed data is stored in SQLite database and location-specific cache files for fast retrieval

- SQLite Database (Primary Backend)
  - **DB-first approach**: All asteroid and comet data loaded from database
  - Stored in `celestial_cache.db`
  - Contains ~2200 asteroids and ~1200 comets with orbital elements
  - Pre-computed positions cached per location and time bucket
  - Automatic nightly updates via `data_updater` service
  - See `doc/sqlite.md` and `doc/data-management.md` for details

- Pickle Cache (Fallback)
  - Asteroids
    - `cache/asteroids_dataframe.pkl` (parsed MPCORB)
    - `cache/asteroids/lat+XX.XXXX_lon+YY.YYYY_el+ZZZZ/YYYYMMDDTHH.pkl` (location/time-specific cache)
  - Comets
    - `cache/COMET_ELEMENTS.txt` (download-once copy of MPC comet elements)
    - `cache/comets_dataframe.pkl` (standardized DataFrame; 49h TTL)
    - `cache/comets/lat+XX.XXXX_lon+YY.YYYY_el+ZZZZ/YYYYMMDDTHH.pkl` (location/time-specific cache with 1h TTL and 1h buckets)
  - Celestial
    - `cache/celestial/lat+XX.XXXX_lon+YY.YYYY_el+ZZZZ/YYYYMMDDTHH.pkl` (location/time-specific cache)

- Magnitude Filters
  - **User-adjustable filters** via UI (⚙️ button under "Visible Objects")
    - Range: magnitude 10.0 to 20.0 (adjustable in 0.5 steps)
    - Saved per user in `user_settings.json`
    - Cache automatically recalculated when filters change (may take several minutes)
  - **Default values** from environment variables:
    - Asteroids: `ASCII_SKY_ASTEROID_MAX_APPARENT_MAG` (default: 10.0)
    - Comets: `ASCII_SKY_COMET_MAX_APPARENT_MAG` (default: 14.0)
  - **Cache strategy**: All objects up to magnitude 20.0 are cached, filtering happens at API level
  - Current filter values exposed via `/api/filters` endpoint

### Without Docker

1. Ensure you have Python 3.9+ installed
2. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   uvicorn main:app --reload
   ```
4. Open your browser and navigate to `http://localhost:8000`

## Project Structure

- `main.py` - FastAPI application with celestial object calculation logic
- `bright_asteroids.py` - Bright asteroid pipeline (IAU H–G), Sun+orbit observation, event times
- `comets.py` - Comet pipeline using MPC data with M1/k1 magnitude model
- `db_utils.py` - SQLite database utilities for efficient data storage and retrieval
- `nightly_data_updater.py` - Automatic daily updates of asteroid and comet data (2:00 AM)
- `settings.py` - User/location settings; persists to `user_settings.json`
- `de421.bsp` - JPL ephemeris used by Skyfield
- `templates/` - HTML templates
- `static/js/` - JavaScript modules
  - `constants.js` - Configuration parameters and centralized API endpoints
  - `skyRenderer.js` - ASCII sky rendering, dialogs, zoom/pan functionality, name normalization and time label handling
  - `skyManager.js` - Sky rendering initialization and update management
  - `i18n.js` - Internationalization module with translations
  - `locationDialog.js` - User location dialog logic
  - `settings.js` - Frontend settings utilities
  - `zodiacRenderer.js` - Zodiac rendering utilities
- `static/css/` - CSS styles
  - `dialogStyles.css` - Object dialog styles
  - `loadingIndicator.css` - Loading indicator styles
  - `locationDialogStyles.css` - Location dialog styles
  - `navigationArrows.css` - Navigation arrows styles
  - `timeControls.css` - Simulated time controls styles
- `doc/` - Documentation files
  - `plan.md` - Development plan and feature tracking
  - `asteroids.md` - Asteroid position and magnitude pipeline (H–G model)
  - `comets.md` - Comet position and magnitude pipeline (M1/k1 model)
  - `planets.md` - Planet/Sun/Moon positions, magnitudes, and event times
  - `cache.md` - Technical documentation of the cache system architecture
  - `sqlite.md` - SQLite database schema and implementation details
  - `data-management.md` - Data loading strategy, nightly updates, and troubleshooting
- `Dockerfile` - Docker configuration
- `docker-compose.yml` - Docker Compose configuration
- `requirements.txt` - Python dependencies

## API Endpoints

All endpoints are referenced in the frontend via `static/js/constants.js`.

- `GET /api/celestial` — positions for Sun, Moon, and planets
- `GET /api/celestial/{body}` — position for a single body
- `GET /api/bright_asteroids` — bright asteroids with H–G magnitudes and event times
- `GET /api/comets` — comets using MPC data with M1/k1 magnitude model and rise/set/transit times; optional `max_comets` query parameter; see `doc/comets.md`
- `GET /api/cache_status` — cache status and precomputed data availability; see `doc/cache.md`
- `GET /api/config` — current configuration including magnitude limits from environment variables

### Simulated Time (optional)

All celestial endpoints accept an optional `time` query parameter to simulate calculations at a specific UTC instant. The value must be ISO 8601 and may end with `Z` or include a timezone offset. The backend normalizes it to UTC.

- Examples:
  - `/api/celestial?lat=48.2082&lon=16.3738&elevation=171&time=2025-01-15T21:30:00Z`
  - `/api/celestial/moon?lat=48.2082&lon=16.3738&elevation=171&time=2025-01-15T21:30:00Z`
  - `/api/bright_asteroids?lat=48.2082&lon=16.3738&elevation=171&time=2025-01-15T21:30:00Z`
  - `/api/comets?lat=48.2082&lon=16.3738&elevation=171&time=2025-01-15T21:30:00Z`

Notes:

- Event windows (rise/set/transit) are anchored to UTC midnight of the simulated day.
- The response echoes `time` in UTC ISO format.
- The frontend simulated time controls persist an offset in minutes and, when enabled, automatically append `time=<ISO8601>` to requests.

Times returned by the backend are plain local `HH:MM`. The frontend appends the localized hour label.

### Zoom and Pan Functionality

The application provides zoom and pan functionality for desktop users:

- **Zoom Levels**: Toggle between 1×, 2×, and 4× magnification using the zoom button in the top-right corner
- **Pan Control**: When zoomed (2× or 4×), click and drag to pan vertically through the sky view
- **Visual Indicators**: 
  - Cursor changes to "grab" when hovering over zoomable content
  - Cursor changes to "grabbing" during active panning
- **Mobile Behavior**: Zoom and pan are automatically disabled on mobile devices (screen width ≤ 768px)
- **Reset**: Zoom level resets vertical offset when toggled

### Environment Variables

The application can be configured using the following environment variables in `docker-compose.yml`:

### Cache Configuration
- `ASCII_SKY_PRECOMPUTE_HOURS` - Number of hours to precompute in the rolling window (default: 144)
- `ASCII_SKY_MAX_PRECOMPUTE_HOURS` - Maximum allowed hours for custom date range precomputation (default: 168)
- `ASCII_SKY_PRECOMPUTE_KINDS` - Types of data to precompute (default: "celestial,asteroids,comets")
- `ASCII_SKY_RETENTION_DAYS` - Number of days to retain cached data (default: 30)

### Database Configuration
- `ASTEROID_USE_SQLITE` - Enable SQLite backend for asteroids (default: 1)
- `COMET_USE_SQLITE` - Enable SQLite backend for comets (default: 1)
- `CELESTIAL_USE_SQLITE` - Enable SQLite backend for celestial objects (default: 1)

### Worker Configuration
- `ASCII_SKY_PRECOMPUTE_WORKERS` - Number of worker threads for precomputation (default: 4)
- `ASCII_SKY_ADAPTIVE_WORKERS` - Enable adaptive worker count based on CPU cores (default: 1)
- `ASCII_SKY_WORKER_RUN_ONCE` - Run worker once and exit (default: not set, only for worker_once service)

### Data Update Configuration
- `ASCII_SKY_UPDATE_HOUR` - Hour of day for automatic data updates (default: 2, meaning 2:00 AM)

### Magnitude Limits Configuration
- `ASCII_SKY_ASTEROID_MAX_ABSOLUTE_MAG` - Maximum absolute magnitude for asteroid prefiltering (default: 12.0)
- `ASCII_SKY_ASTEROID_MAX_APPARENT_MAG` - Maximum apparent magnitude for asteroid display (default: 10.0)
- `ASCII_SKY_COMET_MAX_ABSOLUTE_MAG` - Maximum absolute magnitude for comet prefiltering (default: 20.0)
- `ASCII_SKY_COMET_MAX_APPARENT_MAG` - Maximum apparent magnitude for comet display (default: 14.0)

### General Configuration
- `PYTHONUNBUFFERED` - Python output buffering (default: 1)
- `TZ` - Timezone for the application (default: Europe/Berlin)
- `ASCII_SKY_SESSION_SECRET` - Secret key for session encryption (default: "dev-secret-please-change")

## Documentation

### Core Features
- [Asteroids](doc/asteroids.md) - Implementation details for asteroid tracking
- [Comets](doc/comets.md) - Comet tracking and M1/k1 magnitude model
- [Planets](doc/planets.md) - Planetary positions and calculations
- [Constellations](doc/constellations.md) - Star patterns and visualization (using data from [Stellarium](https://github.com/Stellarium/stellarium/tree/master/skycultures/western))

### Architecture
- [Runtime Ephemerides](doc/runtime_ephemerides.md) - On-demand position computation strategy
- [SQLite Database](doc/sqlite.md) - Database schema and caching strategy
- [Cache Management](doc/cache.md) - Caching layers and performance considerations
- [Data Management](doc/data-management.md) - DB-first loading, nightly updates, and troubleshooting

### Migration & Maintenance
- [Runtime Migration Plan](doc/migration_plan_runtime_ephemerides.md) - Transitioning to on-the-fly computation
- [Session Management](doc/sessionmgm.md) - User sessions and state handling
- [Session Management (English)](doc/sessionmgm_en.md) - English version of session management docs

## Technologies Used

- Backend: FastAPI, [Skyfield](https://rhodesmill.org/skyfield/), SQLite
- Frontend: HTML, CSS, JavaScript
- Containerization: Docker, Docker Compose

## Skyfield 

This project uses Skyfield for astronomical calculations.

Skyfield: High precision research-grade positions for planets and Earth satellites generator
Rhodes, Brandon
Skyfield computes positions for the stars, planets, and satellites in orbit around the Earth. Its results should agree with the positions generated by the United States Naval Observatory and their Astronomical Almanac to within 0.0005 arcseconds (which equals half a "mas" or milliarcsecond). It computes geocentric coordinates or topocentric coordinates specific to your location on the Earth's surface. Skyfield accepts AstroPy (ascl:1304.002) time objects as input and can return results in native AstroPy units but is not dependend on AstroPy nor its compiled libraries.
Code site:
https://github.com/skyfielders/python-skyfield
https://pypi.org/project/skyfield/
Used in:
https://ui.adsabs.harvard.edu/abs/2019AdSpR..63.3795S
Bibcode:
2019ascl.soft07024R
Preferred citation method:
https://ui.adsabs.harvard.edu/abs/2019ascl.soft07024R


## Attribution

This project was built with assistance from Windsurf (agentic AI coding assistant), GPT 5, Claude 3.7 Sonnet and SWE-1. Babysitting by a human in a virtual environment.


## License

This repository is released under the [MIT License](LICENSE).


