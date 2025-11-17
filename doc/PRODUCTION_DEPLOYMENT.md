# ASCII Sky - Production Deployment Guide

## 🏗️ Multi-Host Architecture

### Server Overview

```
┌─────────────────────────────────────────────────────────────┐
│ $RABBITMQ_MAIN (Main server)                                  │
│ ┌─────────────┐  ┌──────────────┐  ┌──────────────┐        │
│ │   Web UI    │  │  RabbitMQ    │  │  PostgreSQL  │        │
│ │  (FastAPI)  │  │   (4.1)      │  │    (16)      │        │
│ │   Port 80   │  │   Port 5672  │  │   Port 5432  │        │
│ │  (nginx →   │  │   Port 15672 │  │              │        │
│ │   :8000)    │  │              │  │              │        │
│ └─────────────┘  └──────────────┘  └──────────────┘        │
│ ┌─────────────┐  ┌──────────────┐                          │
│ │Data Updater │  │  Precompute  │                          │
│ │  (Nightly)  │  │ Coordinator  │                          │
│ └─────────────┘  └──────────────┘                          │
│ ┌───────────────────────────────────────────────┐          │
│ │ Precompute Workers x4 (scalable via .env)     │          │
│ └───────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ AMQP + PostgreSQL (IP-restricted)
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
        ▼                                       ▼
┌──────────────────────┐            ┌──────────────────────┐
│ $RABBITMQ_B          │            │ $RABBITMQ_C          │
│ ┌──────────────────┐ │            │ ┌──────────────────┐ │
│ │Unified Workers   │ │            │ │Unified Workers   │ │
│ │(precompute +     │ │            │ │(precompute +     │ │
│ │asteroids +       │ │            │ │asteroids +       │ │
│ │comets, scalable) │ │            │ │comets, scalable) │ │
│ └──────────────────┘ │            │ └──────────────────┘ │
└──────────────────────┘            └──────────────────────┘
```

### Component distribution

| Server | Components | Ports | Purpose |
|--------|-------------|-------|-------|
| **$RABBITMQ_MAIN** | Web (nginx), RabbitMQ, PostgreSQL, Data Updater, Precompute Coordinator, 4 Precompute Workers | 80, 5672, 15672, 5432 | Main server with UI and databases |
| **$RABBITMQ_B** | Unified workers (handle precompute + asteroids + comets) + 1 Worker Monitor | - | Worker pool B (scalable via `UNIFIED_WORKERS` in .env.b) |
| **$RABBITMQ_C** | Unified workers (handle precompute + asteroids + comets) + 1 Worker Monitor | - | Worker pool C (scalable via `UNIFIED_WORKERS` in .env.c) |

**Total (default example):**
- Main server: 4 Precompute workers
- Worker B: 8 Unified workers + 1 monitor (see `.env.b.example`)
- Worker C: 4 Unified workers + 1 monitor (see `.env.c.example`)

**Worker scaling** via `.env`:
```bash
# Main server (docker-compose.production.yml)
PRECOMPUTE_WORKERS=4

# Worker Server B (see .env.b.example)
UNIFIED_WORKERS=8
WORKER_MONITOR=1

# Worker Server C (see .env.c.example)
UNIFIED_WORKERS=4
WORKER_MONITOR=1
```

---

## 📋 Prerequisites

### On all servers

- Docker Engine 24.0+
- Docker Compose v2.20+
- SSH access (for remote deployment)
- At least 2 GB RAM per server
- 10 GB free disk space

### Network requirements

**Firewall rules:**

```bash
# $RABBITMQ_MAIN (Main server)
Inbound: 80, 443 (Web UI - public)
Inbound: 5672 (RabbitMQ - ONLY from Worker-B/C IPs)
Inbound: 5432 (PostgreSQL - ONLY from Worker-B/C IPs)
Inbound: 15672 (RabbitMQ UI - ONLY localhost/SSH tunnel)
Outbound: 80, 443 (HTTP/HTTPS for data downloads)

# $RABBITMQ_B / $RABBITMQ_C (Worker servers)
Outbound: 5432 (PostgreSQL to main server)
Outbound: 5672 (RabbitMQ to main server)
```

**Automatic firewall setup:**
```bash
# Run only on $RABBITMQ_MAIN:
sudo ./scripts/setup-firewall.sh
```

The script:
- Automatically discovers IPs via DNS
- Restricts port 5672 (RabbitMQ) to worker IPs
- Restricts port 5432 (PostgreSQL) to worker IPs
- Restricts port 15672 (RabbitMQ UI) to localhost (SSH tunnel)
- Worker servers require NO firewall changes

---

## 🚀 Installation

### 1. Preparation

```bash
# On your local development machine
cd /path/to/asciisky

# Create .env from template
cp .env.example .env

# Edit .env and set strong passwords
nano .env
```

**⚠️ IMPORTANT: .env configuration**

The `.env` file is **automatically** copied to all servers!

**Worker-specific .env files (optional):**
- `.env.b` → Worker Server B (if exists, otherwise uses `.env`)
- `.env.c` → Worker Server C (if exists, otherwise uses `.env`)

This allows different worker counts per server while keeping passwords identical.

**Set strong passwords for:**
- `POSTGRES_PASSWORD` — **Must be identical on all servers!**
- `RABBITMQ_PASSWORD` — **Must be identical on all servers!**
- `SESSION_SECRET` — Main server only (generate with: `openssl rand -hex 32`)

**Why identical passwords?**
- Worker servers (rabbit-b/c) connect to PostgreSQL on the main server
- Worker servers (rabbit-b/c) connect to RabbitMQ on the main server
- Authentication only works with matching credentials

**Example .env:**
```bash
# Same passwords on ALL servers
POSTGRES_PASSWORD=SuperSicheres_PG_Passwort_123!
RABBITMQ_PASSWORD=SuperSicheres_RMQ_Passwort_456!
SESSION_SECRET=a1b2c3d4e5f6...  # openssl rand -hex 32

# Deployment options
SETUP_WORKER_B=true
SETUP_WORKER_C=true

# Worker scaling (main server)
PRECOMPUTE_WORKERS=4
ASTEROID_WORKERS=2
COMET_WORKERS=2

# Precompute settings
ASCII_SKY_PRECOMPUTE_HOURS=720  # precompute 30 days ahead
```

**Example .env.b (optional - for Worker Server B):**
```bash
# Same passwords as main .env!
POSTGRES_PASSWORD=SuperSicheres_PG_Passwort_123!
RABBITMQ_PASSWORD=SuperSicheres_RMQ_Passwort_456!

# Different worker counts for Server B
PRECOMPUTE_WORKERS=8
ASTEROID_WORKERS=4
COMET_WORKERS=4
```

**Example .env.c (optional - for Worker Server C):**
```bash
# Same passwords as main .env!
POSTGRES_PASSWORD=SuperSicheres_PG_Passwort_123!
RABBITMQ_PASSWORD=SuperSicheres_RMQ_Passwort_456!

# Different worker counts for Server C
PRECOMPUTE_WORKERS=2
ASTEROID_WORKERS=1
COMET_WORKERS=1
```

### 2. Set up SSH access

```bash
# Copy SSH keys to worker servers
ssh-copy-id $RABBITMQ_B
ssh-copy-id $RABBITMQ_C

# Test connection
ssh $RABBITMQ_B "echo 'Connection OK'"
ssh $RABBITMQ_C "echo 'Connection OK'"
```

### 3. Automatic deployment

```bash
# Make setup script executable
chmod +x scripts/setup-production.sh

# Start deployment
./scripts/setup-production.sh
```

The script:
1. ✅ Builds Docker images
2. ✅ Starts PostgreSQL and RabbitMQ on $RABBITMQ_MAIN
3. ✅ Initializes PostgreSQL schema
4. ✅ Creates RabbitMQ queues
5. ✅ Starts precompute coordinator and workers
6. ✅ **Copies .env.b (or .env) to $RABBITMQ_B** (automatically via scp)
7. ✅ Deploys workers on $RABBITMQ_B
8. ✅ **Copies .env.c (or .env) to $RABBITMQ_C** (automatically via scp)
9. ✅ Deploys workers on $RABBITMQ_C

**Important:** 
- The `.env` file is automatically copied from your local machine to all servers
- If `.env.b` or `.env.c` exist, they are used for the respective worker servers
- You do **not** need to copy .env files manually to each server!

**After deployment:**
```bash
# Configure firewall on main server
ssh $RABBITMQ_MAIN
sudo ./scripts/setup-firewall.sh
```

---

## 🔧 Manual installation

### On $RABBITMQ_MAIN

```bash
# 1. Clone repository
git clone <repo-url> ~/asciisky
cd ~/asciisky

# 2. Create .env
cp .env.example .env
nano .env

# 3. Start services
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d

# 4. Set up RabbitMQ queues
./scripts/setup-rabbitmq-queues.sh

# 5. Load initial data
docker exec asciisky-data-updater python nightly_data_updater.py
```

### On $RABBITMQ_B

```bash
# 1. Clone repository
git clone <repo-url> ~/asciisky
cd ~/asciisky

# 2. Copy .env from main server
scp $RABBITMQ_MAIN:~/asciisky/.env .env

# 3. Start workers
docker compose -f docker-compose.worker-b.yml build
docker compose -f docker-compose.worker-b.yml up -d
```

### On $RABBITMQ_C

```bash
# 1. Clone repository
git clone <repo-url> ~/asciisky
cd ~/asciisky

# 2. Copy .env from main server
scp $RABBITMQ_MAIN:~/asciisky/.env .env

# 3. Start workers
docker compose -f docker-compose.worker-c.yml build
docker compose -f docker-compose.worker-c.yml up -d
```

---

## 🔍 Monitoring

### Check service status

```bash
# On $RABBITMQ_MAIN
docker compose -f docker-compose.production.yml ps
docker compose -f docker-compose.production.yml logs -f web

# On $RABBITMQ_B
ssh $RABBITMQ_B "cd ~/asciisky && docker compose -f docker-compose.worker-b.yml ps"

# On $RABBITMQ_C
ssh $RABBITMQ_C "cd ~/asciisky && docker compose -f docker-compose.worker-c.yml ps"
```

### RabbitMQ Management UI

**Access via SSH tunnel:**
```bash
# From your local machine:
ssh -L 15672:localhost:15672 $RABBITMQ_MAIN

# Then open in the browser:
http://localhost:15672

User: admin
Password: <RABBITMQ_PASSWORD from .env>
```

**Check:**
- ✅ 20 workers connected (12 Precompute + 4 Asteroid + 4 Comet)
- ✅ Queues: `precompute.tasks`, `asteroid.compute`, `comet.compute`
- ✅ Messages are being processed
- ✅ Precompute coordinator running

### PostgreSQL status

```bash
# Test connection
docker exec asciisky-postgres psql -U asciisky -d asciisky -c "SELECT version();"

# Database statistics
docker exec asciisky-postgres psql -U asciisky -d asciisky -c "
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"

# Cache statistics
docker exec asciisky-postgres psql -U asciisky -d asciisky -c "SELECT * FROM cache_statistics;"
```

### API smoke test (/api/celestial)

Use `/api/celestial` as the canonical endpoint for Sun, Moon, and planets.

```bash
# From $RABBITMQ_MAIN (or via SSH)
curl "http://localhost:8000/api/celestial?lat=48.2&lon=16.3&elevation=180&time=2025-01-15T21:30:00Z" \
  | jq '.bodies.sun'
```

If this returns a JSON object with sensible values for altitude, azimuth, distance,
and magnitude, the celestial pipeline (including the former “planets” functionality)
is working correctly.

---

## 🔄 Updates

### Code update on all servers

```bash
# On your development machine
cd /path/to/asciisky

# Create update script
cat > scripts/update-production.sh << 'EOF'
#!/bin/bash
set -e

echo "🔄 Updating ASCII Sky on all servers..."

# Hauptserver
echo "📦 Updating $RABBITMQ_MAIN..."
git pull
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d

# Worker B
echo "📦 Updating $RABBITMQ_B..."
ssh $RABBITMQ_B "cd ~/asciisky && git pull && docker compose -f docker-compose.worker-b.yml build && docker compose -f docker-compose.worker-b.yml up -d"

# Worker C
echo "📦 Updating $RABBITMQ_C..."
ssh $RABBITMQ_C "cd ~/asciisky && git pull && docker compose -f docker-compose.worker-c.yml build && docker compose -f docker-compose.worker-c.yml up -d"

echo "✅ Update complete!"
EOF

chmod +x scripts/update-production.sh
./scripts/update-production.sh
```

---

## 🛠️ Maintenance

### Clear cache

```bash
# Clear old cached positions (example: older than 60 days, see init-postgres.sql)
docker exec asciisky-postgres psql -U asciisky -d asciisky -c "SELECT cleanup_old_positions();"
```

### Rotate logs

```bash
# Limit Docker logs (in docker-compose*.yml)
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

### Backup

```bash
# PostgreSQL backup
docker exec asciisky-postgres pg_dump -U asciisky asciisky > backup_$(date +%Y%m%d).sql

# Restore
cat backup_20250119.sql | docker exec -i asciisky-postgres psql -U asciisky asciisky
```

---

## 🚨 Troubleshooting

### Workers do not connect

```bash
# Check network connectivity
ssh $RABBITMQ_B "telnet $RABBITMQ_MAIN 5672"

# Check RabbitMQ logs
docker logs asciisky-rabbitmq

# Check worker logs
ssh $RABBITMQ_B "docker logs asciisky-asteroid-worker-1"
```

### PostgreSQL connection error

```bash
# Check PostgreSQL is running
docker exec asciisky-postgres pg_isready -U asciisky

# Check firewall
sudo ufw status

# Check PostgreSQL config
docker exec asciisky-postgres cat /var/lib/postgresql/data/pg_hba.conf
```

### Performance issues

```bash
# PostgreSQL Connections
docker exec asciisky-postgres psql -U asciisky -d asciisky -c "
SELECT count(*) FROM pg_stat_activity WHERE state = 'active';
"

# RabbitMQ queue length
docker exec asciisky-rabbitmq rabbitmqctl list_queues name messages consumers
```

---

## 📊 Performance expectations

| Metric | Value |
|--------|------|
| Worker throughput | ~50-100 computations/minute |
| API response time | < 200ms (cached) |
| Cache hit rate | > 90% |
| PostgreSQL connections | < 20 concurrent |
| RabbitMQ messages/sec | ~10-20 |

---

## 🔐 Security

### Recommended measures

1. **Configure firewall (IMPORTANT!)**
   ```bash
   # On $RABBITMQ_MAIN:
   sudo ./scripts/setup-firewall.sh
   ```
   
   The script:
   - ✅ Restricts port 5672 (RabbitMQ) to Worker-B/C IPs
   - ✅ Restricts port 5432 (PostgreSQL) to Worker-B/C IPs
   - ✅ Restricts port 15672 (RabbitMQ UI) to localhost
   - ✅ Automatically discovers IPs via DNS
   - ✅ Worker servers require NO changes

2. **RabbitMQ UI access**
   - ✅ Only via SSH tunnel: `ssh -L 15672:localhost:15672 $RABBITMQ_MAIN`
   - ✅ Not publicly reachable

3. **PostgreSQL access**
   - ✅ Only allowed from worker IPs (via firewall)
   - ✅ Strong password in `.env`

4. **Web UI**
   - ✅ Runs via nginx (port 80/443)
   - ✅ Port 8000 not publicly exposed (internal)

5. **Regular updates**
   ```bash
   docker compose pull
   docker compose up -d
   ```

---

## 📞 Support

If you have issues:
1. Check logs: `docker compose logs -f`
2. Check RabbitMQ UI: http://$RABBITMQ_MAIN:15672
3. Check PostgreSQL: `docker exec asciisky-postgres psql -U asciisky`
