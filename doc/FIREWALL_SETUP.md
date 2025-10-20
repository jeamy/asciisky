# UFW Firewall Setup für ASCII Sky

## 🔥 Übersicht

Firewall-Konfiguration für das Multi-Host Production Deployment.

### Port-Übersicht

| Server | Port | Service | Zugriff | Beschreibung |
|--------|------|---------|---------|--------------|
| **asciisky.eibrain.org** | 22 | SSH | Bereits konfiguriert | Server-Administration |
| | 80/443 | Web UI (nginx) | Öffentlich | ASCII Sky Web-Interface |
| | 8000 | FastAPI | Intern (nginx) | Backend (nicht öffentlich) |
| | 5672 | RabbitMQ AMQP | NUR Worker-B/C IPs | Message Queue |
| | 5432 | PostgreSQL | NUR Worker-B/C IPs | Datenbank |
| | 15672 | RabbitMQ UI | NUR localhost | Management Interface (SSH-Tunnel) |
| **rabbit-b.eibrain.org** | 22 | SSH | Bereits konfiguriert | Server-Administration |
| **rabbit-c.eibrain.org** | 22 | SSH | Bereits konfiguriert | Server-Administration |

---

## 🚀 Schnellstart

### Automatisches Setup (Empfohlen)

**NUR auf asciisky.eibrain.org ausführen:**

```bash
chmod +x scripts/setup-firewall.sh
sudo ./scripts/setup-firewall.sh
```

Das Script:
- ✅ Ermittelt automatisch IPs via DNS
- ✅ Beschränkt Port 5672 (RabbitMQ) auf Worker-B/C IPs
- ✅ Beschränkt Port 5432 (PostgreSQL) auf Worker-B/C IPs
- ✅ Beschränkt Port 15672 (RabbitMQ UI) auf localhost
- ✅ Worker-Server benötigen KEINE Firewall-Änderungen

**Wichtig:** Port 80/443 (nginx) und SSH werden als bereits konfiguriert vorausgesetzt!

---

## 🔧 Manuelle Konfiguration

### Auf asciisky.eibrain.org (Hauptserver)

**Empfehlung:** Verwende das automatische Script (siehe oben)!

**Manuelle Konfiguration:**

```bash
# IPs ermitteln
WORKER_B_IP=$(dig +short rabbit-b.eibrain.org | tail -n1)
WORKER_C_IP=$(dig +short rabbit-c.eibrain.org | tail -n1)

echo "Worker-B IP: $WORKER_B_IP"
echo "Worker-C IP: $WORKER_C_IP"

# RabbitMQ AMQP (NUR von Worker-Servern)
sudo ufw allow from $WORKER_B_IP to any port 5672 proto tcp comment 'RabbitMQ from Worker-B'
sudo ufw allow from $WORKER_C_IP to any port 5672 proto tcp comment 'RabbitMQ from Worker-C'

# PostgreSQL (NUR von Worker-Servern)
sudo ufw allow from $WORKER_B_IP to any port 5432 proto tcp comment 'PostgreSQL from Worker-B'
sudo ufw allow from $WORKER_C_IP to any port 5432 proto tcp comment 'PostgreSQL from Worker-C'

# RabbitMQ Management UI (NUR localhost)
sudo ufw allow from 127.0.0.1 to any port 15672 proto tcp comment 'RabbitMQ UI localhost'

# UFW neu laden
sudo ufw reload

# Status prüfen
sudo ufw status verbose
```

**Hinweis:** Port 80/443 (nginx), SSH und andere Ports werden als bereits konfiguriert vorausgesetzt.

### Auf rabbit-b.eibrain.org und rabbit-c.eibrain.org (Worker Server)

**Keine Firewall-Änderungen nötig!**

Worker-Server:
- ✅ Ausgehende Verbindungen sind bereits erlaubt (`default allow outgoing`)
- ✅ Verbinden sich zu asciisky.eibrain.org:5672 (RabbitMQ)
- ✅ Verbinden sich zu asciisky.eibrain.org:5432 (PostgreSQL)
- ✅ Benötigen keine eingehenden Ports (außer SSH)

**Falls UFW noch nicht konfiguriert:**
```bash
# Nur falls UFW noch nicht aktiv ist
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw enable
```

---

## 🔐 Sicherheits-Empfehlungen

### 1. RabbitMQ und PostgreSQL auf Worker-IPs beschränken

**Status:** ✅ Wird automatisch durch `setup-firewall.sh` konfiguriert!

**Manuelle Prüfung:**
```bash
# Auf asciisky.eibrain.org
sudo ufw status numbered | grep -E '5672|5432'

# Sollte zeigen:
# [X] 5672/tcp ALLOW IN <Worker-B-IP>
# [Y] 5672/tcp ALLOW IN <Worker-C-IP>
# [Z] 5432/tcp ALLOW IN <Worker-B-IP>
# [W] 5432/tcp ALLOW IN <Worker-C-IP>
```

**Falls manuell konfiguriert werden muss:**
```bash
# IPs automatisch ermitteln
WORKER_B_IP=$(dig +short rabbit-b.eibrain.org | tail -n1)
WORKER_C_IP=$(dig +short rabbit-c.eibrain.org | tail -n1)

# Regeln hinzufügen
sudo ufw allow from $WORKER_B_IP to any port 5672 proto tcp comment 'RabbitMQ from Worker-B'
sudo ufw allow from $WORKER_C_IP to any port 5672 proto tcp comment 'RabbitMQ from Worker-C'
sudo ufw allow from $WORKER_B_IP to any port 5432 proto tcp comment 'PostgreSQL from Worker-B'
sudo ufw allow from $WORKER_C_IP to any port 5432 proto tcp comment 'PostgreSQL from Worker-C'
```

### 2. RabbitMQ Management UI absichern

**Status:** ✅ Wird automatisch durch `setup-firewall.sh` auf localhost beschränkt!

**Zugriff via SSH-Tunnel (empfohlen):**
```bash
# Von deinem lokalen Rechner
ssh -L 15672:localhost:15672 asciisky.eibrain.org

# Dann im Browser öffnen:
http://localhost:15672

User: admin
Password: <RABBITMQ_PASSWORD aus .env>
```

**Prüfung:**
```bash
# Auf asciisky.eibrain.org
sudo ufw status | grep 15672

# Sollte zeigen:
# 15672/tcp ALLOW IN 127.0.0.1
```

### 3. SSH absichern (Optional)

**Hinweis:** SSH wird als bereits konfiguriert vorausgesetzt!

**Optionale Verbesserungen:**
```bash
# Rate Limiting aktivieren
sudo ufw limit 22/tcp comment 'SSH with rate limiting'

# Nur von vertrauenswürdigen IPs (falls gewünscht)
sudo ufw delete allow 22/tcp
sudo ufw allow from <admin-IP> to any port 22 proto tcp comment 'SSH from Admin'
```

### 4. Port 8000 (FastAPI) nicht öffentlich

**Status:** ✅ Port 8000 sollte NICHT öffentlich erreichbar sein!

**Prüfung:**
```bash
# Auf asciisky.eibrain.org
sudo ufw status | grep 8000

# Sollte NICHTS zeigen oder nur localhost
```

**Warum?**
- Web UI läuft über nginx (Port 80/443)
- nginx leitet intern zu Port 8000 weiter
- Port 8000 muss nicht öffentlich sein

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
# Prüfe nginx
sudo systemctl status nginx

# Prüfe nginx Konfiguration
sudo nginx -t

# Prüfe ob Port 80/443 offen ist
sudo ufw status | grep -E '80|443'

# Prüfe ob Web-Container läuft
docker ps | grep asciisky-web

# Prüfe ob Port 8000 intern erreichbar ist
curl http://localhost:8000/api/celestial?lat=48.2&lon=16.3
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

**Hauptserver (asciisky.eibrain.org):**
- [ ] `setup-firewall.sh` ausgeführt
- [ ] Port 80/443 (nginx) öffentlich erreichbar
- [ ] Port 8000 (FastAPI) NICHT öffentlich
- [ ] RabbitMQ (Port 5672) NUR von Worker-B/C IPs erreichbar
- [ ] PostgreSQL (Port 5432) NUR von Worker-B/C IPs erreichbar
- [ ] RabbitMQ UI (Port 15672) NUR via SSH-Tunnel
- [ ] UFW Status geprüft: `sudo ufw status verbose`

**Worker-Server (rabbit-b/c):**
- [ ] Keine Firewall-Änderungen nötig (ausgehende Verbindungen erlaubt)
- [ ] Verbindung zu RabbitMQ getestet: `telnet asciisky.eibrain.org 5672`
- [ ] Verbindung zu PostgreSQL getestet: `telnet asciisky.eibrain.org 5432`

**Tests:**
- [ ] Web UI von extern erreichbar: `http://asciisky.eibrain.org`
- [ ] RabbitMQ UI via SSH-Tunnel: `ssh -L 15672:localhost:15672 asciisky.eibrain.org`
- [ ] Worker können Tasks verarbeiten (RabbitMQ UI prüfen)
- [ ] PostgreSQL von Workern erreichbar

---

## 🔗 Weiterführende Links

- [UFW Dokumentation](https://help.ubuntu.com/community/UFW)
- [Docker und UFW](https://github.com/chaifeng/ufw-docker)
- [iptables Grundlagen](https://www.netfilter.org/documentation/)
