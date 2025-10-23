# Worker Setup Guide

## Architecture

ASCII Sky uses a multi-host worker architecture with RabbitMQ:

```
┌─────────────────────────────────────────────────────────────┐
│ Main server ($RABBITMQ_MAIN)                                  │
│ - Web (FastAPI)                                              │
│ - RabbitMQ (Message Broker)                                  │
│ - PostgreSQL (Cache/DB)                                      │
│ - Precompute Worker (4x)                                     │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ RabbitMQ (Port 5672)
                          │ PostgreSQL (Port 5432)
                          │
        ┌─────────────────┴─────────────────┐
        │                                   │
┌───────▼──────────┐              ┌────────▼─────────┐
│ Worker Host B    │              │ Worker Host C    │
│ (rabbit-b)       │              │ (rabbit-c)       │
│                  │              │                  │
│ - Precompute (4x)│              │ - Precompute (4x)│
│ - Asteroid (2x)  │              │ - Asteroid (2x)  │
│ - Comet (2x)     │              │ - Comet (2x)     │
└──────────────────┘              └──────────────────┘
```

## Worker Types

### Precompute Worker
- **Purpose:** Precompute for known locations
- **Trigger:** Coordinator creates tasks hourly
- **Queue:** `precompute.tasks`
- **Hosts:** Main server + B + C (total 12 workers)

### Asteroid Worker
- **Purpose:** On-demand computation on cache miss
- **Trigger:** API request without cache hit
- **Queue:** `asteroid.compute` (via Exchange `computation.direct`)
- **Hosts:** B + C (total 4 workers)

### Comet Worker
- **Purpose:** On-demand computation on cache miss
- **Trigger:** API request without cache hit
- **Queue:** `comet.compute` (via Exchange `computation.direct`)
- **Hosts:** B + C (total 4 Worker)

## Configuration

### .env files

Each host has its **own** `.env` file with generic variables:

**Important:** All hosts use the **same** passwords (for PostgreSQL/RabbitMQ access).

#### Main server (.env)
```bash
# Worker Setup
SETUP_WORKER_B=true
SETUP_WORKER_C=true

# Worker scaling (precompute only on main server)
PRECOMPUTE_WORKERS=4
ASTEROID_WORKERS=0  # Not used on main server
COMET_WORKERS=0     # Not used on main server
```

#### Worker host B (.env on $RABBITMQ_B)
```bash
# Worker scaling (configurable per host)
PRECOMPUTE_WORKERS=4
ASTEROID_WORKERS=2
COMET_WORKERS=2
```

#### Worker host C (.env on $RABBITMQ_C)
```bash
# Worker scaling (configurable per host)
PRECOMPUTE_WORKERS=4
ASTEROID_WORKERS=2
COMET_WORKERS=2
```

## Deployment

### Initial setup

```bash
# On main server
cd /media/docker/asciisky
cp .env.example .env
# Edit .env (passwords, etc.)

# Run setup (deploys to all hosts)
./scripts/setup-production.sh
```

The script:
1. Deploys main server (Web, RabbitMQ, PostgreSQL, precompute workers)
2. Copies `.env` to worker hosts B and C
3. Deploys workers on B and C

### Updates

```bash
# On main server
cd /media/docker/asciisky
git pull

# Update on all hosts
./scripts/update-production.sh
```

### Manual worker scaling

If you want to change the number of workers:

**On main server:**
```bash
# Edit .env
nano .env
# PRECOMPUTE_WORKERS=8  # Increase to 8

# Restart
docker compose -f docker-compose.production.yml up -d --scale precompute_worker=8
```

**On worker host B:**
```bash
ssh $RABBITMQ_B
cd ~/asciisky

# Edit .env
nano .env
# ASTEROID_WORKERS=4  # Increase to 4

# Restart
docker compose -f docker-compose.workers.yml up -d --scale asteroid_worker=4
```

## Monitoring

### RabbitMQ Management UI

```bash
# Create SSH tunnel
ssh -L 15672:localhost:15672 $RABBITMQ_MAIN

# Open browser
http://localhost:15672
# Login: admin / <RABBITMQ_PASSWORD>
```

**What to check:**
- **Connections:** Should show ~12 connections (all workers)
- **Queues:** `precompute.tasks`, `asteroid.compute`, `comet.compute`
- **Messages:** Pending/Processing messages

### Worker Logs

**Main server:**
```bash
docker compose -f docker-compose.production.yml logs -f precompute_worker
```

**Worker host B:**
```bash
ssh $RABBITMQ_B
cd ~/asciisky
docker compose -f docker-compose.workers.yml logs -f asteroid_worker
docker compose -f docker-compose.workers.yml logs -f comet_worker
docker compose -f docker-compose.workers.yml logs -f precompute_worker
```

**Worker host C:**
```bash
ssh $RABBITMQ_C
cd ~/asciisky
docker compose -f docker-compose.workers.yml logs -f asteroid_worker
docker compose -f docker-compose.workers.yml logs -f comet_worker
docker compose -f docker-compose.workers.yml logs -f precompute_worker
```

## Troubleshooting

### Workers do not receive tasks

**Symptom:** Logs show "Waiting for messages..." but no tasks are processed.

**Check:**
1. RabbitMQ Management UI → Connections (all workers connected?)
2. RabbitMQ Management UI → Queues (messages in queue?)
3. Exchange bindings correct? (`computation.direct` → `asteroid.compute`)

**Solution:**
```bash
# Worker neu starten
ssh $RABBITMQ_B
cd ~/asciisky
docker compose -f docker-compose.workers.yml restart
```

### Cache miss but no computation

**Symptom:** API logs show "Cache MISS" but workers are not triggered.

**Check:**
1. API logs: Do you see "Published asteroid task"?
2. RabbitMQ: Messages in `asteroid.compute` queue?
3. Worker logs: Do you see "Processing task"?

**Common causes:**
- Exchange/routing key misconfigured
- Worker not started
- RabbitMQ connection problem

### PostgreSQL connection error

**Symptom:** Workers cannot access PostgreSQL.

**Prüfen:**
```bash
# Von Worker-Host testen
ssh $RABBITMQ_B
telnet $RABBITMQ_MAIN 5432
```

**Solution:**
- Check firewall rules
- Check PostgreSQL `listen_addresses`
- Check PostgreSQL `pg_hba.conf`

## Performance tuning

### Optimize number of workers

**Rule of thumb:**
- **Precompute:** 1 worker per CPU core (I/O-bound)
- **Asteroid/Comet:** 2-4 workers per host (CPU-bound, Skyfield computations)

**Monitoring:**
```bash
# Check CPU utilization
htop

# Worker performance
docker stats
```

### RabbitMQ prefetch

Default: `prefetch_count=1` (one task per worker at a time)

Increase for faster tasks:
```python
# In worker.py
self.channel.basic_qos(prefetch_count=2)
```

## Security

### Firewall

Only worker IPs may access RabbitMQ/PostgreSQL:

```bash
# Auf Hauptserver
sudo ./scripts/setup-firewall.sh
```

### Passwords

Use strong passwords in `.env`:
```bash
# Generate
openssl rand -base64 32
```

## Backup

### PostgreSQL backup

```bash
# Auf Hauptserver
docker exec asciisky-postgres pg_dump -U asciisky asciisky > backup.sql
```

### RabbitMQ backup

```bash
# Export definitions
curl -u admin:password http://localhost:15672/api/definitions > rabbitmq-backup.json
```
