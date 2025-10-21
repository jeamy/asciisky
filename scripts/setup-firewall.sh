#\!/bin/bash
# UFW Firewall Setup für ASCII Sky Multi-Host Deployment
# Führe dieses Skript auf JEDEM Server aus\!
# Konfiguriert IP-basierte Zugriffsbeschränkungen für RabbitMQ/PostgreSQL

set -e

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

# IPv4
MAIN_IP=$(dig +short asciisky.eibrain.org A | tail -n1)
WORKER_B_IP=$(dig +short rabbit-b.eibrain.org A | tail -n1)
WORKER_C_IP=$(dig +short rabbit-c.eibrain.org A | tail -n1)

# IPv6
MAIN_IP6=$(dig +short asciisky.eibrain.org AAAA | tail -n1)
WORKER_B_IP6=$(dig +short rabbit-b.eibrain.org AAAA | tail -n1)
WORKER_C_IP6=$(dig +short rabbit-c.eibrain.org AAAA | tail -n1)

if [ -z "$MAIN_IP" ] || [ -z "$WORKER_B_IP" ] || [ -z "$WORKER_C_IP" ]; then
    error_exit "Konnte nicht alle IPv4-Adressen auflösen. Prüfe DNS-Konfiguration."
fi

echo ""
echo "📍 Ermittelte IPv4-Adressen:"
echo "   asciisky.eibrain.org: $MAIN_IP"
echo "   rabbit-b.eibrain.org: $WORKER_B_IP"
echo "   rabbit-c.eibrain.org: $WORKER_C_IP"

if [ -n "$MAIN_IP6" ] || [ -n "$WORKER_B_IP6" ] || [ -n "$WORKER_C_IP6" ]; then
    echo ""
    echo "📍 Ermittelte IPv6-Adressen:"
    [ -n "$MAIN_IP6" ] && echo "   asciisky.eibrain.org: $MAIN_IP6"
    [ -n "$WORKER_B_IP6" ] && echo "   rabbit-b.eibrain.org: $WORKER_B_IP6"
    [ -n "$WORKER_C_IP6" ] && echo "   rabbit-c.eibrain.org: $WORKER_C_IP6"
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

echo "📍 Konfiguriere Firewall für Hauptserver (asciisky.eibrain.org)"
echo "   RabbitMQ und PostgreSQL werden auf Worker-IPs beschränkt"
echo ""

warning "ACHTUNG: UFW wird konfiguriert!"
warning "Nur auf dem Hauptserver (asciisky.eibrain.org) ausführen!"
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
echo "📋 Setze Firewall-Regeln für RabbitMQ und PostgreSQL (IPv4 + IPv6)..."

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
echo "   💡 Zugriff via SSH-Tunnel: ssh -L 15672:localhost:15672 asciisky.eibrain.org"

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
echo "   ✅ RabbitMQ (5672) und PostgreSQL (5432) NUR von Worker-Servern erreichbar"
echo "   ✅ RabbitMQ UI (15672) NUR via SSH-Tunnel erreichbar"
echo "   ✅ Alle anderen IPs werden auf Ports 5672, 5432, 15672 blockiert"

echo ""
echo "📝 Nützliche Befehle:"
echo "   sudo ufw status verbose          # Status anzeigen"
echo "   sudo ufw status numbered         # Regeln mit Nummern"
echo "   sudo ufw delete <nummer>         # Regel löschen"
echo "   sudo ufw disable                 # UFW deaktivieren"
echo "   sudo ufw reload                  # UFW neu laden"
echo ""
echo "💡 RabbitMQ UI Zugriff (von deinem lokalen Rechner):"
echo "   ssh -L 15672:localhost:15672 asciisky.eibrain.org"
echo "   Dann: http://localhost:15672 im Browser öffnen"
echo ""
