#!/bin/bash
# Update script for production deployment
# Updates code on all servers

set -e

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found! Please create it first."
    exit 1
fi

# Load environment variables
source .env

RABBITMQ_MAIN="${RABBITMQ_MAIN:-asciisky.example.org}"
RABBITMQ_B="${RABBITMQ_B:-rabbit-b.example.org}"
RABBITMQ_C="${RABBITMQ_C:-rabbit-c.example.org}"

echo "🔄 ASCII Sky Production Update"
echo "==============================="
echo ""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

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

# Check git status
if [ -n "$(git status --porcelain)" ]; then
    warning "Uncommitted changes detected. Commit or stash them first."
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# ===== MAIN SERVER =====
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 Updating $RABBITMQ_MAIN"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

git pull || error_exit "Git pull failed"

echo "🔨 Building new images..."
docker compose -f docker-compose.production.yml build || error_exit "Build failed"

echo "🚀 Restarting services with unified worker scaling..."
docker compose -f docker-compose.production.yml up -d --scale precompute_worker=${PRECOMPUTE_WORKERS:-4} || error_exit "Restart failed"

# Verify RabbitMQ exchange exists after update
echo "🔍 Verifying RabbitMQ exchange..."
if docker exec asciisky-rabbitmq rabbitmqctl list_exchanges 2>/dev/null | grep -q "computation.direct"; then
    echo "✅ RabbitMQ exchange verified"
else
    warning "computation.direct exchange not found - creating..."
    docker exec asciisky-rabbitmq rabbitmqctl eval "
    rabbit_exchange:declare(
        {resource, <<\"/\">>, exchange, <<\"computation.direct\">>},
        direct,
        true,
        false,
        false,
        []
    ).
    " > /dev/null 2>&1 || warning "Could not create exchange"
fi

success "Main server updated"
echo ""

# ===== WORKER B =====
if [ "$UPDATE_WORKER_B" != "false" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📦 Updating $RABBITMQ_B"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    ssh "$RABBITMQ_B" "cd ~/asciisky && git pull" || error_exit "Git pull failed on worker B"
    ssh "$RABBITMQ_B" "cd ~/asciisky && docker compose -f docker-compose.workers.yml build" || error_exit "Build failed on worker B"
    ssh "$RABBITMQ_B" "cd ~/asciisky && source .env && docker compose -f docker-compose.workers.yml up -d --scale unified_worker=$((\${PRECOMPUTE_WORKERS:-4} + \${ASTEROID_WORKERS:-2} + \${COMET_WORKERS:-2})) --scale worker_monitor=\${WORKER_MONITOR:-1}" || error_exit "Restart failed on worker B"
    
    success "Worker B updated"
    echo ""
else
    warning "Skipping Worker B (UPDATE_WORKER_B=false)"
fi

# ===== WORKER C =====
if [ "$UPDATE_WORKER_C" != "false" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📦 Updating $RABBITMQ_C"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    ssh "$RABBITMQ_C" "cd ~/asciisky && git pull" || error_exit "Git pull failed on worker C"
    ssh "$RABBITMQ_C" "cd ~/asciisky && docker compose -f docker-compose.workers.yml build" || error_exit "Build failed on worker C"
    ssh "$RABBITMQ_C" "cd ~/asciisky && source .env && docker compose -f docker-compose.workers.yml up -d --scale unified_worker=$((\${PRECOMPUTE_WORKERS:-4} + \${ASTEROID_WORKERS:-2} + \${COMET_WORKERS:-2})) --scale worker_monitor=\${WORKER_MONITOR:-1}" || error_exit "Restart failed on worker C"
    
    success "Worker C updated"
    echo ""
else
    warning "Skipping Worker C (UPDATE_WORKER_C=false)"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Update Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Service Status:"
docker compose -f docker-compose.production.yml ps
echo ""
echo "🔍 Monitoring:"
echo "   RabbitMQ UI:        http://$RABBITMQ_MAIN:15672"
echo "   Worker Monitor:     http://$RABBITMQ_B:8080 (Unified Worker Dashboard)"
echo "   Worker Connections: Should see unified workers + 3 precompute (main)"
echo "   Precompute Queue:   Queues → precompute.tasks"
echo "   Smart Interpolation: Enabled via ENABLE_SMART_INTERPOLATION=true"
echo ""
echo "📝 Useful commands:"
echo "   docker logs -f asciisky-precompute-coordinator  # Precompute coordinator"
echo "   docker compose -f docker-compose.production.yml logs -f precompute_worker  # Precompute worker (main)"
echo "   ssh $RABBITMQ_B 'cd ~/asciisky && docker compose -f docker-compose.workers.yml logs -f unified_worker'  # Unified workers"
echo "   ssh $RABBITMQ_B 'cd ~/asciisky && docker compose -f docker-compose.workers.yml logs -f worker_monitor'  # Worker monitor dashboard"
echo "   ssh $RABBITMQ_C 'cd ~/asciisky && docker compose -f docker-compose.workers.yml logs -f unified_worker'  # Unified workers"
echo ""
