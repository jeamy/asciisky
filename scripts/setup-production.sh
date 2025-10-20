#!/bin/bash
# Setup-Skript für Multi-Host Production Deployment
# ASCII Sky mit PostgreSQL und verteilten RabbitMQ-Workern

set -e

echo "🚀 ASCII Sky Multi-Host Production Setup"
echo "=========================================="
echo ""

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Funktion für Fehlerbehandlung
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

# Prüfe ob .env existiert
if [ ! -f .env ]; then
    error_exit ".env file not found! Please create it first."
fi

# Lade Environment Variables
source .env

# Prüfe erforderliche Variablen
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

# Funktion für Host-Setup
setup_host() {
    local HOST=$1
    local COMPOSE_FILE=$2
    local DESCRIPTION=$3
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🖥️  Setting up: $DESCRIPTION"
    echo "   Host: $HOST"
    echo "   Compose: $COMPOSE_FILE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    if [ "$HOST" == "localhost" ]; then
        # Lokales Setup
        echo "📦 Building Docker image..."
        docker compose -f "$COMPOSE_FILE" build || error_exit "Build failed on $HOST"
        
        echo "🚀 Starting services with worker scaling..."
        # Verwende Env-Variablen für Worker-Anzahl (Fallback auf Defaults in docker-compose.yml)
        docker compose -f "$COMPOSE_FILE" up -d || error_exit "Startup failed on $HOST"
        
        success "Services started on $HOST (Worker scaling via .env)"
    else
        # Remote Setup
        echo "📤 Setting up $HOST..."
        
        # Erstelle ~/docker Verzeichnis
        ssh "$HOST" "mkdir -p ~/docker" || error_exit "Failed to create ~/docker on $HOST"
        
        # Prüfe ob Repository bereits existiert
        if ssh "$HOST" "[ -d ~/docker/asciisky/.git ]"; then
            echo "📥 Repository exists, pulling latest changes..."
            ssh "$HOST" "cd ~/docker/asciisky && git pull" || error_exit "Git pull failed on $HOST"
        else
            echo "📥 Cloning repository from GitHub (HTTPS)..."
            ssh "$HOST" "cd ~/docker && git clone https://github.com/jeamy/asciisky.git" || error_exit "Git clone failed on $HOST"
        fi
        
        # Kopiere .env
        echo "📋 Copying .env..."
        scp .env "$HOST:~/docker/asciisky/.env" || error_exit "Failed to copy .env to $HOST"
        
        echo "🐳 Building and starting on remote host..."
        ssh "$HOST" "cd ~/docker/asciisky && docker compose -f $COMPOSE_FILE build" || error_exit "Build failed on $HOST"
        ssh "$HOST" "cd ~/docker/asciisky && docker compose -f $COMPOSE_FILE up -d" || error_exit "Startup failed on $HOST"
        
        success "Services started on $HOST (Worker scaling via .env)"
    fi
    
    echo ""
}

# ===== HAUPTSERVER: asciisky.eibrain.org =====
setup_host "localhost" "docker-compose.production.yml" "Main Server (Web + RabbitMQ + PostgreSQL)"

# Warte auf PostgreSQL
echo "⏳ Waiting for PostgreSQL to be ready..."
sleep 10

# Prüfe PostgreSQL
docker exec asciisky-postgres pg_isready -U asciisky -d asciisky || error_exit "PostgreSQL not ready"
success "PostgreSQL is ready"

# Warte auf RabbitMQ
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

# ===== WORKER SERVER B: rabbit-b.eibrain.org =====
if [ "$SETUP_WORKER_B" == "true" ]; then
    setup_host "rabbit-b.eibrain.org" "docker-compose.worker-b.yml" "Worker Server B (4 Workers)"
else
    warning "Skipping Worker Server B (SETUP_WORKER_B not set to 'true' in .env)"
fi

# ===== WORKER SERVER C: rabbit-c.eibrain.org =====
if [ "$SETUP_WORKER_C" == "true" ]; then
    setup_host "rabbit-c.eibrain.org" "docker-compose.worker-c.yml" "Worker Server C (4 Workers)"
else
    warning "Skipping Worker Server C (SETUP_WORKER_C not set to 'true' in .env)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Setup Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📍 Services:"
echo "   Web UI:         http://asciisky.eibrain.org (nginx → Port 8000)"
echo "   RabbitMQ UI:    ssh -L 15672:localhost:15672 asciisky.eibrain.org (SSH-Tunnel)"
echo "   PostgreSQL:     asciisky.eibrain.org:5432 (nur von Worker-Servern)"
echo ""
echo "👷 Workers (configured via .env):"
echo "   Main Server:          ${PRECOMPUTE_WORKERS:-4} precompute workers"
echo "   rabbit-b.eibrain.org: ${PRECOMPUTE_WORKERS_B:-4} precompute + ${ASTEROID_WORKERS_B:-2} asteroid + ${COMET_WORKERS_B:-2} comet workers"
echo "   rabbit-c.eibrain.org: ${PRECOMPUTE_WORKERS_C:-4} precompute + ${ASTEROID_WORKERS_C:-2} asteroid + ${COMET_WORKERS_C:-2} comet workers"
echo "   Edit .env to change worker counts (PRECOMPUTE_WORKERS, ASTEROID_WORKERS, COMET_WORKERS, etc.)"
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
echo "   1. Setup Firewall: sudo ./scripts/setup-firewall.sh (auf asciisky.eibrain.org)"
echo "   2. Check RabbitMQ UI: ssh -L 15672:localhost:15672 asciisky.eibrain.org → http://localhost:15672"
echo "   3. Trigger initial data update: docker exec asciisky-data-updater python nightly_data_updater.py"
echo "   4. Monitor precompute: docker logs -f asciisky-precompute-coordinator"
echo "   5. Monitor logs: docker compose -f docker-compose.production.yml logs -f"
echo ""
