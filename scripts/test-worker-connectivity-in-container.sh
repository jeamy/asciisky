#!/bin/bash
# Test Worker Connectivity vom Container aus
# Führe auf Worker-Host aus: ./scripts/test-worker-connectivity-in-container.sh

echo "🔍 Testing connectivity from Worker Container to Main Server"
echo "============================================================="
echo ""

COMPOSE_FILE="docker-compose.workers.yml"
CONTAINER="asteroid_worker"

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Prüfe ob Container läuft
if ! docker compose -f $COMPOSE_FILE ps | grep -q "$CONTAINER"; then
    error "Container $CONTAINER läuft nicht!"
    echo "Starte mit: docker compose -f $COMPOSE_FILE up -d"
    exit 1
fi

MAIN_SERVER="asciisky.eibrain.org"

echo "Testing from container: $CONTAINER"
echo ""

# Test 1: DNS Resolution
echo "1️⃣  Testing DNS resolution..."
if docker compose -f $COMPOSE_FILE exec -T $CONTAINER sh -c "getent hosts $MAIN_SERVER" > /dev/null 2>&1; then
    IP=$(docker compose -f $COMPOSE_FILE exec -T $CONTAINER sh -c "getent hosts $MAIN_SERVER" | awk '{print $1}')
    success "DNS OK: $MAIN_SERVER → $IP"
else
    error "DNS failed for $MAIN_SERVER"
fi
echo ""

# Test 2: Ping
echo "2️⃣  Testing ping..."
if docker compose -f $COMPOSE_FILE exec -T $CONTAINER sh -c "ping -c 3 $MAIN_SERVER" > /dev/null 2>&1; then
    success "Ping OK"
else
    warning "Ping failed (might be blocked by firewall)"
fi
echo ""

# Test 3: RabbitMQ Port (5672)
echo "3️⃣  Testing RabbitMQ port (5672)..."
if docker compose -f $COMPOSE_FILE exec -T $CONTAINER sh -c "timeout 5 nc -zv $MAIN_SERVER 5672" 2>&1 | grep -q "succeeded\|open"; then
    success "RabbitMQ port 5672 is open"
else
    error "RabbitMQ port 5672 is NOT accessible"
    echo "   Check firewall rules on main server"
fi
echo ""

# Test 4: PostgreSQL Port (5432)
echo "4️⃣  Testing PostgreSQL port (5432)..."
if docker compose -f $COMPOSE_FILE exec -T $CONTAINER sh -c "timeout 5 nc -zv $MAIN_SERVER 5432" 2>&1 | grep -q "succeeded\|open"; then
    success "PostgreSQL port 5432 is open"
else
    error "PostgreSQL port 5432 is NOT accessible"
    echo "   Check:"
    echo "   - Firewall rules on main server"
    echo "   - PostgreSQL listen_addresses setting"
    echo "   - PostgreSQL pg_hba.conf"
fi
echo ""

# Test 5: PostgreSQL Connection
echo "5️⃣  Testing PostgreSQL connection..."
RESULT=$(docker compose -f $COMPOSE_FILE exec -T $CONTAINER python3 -c "
import psycopg2
import os
try:
    conn = psycopg2.connect(
        host='$MAIN_SERVER',
        port=5432,
        database='asciisky',
        user='asciisky',
        password=os.environ.get('POSTGRES_PASSWORD', 'changeme'),
        connect_timeout=5
    )
    conn.close()
    print('OK')
except Exception as e:
    print(f'ERROR: {e}')
" 2>&1)

if echo "$RESULT" | grep -q "OK"; then
    success "PostgreSQL connection OK"
else
    error "PostgreSQL connection failed"
    echo "   Error: $RESULT"
    echo "   Check:"
    echo "   - POSTGRES_PASSWORD in .env"
    echo "   - pg_hba.conf allows connection from this IP"
fi
echo ""

# Test 6: RabbitMQ Connection
echo "6️⃣  Testing RabbitMQ connection..."
RESULT=$(docker compose -f $COMPOSE_FILE exec -T $CONTAINER python3 -c "
import pika
import os
try:
    url = f\"amqp://admin:{os.environ.get('RABBITMQ_PASSWORD', 'changeme')}@$MAIN_SERVER:5672/\"
    params = pika.URLParameters(url)
    params.connection_attempts = 1
    params.retry_delay = 1
    params.socket_timeout = 5
    conn = pika.BlockingConnection(params)
    conn.close()
    print('OK')
except Exception as e:
    print(f'ERROR: {e}')
" 2>&1)

if echo "$RESULT" | grep -q "OK"; then
    success "RabbitMQ connection OK"
else
    error "RabbitMQ connection failed"
    echo "   Error: $RESULT"
    echo "   Check:"
    echo "   - RABBITMQ_PASSWORD in .env"
    echo "   - RabbitMQ user 'admin' exists"
fi
echo ""

# Test 7: Check Environment Variables
echo "7️⃣  Checking environment variables..."
echo "POSTGRES_HOST=$(docker compose -f $COMPOSE_FILE exec -T $CONTAINER sh -c 'echo $POSTGRES_HOST')"
echo "POSTGRES_PORT=$(docker compose -f $COMPOSE_FILE exec -T $CONTAINER sh -c 'echo $POSTGRES_PORT')"
echo "POSTGRES_DB=$(docker compose -f $COMPOSE_FILE exec -T $CONTAINER sh -c 'echo $POSTGRES_DB')"
echo "POSTGRES_USER=$(docker compose -f $COMPOSE_FILE exec -T $CONTAINER sh -c 'echo $POSTGRES_USER')"
echo "RABBITMQ_URL=$(docker compose -f $COMPOSE_FILE exec -T $CONTAINER sh -c 'echo $RABBITMQ_URL' | sed 's/:[^:]*@/:***@/')"
echo ""

echo "============================================================="
echo "📊 Summary"
echo "============================================================="
echo ""
echo "If PostgreSQL port is NOT accessible from container:"
echo ""
echo "1. Get Worker Host IP:"
echo "   curl -s ifconfig.me"
echo ""
echo "2. On main server, allow this IP:"
echo "   sudo ufw allow from <worker-ip> to any port 5432"
echo "   sudo ufw allow from <worker-ip> to any port 5672"
echo ""
echo "3. Check PostgreSQL docker-compose.production.yml:"
echo "   ports:"
echo "     - \"5432:5432\"  # Must be exposed!"
echo ""
echo "4. Check PostgreSQL listen_addresses:"
echo "   docker exec asciisky-postgres psql -U asciisky -c \"SHOW listen_addresses;\""
echo "   Should be: '*' or '0.0.0.0'"
echo ""
echo "5. Add to pg_hba.conf (if needed):"
echo "   host all all <worker-ip>/32 md5"
echo ""
