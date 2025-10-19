#!/bin/bash
# UFW Firewall Setup für ASCII Sky Multi-Host Deployment
# Führe dieses Skript auf JEDEM Server aus!

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

# Prüfe ob UFW installiert ist
if ! command -v ufw &> /dev/null; then
    echo "📦 UFW nicht installiert. Installiere..."
    sudo apt-get update
    sudo apt-get install -y ufw || error_exit "UFW Installation fehlgeschlagen"
fi

# Hostname ermitteln
HOSTNAME=$(hostname -f)
echo "🖥️  Server: $HOSTNAME"
echo ""

# Frage nach Server-Rolle
echo "Welche Server-Rolle hat diese Maschine?"
echo "1) asciisky.eibrain.org (Hauptserver: Web + RabbitMQ + PostgreSQL)"
echo "2) rabbit-b.eibrain.org (Worker Server B)"
echo "3) rabbit-c.eibrain.org (Worker Server C)"
echo ""
read -p "Wähle (1-3): " ROLE

case $ROLE in
    1)
        SERVER_TYPE="main"
        echo "📍 Konfiguriere als: Hauptserver (asciisky.eibrain.org)"
        ;;
    2)
        SERVER_TYPE="worker-b"
        echo "📍 Konfiguriere als: Worker Server B (rabbit-b.eibrain.org)"
        ;;
    3)
        SERVER_TYPE="worker-c"
        echo "📍 Konfiguriere als: Worker Server C (rabbit-c.eibrain.org)"
        ;;
    *)
        error_exit "Ungültige Auswahl"
        ;;
esac

echo ""
warning "ACHTUNG: UFW wird neu konfiguriert!"
warning "Stelle sicher, dass SSH (Port 22) erlaubt wird, sonst verlierst du den Zugriff!"
echo ""
read -p "Fortfahren? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Abgebrochen."
    exit 0
fi

echo ""
echo "🔧 Konfiguriere UFW..."

# UFW zurücksetzen (optional)
# sudo ufw --force reset

# Standard-Policies
sudo ufw default deny incoming
sudo ufw default allow outgoing
success "Standard-Policies gesetzt (deny incoming, allow outgoing)"

# ===== GEMEINSAME REGELN (alle Server) =====
echo ""
echo "📋 Setze gemeinsame Regeln..."

# SSH (WICHTIG!)
sudo ufw allow 22/tcp comment 'SSH'
success "Port 22 (SSH) erlaubt"

# ===== SERVER-SPEZIFISCHE REGELN =====
echo ""
echo "📋 Setze server-spezifische Regeln..."

if [ "$SERVER_TYPE" == "main" ]; then
    # ===== HAUPTSERVER: asciisky.eibrain.org =====
    echo "🌐 Hauptserver-Regeln..."
    
    # Web UI (öffentlich)
    sudo ufw allow 8000/tcp comment 'ASCII Sky Web UI'
    success "Port 8000 (Web UI) erlaubt"
    
    # RabbitMQ AMQP (nur von Worker-Servern)
    # Option 1: Von überall (einfacher, aber weniger sicher)
    sudo ufw allow 5672/tcp comment 'RabbitMQ AMQP'
    success "Port 5672 (RabbitMQ AMQP) erlaubt"
    
    # RabbitMQ Management UI (nur aus vertrautem Netz empfohlen)
    echo ""
    read -p "RabbitMQ Management UI (Port 15672) öffentlich freigeben? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo ufw allow 15672/tcp comment 'RabbitMQ Management UI'
        success "Port 15672 (RabbitMQ Management UI) erlaubt"
        warning "Empfehlung: Nur über VPN/SSH-Tunnel zugreifen!"
    else
        echo "Port 15672 nicht freigegeben (Zugriff über SSH-Tunnel empfohlen)"
    fi
    
    # PostgreSQL (nur von Worker-Servern)
    # Option 1: Von überall (einfacher, aber weniger sicher)
    sudo ufw allow 5432/tcp comment 'PostgreSQL'
    success "Port 5432 (PostgreSQL) erlaubt"
    
    echo ""
    warning "SICHERHEITSHINWEIS für Produktion:"
    echo "   Beschränke Ports 5672 und 5432 auf Worker-IPs:"
    echo "   sudo ufw delete allow 5672/tcp"
    echo "   sudo ufw delete allow 5432/tcp"
    echo "   sudo ufw allow from <rabbit-b-IP> to any port 5672 proto tcp"
    echo "   sudo ufw allow from <rabbit-b-IP> to any port 5432 proto tcp"
    echo "   sudo ufw allow from <rabbit-c-IP> to any port 5672 proto tcp"
    echo "   sudo ufw allow from <rabbit-c-IP> to any port 5432 proto tcp"
    
elif [ "$SERVER_TYPE" == "worker-b" ] || [ "$SERVER_TYPE" == "worker-c" ]; then
    # ===== WORKER SERVER =====
    echo "👷 Worker-Server-Regeln..."
    
    # Worker brauchen nur ausgehende Verbindungen zu:
    # - RabbitMQ (5672)
    # - PostgreSQL (5432)
    # Diese sind bereits durch "default allow outgoing" erlaubt
    
    success "Keine zusätzlichen eingehenden Ports nötig"
    echo "   Worker verbinden sich ausgehend zu asciisky.eibrain.org:5672 und :5432"
fi

# ===== UFW AKTIVIEREN =====
echo ""
echo "🚀 Aktiviere UFW..."

# UFW aktivieren (mit --force um Bestätigung zu überspringen)
sudo ufw --force enable || error_exit "UFW Aktivierung fehlgeschlagen"

success "UFW aktiviert und konfiguriert!"

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

if [ "$SERVER_TYPE" == "main" ]; then
    echo "🌐 Hauptserver-Ports:"
    echo "   ✅ 22    - SSH"
    echo "   ✅ 8000  - Web UI (öffentlich)"
    echo "   ✅ 5672  - RabbitMQ AMQP (für Worker)"
    echo "   ✅ 5432  - PostgreSQL (für Worker)"
    if sudo ufw status | grep -q "15672"; then
        echo "   ✅ 15672 - RabbitMQ Management UI"
    else
        echo "   ⚠️  15672 - RabbitMQ Management UI (nicht freigegeben)"
        echo "              Zugriff via SSH-Tunnel: ssh -L 15672:localhost:15672 asciisky.eibrain.org"
    fi
else
    echo "👷 Worker-Server-Ports:"
    echo "   ✅ 22    - SSH"
    echo "   ℹ️  Ausgehende Verbindungen zu asciisky.eibrain.org:5672 und :5432"
fi

echo ""
echo "📝 Nützliche Befehle:"
echo "   sudo ufw status verbose          # Status anzeigen"
echo "   sudo ufw status numbered         # Regeln mit Nummern"
echo "   sudo ufw delete <nummer>         # Regel löschen"
echo "   sudo ufw disable                 # UFW deaktivieren"
echo "   sudo ufw reload                  # UFW neu laden"
echo ""
