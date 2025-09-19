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
- Auto-updates every 60 seconds
- Internationalization (i18n) with German as default language
- Simulated time controls (optional): view the sky at a chosen UTC time
  - Extended navigation controls: day back, hour back, reset to current time, hour forward, day forward
  - Clickable time display for entering any custom date and time
  - Frontend appends `?time=<ISO8601>` to API calls automatically when enabled
  - Automatic background precomputation for smooth time navigation
- Minimalist UI design with optimized space usage
- Cache status panel showing precomputed data availability
- Custom date range cache precomputation with progress tracking
- Horizontal navigation with arrow controls
- Labels for bright asteroids and comets
- Responsive design with mobile/tablet support
- Desktop zoom functionality (1×, 2×, 4×) with vertical pan/scroll (desktop only, disabled on mobile devices)
- SQLite database backend for efficient data storage and retrieval

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

### First Run and Caching

- The first startup can take longer because the app downloads and parses MPC orbital data and creates caches.

- Cache Precomputation
  - The cache status panel allows precomputing celestial data for a custom date range
  - Select start and end dates, then click "Start Precompute" to begin background calculation
  - Progress is displayed in real-time with a progress bar
  - Maximum range is 7 days (168 hours) to prevent excessive resource usage
  - Precomputed data is stored in SQLite database and location-specific cache files for fast retrieval

- SQLite Database Cache
  - Primary cache backend for all astronomical data
  - Stored in `cache/asciisky.db`
  - Provides efficient storage and retrieval of asteroid/comet orbital data
  - Caches computed positions for specific locations and time buckets
  - See `doc/sqlite.md` for detailed schema and implementation

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

- Thresholds (configurable via environment variables)
  - Asteroids: 
    - `ASCII_SKY_ASTEROID_MAX_ABSOLUTE_MAG` (default: 12.0)
    - `ASCII_SKY_ASTEROID_MAX_APPARENT_MAG` (default: 10.0)
  - Comets:
    - `ASCII_SKY_COMET_MAX_ABSOLUTE_MAG` (default: 18.0)
    - `ASCII_SKY_COMET_MAX_APPARENT_MAG` (default: 16.0)
  - Current values exposed via `/api/config` endpoint
  - To force recomputation with new thresholds, delete both SQLite database and pickle cache files

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
- `db_utils.py` - SQLite database utilities for efficient data storage and retrieval
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

### Magnitude Limits Configuration
- `ASCII_SKY_ASTEROID_MAX_ABSOLUTE_MAG` - Maximum absolute magnitude for asteroid prefiltering (default: 12.0)
- `ASCII_SKY_ASTEROID_MAX_APPARENT_MAG` - Maximum apparent magnitude for asteroid display (default: 10.0)
- `ASCII_SKY_COMET_MAX_ABSOLUTE_MAG` - Maximum absolute magnitude for comet prefiltering (default: 18.0)
- `ASCII_SKY_COMET_MAX_APPARENT_MAG` - Maximum apparent magnitude for comet display (default: 16.0)

### General Configuration
- `PYTHONUNBUFFERED` - Python output buffering (default: 1)
- `TZ` - Timezone for the application (default: Europe/Berlin)
- `ASCII_SKY_SESSION_SECRET` - Secret key for session encryption (default: "dev-secret-please-change")

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


