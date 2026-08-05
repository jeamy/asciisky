#!/bin/bash
# Update script for production deployment
# Updates code on all servers

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/docker-build.sh"

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

echo "🔨 Building multi-stage images..."
# Default production updates to no-cache unless overridden
BUILD_NO_CACHE="${BUILD_NO_CACHE:-1}"
asciisky_prepare_data_dirs .
asciisky_compose_build docker-compose.production.yml . || error_exit "Build failed"
asciisky_tag_aliases asciisky-web:latest
asciisky_verify_image asciisky-web:latest || warning "Image verify reported issues (continuing)"

echo "🚀 Restarting services with Hybrid Deduplication..."
docker compose -f docker-compose.production.yml up -d --scale precompute_worker=${PRECOMPUTE_WORKERS:-4} || error_exit "Restart failed"

# Verify Hybrid Deduplication is active
echo "🔍 Verifying Hybrid Deduplication components..."
echo "  Checking RabbitMQ Message Deduplication plugin..."
if docker exec asciisky-rabbitmq rabbitmq-plugins list | grep -q "rabbitmq_message_deduplication"; then
    success "RabbitMQ Message Deduplication plugin active"
else
    echo "🔧 Enabling RabbitMQ Message Deduplication plugin..."
    docker exec asciisky-rabbitmq rabbitmq-plugins enable rabbitmq_message_deduplication
    docker restart asciisky-rabbitmq
    sleep 5
    success "RabbitMQ Message Deduplication plugin enabled"
fi

echo "  Checking PostgreSQL Advisory Locks support..."
if docker exec asciisky-postgres psql -U asciisky -d asciisky -c "SELECT 1;" >/dev/null 2>&1; then
    success "PostgreSQL Advisory Locks available"
else
    error_exit "PostgreSQL not responding for Advisory Locks"
fi

echo "ℹ️  Note: Queues with deduplication are automatically managed by workers (RabbitMQ 4.x)"

success "Main server updated with Hybrid Deduplication"
echo ""

# ===== WORKER B =====
if [ "$UPDATE_WORKER_B" != "false" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📦 Updating $RABBITMQ_B"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    ssh "$RABBITMQ_B" "cd ~/asciisky && git pull" || error_exit "Git pull failed on worker B"
    scp -q "${SCRIPT_DIR}/lib/docker-build.sh" "$RABBITMQ_B:~/asciisky/scripts/lib/docker-build.sh" 2>/dev/null ||       ssh "$RABBITMQ_B" "mkdir -p ~/asciisky/scripts/lib"
    scp -q "${SCRIPT_DIR}/lib/docker-build.sh" "$RABBITMQ_B:~/asciisky/scripts/lib/docker-build.sh" || true
    ssh "$RABBITMQ_B" "cd ~/asciisky && source scripts/lib/docker-build.sh && asciisky_prepare_data_dirs . && BUILD_NO_CACHE=${BUILD_NO_CACHE:-1} asciisky_compose_build docker-compose.workers.yml . && asciisky_tag_aliases asciisky-web:latest && asciisky_verify_image asciisky-web:latest"         || error_exit "Build/verify failed on worker B"
    # worker_monitor is commented out in docker-compose.workers.yml — do not --scale it
    ssh "$RABBITMQ_B" "cd ~/asciisky && source .env && docker compose -f docker-compose.workers.yml up -d --scale unified_worker=\${UNIFIED_WORKERS:-\${PRECOMPUTE_WORKERS:-8}}"         || error_exit "Restart failed on worker B"
    
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
    scp -q "${SCRIPT_DIR}/lib/docker-build.sh" "$RABBITMQ_C:~/asciisky/scripts/lib/docker-build.sh" 2>/dev/null ||       ssh "$RABBITMQ_C" "mkdir -p ~/asciisky/scripts/lib"
    scp -q "${SCRIPT_DIR}/lib/docker-build.sh" "$RABBITMQ_C:~/asciisky/scripts/lib/docker-build.sh" || true
    ssh "$RABBITMQ_C" "cd ~/asciisky && source scripts/lib/docker-build.sh && asciisky_prepare_data_dirs . && BUILD_NO_CACHE=${BUILD_NO_CACHE:-1} asciisky_compose_build docker-compose.workers.yml . && asciisky_tag_aliases asciisky-web:latest && asciisky_verify_image asciisky-web:latest"         || error_exit "Build/verify failed on worker C"
    ssh "$RABBITMQ_C" "cd ~/asciisky && source .env && docker compose -f docker-compose.workers.yml up -d --scale unified_worker=\${UNIFIED_WORKERS:-\${PRECOMPUTE_WORKERS:-8}}"         || error_exit "Restart failed on worker C"
    
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
echo "   Precompute Queue:   Queues → precompute.tasks (with deduplication)"
echo "   Smart Interpolation: Enabled via ENABLE_SMART_INTERPOLATION=true"
echo "   Hybrid Deduplication: RabbitMQ + PostgreSQL Advisory Locks active"
echo ""
echo "📝 Useful commands:"
echo "   docker logs -f asciisky-precompute-coordinator  # Precompute coordinator"
echo "   docker compose -f docker-compose.production.yml logs -f precompute_worker  # Precompute worker (main)"
echo "   ssh $RABBITMQ_B 'cd ~/asciisky && docker compose -f docker-compose.workers.yml logs -f unified_worker'  # Unified workers"
echo "   # worker_monitor service is currently disabled in docker-compose.workers.yml"
echo "   ssh $RABBITMQ_C 'cd ~/asciisky && docker compose -f docker-compose.workers.yml logs -f unified_worker'  # Unified workers"
echo ""
echo "🔒 Hybrid Deduplication Commands:"
echo "   docker exec asciisky-rabbitmq rabbitmqctl list_queues  # Check queue depths"
echo "   docker exec asciisky-postgres psql -U asciisky -c \"SELECT * FROM pg_locks WHERE locktype = 'advisory';\"  # Check advisory locks"
echo "   docker exec asciisky-web python test_hybrid_deduplication.py  # Run deduplication tests"
echo "   curl -s \"http://$RABBITMQ_MAIN:8000/api/bright_asteroids?lat=46.7632&lon=14.8417&elevation=405\"  # Test API with deduplication"
echo ""
