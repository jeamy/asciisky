# Worker Firewall Setup

## Übersicht

Die Worker-Server (rabbit-b, rabbit-c) verwenden eine spezielle Firewall-Konfiguration, die Docker-Container vollständig nach außen isoliert. Docker-Container kommunizieren nur über lokale Docker-Netzwerke.

## Funktionsweise

### Docker daemon.json Konfiguration

Die Worker verwenden eine angepasste `/etc/docker/daemon.json`:

```json
{
    "iptables": false,
    "userland-proxy": false,
    "experimental": false,
    "metrics-addr": "127.0.0.1:9323",
    "bridge": "none",
    "ip-forward": false,
    "userland-proxy-path": "/usr/bin/docker-proxy",
    "seccomp-profile": "/etc/docker/seccomp.json"
}
```

**Wichtige Einstellungen:**
- `"iptables": false` - Docker manipuliert nicht die System-iptables
- `"ip-forward": false` - Kein IP-Forwarding nach außen
- `"bridge": "none"` - Keine Bridge-Netzwerke nach außen

### DOCKER-USER Chain Regeln

Die DOCKER-USER Chain blockiert aktiv alle Docker-Container-Ports nach außen:

```bash
# Blockiere PostgreSQL extern
-A DOCKER-USER -p tcp --dport 5432 -j DROP

# Blockiere RabbitMQ extern  
-A DOCKER-USER -p tcp --dport 5672 -j DROP

# Blockiere Web API extern
-A DOCKER-USER -p tcp --dport 8000 -j DROP

# Blockiere RabbitMQ UI extern
-A DOCKER-USER -p tcp --dport 15672 -j DROP
```

### UFW Firewall Regeln

Die UFW Firewall erlaubt nur notwendige ausgehende Verbindungen:

```bash
# SSH für Server-Verwaltung
sudo ufw allow ssh

# HTTP/HTTPS für Updates und Docker Registry
sudo ufw allow out 80
sudo ufw allow out 443
```

## Installation

Führe das Setup-Skript auf jedem Worker-Server aus:

```bash
# Auf rabbit-b.eibrain.org und rabbit-c.eibrain.org
./scripts/setup-firewall-worker.sh
```

## Überprüfung

### UFW Status prüfen
```bash
sudo ufw status verbose
```

### DOCKER-USER Chain prüfen
```bash
sudo iptables -L DOCKER-USER -n -v
```

### Docker Container prüfen
```bash
sudo docker ps
sudo docker network ls
```

## Sicherheit

### ✅ Was funktioniert
- Container-zu-Container Kommunikation über Docker-Netzwerke
- Lokale Kommunikation zwischen Containern
- Ausgehende HTTP/HTTPS Verbindungen für Updates
- SSH Zugriff für Server-Verwaltung

### ❌ Was ist blockiert
- PostgreSQL (5432) von außen
- RabbitMQ (5672) von außen  
- Web API (8000) von außen
- RabbitMQ Management UI (15672) von außen
- Alle anderen Container-Ports nach außen

## Kommunikation mit Hauptserver

Die Worker kommunizieren mit dem Hauptserver über ausgehende Verbindungen:

- **RabbitMQ**: Worker → Hauptserver (Port 5672)
- **PostgreSQL**: Worker → Hauptserver (Port 5432)

Diese Verbindungen sind ausgehend und werden von der Firewall erlaubt.

## Fehlerbehebung

### Container starten nicht
Prüfe ob Docker korrekt konfiguriert ist:
```bash
sudo systemctl restart docker
sudo docker ps
```

### Keine Verbindung zum Hauptserver
Prüfe ausgehende Verbindungen:
```bash
telnet asciisky.eibrain.org 5672
telnet asciisky.eibrain.org 5432
```

### DOCKER-USER Regeln zurücksetzen
```bash
sudo iptables -F DOCKER-USER
sudo netfilter-persistent save
```

## Wichtige Befehle

```bash
# Firewall Status
sudo ufw status verbose
sudo iptables -L DOCKER-USER -n -v

# Regeln speichern
sudo netfilter-persistent save

# Docker neustarten
sudo systemctl restart docker

# Logs prüfen
sudo journalctl -u docker
sudo ufw status numbered
```

## Architektur

```
┌─────────────────┐    ┌─────────────────┐
│   Worker-B      │    │   Worker-C      │
│                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │ Docker      │ │    │ │ Docker      │ │
│ │ Container   │ │    │ │ Container   │ │
│ │ (localhost) │ │    │ │ (localhost) │ │
│ └─────────────┘ │    │ └─────────────┘ │
│                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │ UFW         │ │    │ │ UFW         │ │
│ │ Firewall    │ │    │ │ Firewall    │ │
│ └─────────────┘ │    │ └─────────────┘ │
└─────────────────┘    └─────────────────┘
         │                       │
         └───────────┬───────────┘
                     │
         ┌─────────────────┐
         │  Hauptserver    │
         │  asciisky       │
         │                 │
         │ ┌─────────────┐ │
         │ │ RabbitMQ    │ │
         │ │ PostgreSQL  │ │
         │ │ Web UI      │ │
         │ └─────────────┘ │
         └─────────────────┘
```

Die Worker sind vollständig nach außen isoliert und kommunizieren nur mit dem Hauptserver.
