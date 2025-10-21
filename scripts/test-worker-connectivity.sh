#!/bin/bash
# Test Worker Connectivity zu Hauptserver
# Führe dieses Script auf Worker-Hosts aus

echo "🔍 Testing connectivity from Worker to Main Server"
echo "=================================================="
echo ""

MAIN_SERVER="asciisky.eibrain.org"

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

# Test 1: DNS Resolution
echo "1️⃣  Testing DNS resolution..."
if host $MAIN_SERVER > /dev/null 2>&1; then
    IP=$(host $MAIN_SERVER | grep "has address" | awk '{print $4}' | head -1)
    success "DNS OK: $MAIN_SERVER → $IP"
else
    error "DNS failed for $MAIN_SERVER"
    exit 1
fi
echo ""

# Test 2: Ping
echo "2️⃣  Testing ping..."
if ping -c 3 $MAIN_SERVER > /dev/null 2>&1; then
    success "Ping OK"
else
    warning "Ping failed (might be blocked by firewall)"
fi
echo ""

# Test 3: RabbitMQ Port (5672)
echo "3️⃣  Testing RabbitMQ port (5672)..."
if timeout 5 bash -c "cat < /dev/null > /dev/tcp/$MAIN_SERVER/5672" 2>/dev/null; then
    success "RabbitMQ port 5672 is open"
else
    error "RabbitMQ port 5672 is NOT accessible"
    echo "   Check firewall rules on main server"
fi
echo ""

# Test 4: PostgreSQL Port (5432)
echo "4️⃣  Testing PostgreSQL port (5432)..."
if timeout 5 bash -c "cat < /dev/null > /dev/tcp/$MAIN_SERVER/5432" 2>/dev/null; then
    success "PostgreSQL port 5432 is open"
else
    error "PostgreSQL port 5432 is NOT accessible"
    echo "   Check:"
    echo "   - Firewall rules on main server"
    echo "   - PostgreSQL listen_addresses setting"
    echo "   - PostgreSQL pg_hba.conf"
fi
echo ""

# Test 5: PostgreSQL Connection (if psql available)
echo "5️⃣  Testing PostgreSQL connection..."
if command -v psql &> /dev/null; then
    if [ -z "$POSTGRES_PASSWORD" ]; then
        warning "POSTGRES_PASSWORD not set in environment"
        echo "   Set it with: export POSTGRES_PASSWORD=your_password"
    else
        if PGPASSWORD=$POSTGRES_PASSWORD psql -h $MAIN_SERVER -U asciisky -d asciisky -c "SELECT 1;" > /dev/null 2>&1; then
            success "PostgreSQL connection OK"
        else
            error "PostgreSQL connection failed"
            echo "   Check password and pg_hba.conf on main server"
        fi
    fi
else
    warning "psql not installed, skipping PostgreSQL connection test"
    echo "   Install with: apt-get install postgresql-client"
fi
echo ""

# Test 6: RabbitMQ Connection (if available)
echo "6️⃣  Testing RabbitMQ connection..."
if command -v curl &> /dev/null; then
    if [ -z "$RABBITMQ_PASSWORD" ]; then
        warning "RABBITMQ_PASSWORD not set in environment"
        echo "   Set it with: export RABBITMQ_PASSWORD=your_password"
    else
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -u admin:$RABBITMQ_PASSWORD http://$MAIN_SERVER:15672/api/overview)
        if [ "$HTTP_CODE" = "200" ]; then
            success "RabbitMQ Management API OK"
        else
            warning "RabbitMQ Management API returned HTTP $HTTP_CODE"
            echo "   This is OK if Management UI is not exposed externally"
        fi
    fi
else
    warning "curl not installed, skipping RabbitMQ test"
fi
echo ""

echo "=================================================="
echo "📊 Summary"
echo "=================================================="
echo ""
echo "If PostgreSQL port is NOT accessible:"
echo "  1. On main server, check firewall:"
echo "     sudo ufw status"
echo "     sudo ufw allow from <worker-ip> to any port 5432"
echo ""
echo "  2. Check PostgreSQL listen_addresses:"
echo "     docker exec asciisky-postgres psql -U asciisky -c \"SHOW listen_addresses;\""
echo "     Should be: '*' or '0.0.0.0'"
echo ""
echo "  3. Check pg_hba.conf:"
echo "     docker exec asciisky-postgres cat /var/lib/postgresql/data/pg_hba.conf"
echo "     Should have: host all all <worker-ip>/32 md5"
echo ""
