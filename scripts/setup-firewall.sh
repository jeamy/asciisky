#\!/bin/bash
# UFW Firewall Setup für ASCII Sky Multi-Host Deployment
# Führe dieses Skript NUR auf dem HAUPTSERVER aus\!
# Konfiguriert IP-basierte Zugriffsbeschränkungen für RabbitMQ/PostgreSQL

set -e

# Lade .env falls vorhanden
if [ -f .env ]; then
    echo "📄 Lade .env Datei..."
    set -a  # Automatisch alle Variablen exportieren
    source .env
    set +a
elif [ -f ../.env ]; then
    echo "📄 Lade ../.env Datei..."
    set -a
    source ../.env
    set +a
fi

# Hostnames (can be provided via environment or .env); fall back to example.org
RABBITMQ_MAIN="${RABBITMQ_MAIN:-asciisky.example.org}"
RABBITMQ_B="${RABBITMQ_B:-rabbit-b.example.org}"
RABBITMQ_C="${RABBITMQ_C:-rabbit-c.example.org}"

echo "🔥 ASCII Sky Firewall Setup (UFW)"
echo "=================================="
echo ""

# Farben
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

# ===== SERVER IPs AUTOMATISCH ERMITTELN (IPv4 + IPv6) =====
echo "📋 Ermittle Server-IPs (IPv4 + IPv6)..."

# Prüfe ob bereits IPs gesetzt sind (z.B. WORKER_B_IP, WORKER_C_IP)
# Falls nicht, versuche DNS-Auflösung mit dig, host oder getent
resolve_ip() {
    local hostname=$1
    local ip=""
    
    # Versuche dig
    if command -v dig &> /dev/null; then
        ip=$(dig +short "$hostname" A 2>/dev/null | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | head -n1)
    fi
    
    # Falls dig fehlschlägt, versuche host
    if [ -z "$ip" ] && command -v host &> /dev/null; then
        ip=$(host "$hostname" 2>/dev/null | grep "has address" | head -n1 | awk '{print $NF}')
    fi
    
    # Falls host fehlschlägt, versuche getent
    if [ -z "$ip" ] && command -v getent &> /dev/null; then
        ip=$(getent hosts "$hostname" 2>/dev/null | awk '{print $1}' | head -n1)
    fi
    
    echo "$ip"
}

if [ -z "$WORKER_B_IP" ]; then
    WORKER_B_IP=$(resolve_ip "$RABBITMQ_B")
fi
if [ -z "$WORKER_C_IP" ]; then
    WORKER_C_IP=$(resolve_ip "$RABBITMQ_C")
fi
if [ -z "$MAIN_IP" ]; then
    MAIN_IP=$(resolve_ip "$RABBITMQ_MAIN")
fi

# IPv6 (optional, nur mit dig)
if command -v dig &> /dev/null; then
    if [ -z "$WORKER_B_IP6" ]; then
        WORKER_B_IP6=$(dig +short "$RABBITMQ_B" AAAA 2>/dev/null | grep -E '^[0-9a-f:]+$' | head -n1)
    fi
    if [ -z "$WORKER_C_IP6" ]; then
        WORKER_C_IP6=$(dig +short "$RABBITMQ_C" AAAA 2>/dev/null | grep -E '^[0-9a-f:]+$' | head -n1)
    fi
    if [ -z "$MAIN_IP6" ]; then
        MAIN_IP6=$(dig +short "$RABBITMQ_MAIN" AAAA 2>/dev/null | grep -E '^[0-9a-f:]+$' | head -n1)
    fi
fi

if [ -z "$WORKER_B_IP" ] || [ -z "$WORKER_C_IP" ]; then
    error_exit "Konnte Worker-IPs nicht ermitteln. Setze WORKER_B_IP und WORKER_C_IP als Environment-Variablen!"
fi

echo ""
echo "📍 Ermittelte IPv4-Adressen:"
echo "   $RABBITMQ_MAIN: $MAIN_IP"
echo "   $RABBITMQ_B: $WORKER_B_IP"
echo "   $RABBITMQ_C: $WORKER_C_IP"

if [ -n "$MAIN_IP6" ] || [ -n "$WORKER_B_IP6" ] || [ -n "$WORKER_C_IP6" ]; then
    echo ""
    echo "📍 Ermittelte IPv6-Adressen:"
    [ -n "$MAIN_IP6" ] && echo "   $RABBITMQ_MAIN: $MAIN_IP6"
    [ -n "$WORKER_B_IP6" ] && echo "   $RABBITMQ_B: $WORKER_B_IP6"
    [ -n "$WORKER_C_IP6" ] && echo "   $RABBITMQ_C: $WORKER_C_IP6"
fi
echo ""

# Prüfe ob UFW installiert ist
if \! command -v ufw &> /dev/null; then
    echo "📦 UFW nicht installiert. Installiere..."
    sudo apt-get update
    sudo apt-get install -y ufw || error_exit "UFW Installation fehlgeschlagen"
fi

# Hostname ermitteln
HOSTNAME=$(hostname -f)
echo "🖥️  Server: $HOSTNAME"
echo ""

echo "📍 Konfiguriere Firewall für Hauptserver ($RABBITMQ_MAIN)"
echo "   RabbitMQ und PostgreSQL werden auf Worker-IPs beschränkt"
echo ""

warning "ACHTUNG: UFW wird konfiguriert!"
warning "Nur auf dem Hauptserver ($RABBITMQ_MAIN) ausführen!"
warning "Worker-Server (rabbit-b/c) benötigen KEINE Firewall-Änderungen!"
echo ""
read -p "Fortfahren? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Abgebrochen."
    exit 0
fi

echo ""
echo "🔧 Konfiguriere UFW..."
echo ""

# IPv6 in UFW aktivieren
if grep -q "IPV6=no" /etc/default/ufw; then
    echo "🌐 Aktiviere IPv6 in UFW..."
    sudo sed -i 's/IPV6=no/IPV6=yes/' /etc/default/ufw
    success "IPv6 in UFW aktiviert"
fi

echo ""
echo "🐳 Konfiguriere DOCKER-USER Chain (verhindert Docker-Bypass von UFW)..."

# Docker fügt automatisch Regeln in die DOCKER-USER Chain ein, die VOR UFW greifen
# Wir müssen explizit DENY-Regeln in DOCKER-USER hinzufügen, um Docker-Container zu schützen

# Erstelle /etc/docker/daemon.json falls nicht vorhanden
if [ ! -f /etc/docker/daemon.json ]; then
    echo '{"iptables": true}' | sudo tee /etc/docker/daemon.json > /dev/null
    success "Docker daemon.json erstellt"
fi

# Füge DOCKER-USER Chain Regeln hinzu (werden VOR UFW ausgewertet!)
echo "🔒 Setze DOCKER-USER Chain Regeln (blockiert alle außer Worker-IPs)..."

# Lösche alte DOCKER-USER Regeln (außer RETURN am Ende)
sudo iptables -F DOCKER-USER 2>/dev/null || true
sudo ip6tables -F DOCKER-USER 2>/dev/null || true

# IPv4: Erlaube Worker-B und Worker-C auf RabbitMQ (5672) und PostgreSQL (5432)
sudo iptables -I DOCKER-USER -s $WORKER_B_IP -p tcp --dport 5672 -j ACCEPT -m comment --comment "RabbitMQ from Worker-B"
sudo iptables -I DOCKER-USER -s $WORKER_C_IP -p tcp --dport 5672 -j ACCEPT -m comment --comment "RabbitMQ from Worker-C"
sudo iptables -I DOCKER-USER -s $WORKER_B_IP -p tcp --dport 5432 -j ACCEPT -m comment --comment "PostgreSQL from Worker-B"
sudo iptables -I DOCKER-USER -s $WORKER_C_IP -p tcp --dport 5432 -j ACCEPT -m comment --comment "PostgreSQL from Worker-C"

# IPv4: Erlaube localhost auf RabbitMQ Management UI (15672)
sudo iptables -I DOCKER-USER -s 127.0.0.1 -p tcp --dport 15672 -j ACCEPT -m comment --comment "RabbitMQ UI localhost"

# IPv4: BLOCKIERE alle anderen auf RabbitMQ, PostgreSQL und Management UI
sudo iptables -A DOCKER-USER -p tcp --dport 5672 -j DROP -m comment --comment "Block RabbitMQ from others"
sudo iptables -A DOCKER-USER -p tcp --dport 5432 -j DROP -m comment --comment "Block PostgreSQL from others"
sudo iptables -A DOCKER-USER -p tcp --dport 15672 -j DROP -m comment --comment "Block RabbitMQ UI from others"

# IPv6: Gleiche Regeln für IPv6 (falls vorhanden)
if [ -n "$WORKER_B_IP6" ] || [ -n "$WORKER_C_IP6" ]; then
    if [ -n "$WORKER_B_IP6" ]; then
        sudo ip6tables -I DOCKER-USER -s $WORKER_B_IP6 -p tcp --dport 5672 -j ACCEPT -m comment --comment "RabbitMQ from Worker-B IPv6"
        sudo ip6tables -I DOCKER-USER -s $WORKER_B_IP6 -p tcp --dport 5432 -j ACCEPT -m comment --comment "PostgreSQL from Worker-B IPv6"
    fi
    if [ -n "$WORKER_C_IP6" ]; then
        sudo ip6tables -I DOCKER-USER -s $WORKER_C_IP6 -p tcp --dport 5672 -j ACCEPT -m comment --comment "RabbitMQ from Worker-C IPv6"
        sudo ip6tables -I DOCKER-USER -s $WORKER_C_IP6 -p tcp --dport 5432 -j ACCEPT -m comment --comment "PostgreSQL from Worker-C IPv6"
    fi
    sudo ip6tables -I DOCKER-USER -s ::1 -p tcp --dport 15672 -j ACCEPT -m comment --comment "RabbitMQ UI localhost IPv6"
    sudo ip6tables -A DOCKER-USER -p tcp --dport 5672 -j DROP -m comment --comment "Block RabbitMQ from others IPv6"
    sudo ip6tables -A DOCKER-USER -p tcp --dport 5432 -j DROP -m comment --comment "Block PostgreSQL from others IPv6"
    sudo ip6tables -A DOCKER-USER -p tcp --dport 15672 -j DROP -m comment --comment "Block RabbitMQ UI from others IPv6"
fi

# WICHTIG: RETURN am Ende (lässt andere Verbindungen durch)
sudo iptables -A DOCKER-USER -j RETURN
sudo ip6tables -A DOCKER-USER -j RETURN 2>/dev/null || true

success "DOCKER-USER Chain konfiguriert (blockiert Docker-Bypass!)"

# Mache DOCKER-USER Regeln persistent via UFW after.rules
echo "💾 Füge DOCKER-USER Regeln zu /etc/ufw/after.rules hinzu..."

# Entferne alte systemd-basierte Lösung (falls vorhanden)
if [ -f /etc/systemd/system/restore-docker-firewall.service ]; then
    echo "🧹 Entferne alte systemd-basierte Firewall-Regeln..."
    sudo systemctl stop restore-docker-firewall.service 2>/dev/null || true
    sudo systemctl disable restore-docker-firewall.service 2>/dev/null || true
    sudo rm -f /etc/systemd/system/restore-docker-firewall.service
    sudo rm -f /usr/local/bin/restore-docker-firewall.sh
    sudo systemctl daemon-reload
    success "Alte systemd-Services entfernt"
fi

# Backup der originalen after.rules
if [ ! -f /etc/ufw/after.rules.backup ]; then
    sudo cp /etc/ufw/after.rules /etc/ufw/after.rules.backup
    success "Backup erstellt: /etc/ufw/after.rules.backup"
fi

# Entferne alte ASCII Sky DOCKER-USER Regeln falls vorhanden
sudo sed -i '/# ASCII Sky DOCKER-USER rules - START/,/# ASCII Sky DOCKER-USER rules - END/d' /etc/ufw/after.rules

# Füge neue DOCKER-USER Regeln am Ende hinzu (vor COMMIT)
sudo sed -i '/^COMMIT$/i \
# ASCII Sky DOCKER-USER rules - START\
# Diese Regeln verhindern dass Docker die UFW-Firewall umgeht\
*filter\
:DOCKER-USER - [0:0]\
\
# Erlaube Worker-B und Worker-C auf RabbitMQ und PostgreSQL\
-A DOCKER-USER -s '"$WORKER_B_IP"' -p tcp --dport 5672 -j ACCEPT -m comment --comment "RabbitMQ from Worker-B"\
-A DOCKER-USER -s '"$WORKER_C_IP"' -p tcp --dport 5672 -j ACCEPT -m comment --comment "RabbitMQ from Worker-C"\
-A DOCKER-USER -s '"$WORKER_B_IP"' -p tcp --dport 5432 -j ACCEPT -m comment --comment "PostgreSQL from Worker-B"\
-A DOCKER-USER -s '"$WORKER_C_IP"' -p tcp --dport 5432 -j ACCEPT -m comment --comment "PostgreSQL from Worker-C"\
\
# Erlaube localhost auf RabbitMQ Management UI\
-A DOCKER-USER -s 127.0.0.1 -p tcp --dport 15672 -j ACCEPT -m comment --comment "RabbitMQ UI localhost"\
\
# BLOCKIERE alle anderen auf diesen Ports\
-A DOCKER-USER -p tcp --dport 5672 -j DROP -m comment --comment "Block RabbitMQ from others"\
-A DOCKER-USER -p tcp --dport 5432 -j DROP -m comment --comment "Block PostgreSQL from others"\
-A DOCKER-USER -p tcp --dport 15672 -j DROP -m comment --comment "Block RabbitMQ UI from others"\
\
# RETURN (lässt andere Verbindungen durch)\
-A DOCKER-USER -j RETURN\
# ASCII Sky DOCKER-USER rules - END\
' /etc/ufw/after.rules

success "DOCKER-USER Regeln zu /etc/ufw/after.rules hinzugefügt"

echo ""
echo "📋 Setze zusätzliche UFW-Regeln (Backup-Schutz)..."

# UFW-Regeln als zusätzliche Sicherheitsebene (werden NACH DOCKER-USER ausgewertet)
# RabbitMQ AMQP (nur von Worker-Servern) - IPv4
sudo ufw allow from $WORKER_B_IP to any port 5672 proto tcp comment 'RabbitMQ from Worker-B IPv4'
sudo ufw allow from $WORKER_C_IP to any port 5672 proto tcp comment 'RabbitMQ from Worker-C IPv4'

# RabbitMQ AMQP - IPv6 (falls vorhanden)
if [ -n "$WORKER_B_IP6" ]; then
    sudo ufw allow from $WORKER_B_IP6 to any port 5672 proto tcp comment 'RabbitMQ from Worker-B IPv6'
fi
if [ -n "$WORKER_C_IP6" ]; then
    sudo ufw allow from $WORKER_C_IP6 to any port 5672 proto tcp comment 'RabbitMQ from Worker-C IPv6'
fi
success "Port 5672 (RabbitMQ AMQP) - IPv4 + IPv6"

# PostgreSQL (NUR von Worker-Servern) - IPv4
sudo ufw allow from $WORKER_B_IP to any port 5432 proto tcp comment 'PostgreSQL from Worker-B IPv4'
sudo ufw allow from $WORKER_C_IP to any port 5432 proto tcp comment 'PostgreSQL from Worker-C IPv4'

# PostgreSQL - IPv6 (falls vorhanden)
if [ -n "$WORKER_B_IP6" ]; then
    sudo ufw allow from $WORKER_B_IP6 to any port 5432 proto tcp comment 'PostgreSQL from Worker-B IPv6'
fi
if [ -n "$WORKER_C_IP6" ]; then
    sudo ufw allow from $WORKER_C_IP6 to any port 5432 proto tcp comment 'PostgreSQL from Worker-C IPv6'
fi
success "Port 5432 (PostgreSQL) - IPv4 + IPv6"

# RabbitMQ Management UI (NUR localhost für SSH-Tunnel) - IPv4 + IPv6
sudo ufw allow from 127.0.0.1 to any port 15672 proto tcp comment 'RabbitMQ UI localhost IPv4'
sudo ufw allow from ::1 to any port 15672 proto tcp comment 'RabbitMQ UI localhost IPv6'
success "Port 15672 (RabbitMQ Management UI) - NUR localhost (SSH-Tunnel)"
echo "   💡 Zugriff via SSH-Tunnel: ssh -L 15672:localhost:15672 $RABBITMQ_MAIN"

# ===== UFW NEU LADEN =====
echo ""
echo "🔄 Lade UFW-Regeln neu..."
sudo ufw reload || error_exit "UFW Reload fehlgeschlagen"

success "Firewall-Regeln erfolgreich hinzugefügt!"

# ===== STATUS ANZEIGEN =====
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 UFW Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sudo ufw status verbose

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Firewall Setup abgeschlossen!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "🌐 Hauptserver - Neue Firewall-Regeln:"
echo "   🔒 5672  - RabbitMQ AMQP (NUR Worker-B: $WORKER_B_IP, Worker-C: $WORKER_C_IP)"
echo "   🔒 5432  - PostgreSQL (NUR Worker-B: $WORKER_B_IP, Worker-C: $WORKER_C_IP)"
echo "   🔒 15672 - RabbitMQ Management UI (NUR localhost/SSH-Tunnel)"
echo ""
echo "🔒 Sicherheit:"
echo "   ✅ DOCKER-USER Chain konfiguriert (verhindert Docker-Bypass!)"
echo "   ✅ RabbitMQ (5672) und PostgreSQL (5432) NUR von Worker-Servern erreichbar"
echo "   ✅ RabbitMQ UI (15672) NUR via SSH-Tunnel erreichbar"
echo "   ✅ Alle anderen IPs werden auf Ports 5672, 5432, 15672 blockiert"
echo "   ✅ iptables-Regeln persistent gespeichert (überleben Neustart)"

echo ""
echo "📝 Nützliche Befehle:"
echo "   sudo ufw status verbose                    # UFW Status anzeigen"
echo "   sudo iptables -L DOCKER-USER -n -v         # DOCKER-USER Chain anzeigen"
echo "   sudo iptables -L DOCKER-USER -n --line-numbers  # Mit Zeilennummern"
echo "   sudo ufw status numbered                   # UFW Regeln mit Nummern"
echo "   sudo ufw delete <nummer>                   # UFW Regel löschen"
echo "   sudo netfilter-persistent save             # iptables speichern"
echo ""
echo "💡 RabbitMQ UI Zugriff (von deinem lokalen Rechner):"
echo "   ssh -L 15672:localhost:15672 $RABBITMQ_MAIN"
echo "   Dann: http://localhost:15672 im Browser öffnen"
echo ""
