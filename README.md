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
  - Quick controls: hour back, reset to current time, hour forward
  - Clickable time display for entering any custom date and time
  - Frontend appends `?time=<ISO8601>` to API calls automatically when enabled
- Minimalist UI design with optimized space usage
- Cache status panel showing precomputed data availability
- Custom date range cache precomputation with progress tracking
- Horizontal navigation with arrow controls
- Labels for bright asteroids and comets
- Responsive design with mobile/tablet support

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
  - Precomputed data is stored in location-specific cache files for fast retrieval

- Asteroids
  - `cache/asteroids_dataframe.pkl` (parsed MPCORB)
  - `cache/bright_asteroid_cache.pkl` (final filtered results; ~6h TTL)
  - If you change thresholds in `bright_asteroids.py` (`MAX_ABSOLUTE_MAGNITUDE`, `MAX_APPARENT_MAGNITUDE`), delete asteroid cache files under `cache/`.

- Comets
  - `cache/CometEls.txt` (download-once copy of MPC comet elements)
  - `cache/comets_dataframe.pkl` (standardized DataFrame; ~6h TTL)
  - `cache/bright_comet_cache.pkl` (final comet list; ~6h TTL; not keyed by location)
  - Thresholds are defined in `comets.py` (`MAX_ABSOLUTE_MAGNITUDE = 14.0`, `MAX_APPARENT_MAGNITUDE = 10.0`). Delete the comet cache files under `cache/` to force recompute with new thresholds.

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
- `settings.py` - User/location settings; persists to `user_settings.json`
- `de421.bsp` - JPL ephemeris used by Skyfield
- `templates/` - HTML templates
- `static/js/` - JavaScript modules
  - `constants.js` - Configuration parameters and centralized API endpoints
  - `skyRenderer.js` - ASCII sky rendering, dialogs, name normalization and time label handling
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
- `Dockerfile` - Docker configuration
- `docker-compose.yml` - Docker Compose configuration
- `requirements.txt` - Python dependencies

## API Endpoints

All endpoints are referenced in the frontend via `static/js/constants.js`.

- `GET /api/celestial` — positions for Sun, Moon, and planets
- `GET /api/celestial/{body}` — position for a single body
- `GET /api/bright_asteroids` — bright asteroids with H–G magnitudes and event times
- `GET /api/asteroids` — same data shape as bright asteroids (filtered by apparent magnitude)
- `GET /api/comets` — comets using MPC data with M1/k1 magnitude model and rise/set/transit times; optional `max_comets` query parameter; see `doc/comets.md`

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

## Environment Variables

The application can be configured using the following environment variables in `docker-compose.yml`:

### Cache Configuration
- `ASCII_SKY_PRECOMPUTE_HOURS` - Number of hours to precompute in the rolling window (default: 144)
- `ASCII_SKY_MAX_PRECOMPUTE_HOURS` - Maximum allowed hours for custom date range precomputation (default: 168)
- `ASCII_SKY_PRECOMPUTE_KINDS` - Types of data to precompute (default: "celestial,asteroids,comets")
- `ASCII_SKY_RETENTION_DAYS` - Number of days to retain cached data (default: 30)

### Worker Configuration
- `ASCII_SKY_PRECOMPUTE_WORKERS` - Number of worker threads for precomputation (default: 4)
- `ASCII_SKY_ADAPTIVE_WORKERS` - Enable adaptive worker count based on CPU cores (default: 1)
- `ASCII_SKY_WORKER_RUN_ONCE` - Run worker once and exit (default: not set, only for worker_once service)

### General Configuration
- `PYTHONUNBUFFERED` - Python output buffering (default: 1)
- `TZ` - Timezone for the application (default: Europe/Berlin)
- `ASCII_SKY_SESSION_SECRET` - Secret key for session encryption (default: "dev-secret-please-change")

## Technologies Used

- Backend: FastAPI, [Skyfield](https://rhodesmill.org/skyfield/)
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


