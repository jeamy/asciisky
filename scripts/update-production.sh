#!/bin/bash
# Update-Skript für Production Deployment
# Aktualisiert Code auf allen Servern

set -e

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

# Prüfe Git Status
if [ -n "$(git status --porcelain)" ]; then
    warning "Uncommitted changes detected. Commit or stash them first."
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# ===== HAUPTSERVER =====
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 Updating asciisky.eibrain.org"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

git pull || error_exit "Git pull failed"

echo "🔨 Building new images..."
docker compose -f docker-compose.production.yml build || error_exit "Build failed"

echo "🚀 Restarting services..."
docker compose -f docker-compose.production.yml up -d || error_exit "Restart failed"

success "Main server updated"
echo ""

# ===== WORKER B =====
if [ "$UPDATE_WORKER_B" != "false" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📦 Updating rabbit-b.eibrain.org"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    ssh rabbit-b.eibrain.org "cd ~/asciisky && git pull" || error_exit "Git pull failed on rabbit-b"
    ssh rabbit-b.eibrain.org "cd ~/asciisky && docker compose -f docker-compose.workers.yml build" || error_exit "Build failed on rabbit-b"
    ssh rabbit-b.eibrain.org "cd ~/asciisky && docker compose -f docker-compose.workers.yml up -d --scale precompute_worker=\${PRECOMPUTE_WORKERS:-4} --scale asteroid_worker=\${ASTEROID_WORKERS:-2} --scale comet_worker=\${COMET_WORKERS:-2}" || error_exit "Restart failed on rabbit-b"
    
    success "Worker B updated"
    echo ""
else
    warning "Skipping Worker B (UPDATE_WORKER_B=false)"
fi

# ===== WORKER C =====
if [ "$UPDATE_WORKER_C" != "false" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📦 Updating rabbit-c.eibrain.org"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    ssh rabbit-c.eibrain.org "cd ~/asciisky && git pull" || error_exit "Git pull failed on rabbit-c"
    ssh rabbit-c.eibrain.org "cd ~/asciisky && docker compose -f docker-compose.workers.yml build" || error_exit "Build failed on rabbit-c"
    ssh rabbit-c.eibrain.org "cd ~/asciisky && docker compose -f docker-compose.workers.yml up -d --scale precompute_worker=\${PRECOMPUTE_WORKERS:-4} --scale asteroid_worker=\${ASTEROID_WORKERS:-2} --scale comet_worker=\${COMET_WORKERS:-2}" || error_exit "Restart failed on rabbit-c"
    
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
echo "   RabbitMQ UI:        http://asciisky.eibrain.org:15672"
echo "   Worker Connections: Should see 11 connections (8 compute + 3 precompute)"
echo "   Precompute Queue:   Queues → precompute.tasks"
echo ""
echo "📝 Useful commands:"
echo "   docker logs -f asciisky-precompute-coordinator  # Precompute coordinator"
echo "   docker compose -f docker-compose.production.yml logs -f precompute_worker  # Precompute worker (main)"
echo "   ssh rabbit-b.eibrain.org 'cd ~/asciisky && docker compose -f docker-compose.workers.yml logs -f precompute_worker'"
echo "   ssh rabbit-c.eibrain.org 'cd ~/asciisky && docker compose -f docker-compose.workers.yml logs -f precompute_worker'"
echo ""
