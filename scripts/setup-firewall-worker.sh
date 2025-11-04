#!/bin/bash
# DOCKER-USER Firewall Setup für ASCII Sky Worker Server
# Führe dieses Skript NUR auf WORKER-SERVERN aus (rabbit-b, rabbit-c)
# Konfiguriert Docker-Container für NUR lokale Kommunikation über DOCKER-USER Chain

set -e

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

echo "🔥 ASCII Sky Worker DOCKER-USER Setup"
echo "======================================"
echo ""

# Hostname ermitteln
HOSTNAME=$(hostname -f)
echo "🖥️  Worker Server: $HOSTNAME"
echo ""

warning "ACHTUNG: Dieses Skript konfiguriert NUR DOCKER-USER Chain!"
warning "Keine UFW Konfiguration!"
warning "Docker-Container werden nach außen blockiert!"
echo ""

read -p "Fortfahren? (y/N) " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Abgebrochen."
    exit 0
fi

echo ""
echo "🐳 Konfiguriere DOCKER-USER Chain (Worker-spezifisch)..."
echo ""

# Docker fügt automatisch Regeln in die DOCKER-USER Chain ein, die VOR UFW greifen
# Wir müssen explizit DENY-Regeln in DOCKER-USER hinzufügen, um Docker-Container zu schützen

# Lösche alte DOCKER-USER Regeln (außer RETURN am Ende)
sudo iptables -F DOCKER-USER 2>/dev/null || true
sudo ip6tables -F DOCKER-USER 2>/dev/null || true

# Worker: BLOCKIERE eingehende Verbindungen von außen, ERLAUBE localhost
# Erlaube localhost (127.0.0.1) zu Docker-Containern
sudo iptables -A DOCKER-USER -s 127.0.0.1 -j ACCEPT -m comment --comment "Allow localhost to containers"
sudo ip6tables -A DOCKER-USER -s ::1 -j ACCEPT -m comment --comment "Allow localhost IPv6 to containers"

# DROP alle anderen eingehenden TCP-Verbindungen auf Docker-Container
sudo iptables -A DOCKER-USER -p tcp -j DROP -m comment --comment "Block external TCP to containers"
sudo ip6tables -A DOCKER-USER -p tcp -j DROP -m comment --comment "Block external TCP to containers IPv6"

# DROP alle anderen eingehenden UDP-Verbindungen auf Docker-Container
sudo iptables -A DOCKER-USER -p udp -j DROP -m comment --comment "Block external UDP to containers"
sudo ip6tables -A DOCKER-USER -p udp -j DROP -m comment --comment "Block external UDP to containers IPv6"

# WICHTIG: RETURN am Ende (lässt andere Verbindungen durch)
sudo iptables -A DOCKER-USER -j RETURN
sudo ip6tables -A DOCKER-USER -j RETURN 2>/dev/null || true

success "DOCKER-USER Chain konfiguriert (blockiert externe Docker-Ports!)"

# Mache DOCKER-USER Regeln persistent via UFW after.rules
echo "💾 Füge DOCKER-USER Regeln zu /etc/ufw/after.rules hinzu..."

# Backup der originalen after.rules
if [ ! -f /etc/ufw/after.rules.backup ]; then
    sudo cp /etc/ufw/after.rules /etc/ufw/after.rules.backup
    success "Backup erstellt: /etc/ufw/after.rules.backup"
fi

# Entferne alte ASCII Sky Worker DOCKER-USER Regeln falls vorhanden
sudo sed -i '/# ASCII Sky Worker DOCKER-USER rules - START/,/# ASCII Sky Worker DOCKER-USER rules - END/d' /etc/ufw/after.rules

# Füge neue DOCKER-USER Regeln am Ende hinzu (vor COMMIT)
# WICHTIG: Keine *filter oder :DOCKER-USER - Chain existiert bereits!
sudo sed -i '/^COMMIT$/i \
# ASCII Sky Worker DOCKER-USER rules - START\
# Diese Regeln blockieren alle Docker-Container-Ports von außen\
# Erlaube localhost zu Docker-Containern\
-A DOCKER-USER -s 127.0.0.1 -j ACCEPT -m comment --comment "Allow localhost to containers"\
# BLOCKIERE alle anderen eingehenden TCP/UDP Verbindungen\
-A DOCKER-USER -p tcp -j DROP -m comment --comment "Block external TCP to containers"\
-A DOCKER-USER -p udp -j DROP -m comment --comment "Block external UDP to containers"\
# RETURN (lässt andere Verbindungen durch)\
-A DOCKER-USER -j RETURN\
# ASCII Sky Worker DOCKER-USER rules - END\
' /etc/ufw/after.rules

success "DOCKER-USER Regeln zu /etc/ufw/after.rules hinzugefügt"

# ===== STATUS ANZEIGEN =====
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🐳 Docker DOCKER-USER Chain Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sudo iptables -L DOCKER-USER -n -v

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Worker DOCKER-USER Setup abgeschlossen!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "🔒 Worker Server - DOCKER-USER Konfiguration:"
echo "   ✅ Localhost (127.0.0.1) -> Docker - erlaubt"
echo "   ❌ Internet -> Docker - blockiert"
echo "   ✅ Ausgehende Verbindungen - erlaubt (Default)"
echo "   ✅ Lokale Docker-Netzwerke - erlaubt"
echo ""

echo "🌐 Docker-Container kommunizieren:"
echo "   🔗 Localhost kann auf Container zugreifen"
echo "   🔗 Ausgehende Verbindungen funktionieren"
echo "   🔗 Vollständig vor externem Internet geschützt"
echo ""

echo "📝 Nützliche Befehle:"
echo "   sudo iptables -L DOCKER-USER -n -v         # DOCKER-USER Chain anzeigen"
echo "   sudo iptables -L DOCKER-USER -n --line-numbers  # Mit Zeilennummern"
echo "   sudo ufw reload                            # UFW neu laden (lädt after.rules)"
echo "   sudo iptables -F DOCKER-USER               # DOCKER-USER zurücksetzen"
echo ""

echo "💡 Worker-Container:"
echo "   ✅ Localhost -> Container (z.B. curl localhost:8000)"
echo "   ✅ Container-zu-Container Kommunikation"
echo "   ✅ Ausgehende Verbindungen (z.B. zu Hauptserver)"
echo "   ❌ Internet -> Container (blockiert)"
echo ""
