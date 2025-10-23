# Precompute with RabbitMQ - Simple Coordination

## 🎯 Concept

**Problem solved:** No manual location partitioning needed anymore!

**Solution:** RabbitMQ queue-based coordination

```
┌─────────────────────────────────────────────────────────┐
│ Coordinator (Main server)                               │
│ ├─ Reads locations (user_settings.json + precompute_    │
│ │  locations.json)                                      │
│ ├─ Creates tasks for all locations × times              │
│ └─ Publishes tasks to RabbitMQ queue                    │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │ RabbitMQ Queue        │
            │ 'precompute.tasks'    │
            │ (Priority Queue)      │
            └───────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Workers x4   │ │ Workers x4   │ │ Workers x4   │
│ (Main)       │ │ (rabbit-b)   │ │ (rabbit-c)   │
│ (scalable)   │ │ (scalable)   │ │ (scalable)   │
│              │ │              │ │              │
│ Fetches task │ │ Fetches task │ │ Fetches task │
│ Computes     │ │ Computes     │ │ Computes     │
│ Stores in DB │ │ Stores in DB │ │ Stores in DB │
│ ACK          │ │ ACK          │ │ ACK          │
└──────────────┘ └──────────────┘ └──────────────┘

Default: 12 workers total (4 per server)
Scalable via .env: PRECOMPUTE_WORKERS, PRECOMPUTE_WORKERS_B/C
```

**Important:** Precompute workers perform scheduled precomputation. Asteroid/Comet workers handle on-demand API requests (see below).

---

## 🔄 Worker Types

### 1. Precompute Worker (active)
- **Purpose:** Precompute for known locations
- **Queue:** `precompute.tasks`
- **Trigger:** Coordinator (hourly)
- **Computes:** Asteroids + comets for all locations
- **Status:** ✅ Always active

### 2. Asteroid/Comet Worker (on-demand)
- **Purpose:** On-demand computations for API requests
- **Queues:** `asteroid.compute`, `comet.compute`
- **Trigger:** API request (when location is not in cache)
- **Feature flags:** `USE_RABBITMQ_ASTEROIDS=true`, `USE_RABBITMQ_COMETS=true`
- **Status:** ✅ Active (idle until API requests arrive)
- **Use cases:** Unknown locations, cache-miss, or times outside the precompute window

**Why are asteroid/comet workers sometimes idle?**
- They wait for API requests for non-precomputed locations
- Precompute only covers known locations + a 720h time window
- As soon as a user requests a different location/time, they become active
- **Important:** These workers MUST be running, or API requests for new locations will fail!

---

## ✅ Benefits

1. **No duplicates**
   - Each task is processed exactly once
   - RabbitMQ ensures fair dispatch

2. **Automatic load balancing**
   - Workers pull when free
   - Faster workers process more tasks

3. **Easily scalable**
   - More workers = faster completion
   - Scale via `.env`: `PRECOMPUTE_WORKERS=8`
   - Then: `docker compose up -d`

4. **Failover**
   - If a worker fails, another takes over
   - Tasks are not lost (persistent queue)

5. **Priorities**
   - Next 24h = HIGH priority (10)
   - After that = NORMAL priority (5)

---

## 🚀 Setup

### 1. Automatic setup (recommended)

```bash
# On your development machine
./scripts/setup-production.sh
```

The script deploys:
- Main server: Coordinator + 4 precompute workers
- Worker-B: 4 precompute workers
- Worker-C: 4 precompute workers

### 2. Worker scaling (via .env)

```bash
# Edit .env
PRECOMPUTE_WORKERS=8        # Main server
PRECOMPUTE_WORKERS_B=8      # Worker-B
PRECOMPUTE_WORKERS_C=8      # Worker-C

# Restart
docker compose up -d
```

### 3. Manual setup

```bash
# Main server
docker compose -f docker-compose.production.yml up -d

# Worker-B (optional)
ssh $RABBITMQ_B
cd ~/asciisky
docker compose -f docker-compose.worker-b.yml up -d

# Worker-C (optional)
ssh $RABBITMQ_C
cd ~/asciisky
docker compose -f docker-compose.worker-c.yml up -d
```

---

## 📊 Scaling scenarios

### Scenario 1: Small installation (1–2 locations)

**Setup:**
- 1 Coordinator (main server)
- 4 workers (main server)

```bash
# .env
PRECOMPUTE_WORKERS=4

# Main server only
docker compose -f docker-compose.production.yml up -d
```

**Performance:** ~30 min for 720h × 2 locations

---

### Scenario 2: Standard production (2–5 locations)

**Setup:**
- 1 Coordinator (main server)
- 12 workers (4 main + 4 rabbit-b + 4 rabbit-c)

```bash
# .env (Default)
PRECOMPUTE_WORKERS=4
PRECOMPUTE_WORKERS_B=4
PRECOMPUTE_WORKERS_C=4

# Deployment
./scripts/setup-production.sh
```

**Performance:** ~10 min for 720h × 5 locations

---

### Scenario 3: High performance (5+ locations)

**Setup:**
- 1 Coordinator (main server)
- 24 workers (8 main + 8 rabbit-b + 8 rabbit-c)

```bash
# .env
PRECOMPUTE_WORKERS=8
PRECOMPUTE_WORKERS_B=8
PRECOMPUTE_WORKERS_C=8

# Deployment
./scripts/setup-production.sh
```

**Performance:** ~5 min for 720h × 10 locations

---

## 💡 Do I need asteroid/comet workers?

**Short answer:** Yes! They are critical for API requests.

**Long answer:**

### Precompute workers (scheduled)
- Compute known locations in advance (720h window)
- Store in PostgreSQL cache
- Run automatically every hour
- **Coverage:** Only locations in `precompute_locations.json`

### Asteroid/Comet workers (on-demand)
- Handle API requests for:
  - ✅ New/unknown locations
  - ✅ Times outside the 720h window
  - ✅ Cache miss (e.g., after restart)
- Feature flags: `USE_RABBITMQ_ASTEROIDS=true`, `USE_RABBITMQ_COMETS=true`
- **Important:** Without these workers, API requests for non-precomputed data will not work!

**Recommendation:** 
- **Minimum:** 2 asteroid + 2 comet workers per server (default)
- **Optimal:** 4+ workers per server under high load
- **Idle is normal:** Workers wait for API requests—that's OK!

---

## 🔍 Monitoring

### RabbitMQ UI

**Access via SSH tunnel:**
```bash
# From your local machine
ssh -L 15672:localhost:15672 $RABBITMQ_MAIN

# Then open in the browser
http://localhost:15672

User: admin
Password: <RABBITMQ_PASSWORD from .env>

Queue: precompute.tasks
```

**Check:**
- ✅ Tasks in queue
- ✅ Workers connected (consumers) — should be 12 (default)
- ✅ Messages/sec rate

### Logs

```bash
# Coordinator
docker logs -f asciisky-precompute-coordinator

# Worker (Hauptserver)
docker logs -f asciisky-precompute-worker

# Worker (rabbit-b) - alle 4 Worker
ssh $RABBITMQ_B "docker compose -f docker-compose.worker-b.yml logs -f precompute_worker"

# Worker (rabbit-c) - alle 4 Worker
ssh $RABBITMQ_C "docker compose -f docker-compose.worker-c.yml logs -f precompute_worker"
```

### PostgreSQL cache status

```bash
docker exec asciisky-postgres psql -U asciisky -d asciisky -c "
SELECT 
    location_key,
    COUNT(*) as entries,
    MIN(created_at) as oldest,
    MAX(created_at) as newest
FROM cached_positions
GROUP BY location_key;
"
```

---

## ⚙️ Configuration

### Coordinator (precompute_coordinator.py)

**Environment variables:**
- `ASCII_SKY_PRECOMPUTE_HOURS`: How many hours ahead (default: 720)
- `PRECOMPUTE_COORDINATOR_INTERVAL`: How often to create tasks in seconds (default: 3600 = 1h)
- `RABBITMQ_URL`: RabbitMQ connection

**Location sources (in order):**
1. `user_settings.json` — user location
2. `precompute_locations.json` — configured locations
3. `ASCII_SKY_PRECOMPUTE_LOCATIONS` — environment variable

### Worker (workers/precompute_worker.py)

**Environment variables:**
- `WORKER_ID`: Unique worker ID (for logging)
- `RABBITMQ_URL`: RabbitMQ connection
- `RABBITMQ_PREFETCH_COUNT`: How many tasks concurrently (default: 1)
- `POSTGRES_HOST`: PostgreSQL server
- `USE_POSTGRES`: true for PostgreSQL

---

## 🔧 Troubleshooting

### Issue: No tasks in queue

```bash
# Check coordinator logs
docker logs asciisky-precompute-coordinator

# Check if locations are configured
cat precompute_locations.json
cat user_settings.json
```

### Issue: Workers are not processing tasks

```bash
# Check worker logs
docker logs asciisky-precompute-worker

# Check RabbitMQ connection
docker exec asciisky-precompute-worker ping rabbitmq

# Check PostgreSQL connection
docker exec asciisky-precompute-worker pg_isready -h postgres -U asciisky
```

### Issue: Tasks are not being processed

```bash
# Check queue in RabbitMQ UI
# http://$RABBITMQ_MAIN:15672

# Check consumer count
# Should equal the number of workers
```

---

## 📈 Performance tips

### 1. Start more workers

```bash
# Edit .env
PRECOMPUTE_WORKERS=8  # Instead of 4

# Restart
docker compose -f docker-compose.production.yml up -d
```

### 2. Increase PREFETCH_COUNT

```yaml
# For faster workers
environment:
  - RABBITMQ_PREFETCH_COUNT=2  # Instead of 1
```

**Note:** Only if workers are fast enough!

### 3. Adjust coordinator interval

```yaml
# Create tasks more frequently
environment:
  - PRECOMPUTE_COORDINATOR_INTERVAL=1800  # 30 minutes instead of 1h
```

---

## 🎉 Summary

**Before (complicated):**
- ❌ Manual location partitioning
- ❌ Complicated configuration
- ❌ Possible duplicates

**Now (simple):**
- ✅ RabbitMQ coordinates automatically
- ✅ Easy to scale (more workers = faster)
- ✅ No duplicates (fair dispatch)
- ✅ Failover included
- ✅ Priorities (next 24h first)

**Deployment:**
```bash
# Automatic (recommended)
./scripts/setup-production.sh

# Or manual:
# Main server
docker compose -f docker-compose.production.yml up -d

# Worker server B
ssh $RABBITMQ_B "cd ~/asciisky && docker compose -f docker-compose.worker-b.yml up -d"

# Worker server C
ssh $RABBITMQ_C "cd ~/asciisky && docker compose -f docker-compose.worker-c.yml up -d"
```

**Worker scaling:**
```bash
# Edit .env
PRECOMPUTE_WORKERS=8        # Main server: 8 workers
PRECOMPUTE_WORKERS_B=8      # Worker-B: 8 workers
PRECOMPUTE_WORKERS_C=8      # Worker-C: 8 workers
# = 24 workers total

# Restart
docker compose up -d
```

**Done!** 🚀
