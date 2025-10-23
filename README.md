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
  - No cache invalidation when filters change; filtering is applied in API routes and cached positions are unfiltered and reused
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
- PostgreSQL database backend for efficient data storage and retrieval
- RabbitMQ message queue with distributed compute workers (precompute and on-demand), scalable across multiple hosts; see [API Request Flow](doc/ARCHITECTURE_FLOW_API.md) and [Worker Setup](doc/WORKER_SETUP.md)
- Automatic nightly updates of asteroid and comet orbital data (configurable; default 4:00 AM)
- DB-first loading strategy for optimal performance (10x faster than file parsing)

## Prerequisites

- Docker and Docker Compose

## Running the Application

### Development Setup (Local)

1. Clone this repository
2. Navigate to the project directory
3. Run the setup script:
   ```bash
   ./scripts/setup-dev.sh
   ```
4. Open your browser and navigate to `http://localhost:8000`

The setup script automatically:
- Creates `.env` file with default configuration
- Builds Docker images
- Starts all services (web, PostgreSQL, RabbitMQ, workers)
- Initializes the database
- Downloads initial asteroid/comet data

### Production Deployment (Multi-Host)

For production deployment across multiple servers:

1. Configure `.env` file (see `.env.example`)
2. Run the production setup script:
   ```bash
   ./scripts/setup-production.sh
   ```

This deploys:
- **Main Server** ($RABBITMQ_MAIN): Web UI, PostgreSQL, RabbitMQ, Data Updater
- **Worker Server B** ($RABBITMQ_B): Scalable compute workers
- **Worker Server C** ($RABBITMQ_C): Scalable compute workers

See `doc/PRODUCTION_DEPLOYMENT.md` for detailed deployment instructions.

Compose files for production:
- `docker-compose.production.yml` — main server (web, PostgreSQL, RabbitMQ, coordinator, precompute workers)
- `docker-compose.workers.yml` — worker hosts (precompute, asteroid, comet workers)

### Docker Services

The application runs multiple services:

- **`web`** - FastAPI web server (port 8000)
- **`postgres`** - PostgreSQL database (port 5432)
- **`rabbitmq`** - RabbitMQ message broker for async task processing (ports 5672, 15672)
- **`precompute_worker`** - Scalable workers for precomputation tasks (configurable via `.env`)
- **`asteroid_worker`** - Scalable workers for asteroid computations (configurable via `.env`)
- **`comet_worker`** - Scalable workers for comet computations (configurable via `.env`)
- **`precompute_coordinator`** - Coordinates precomputation tasks
- **`data_updater`** - Nightly data update service (runs at 2:00 AM)

All services restart automatically unless stopped.

**Worker Scaling** (via `.env`):
```bash
PRECOMPUTE_WORKERS=4  # Number of precompute workers
ASTEROID_WORKERS=2    # Number of asteroid workers
COMET_WORKERS=2       # Number of comet workers
```

### First Run and Data Management

- **First Startup**: The app automatically downloads and stores MPC orbital data in PostgreSQL database
- **Daily Updates**: The `data_updater` service automatically downloads fresh data at the configured hour (default 4:00 AM local time)
- **Performance**: After initial setup, all data loads from database (10x faster than file parsing)

### Cache Architecture

- **PostgreSQL Database**
  - All asteroid and comet orbital data (~2200 asteroids, ~1200 comets)
  - Pre-computed positions cached per location and time bucket
  - Automatic nightly updates via `data_updater` service
  - Multi-host capable: All workers connect to central PostgreSQL instance
  - See `doc/ARCHITECTURE_DATABASE.md` and `doc/ARCHITECTURE_CACHE.md` for details

- **RabbitMQ Task Queue**
  - Async computation of asteroid and comet positions
  - Dedicated worker processes for parallel processing
  - Cache-first strategy: returns cached data immediately, computes missing data in background
  - Automatic retry and error handling

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

### Core Application
- `main.py` - FastAPI application with celestial object calculation logic
- `bright_asteroids.py` - Bright asteroid pipeline (IAU H–G), Sun+orbit observation, event times
- `comets.py` - Comet pipeline using MPC data with M1/k1 magnitude model
- `db_utils.py` - PostgreSQL database utilities for efficient data storage and retrieval
- `nightly_data_updater.py` - Automatic daily updates of asteroid and comet data (2:00 AM)
- `settings.py` - User/location settings; persists to `user_settings.json`
- `de421.bsp` - JPL ephemeris used by Skyfield

### RabbitMQ Workers
- `workers/precompute_worker.py` - Async worker for precomputation tasks
- `workers/asteroid_worker.py` - Async worker for asteroid computations
- `workers/comet_worker.py` - Async worker for comet computations
- `workers/precompute_coordinator.py` - Coordinates precomputation across workers

### Deployment Scripts
- `scripts/setup-dev.sh` - Development environment setup
- `scripts/setup-production.sh` - Multi-host production deployment
- `scripts/setup-firewall.sh` - Firewall configuration for production
- `scripts/setup-rabbitmq-queues.sh` - RabbitMQ queue initialization

### Frontend
- `templates/` - HTML templates
- `static/js/` - JavaScript modules
  - `constants.js` - Configuration parameters and centralized API endpoints
  - `skyRenderer.js` - ASCII sky rendering, dialogs, zoom/pan functionality
  - `skyManager.js` - Sky rendering initialization and update management
  - `i18n.js` - Internationalization module with translations
  - `locationDialog.js` - User location dialog logic
  - `settings.js` - Frontend settings utilities
  - `zodiacRenderer.js` - Zodiac rendering utilities
- `static/css/` - CSS styles

### Documentation
- `doc/asteroids.md` - Asteroid position and magnitude pipeline (H–G model)
- `doc/comets.md` - Comet position and magnitude pipeline (M1/k1 model)
- `doc/planets.md` - Planet/Sun/Moon positions, magnitudes, and event times
- `doc/ARCHITECTURE_INDEX.md` - Architecture entry point
- `doc/ARCHITECTURE_FLOW.md` - System & precompute flow
- `doc/ARCHITECTURE_FLOW_API.md` - API request flow
- `doc/ARCHITECTURE_CACHE.md` - Cache strategy
- `doc/ARCHITECTURE_DATABASE.md` - Database schema and data flow

### Configuration
- `Dockerfile` - Docker configuration
- `docker-compose.yml` - Development Docker Compose configuration
- `docker-compose.production.yml` - Production configuration (main server)
- `docker-compose.worker-b.yml` - Worker server B configuration
- `docker-compose.worker-c.yml` - Worker server C configuration
- `.env.example` - Environment variables template
- `requirements.txt` - Python dependencies

## API Endpoints

All endpoints are referenced in the frontend via `static/js/constants.js`.

- `GET /api/planets` — positions for Sun, Moon, and planets (direct computation, no cache)
- `GET /api/bright_asteroids` — bright asteroids with H–G magnitudes and event times
- `GET /api/comets` — comets using MPC data with M1/k1 magnitude model and rise/set/transit times; optional `max_comets` query parameter; see `doc/comets.md`
- `GET /api/filters` — get/set user magnitude filters (applied at API layer)

### Simulated Time (optional)

All endpoints above accept an optional `time` query parameter to simulate calculations at a specific UTC instant. The value must be ISO 8601 and may end with `Z` or include a timezone offset. The backend normalizes it to UTC.

- Examples:
  - `/api/planets?lat=48.2082&lon=16.3738&elevation=171&time=2025-01-15T21:30:00Z`
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

#### Distributed Host Configuration
- `RABBITMQ_MAIN` — Main server hostname used by workers (default: `asciisky.example.org`)
- `RABBITMQ_B` — Worker server B hostname (default: `rabbit-b.example.org`)
- `RABBITMQ_C` — Worker server C hostname (default: `rabbit-c.example.org`)
- `RABBITMQ_MAIN_IP` — Main server static IP used by `extra_hosts` in `docker-compose.workers.yml` (default: `203.0.113.10`)

Notes:
- These values are read from `.env` by `docker-compose.workers.yml` to resolve `POSTGRES_HOST`, `RABBITMQ_URL`, and `extra_hosts`.
- Replace the example hostnames/IP with your production domain names or static IPs.

### RabbitMQ Configuration
- `USE_RABBITMQ` - Enable RabbitMQ for async processing (default: true)
- `USE_RABBITMQ_ASTEROIDS` - Enable RabbitMQ for asteroids (default: true)
- `USE_RABBITMQ_COMETS` - Enable RabbitMQ for comets (default: true)
- `RABBITMQ_URL` - RabbitMQ connection URL (default: amqp://admin:password@rabbitmq:5672/)
- `RABBITMQ_TIMEOUT` - RabbitMQ task timeout in seconds (default: 120)
- `PRECOMPUTE_WORKERS` - Number of precompute workers on the main server (default: 4)
- `ASTEROID_WORKERS` - Number of on-demand asteroid workers per host (default: 2)
- `COMET_WORKERS` - Number of on-demand comet workers per host (default: 2)
- `RABBITMQ_PREFETCH_COUNT` - Prefetch count per worker (default: 1)

### Data Update Configuration
- `ASCII_SKY_UPDATE_HOUR` - Hour of day for automatic data updates (default: 4, meaning 4:00 AM)

### Magnitude Limits Configuration
- `ASCII_SKY_ASTEROID_MAX_ABSOLUTE_MAG` - Maximum absolute magnitude for asteroid prefiltering (default: 12.0)
- `ASCII_SKY_ASTEROID_MAX_APPARENT_MAG` - Maximum apparent magnitude for asteroid display (default: 10.0)
- `ASCII_SKY_COMET_MAX_ABSOLUTE_MAG` - Maximum absolute magnitude for comet prefiltering (default: 20.0)
- `ASCII_SKY_COMET_MAX_APPARENT_MAG` - Maximum apparent magnitude for comet display (default: 14.0)
- `ASCII_SKY_ASTEROIDS_EVENTS_MAX` - Maximum number of asteroid events (default: 100)
- `ASCII_SKY_COMET_EVENTS_MAX` - Maximum number of comet events (default: 50)

### General Configuration
- `PYTHONUNBUFFERED` - Python output buffering (default: 1)
- `TZ` - Timezone for the application (default: Europe/Berlin)
- `ASCII_SKY_SESSION_SECRET` - Secret key for session encryption (default: change-in-production)

## Documentation

### Core Features
- [Asteroids](doc/asteroids.md) - Implementation details for asteroid tracking
- [Comets](doc/comets.md) - Comet tracking and M1/k1 magnitude model
- [Planets](doc/planets.md) - Planetary positions and calculations

### Architecture
- [Architecture Index](doc/ARCHITECTURE_INDEX.md) - Entry point for architecture docs
- [System & Precompute Flow](doc/ARCHITECTURE_FLOW.md)
- [API Request Flow](doc/ARCHITECTURE_FLOW_API.md)
- [Cache Strategy](doc/ARCHITECTURE_CACHE.md)
- [Database Schema](doc/ARCHITECTURE_DATABASE.md)
- [Worker Setup](doc/WORKER_SETUP.md)
- [Production Deployment](doc/PRODUCTION_DEPLOYMENT.md)
- [Firewall Setup](doc/FIREWALL_SETUP.md)

## Technologies Used

- **Backend**: FastAPI, [Skyfield](https://rhodesmill.org/skyfield/), PostgreSQL
- **Message Queue**: RabbitMQ 4.1 with async workers
- **Frontend**: HTML, CSS, JavaScript
- **Containerization**: Docker, Docker Compose

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


