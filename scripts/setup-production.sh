#!/bin/bash
# Setup script for multi-host production deployment
# ASCII Sky with PostgreSQL and distributed RabbitMQ workers

set -e

# Hostnames (can be provided via environment or .env); fall back to example.org
RABBITMQ_MAIN="${RABBITMQ_MAIN:-asciisky.example.org}"
RABBITMQ_B="${RABBITMQ_B:-rabbit-b.example.org}"
RABBITMQ_C="${RABBITMQ_C:-rabbit-c.example.org}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function for error handling
error_exit() {
    echo -e "${RED}❌ Error: $1${NC}" >&2
    exit 1
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Check if .env exists
if [ ! -f .env ]; then
    error_exit ".env file not found! Please create it first."
fi

# Load environment variables
source .env

# Check required variables
if [ -z "$POSTGRES_PASSWORD" ]; then
    error_exit "POSTGRES_PASSWORD not set in .env"
fi

if [ -z "$RABBITMQ_PASSWORD" ]; then
    error_exit "RABBITMQ_PASSWORD not set in .env"
fi

if [ -z "$SESSION_SECRET" ]; then
    warning "SESSION_SECRET not set in .env - using default (not recommended for production)"
fi

echo "📋 Configuration loaded from .env"
echo ""

# Host setup function
setup_host() {
    local HOST=$1
    local COMPOSE_FILE=$2
    local DESCRIPTION=$3
    local ENV_SUFFIX=$4  # Optional: "b" or "c" for worker-specific .env files
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🖥️  Setting up: $DESCRIPTION"
    echo "   Host: $HOST"
    echo "   Compose: $COMPOSE_FILE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    if [ "$HOST" == "localhost" ]; then
        # Local setup
        echo "📦 Building Docker image..."
        docker compose -f "$COMPOSE_FILE" build || error_exit "Build failed on $HOST"
        
        echo "🚀 Starting services with worker scaling..."
        # Use env variables for worker counts (fallback to defaults in docker-compose.yml)
        docker compose -f "$COMPOSE_FILE" up -d || error_exit "Startup failed on $HOST"
        
        success "Services started on $HOST (Worker scaling via .env)"
    else
        # Remote setup
        echo "📤 Setting up $HOST..."
        
        # Check if repository already exists
        if ssh "$HOST" "[ -d ~/asciisky/.git ]"; then
            echo "📥 Repository exists, pulling latest changes..."
            ssh "$HOST" "cd ~/asciisky && git pull" || error_exit "Git pull failed on $HOST"
        else
            echo "📥 Cloning repository from GitHub (HTTPS)..."
            ssh "$HOST" "cd ~ && git clone https://github.com/jeamy/asciisky.git" || error_exit "Git clone failed on $HOST"
        fi
        
        # Copy .env (with worker-specific fallback)
        if [ -n "$ENV_SUFFIX" ] && [ -f ".env.$ENV_SUFFIX" ]; then
            echo "📋 Copying worker-specific .env.$ENV_SUFFIX → .env..."
            scp ".env.$ENV_SUFFIX" "$HOST:~/asciisky/.env" || error_exit "Failed to copy .env.$ENV_SUFFIX to $HOST"
            success "Using .env.$ENV_SUFFIX for $HOST"
        else
            if [ -n "$ENV_SUFFIX" ]; then
                warning ".env.$ENV_SUFFIX not found, using default .env"
            fi
            echo "📋 Copying .env..."
            scp .env "$HOST:~/asciisky/.env" || error_exit "Failed to copy .env to $HOST"
        fi
        
        echo "🐳 Building and starting on remote host..."
        ssh "$HOST" "cd ~/asciisky && docker compose -f $COMPOSE_FILE build" || error_exit "Build failed on $HOST"
        
        # Worker scaling via --scale (from .env on remote host)
        if [[ "$COMPOSE_FILE" == "docker-compose.workers.yml" ]]; then
            ssh "$HOST" "cd ~/asciisky && docker compose -f $COMPOSE_FILE up -d --scale precompute_worker=\${PRECOMPUTE_WORKERS:-4} --scale asteroid_worker=\${ASTEROID_WORKERS:-2} --scale comet_worker=\${COMET_WORKERS:-2}" || error_exit "Startup failed on $HOST"
        else
            ssh "$HOST" "cd ~/asciisky && docker compose -f $COMPOSE_FILE up -d" || error_exit "Startup failed on $HOST"
        fi
        
        success "Services started on $HOST (Worker scaling via .env)"
    fi
    
    echo ""
}

# ===== MAIN SERVER =====
setup_host "localhost" "docker-compose.production.yml" "Main Server (Web + RabbitMQ + PostgreSQL)"

# Wait for PostgreSQL
echo "⏳ Waiting for PostgreSQL to be ready..."
sleep 10

# Check PostgreSQL
docker exec asciisky-postgres pg_isready -U asciisky -d asciisky || error_exit "PostgreSQL not ready"
success "PostgreSQL is ready"

# Wait for RabbitMQ
echo "⏳ Waiting for RabbitMQ to be ready..."
sleep 10

# Setup RabbitMQ Queues
echo "🐰 Setting up RabbitMQ queues..."
./scripts/setup-rabbitmq-queues.sh || error_exit "RabbitMQ queue setup failed"
success "RabbitMQ queues created"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Main Server Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker compose -f docker-compose.production.yml ps
echo ""

# ===== WORKER SERVER B =====
if [ "$SETUP_WORKER_B" == "true" ]; then
    setup_host "$RABBITMQ_B" "docker-compose.workers.yml" "Worker Server B" "b"
else
    warning "Skipping Worker Server B (SETUP_WORKER_B not set to 'true' in .env)"
fi

# ===== WORKER SERVER C =====
if [ "$SETUP_WORKER_C" == "true" ]; then
    setup_host "$RABBITMQ_C" "docker-compose.workers.yml" "Worker Server C" "c"
else
    warning "Skipping Worker Server C (SETUP_WORKER_C not set to 'true' in .env)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Setup Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📍 Services:"
echo "   Web UI:         http://$RABBITMQ_MAIN (nginx → Port 8000)"
echo "   RabbitMQ UI:    ssh -L 15672:localhost:15672 $RABBITMQ_MAIN (SSH tunnel)"
echo "   PostgreSQL:     $RABBITMQ_MAIN:5432 (restricted to worker servers)"
echo ""
echo "👷 Workers (configured via .env on each host):"
echo "   Main Server:          ${PRECOMPUTE_WORKERS:-4} precompute workers"
echo "   $RABBITMQ_B: PRECOMPUTE_WORKERS, ASTEROID_WORKERS, COMET_WORKERS (in .env)"
echo "   $RABBITMQ_C: PRECOMPUTE_WORKERS, ASTEROID_WORKERS, COMET_WORKERS (in .env)"
echo "   Edit .env on each host to change worker counts"
echo ""
echo "🔄 Precompute System:"
echo "   Coordinator: Creates tasks every hour"
echo "   Workers: Process tasks from RabbitMQ queue 'precompute.tasks'"
echo ""
echo "🔒 Firewall Setup:"
echo "   Run on main server: sudo ./scripts/setup-firewall.sh"
echo "   Restricts RabbitMQ/PostgreSQL to Worker-IPs only"
echo ""
echo "📝 Next steps:"
echo "   1. Setup Firewall: sudo ./scripts/setup-firewall.sh (on $RABBITMQ_MAIN)"
echo "   2. Check RabbitMQ UI: ssh -L 15672:localhost:15672 $RABBITMQ_MAIN → http://localhost:15672"
echo "   3. Trigger initial data update: docker exec asciisky-data-updater python nightly_data_updater.py"
echo "   4. Monitor precompute: docker logs -f asciisky-precompute-coordinator"
echo "   5. Monitor logs: docker compose -f docker-compose.production.yml logs -f"
echo ""
