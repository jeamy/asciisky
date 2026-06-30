# ASCII Sky – RabbitMQ/PostgreSQL Test Application

ASCII Sky is a **test and demonstration application for the combined use of RabbitMQ and PostgreSQL**. Its astronomy UI displays the current positions of the Sun, Moon, planets, asteroids, and comets as ASCII art, while providing a realistic workload for queues, workers, caching, persistence, and deduplication.

The supported default setup is a **local, single-workstation system**: the web application, PostgreSQL, RabbitMQ, and the workers all run on one computer with Docker Compose and are used from a browser on that same computer. It is intended for development and experimentation, not as a production-ready public service. The repository also contains historical and experimental multi-host deployment material; that is outside the primary usage described here.

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
- Messier objects overlay (catalog from RASC list via SEDS [dataRASC.txt](http://www.messier.seds.org/xtra/similar/dataRASC.txt)), real-time Alt/Az with rise/set/transit, toggleable like constellations
- Auto-updates every 60 seconds
- Internationalization (i18n) with German as default language
- Simulated time controls (optional): view the sky at a chosen UTC time
  - Extended navigation controls: day back, hour back, reset to current time, hour forward, day forward
  - Clickable time display for entering any custom date and time
  - Frontend appends `?time=<ISO8601>` to API calls automatically when enabled
  - Automatic background precomputation for smooth time navigation
- Yearly sunpath overlay for the current location
  - Toggleable SVG overlay with sunrise/sunset curves for the whole year
  - Hover tooltips with localized date, sunrise, sunset, and day length in hours and minutes
  - Visualization of astronomical, nautical, and civil twilight as colored bands
  - Monthly markers (vertical lines) on the 1st of each month with short month labels at the bottom
- **Planisphere view** (circular sky map)
  - Toggle between horizon and planisphere view
  - Physically consistent projection of objects above and below the horizon
  - SVG horizon overlay aligned with the ASCII sky grid
- Minimalist UI design with optimized space usage
- Horizontal navigation with arrow controls and mouse drag panning
- Labels for bright asteroids, comets, and constellations
- Responsive design with mobile/tablet support
- Desktop zoom functionality (1×, 2×, 4×) with vertical pan/scroll (desktop only, disabled on mobile devices)
- PostgreSQL database backend for efficient data storage and retrieval
- RabbitMQ message queue with distributed compute workers (precompute and on-demand), scalable across multiple hosts; see [API Request Flow](doc/ARCHITECTURE_FLOW_API.md)
- **Distributed duplicate-work protection**: deterministic RabbitMQ message IDs + PostgreSQL advisory locks
  - Message IDs make equivalent tasks identifiable in logs and tooling; standard RabbitMQ queues do not deduplicate on this property
  - Advisory locks serialize equivalent computations across workers that use the same PostgreSQL instance
  - Locks are released explicitly after processing and automatically when their database connection closes
- **Vectorized computation path**: NumPy-based orbit propagation, geometry, and magnitude calculations
  - Asteroids use an H filter, a rough apparent-magnitude filter, then batched propagation and H–G magnitude evaluation
  - Comets use an M1 filter followed by vectorized geometry and M1/k1 magnitude evaluation
  - Rise/set/transit calculations remain limited to the brightest result subset because they are comparatively expensive
- Automatic nightly updates of asteroid and comet orbital data (configurable; default 4:00 AM)
- DataFrame-first loading from filesystem cache (pickled MPC DataFrames) instead of reparsing raw MPC text files

### Screenshots

![ASCII Sky – Main view](doc/ASCII-0.png)

![ASCII Sky – Sunpath overlay](doc/ASCII-1.png)

## Local Usage (Single-Workstation System)

The local Docker Compose stack runs these components on one machine:

- FastAPI web application and astronomy UI
- PostgreSQL for orbital data, user data, cached results, and advisory locks
- RabbitMQ for asynchronous task distribution
- Unified workers for precomputation and on-demand calculations
- A nightly data updater and a precompute coordinator

This setup demonstrates the complete RabbitMQ/PostgreSQL processing path without requiring additional hosts.

### Prerequisites

- Docker with Docker Compose v2
- A current browser
- Internet access during the initial data download

### Quick Start

1. Clone this repository
2. Navigate to the project directory
3. Start the local stack:
   ```bash
   ./scripts/hybrid-setup.sh local
   ```
4. Open `http://localhost:8000` in a browser on the same computer.

The setup script creates `.env` from `.env.example` if necessary, builds the images, starts the services, initializes PostgreSQL, downloads the astronomy data, launches the RabbitMQ workers, and runs smoke tests. The first start can take several minutes because images and orbital data must be downloaded.

Local access points:

- Application: http://localhost:8000
- OpenAPI documentation: http://localhost:8000/docs
- RabbitMQ management UI: http://localhost:15672

The RabbitMQ login is taken from `RABBITMQ_USER` and `RABBITMQ_PASSWORD` in `.env` (development defaults: `admin` / `changeme`). These defaults and the published database/message-broker ports are suitable only for an isolated development machine. Do not expose this stack directly to an untrusted network.

### Daily Operation

```bash
# Show container status
docker compose ps

# Follow logs from all services
docker compose logs -f

# Stop the application and retain PostgreSQL/RabbitMQ data
docker compose down

# Start it again with the retained data
docker compose up -d
```

PostgreSQL and RabbitMQ state is stored in named Docker volumes. Normal restarts retain it. To deliberately remove containers **and all local database and queue data**, run:

```bash
./scripts/hybrid-setup.sh local --clean
```

### What the Test Application Demonstrates

- API requests use PostgreSQL as a cache and persistent data store.
- Cache misses create asynchronous tasks in RabbitMQ.
- Workers consume those tasks, calculate asteroid/comet positions, and write results to PostgreSQL.
- Deterministic message IDs and PostgreSQL advisory locks prevent duplicate work.
- The browser receives cached results while missing data can be calculated in the background.

See [API Request Flow](doc/ARCHITECTURE_FLOW_API.md) for the detailed processing path.

### Verification

```bash
# Run the RabbitMQ/PostgreSQL integration checks
./scripts/hybrid-setup.sh test

# Exercise an API endpoint
curl -s "http://localhost:8000/api/bright_asteroids?lat=46.7632&lon=14.8417&elevation=405"
```

### Experimental Multi-Host Deployment

The files below document an experimental multi-host topology. They are not required for, and are not the supported default of, the local single-workstation test application.

For deployment across multiple servers:

1. Configure `.env` file (see `.env.example`)
2. Optional: Create `.env.b` and `.env.c` for worker-specific settings (see `.env.b.example`, `.env.c.example`)
3. Run the production setup script:
   ```bash
   ./scripts/setup-production.sh
   ```

This deploys with **PostgreSQL advisory locks**:
- **Main Server** ($RABBITMQ_MAIN): Web UI, PostgreSQL, RabbitMQ, Data Updater
- **Worker Server B** ($RABBITMQ_B): Unified Workers with PostgreSQL Advisory Locks
- **Worker Server C** ($RABBITMQ_C): Unified Workers with PostgreSQL Advisory Locks

**PostgreSQL Deduplication Features:**
- PostgreSQL advisory locks prevent workers from computing the same cache key concurrently
- Standard RabbitMQ queues for task distribution
- Horizontal worker scaling against the shared RabbitMQ/PostgreSQL services

See `doc/PRODUCTION_DEPLOYMENT.md` for detailed deployment instructions and `doc/hybrid-deduplication.md` for duplicate-work protection details.

Compose files for production:
- `docker-compose.production.yml` — main server with PostgreSQL Advisory Locks
- `docker-compose.workers.yml` — worker hosts with Unified Workers and Advisory Locks

**Production Updates:**
```bash
# Update with PostgreSQL Advisory Locks verification
./scripts/hybrid-setup.sh update

# Check PostgreSQL Advisory Locks status
./scripts/hybrid-setup.sh test
```

### Docker Services

The application runs multiple services. In local development these are defined in `docker-compose.yml`, in production on the main server in `docker-compose.production.yml`, and on worker hosts in `docker-compose.workers.yml`.

**Core services (main server / local):**

- **`web`** – FastAPI web server (port 8000)
- **`postgres`** – PostgreSQL database with Advisory Locks support (port 5432)
- **`rabbitmq`** – RabbitMQ 4.1 message broker for task distribution (ports 5672, 15672)
- **`data_updater`** – Nightly data update service (runs via `nightly_data_updater.py`)
- **`precompute_coordinator`** – Coordinates creation of precompute tasks and publishes them to RabbitMQ
- **`precompute_worker`** – Dedicated precompute workers that consume `precompute.tasks` and write asteroid/comet positions to PostgreSQL (production main server only)

**Unified Workers and monitoring (local + worker hosts):**

- **`unified_worker`** – Unified Worker(s) with hybrid deduplication
  - Handles all task types: precompute, on-demand asteroids, on-demand comets
  - Publishes deterministic RabbitMQ message IDs and uses PostgreSQL advisory locks while computing
  - Runs as a locally replicated service in `docker-compose.yml` and as scalable workers in `docker-compose.workers.yml`
- **`worker_monitor`** – Real-time performance dashboard for workers (port configurable via `MONITOR_PORT`)

**Unified Worker Architecture:**
- Loads shared Skyfield resources once per worker process and handles precompute, on-demand, and RPC tasks
- Supports horizontal scaling across worker hosts connected to the same broker and database
- Uses PostgreSQL advisory locks to avoid concurrent work for the same computation key
- Adds deterministic message IDs for traceability; this is not broker-side deduplication
- **RabbitMQ 4.1** – Modern message broker with management UI and advanced features

 All services restart automatically unless stopped.

**Worker Scaling** (via `.env`):
```bash
# Main server (precompute_worker in docker-compose.production.yml)
PRECOMPUTE_WORKERS=4  # Dedicated precompute workers on the main server

# Worker hosts (unified_worker in docker-compose.workers.yml)
UNIFIED_WORKERS=8     # Number of unified workers per worker host (handles all task types)
WORKER_MONITOR=1      # Worker monitoring dashboard
```

On worker hosts, `UNIFIED_WORKERS` controls `unified_worker` scaling. If it is not set,
the deployment scripts fall back to `PRECOMPUTE_WORKERS`.

**Duplicate-work protection configuration:**
```bash
ENABLE_HYBRID_DEDUPLICATION=true     # Legacy compatibility value; currently not read by Python
ASCII_SKY_DEDUPLICATION_TTL=300       # Legacy/configuration value; publishing code currently uses a fixed 5-minute message expiration
ASCII_SKY_ADVISORY_LOCK_TTL=300       # Passed to lock instrumentation; it does not expire a PostgreSQL advisory lock
```

### First Run and Data Management

- **First Startup**: The app automatically downloads and stores MPC orbital data in PostgreSQL database
- **Daily Updates**: The `data_updater` service automatically downloads fresh data at the configured hour (default 4:00 AM local time)
- **Loading**: Parsed MPC data is cached as pickled DataFrames on the filesystem; PostgreSQL stores orbital records and computed positions

### Cache Architecture

- **PostgreSQL Database**
  - All MPC orbital data (currently >1.1 million minor planets, ~4,000 comets)
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

1. Ensure you have Python 3.14+ installed
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
- `nightly_data_updater.py` - Automatic daily updates of asteroid and comet data (default: 4:00 AM)
- `settings.py` - User/location settings; persists to `user_settings.json`
- `de421.bsp` - JPL ephemeris used by Skyfield

### RabbitMQ Workers (Unified Architecture)
- `workers/unified_worker.py` - **Unified Worker** (replaces separate asteroid/comet workers)
  - Handles all task types: precompute, asteroids, comets
  - Uses deterministic RabbitMQ message IDs + PostgreSQL Advisory Locks
  - Vectorized magnitude calculations for performance
- `workers/precompute_worker.py` - Dedicated precompute worker consuming `precompute.tasks` and writing positions to PostgreSQL
- `precompute_coordinator.py` - Coordinates precomputation across workers (schedules tasks to RabbitMQ)

### Deployment Scripts
- `scripts/hybrid-setup.sh` - All-in-one local/production setup and diagnostics
- `scripts/setup-production.sh` - Multi-host production deployment
- `scripts/setup-firewall.sh` - Firewall configuration for production


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
- `doc/ARCHITECTURE_FLOW_API.md` - API request flow
- `doc/ARCHITECTURE_CACHE.md` - Cache strategy
- `doc/ARCHITECTURE_DATABASE.md` - Database schema and data flow
- `doc/hybrid-deduplication.md` - Distributed duplicate-work protection

### Configuration
- `Dockerfile` - Docker configuration
- `docker-compose.yml` - Development Docker Compose configuration
- `docker-compose.production.yml` - Production configuration (main server)
- `docker-compose.workers.yml` - Worker servers configuration
- `.env.example` - Environment variables template (main server)
- `.env.b.example` - Environment variables template (worker server B)
- `.env.c.example` - Environment variables template (worker server C)
- `requirements.txt` - Python dependencies

### Scripts

#### Setup and Deployment
- `scripts/hybrid-setup.sh` - All-in-one local/production setup and diagnostics
- `scripts/setup-production.sh` - Experimental multi-host deployment
- `scripts/update-production.sh` - Experimental multi-host updates

#### Utility Scripts
- `scripts/setup-firewall.sh` - Production firewall configuration
- `scripts/init-postgres.sql` - PostgreSQL schema initialization
- `test_hybrid_deduplication.py` - Message-ID and advisory-lock smoke tests

## API Endpoints

All frontend calls use centralized API endpoint constants in `static/js/constants.js`.

- `GET /api/celestial` — real-time snapshot for Sun, Moon, and planets (no cache)
- `GET /api/celestial/{body_id}` — real-time data for a single celestial body
- `GET /api/celestial/sunpath` — yearly sunrise/sunset curve for the current or given location
- `GET /api/bright_asteroids` — bright asteroids with H–G magnitudes, distances and rise/set/transit times
- `GET /api/asteroids` — backward-compatible alias for `/api/bright_asteroids`
- `GET /api/comets` — comets using MPC data with M1/k1 magnitude model and rise/set/transit times; see `doc/comets.md`
- `GET /api/zodiac` — zodiac and selected constellations for a location and time
- `GET /api/session/location` — get current session location (if set)
- `POST /api/session/location` — set session location; triggers background sunpath precompute
- `GET /api/config` — exposure of magnitude limits and constellation defaults to the frontend
- `GET /api/filters` — get current user magnitude filters (applied at API layer, caches stay unfiltered)
- `POST /api/filters` — update user magnitude filters
- `GET /api/user/settings` — get per-user settings (location, display, filters, theme, language, options)
- `PUT /api/user/settings` — upsert per-user settings
- `POST /api/auth/register` — register a new user (first user becomes admin)
- `POST /api/auth/login` — log in with username or email + password
- `POST /api/auth/logout` — clear current session
- `GET /api/auth/me` — return authentication status and basic user info
- `GET /api/admin/users` — list users (admin-only)
- `PATCH /api/admin/users/{user_id}` — update user (admin-only)
- `DELETE /api/admin/users/{user_id}` — delete user (admin-only)

### Simulated Time (optional)

The sky-data endpoints (`/api/celestial`, `/api/bright_asteroids`, `/api/comets`, `/api/zodiac`) accept an optional `time` query parameter to simulate calculations at a specific UTC instant. The value must be ISO 8601 and may end with `Z` or include a timezone offset. The backend normalizes it to UTC.

- Examples:
  - `/api/celestial?lat=48.2082&lon=16.3738&elevation=171&time=2025-01-15T21:30:00Z`
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
- `RABBITMQ_URL` - RabbitMQ connection URL (default: amqp://admin:password@rabbitmq:5672/)
- `RABBITMQ_TIMEOUT` - RabbitMQ task timeout in seconds (default: 120)
- `RABBITMQ_PREFETCH_COUNT` - Prefetch count per worker (default: 1)

### Unified Worker Configuration
- `UNIFIED_WORKERS` - Number of unified workers (handles all task types) (default: 8)
- `WORKER_MONITOR` - Worker monitoring dashboard instances (default: 1)
- `PRECOMPUTE_WORKERS` - Number of dedicated `precompute_worker` instances on the main server (default: 4).
  On worker hosts it is used as a fallback if `UNIFIED_WORKERS` is not set.

### Precompute Configuration
- `ASCII_SKY_PRECOMPUTE_HOURS` – Number of hours into the future that the precompute coordinator generates tasks for (default: 720 = 30 days)
- `ASCII_SKY_PRECOMPUTE_LOCATIONS` – Optional JSON array of locations (`latitude`, `longitude`, `elevation`, `name`) used by the precompute coordinator in addition to the last global location, static `precompute_locations.json`, and all user locations from the database.
- `PRECOMPUTE_TASK_CLAIM_TTL` – Expiry for persistent duplicate-publication claims (default: 86400 seconds)

### Legacy Duplicate-Work Settings
- `ENABLE_HYBRID_DEDUPLICATION`, `ASCII_SKY_DEDUPLICATION_TTL`, and
  `ASCII_SKY_ADVISORY_LOCK_TTL` remain in Compose and environment examples but are
  currently not read by Python. PostgreSQL advisory locks have no TTL; see
  [`doc/hybrid-deduplication.md`](doc/hybrid-deduplication.md).

**Note:** The old separate worker variables (`ASTEROID_WORKERS`, `COMET_WORKERS`) have been replaced by `UNIFIED_WORKERS` for better resource efficiency.

### Data Update Configuration
- `ASCII_SKY_UPDATE_HOUR` - Hour of day for automatic data updates (default: 4, meaning 4:00 AM)

### Magnitude Limits Configuration
- `ASCII_SKY_ASTEROID_MAX_ABSOLUTE_MAG` – Maximum absolute magnitude for asteroid prefiltering (Docker default: 14.0, code fallback: 12.0)
- `ASCII_SKY_ASTEROID_MAX_APPARENT_MAG` – Maximum apparent magnitude for asteroid processing/display (default: 10.0)
- `ASCII_SKY_COMET_MAX_ABSOLUTE_MAG` – Maximum absolute magnitude for comet prefiltering (Docker default: 20.0, code fallback: 18.0)
- `ASCII_SKY_COMET_MAX_APPARENT_MAG` – Maximum apparent magnitude for comets (default: 14.0)
- `ASCII_SKY_ASTEROIDS_EVENTS_MAX` – Max rise/set/transit computations per asteroid (default: 50)
- `ASCII_SKY_COMET_EVENTS_MAX` – Max rise/set/transit computations per comet (Docker default: 50, code fallback: 300)
- `ASCII_SKY_EVENT_GRID_MINUTES` – Event sampling interval; rise/set crossings are interpolated (default: 10)

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
- [API Request Flow](doc/ARCHITECTURE_FLOW_API.md)
- [Cache Strategy](doc/ARCHITECTURE_CACHE.md)
- [Database Schema](doc/ARCHITECTURE_DATABASE.md)
- [Production Deployment](doc/PRODUCTION_DEPLOYMENT.md)
- [Firewall Setup](doc/FIREWALL_SETUP.md)

## Technologies Used

- **Backend**: FastAPI, [Skyfield](https://rhodesmill.org/skyfield/), PostgreSQL with Advisory Locks
- **Performance**: NumPy vectorization for high-speed magnitude calculations
- **Message Queue**: RabbitMQ 4.1 with async workers (deterministic IDs + PostgreSQL locks for dedup)
- **Frontend**: HTML, CSS, JavaScript
- **Containerization**: Docker, Docker Compose

## Duplicate-Work Protection Quick Reference

**All-in-One Setup:**
```bash
./scripts/hybrid-setup.sh local           # Start local development (keeps data)
./scripts/hybrid-setup.sh local --clean   # Fresh start with empty database
./scripts/hybrid-setup.sh production      # Deploy to production  
./scripts/hybrid-setup.sh update          # Update production
./scripts/hybrid-setup.sh test            # Run tests
./scripts/hybrid-setup.sh summary         # Show overview
```

**How it works:**
- Publishers attach a deterministic `message_id` and a message expiration; the standard queues still accept duplicate messages.
- Before computing, workers acquire a PostgreSQL advisory lock derived from the normalized location, time bucket, and object type.
- A second equivalent task waits for the lock and then rechecks the cache, so it normally skips work completed by the first worker.
- The lock is connection-scoped, has no time-based expiry, and is released in `finally` or when the database connection closes.

**Monitoring:**
- RabbitMQ UI: http://localhost:15672
- Quick status: `./scripts/hybrid-setup.sh test`
- Complete overview: `./scripts/hybrid-setup.sh summary`

**Documentation:** See [`doc/hybrid-deduplication.md`](doc/hybrid-deduplication.md) for implementation details and limitations.

## Performance Optimizations

### Current Local Measurement (2026-06-30)

Measured with the repository data (1,552,856 asteroids and 958 comets), Vienna,
2026-06-28 12:00 UTC, Python 3.14.6 / NumPy 2.5.0. DataFrames were already loaded,
matching a long-running worker:

| Pipeline | Candidates/results | Wall time |
|---|---:|---:|
| Asteroids, magnitude ≤ 10 | 5,399 / 7 | 1.66 s |
| Comets, top results | 939 / 20 | 2.48 s |

These are current-path measurements, not a controlled before/after claim. Exact
times vary with data, event limits, cache state, and hardware.

### What Changed

**Asteroid pipeline (`bright_asteroids.py`):**
- Replaced bulk `observe(target)` loops with vectorised NumPy position arithmetic
  for heliocentric distance `r`, geocentric distance `δ`, and phase angle `α`.
- `observer.at(t)` is now called only for the small final output set (≤ 50 objects) to produce
  RA / Dec / Alt / Az — not for every candidate.
- Tightened the rough-magnitude pre-filter margin from **+3.0 → +1.5 mag** (26 % fewer candidates;
  profiling confirmed 0 bright objects missed at margin 1.0).
- Accuracy impact: < 0.001 AU in distance, < 0.001° in phase angle vs. the full light-time-corrected
  `observe()` path — negligible for H–G magnitude computation.

**Comet pipeline (`comets.py`):**
- Fixed `AttributeError: eccentricity` crash: `mpc.comet_orbit()` requires `eccentricity`,
  `perihelion_distance_au`, `inclination_degrees`, etc. as row attributes; the `_RowProxy` data
  dictionary was missing these MPC field aliases → all aliases now generated consistently.
- Fixed fractional perihelion-day handling (`perihelion_day = 20.3223` → float preserved in
  `ts.tt(y, m, d)`; previously truncated to integer).
- Same `target.at(t)` vectorisation as asteroids: `observe()` eliminated from the first pass,
  deferred to the final output loop only.
- Perihelion epochs are prepared during ingestion; full Skyfield targets are built only for final results.

### Vectorized Computations
ASCII Sky uses NumPy vectorization to reduce Python-loop and per-object astronomy overhead:

**Batched calculations:**
- Asteroid orbit propagation, geometry, phase angle, and H–G apparent magnitude
- Comet distance geometry and M1/k1 apparent magnitude
- Batch processing of candidate arrays

**Smart Pre-Filtering:**
- NumPy rough magnitude estimation
- Filters impossible objects before expensive Skyfield calls
- Asteroid pipeline: absolute-magnitude filter → rough apparent-magnitude filter (+1.5 mag margin) → vectorized precise calculation
- Comet pipeline: absolute-magnitude filter → vectorized calculation → apparent-magnitude selection
- Event-time calculations are capped via `ASCII_SKY_ASTEROIDS_EVENTS_MAX` and `ASCII_SKY_COMET_EVENTS_MAX`
- Event-grid resolution is controlled by `ASCII_SKY_EVENT_GRID_MINUTES` (default 10 minutes; crossings are interpolated)

### Database Optimization
- DataFrame-first loading from filesystem cache (pickled MPC DataFrames) instead of reparsing raw MPC text files
- Intelligent caching with TTL and precompute windows
- PostgreSQL advisory locks for database consistency
- Persistent precompute claims reduce duplicate queue publications across coordinator restarts
- Current and adjacent hourly buckets receive the highest precompute priority
- MPC updates invalidate only the changed asteroid/comet cache type, and unchanged datasets retain cached positions

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

This project was built with assistance from Windsurf (agentic AI coding assistant), GPT, Claude, Kimi, GLM, SWE and google-labs-jules[bot]. Babysitting by a human in a virtual environment.

This research has made use of data and/or services provided by the International Astronomical Union's Minor Planet Center. 

## Live Demo

You can try ASCII Sky online at: https://asciisky.eibrain.org/
When switching to a new location for the first time, calculations may take longer because asteroid and comet sky data for that location must be computed and cached first.

Registration & Accounts
The login and registration feature is a convenience option for this demo. The app can be used fully without logging in.

When you register, the following data is stored: username, password hash (no plain-text password) and optional user settings such as location, display settings (e.g. horizontal shift), simulated time, brightness filters, color theme and language. Without logging in, these settings are only stored locally in your browser (localStorage), not on the server.

Important: There is no password reset and no support for account recovery. If you forget your password, the account cannot be restored – simply create a new account instead.


## License

This repository is released under the [MIT License](LICENSE).
