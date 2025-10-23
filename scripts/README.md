# ASCII Sky - Setup Scripts


## 📋 Overview

Automated setup and deployment scripts for ASCII Sky.

---

## 🚀 Development (Local)

### setup-dev.sh

**Purpose:** Set up a local development environment

**What it does:**
- ✅ Creates `.env` if missing
- ✅ Builds Docker images
- ✅ Starts all services (Web, RabbitMQ, PostgreSQL, Workers)
- ✅ Sets up RabbitMQ queues
- ✅ Waits for database initialization
- ✅ Optionally loads initial data (via data_updater)

**Usage:**
```bash
./scripts/setup-dev.sh
```

**Requirements:**
- Docker & Docker Compose v2
- No additional dependencies

**Services after setup:**
- Web UI: http://localhost:8000
- RabbitMQ UI: http://localhost:15672 (admin/password)
- PostgreSQL: localhost:5432

**Workers:**
- 4 Precompute Workers (scalable via `PRECOMPUTE_WORKERS` in .env)
- 2 Asteroid Workers (scalable via `ASTEROID_WORKERS` in .env)
- 2 Comet Workers (scalable via `COMET_WORKERS` in .env)

---

## 🏭 Production (Multi-Host)

### setup-production.sh

**Purpose:** Production deployment across 3 servers

**What it does:**
- ✅ Deploys to $RABBITMQ_MAIN (Main server: Web, PostgreSQL, RabbitMQ, 4 Precompute Workers)
- ✅ Clones repository via HTTPS on worker servers (if not present)
- ✅ Deploys to $RABBITMQ_B (Worker B: 4 Precompute + 2 Asteroid + 2 Comet Workers)
- ✅ Deploys to $RABBITMQ_C (Worker C: 4 Precompute + 2 Asteroid + 2 Comet Workers)
- ✅ Initializes PostgreSQL (automatically via init-postgres.sql)
- ✅ Sets up RabbitMQ queues (automatically)
- ✅ Copies `.env` to all servers automatically
- ✅ Scales workers via `--scale` parameter

**Usage:**
```bash
# 1. Create and edit .env (LOCALLY on your machine)
cp .env.example .env
nano .env

# IMPORTANT: Use STRONG passwords!
# These passwords will be copied to ALL servers

# 2. Copy SSH keys to worker servers
ssh-copy-id $RABBITMQ_B
ssh-copy-id $RABBITMQ_C

# 3. Setup ausführen (kopiert .env automatisch auf alle Server)
./scripts/setup-production.sh
```

**Requirements:**
- SSH access to all 3 servers
- Docker installed on all servers
- `.env` configured locally with secure passwords

**Environment Variables (.env):**
```bash
# IMPORTANT: Same passwords on ALL servers!
POSTGRES_PASSWORD=...      # Must be identical (workers connect to main server)
RABBITMQ_PASSWORD=...      # Must be identical (workers connect to main server)
SESSION_SECRET=...         # Only for main server (Web UI)

# Deployment options
SETUP_WORKER_B=true        # Deploy Worker B?
SETUP_WORKER_C=true        # Deploy Worker C?

# Worker scaling (main server)
PRECOMPUTE_WORKERS=4
ASTEROID_WORKERS=2
COMET_WORKERS=2

# Worker scaling (Worker Server B)
PRECOMPUTE_WORKERS_B=4
ASTEROID_WORKERS_B=2
COMET_WORKERS_B=2

# Worker scaling (Worker Server C)
PRECOMPUTE_WORKERS_C=4
ASTEROID_WORKERS_C=2
COMET_WORKERS_C=2

# Precompute settings
ASCII_SKY_PRECOMPUTE_HOURS=720  # precompute 30 days ahead
```

**What happens during setup?**
- ✅ You create `.env` locally (on your development machine)
- ✅ Worker servers: `git clone https://github.com/jeamy/asciisky.git` into `~/asciisky`
- ✅ `setup-production.sh` copies `.env` to all servers automatically
- ✅ All servers use the same passwords (required for connections)

---

### update-production.sh

**Purpose:** Update code across all servers

**What it does:**
- ✅ Git pull on all servers
- ✅ Rebuild Docker images
- ✅ Rolling restart (no downtime)

**Usage:**
```bash
./scripts/update-production.sh
```

**Environment Variables (.env):**
```bash
UPDATE_WORKER_B=true  # Optional: Worker B updaten
UPDATE_WORKER_C=true  # Optional: Worker C updaten
```

---

## 🔧 Utility Scripts

### setup-rabbitmq-queues.sh

**Purpose:** Create RabbitMQ queues

**What it does:**
- ✅ Creates exchange `computation.direct`
- ✅ Creates queue `asteroid.compute` (Quorum)
- ✅ Creates queue `comet.compute` (Quorum)
- ✅ Creates queue `precompute.tasks` (Classic, Priority)
- ✅ Creates result/status queues

**Usage:**
```bash
# Automatic (called by setup-*.sh)
./scripts/setup-rabbitmq-queues.sh

# Manual with custom container
RABBITMQ_CONTAINER=my-rabbitmq ./scripts/setup-rabbitmq-queues.sh
```

**Environment Variables:**
```bash
RABBITMQ_CONTAINER=asciisky-rabbitmq  # Container-Name
RABBITMQ_USER=admin                   # RabbitMQ User
RABBITMQ_PASSWORD=...                 # RabbitMQ Passwort
```

---

### setup-firewall.sh

**Purpose:** Configure UFW firewall on main server

**What it does:**
- ✅ Resolves worker IPs via DNS automatically
- ✅ Restricts port 5672 (RabbitMQ) to Worker B/C IPs
- ✅ Restricts port 5432 (PostgreSQL) to Worker B/C IPs
- ✅ Restricts port 15672 (RabbitMQ UI) to localhost (SSH-tunnel)
- ✅ Worker servers require NO firewall changes

**Usage:**
```bash
# Run only on the main server (example: $RABBITMQ_MAIN):
sudo ./scripts/setup-firewall.sh
```

**Ports (Main server):**
- 80/443: Web UI (nginx) - public
- 8000: FastAPI - internal (nginx)
- 5672: RabbitMQ - ONLY Worker B/C IPs
- 5432: PostgreSQL - ONLY Worker B/C IPs
- 15672: RabbitMQ UI - ONLY localhost (SSH tunnel)

**Worker servers:**
- No firewall changes required
- Outgoing connections are allowed by default

---

### init-postgres.sql

**Purpose:** Initialize PostgreSQL schema

**What it does:**
- ✅ Creates tables (asteroid_dataframes, comet_dataframes, cached_positions, data_updates)
- ✅ Creates indexes for fast lookups
- ✅ Creates views (cache_statistics)
- ✅ Creates functions (cleanup_expired_positions)

**Usage:**
```bash
# Automatic (on first PostgreSQL start via docker-entrypoint-initdb.d)

# Manual:
docker exec -i asciisky-postgres psql -U asciisky -d asciisky < scripts/init-postgres.sql
```

---

## 📊 Workflow Overview

### Development Workflow

```
1. ./scripts/setup-dev.sh
   ↓
2. Change code (auto-reload)
   ↓
3. Test at http://localhost:8000
   ↓
4. Git commit & push
```

### Production Deployment Workflow

```
1. Initial setup:
   ./scripts/setup-production.sh
   
2. Code updates:
   git push
   ./scripts/update-production.sh
   
3. Firewall (run once on main server):
   ssh $RABBITMQ_MAIN
   sudo ./scripts/setup-firewall.sh
```

---

## 🔍 Troubleshooting

### Issue: setup-dev.sh fails

**Solution:**
```bash
# Is Docker running?
docker info

# Stop old containers
docker compose down -v

# Restart
./scripts/setup-dev.sh
```

### Issue: setup-production.sh - SSH errors

**Solution:**
```bash
# Copy SSH keys
ssh-copy-id $RABBITMQ_B
ssh-copy-id $RABBITMQ_C

# Test connection
ssh $RABBITMQ_B "echo OK"
```

### Issue: RabbitMQ queues not created

**Solution:**
```bash
# Create manually
export RABBITMQ_CONTAINER=asciisky-rabbitmq
./scripts/setup-rabbitmq-queues.sh

# Verify
docker exec asciisky-rabbitmq rabbitmqctl list_queues
```

---

## 📝 Checklist

### Before first production deployment

- [ ] `.env` created locally and secure passwords set
- [ ] Same passwords in .env (POSTGRES_PASSWORD, RABBITMQ_PASSWORD)
- [ ] Worker scaling configured in .env (PRECOMPUTE_WORKERS, etc.)
- [ ] SSH keys copied to all servers (`ssh-copy-id`)
- [ ] Docker installed on all servers
- [ ] DNS/hostnames configured ($RABBITMQ_MAIN, $RABBITMQ_B/$RABBITMQ_C)
- [ ] nginx configured on main server (Port 80/443 → 8000)

### After production deployment

- [ ] Firewall configured: `sudo ./scripts/setup-firewall.sh` (on main server)
- [ ] RabbitMQ UI via SSH tunnel: `ssh -L 15672:localhost:15672 $RABBITMQ_MAIN`
- [ ] Web UI reachable: http://$RABBITMQ_MAIN (nginx)
- [ ] 20 worker connections in RabbitMQ (12 Precompute + 4 Asteroid + 4 Comet)
- [ ] Queues created: `precompute.tasks`, `asteroid.compute`, `comet.compute`
- [ ] PostgreSQL reachable from worker servers: `telnet $RABBITMQ_MAIN 5432`
- [ ] Check logs: `docker compose -f docker-compose.production.yml logs -f`

---

---

## ❓ FAQ

### How many workers are deployed?

**Default (12 Precompute + 4 Asteroid + 4 Comet = 20 workers):**
- Main server: 4 Precompute Workers
- Worker B: 4 Precompute + 2 Asteroid + 2 Comet Workers
- Worker C: 4 Precompute + 2 Asteroid + 2 Comet Workers

**Scaling via .env:**
```bash
PRECOMPUTE_WORKERS=8        # Main server: 8 instead of 4
PRECOMPUTE_WORKERS_B=8      # Worker B: 8 instead of 4
PRECOMPUTE_WORKERS_C=8      # Worker C: 8 instead of 4
# = 24 Precompute workers total
```

### Does .env need to exist on all servers?

**Yes!** But you do not need to copy it manually.

**Automatic (recommended):**
```bash
# .env is copied automatically
./scripts/setup-production.sh
```

**Manual (if needed):**
```bash
scp .env $RABBITMQ_MAIN:~/asciisky/.env
scp .env $RABBITMQ_B:~/asciisky/.env
scp .env $RABBITMQ_C:~/asciisky/.env
```

### Must the passwords be identical on all servers?

**Yes!** Worker servers connect to PostgreSQL/RabbitMQ on the main server.

```bash
# .env on ALL servers:
POSTGRES_PASSWORD=SamePassword123!
RABBITMQ_PASSWORD=SamePassword456!
```

### How do I access the RabbitMQ UI?

**Via SSH tunnel (secure):**
```bash
# From your local machine:
ssh -L 15672:localhost:15672 $RABBITMQ_MAIN

# Then open in the browser:
http://localhost:15672

User: admin
Password: <RABBITMQ_PASSWORD aus .env>
```

**Why not directly?**
- Port 15672 is restricted to localhost (firewall)
- Safer: No public access
- SSH tunnel encrypts the connection

### Is the repository public or private?

**Public repository** - No SSH keys required!

The repository is cloned via HTTPS:
```bash
git clone https://github.com/jeamy/asciisky.git
```

Worker servers do **not** need GitHub SSH keys, since the repository is public.

### How do I scale workers manually?

**On worker servers:**
```bash
# Worker-Server B
ssh $RABBITMQ_B
cd ~/asciisky
docker compose -f docker-compose.worker-b.yml up -d \
  --scale precompute_worker=8 \
  --scale asteroid_worker=4 \
  --scale comet_worker=4

# Worker-Server C
ssh $RABBITMQ_C
cd ~/asciisky
docker compose -f docker-compose.worker-c.yml up -d \
  --scale precompute_worker=8 \
  --scale asteroid_worker=4 \
  --scale comet_worker=4
```

**Important:** The `--scale` parameters override `.env` values!

### Can I use different `.env` files per server?

**Yes**, but the **passwords must be identical**:

```bash
# .env.main ($RABBITMQ_MAIN)
POSTGRES_PASSWORD=SamePassword123!
RABBITMQ_PASSWORD=SamePassword456!
SESSION_SECRET=abc123...
SETUP_WORKER_B=true

# .env.worker-b ($RABBITMQ_B)
POSTGRES_PASSWORD=SamePassword123!  # ← SAME!
RABBITMQ_PASSWORD=SamePassword456!  # ← SAME!
# SESSION_SECRET not needed (no Web UI)
```

### What happens if passwords are different?

**Workers cannot connect:**
```
Error: FATAL: password authentication failed for user "asciisky"
Error: Access refused for user 'admin'
```

**Solution:** Set identical passwords in all `.env` files.

---

## 🔗 Further documentation

- [Production Deployment Guide](../doc/PRODUCTION_DEPLOYMENT.md)
- [Firewall Setup](../doc/FIREWALL_SETUP.md)
- [Precompute RabbitMQ](../doc/PRECOMPUTE_RABBITMQ.md)
