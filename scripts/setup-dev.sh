#!/bin/bash
# Setup script for local development
# ASCII Sky with Docker Compose (local)

set -e

echo "🚀 ASCII Sky Development Setup"
echo "================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    error_exit "Docker is not running. Please start Docker first."
fi

# Check if docker compose is available
if ! docker compose version > /dev/null 2>&1; then
    error_exit "docker compose not found. Please install Docker Compose v2."
fi

echo "📋 Environment Setup"
echo "===================="
echo ""

# Create .env if not present
if [ ! -f .env ]; then
    info "Creating .env file from .env.example..."
    if [ -f .env.example ]; then
        cp .env.example .env
        success ".env created from .env.example"
        warning "Please edit .env and set your passwords!"
        echo ""
        read -p "Press Enter to continue after editing .env, or Ctrl+C to abort..."
    else
        warning ".env.example not found, creating minimal .env..."
        cat > .env << 'EOF'
# ASCII Sky Development Environment

# PostgreSQL
POSTGRES_PASSWORD=dev_password_change_me
POSTGRES_USER=asciisky
POSTGRES_DB=asciisky

# RabbitMQ
RABBITMQ_USER=admin
RABBITMQ_PASSWORD=dev_password_change_me

# Session Secret (generate with: openssl rand -hex 32)
SESSION_SECRET=dev_secret_change_me_in_production

# Worker Setup (optional for dev)
SETUP_WORKER_B=false
SETUP_WORKER_C=false
UPDATE_WORKER_B=false
UPDATE_WORKER_C=false

# Precompute Settings
ASCII_SKY_PRECOMPUTE_HOURS=168
PRECOMPUTE_COORDINATOR_INTERVAL=3600
EOF
        success "Minimal .env created"
        warning "Please edit .env and set secure passwords!"
        echo ""
        read -p "Press Enter to continue after editing .env, or Ctrl+C to abort..."
    fi
else
    success ".env already exists"
fi

# Load environment variables
source .env

echo ""
echo "🐳 Docker Setup"
echo "==============="
echo ""

# Stop old containers (if any)
info "Stopping old containers (if any)..."
docker compose down 2>/dev/null || true

# Build images
echo ""
info "Building Docker images..."
docker compose build || error_exit "Docker build failed"
success "Docker images built"

# Start services with worker scaling (from .env or defaults)
echo ""
info "Starting services with worker scaling..."
docker compose up -d || error_exit "Failed to start services"
success "Services started (Worker scaling via .env or docker-compose.yml defaults)"

# Wait for PostgreSQL
echo ""
info "Waiting for PostgreSQL to be ready..."
sleep 5

MAX_RETRIES=30
RETRY_COUNT=0
until docker exec asciisky-postgres pg_isready -U asciisky -d asciisky > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        error_exit "PostgreSQL did not become ready in time"
    fi
    echo "   Waiting... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done
success "PostgreSQL is ready"

# Wait for RabbitMQ
echo ""
info "Waiting for RabbitMQ to be ready..."
sleep 5

RETRY_COUNT=0
until docker exec asciisky-rabbitmq rabbitmqctl status > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        error_exit "RabbitMQ did not become ready in time"
    fi
    echo "   Waiting... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done
success "RabbitMQ is ready"

# Setup RabbitMQ queues
echo ""
info "Setting up RabbitMQ queues..."
export RABBITMQ_CONTAINER=asciisky-rabbitmq
./scripts/setup-rabbitmq-queues.sh || error_exit "RabbitMQ queue setup failed"
success "RabbitMQ queues created"

# Load initial data (optional)
echo ""
read -p "Load initial asteroid/comet data? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    info "Loading initial data (this may take a few minutes)..."
    docker exec asciisky-data-updater python nightly_data_updater.py || warning "Data update failed (you can run it manually later)"
    success "Initial data loaded"
else
    info "Skipping initial data load (you can run it manually later)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Development Setup Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Service Status:"
docker compose ps
echo ""
echo "🌐 Services:"
echo "   Web UI:         http://localhost:8000"
echo "   RabbitMQ UI:    http://localhost:15672"
echo "   PostgreSQL:     localhost:5432"
echo ""
echo "👤 Credentials:"
echo "   RabbitMQ:       admin / $RABBITMQ_PASSWORD"
echo "   PostgreSQL:     asciisky / $POSTGRES_PASSWORD"
echo ""
echo "🔄 Running Services:"
echo "   - web (FastAPI)"
echo "   - rabbitmq (Message Queue)"
echo "   - postgres (Database)"
echo "   - data_updater (Nightly Updates)"
echo "   - precompute_coordinator (Task Creator)"
echo "   - precompute_worker x${PRECOMPUTE_WORKERS:-4} (Task Processor)"
echo "   - asteroid-worker x${ASTEROID_WORKERS:-2} (Asteroid Compute)"
echo "   - comet-worker x${COMET_WORKERS:-2} (Comet Compute)"
echo ""
echo "📝 Useful commands:"
echo "   docker compose logs -f web                    # Web logs"
echo "   docker compose logs -f precompute_coordinator # Precompute coordinator"
echo "   docker compose logs -f precompute_worker      # Precompute worker (all)"
echo "   docker compose logs -f asteroid-worker        # Asteroid worker (all)"
echo "   docker compose ps                             # Service status"
echo "   docker compose down                           # Stop all services"
echo "   docker compose up -d                          # Start all services"
echo ""
echo "⚙️  Worker Scaling (via .env):"
echo "   Edit .env and set:"
echo "     PRECOMPUTE_WORKERS=8    # Number of precompute workers"
echo "     ASTEROID_WORKERS=4      # Number of asteroid workers"
echo "     COMET_WORKERS=4         # Number of comet workers"
echo "   Then: docker compose up -d"
echo ""
echo "🔍 Monitoring:"
echo "   RabbitMQ UI:    Check queue 'precompute.tasks' for tasks"
echo "   PostgreSQL:     docker exec asciisky-postgres psql -U asciisky -d asciisky"
echo ""
echo "🚀 Next steps:"
echo "   1. Open http://localhost:8000 in your browser"
echo "   2. Check RabbitMQ UI at http://localhost:15672"
echo "   3. Monitor logs: docker compose logs -f"
echo ""
echo "💡 Tips:"
echo "   - Code changes are auto-reloaded (volume mount)"
echo "   - Use 'docker compose restart web' to restart web service"
echo "   - Use 'docker compose down -v' to reset database (removes volumes)"
echo ""
