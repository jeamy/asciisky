# UFW Firewall Setup für ASCII Sky

## 🔥 Übersicht

Firewall-Konfiguration für das Multi-Host Production Deployment.

### Port-Übersicht

| Server | Port | Service | Zugriff | Beschreibung |
|--------|------|---------|---------|--------------|
| **asciisky.eibrain.org** | 22 | SSH | Vertrauenswürdig | Server-Administration |
| | 8000 | Web UI | Öffentlich | ASCII Sky Web-Interface |
| | 5672 | RabbitMQ AMQP | Worker-Server | Message Queue |
| | 5432 | PostgreSQL | Worker-Server | Datenbank |
| | 15672 | RabbitMQ UI | Optional/VPN | Management Interface |
| **rabbit-b.eibrain.org** | 22 | SSH | Vertrauenswürdig | Server-Administration |
| **rabbit-c.eibrain.org** | 22 | SSH | Vertrauenswürdig | Server-Administration |

---

## 🚀 Schnellstart

### Automatisches Setup

```bash
# Auf JEDEM Server ausführen:
chmod +x scripts/setup-firewall.sh
sudo ./scripts/setup-firewall.sh
```

Das Skript fragt nach der Server-Rolle und konfiguriert UFW automatisch.

---

## 🔧 Manuelle Konfiguration

### Auf asciisky.eibrain.org (Hauptserver)

```bash
# UFW installieren (falls nicht vorhanden)
sudo apt-get update
sudo apt-get install -y ufw

# Standard-Policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# SSH (WICHTIG - zuerst!)
sudo ufw allow 22/tcp comment 'SSH'

# Web UI (öffentlich)
sudo ufw allow 8000/tcp comment 'ASCII Sky Web UI'

# RabbitMQ AMQP (für Worker)
sudo ufw allow 5672/tcp comment 'RabbitMQ AMQP'

# PostgreSQL (für Worker)
sudo ufw allow 5432/tcp comment 'PostgreSQL'

# RabbitMQ Management UI (optional, siehe Sicherheitshinweise)
sudo ufw allow 15672/tcp comment 'RabbitMQ Management UI'

# UFW aktivieren
sudo ufw enable

# Status prüfen
sudo ufw status verbose
```

### Auf rabbit-b.eibrain.org (Worker Server B)

```bash
# UFW installieren
sudo apt-get update
sudo apt-get install -y ufw

# Standard-Policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# SSH
sudo ufw allow 22/tcp comment 'SSH'

# UFW aktivieren
sudo ufw enable

# Status prüfen
sudo ufw status verbose
```

### Auf rabbit-c.eibrain.org (Worker Server C)

```bash
# Identisch zu rabbit-b.eibrain.org
sudo apt-get update
sudo apt-get install -y ufw
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment 'SSH'
sudo ufw enable
sudo ufw status verbose
```

---

## 🔐 Sicherheits-Empfehlungen

### 1. RabbitMQ und PostgreSQL auf Worker-IPs beschränken

**Problem:** Ports 5672 und 5432 sind von überall erreichbar.

**Lösung:** Beschränke auf Worker-Server-IPs:

```bash
# Auf asciisky.eibrain.org

# Aktuelle Regeln entfernen
sudo ufw delete allow 5672/tcp
sudo ufw delete allow 5432/tcp

# Nur von rabbit-b.eibrain.org erlauben
sudo ufw allow from <rabbit-b-IP> to any port 5672 proto tcp comment 'RabbitMQ from rabbit-b'
sudo ufw allow from <rabbit-b-IP> to any port 5432 proto tcp comment 'PostgreSQL from rabbit-b'

# Nur von rabbit-c.eibrain.org erlauben
sudo ufw allow from <rabbit-c-IP> to any port 5672 proto tcp comment 'RabbitMQ from rabbit-c'
sudo ufw allow from <rabbit-c-IP> to any port 5432 proto tcp comment 'PostgreSQL from rabbit-c'

# Status prüfen
sudo ufw status numbered
```

**IPs ermitteln:**
```bash
# Auf rabbit-b.eibrain.org
hostname -I | awk '{print $1}'

# Auf rabbit-c.eibrain.org
hostname -I | awk '{print $1}'
```

### 2. RabbitMQ Management UI absichern

**Option A: Nicht öffentlich freigeben (empfohlen)**

Zugriff nur über SSH-Tunnel:
```bash
# Von deinem lokalen Rechner
ssh -L 15672:localhost:15672 asciisky.eibrain.org

# Dann im Browser öffnen:
# http://localhost:15672
```

**Option B: Auf vertrauenswürdige IPs beschränken**

```bash
# Nur von deiner Admin-IP erlauben
sudo ufw allow from <deine-IP> to any port 15672 proto tcp comment 'RabbitMQ UI from Admin'
```

### 3. SSH absichern

```bash
# SSH-Port ändern (optional)
# /etc/ssh/sshd_config: Port 2222
sudo ufw allow 2222/tcp comment 'SSH (custom port)'
sudo ufw delete allow 22/tcp

# Nur von vertrauenswürdigen IPs
sudo ufw delete allow 22/tcp
sudo ufw allow from <admin-IP> to any port 22 proto tcp comment 'SSH from Admin'

# SSH neu starten
sudo systemctl restart sshd
```

### 4. Rate Limiting für SSH

```bash
# Schutz vor Brute-Force
sudo ufw limit 22/tcp comment 'SSH with rate limiting'
```

---

## 📊 Monitoring

### UFW Status prüfen

```bash
# Ausführlicher Status
sudo ufw status verbose

# Nummerierte Regeln
sudo ufw status numbered

# Logging aktivieren
sudo ufw logging on

# Logs anzeigen
sudo tail -f /var/log/ufw.log
```

### Offene Ports prüfen

```bash
# Alle offenen Ports
sudo netstat -tulpn | grep LISTEN

# Oder mit ss
sudo ss -tulpn | grep LISTEN

# Nur Docker-Container
docker ps --format "table {{.Names}}\t{{.Ports}}"
```

---

## 🛠️ Troubleshooting

### Problem: Kein Zugriff auf Web UI

```bash
# Prüfe ob Port 8000 offen ist
sudo ufw status | grep 8000

# Prüfe ob Web-Container läuft
docker ps | grep asciisky-web

# Prüfe ob Port gebunden ist
sudo netstat -tulpn | grep 8000
```

### Problem: Worker können sich nicht verbinden

```bash
# Auf asciisky.eibrain.org: Prüfe Ports 5672 und 5432
sudo ufw status | grep -E '5672|5432'

# Teste Verbindung von Worker-Server
# Auf rabbit-b.eibrain.org:
telnet asciisky.eibrain.org 5672
telnet asciisky.eibrain.org 5432

# Prüfe RabbitMQ Logs
docker logs asciisky-rabbitmq | tail -50

# Prüfe PostgreSQL Logs
docker logs asciisky-postgres | tail -50
```

### Problem: UFW blockiert Docker-Container

Docker manipuliert iptables direkt und kann UFW-Regeln umgehen.

**Lösung:** UFW für Docker konfigurieren:

```bash
# /etc/ufw/after.rules bearbeiten
sudo nano /etc/ufw/after.rules

# Am Ende hinzufügen:
# BEGIN UFW AND DOCKER
*filter
:ufw-user-forward - [0:0]
:DOCKER-USER - [0:0]
-A DOCKER-USER -j RETURN -s 10.0.0.0/8
-A DOCKER-USER -j RETURN -s 172.16.0.0/12
-A DOCKER-USER -j RETURN -s 192.168.0.0/16
-A DOCKER-USER -j ufw-user-forward
-A DOCKER-USER -j DROP -p tcp -m tcp --tcp-flags FIN,SYN,RST,ACK SYN -d 192.168.0.0/16
-A DOCKER-USER -j DROP -p tcp -m tcp --tcp-flags FIN,SYN,RST,ACK SYN -d 10.0.0.0/8
-A DOCKER-USER -j DROP -p tcp -m tcp --tcp-flags FIN,SYN,RST,ACK SYN -d 172.16.0.0/12
-A DOCKER-USER -j DROP -p udp -m udp --dport 0:32767 -d 192.168.0.0/16
-A DOCKER-USER -j DROP -p udp -m udp --dport 0:32767 -d 10.0.0.0/8
-A DOCKER-USER -j DROP -p udp -m udp --dport 0:32767 -d 172.16.0.0/12
-A DOCKER-USER -j RETURN
COMMIT
# END UFW AND DOCKER

# UFW neu laden
sudo ufw reload
```

---

## 🔄 UFW Befehle Cheat Sheet

```bash
# Status
sudo ufw status                    # Einfacher Status
sudo ufw status verbose            # Ausführlicher Status
sudo ufw status numbered           # Mit Regel-Nummern

# Aktivieren/Deaktivieren
sudo ufw enable                    # UFW aktivieren
sudo ufw disable                   # UFW deaktivieren
sudo ufw reload                    # UFW neu laden

# Regeln hinzufügen
sudo ufw allow 8000/tcp            # Port erlauben
sudo ufw allow from 1.2.3.4        # IP erlauben
sudo ufw allow from 1.2.3.4 to any port 5432  # IP zu Port
sudo ufw limit 22/tcp              # Rate Limiting

# Regeln löschen
sudo ufw delete allow 8000/tcp     # Nach Regel
sudo ufw delete 5                  # Nach Nummer
sudo ufw status numbered           # Nummern anzeigen

# Zurücksetzen
sudo ufw reset                     # Alle Regeln löschen

# Logging
sudo ufw logging on                # Logging aktivieren
sudo ufw logging off               # Logging deaktivieren
sudo tail -f /var/log/ufw.log      # Logs anzeigen

# Default Policies
sudo ufw default deny incoming     # Eingehend blockieren
sudo ufw default allow outgoing    # Ausgehend erlauben
```

---

## 📋 Checkliste für Production

- [ ] UFW auf allen 3 Servern installiert und aktiviert
- [ ] SSH (Port 22) auf allen Servern erlaubt
- [ ] Web UI (Port 8000) auf asciisky.eibrain.org öffentlich
- [ ] RabbitMQ (Port 5672) auf Worker-IPs beschränkt
- [ ] PostgreSQL (Port 5432) auf Worker-IPs beschränkt
- [ ] RabbitMQ UI (Port 15672) nur über SSH-Tunnel oder VPN
- [ ] SSH Rate Limiting aktiviert (`ufw limit 22/tcp`)
- [ ] UFW Logging aktiviert für Monitoring
- [ ] Firewall-Regeln dokumentiert
- [ ] Worker-Verbindung getestet (telnet/nc)
- [ ] Web UI von extern erreichbar getestet

---

## 🔗 Weiterführende Links

- [UFW Dokumentation](https://help.ubuntu.com/community/UFW)
- [Docker und UFW](https://github.com/chaifeng/ufw-docker)
- [iptables Grundlagen](https://www.netfilter.org/documentation/)
