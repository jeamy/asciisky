# ASCII Sky - Setup Scripts

## 📋 Übersicht

Automatisierte Setup- und Deployment-Skripte für ASCII Sky.

---

## 🚀 Development (Lokal)

### setup-dev.sh

**Zweck:** Lokale Entwicklungsumgebung einrichten

**Was es macht:**
- ✅ Erstellt `.env` falls nicht vorhanden
- ✅ Baut Docker Images
- ✅ Startet alle Services (Web, RabbitMQ, PostgreSQL, Worker)
- ✅ Richtet RabbitMQ Queues ein
- ✅ Wartet auf Datenbank-Initialisierung
- ✅ Lädt initiale Daten automatisch (via data_updater)

**Verwendung:**
```bash
./scripts/setup-dev.sh
```

**Voraussetzungen:**
- Docker & Docker Compose v2
- Keine weiteren Abhängigkeiten

**Services nach Setup:**
- Web UI: http://localhost:8000
- RabbitMQ UI: http://localhost:15672 (admin/password)
- PostgreSQL: localhost:5432

**Worker:**
- 4 Precompute Workers (skalierbar via `PRECOMPUTE_WORKERS` in .env)
- 2 Asteroid Workers (skalierbar via `ASTEROID_WORKERS` in .env)
- 2 Comet Workers (skalierbar via `COMET_WORKERS` in .env)

---

## 🏭 Production (Multi-Host)

### setup-production.sh

**Zweck:** Production-Deployment auf 3 Servern

**Was es macht:**
- ✅ Deployed auf asciisky.eibrain.org (Hauptserver: Web, PostgreSQL, RabbitMQ, 4 Precompute Workers)
- ✅ Deployed auf rabbit-b.eibrain.org (Worker-Server B: 4 Precompute + 2 Asteroid + 2 Comet Workers)
- ✅ Deployed auf rabbit-c.eibrain.org (Worker-Server C: 4 Precompute + 2 Asteroid + 2 Comet Workers)
- ✅ Richtet PostgreSQL ein (automatisch via init-postgres.sql)
- ✅ Richtet RabbitMQ Queues ein (automatisch)
- ✅ Kopiert .env automatisch auf alle Server

**Verwendung:**
```bash
# 1. .env erstellen und anpassen (LOKAL auf deinem Rechner)
cp .env.example .env
nano .env

# WICHTIG: Setze SICHERE Passwörter!
# Diese Passwörter werden auf ALLE Server kopiert

# 2. SSH-Keys zu Worker-Servern kopieren
ssh-copy-id rabbit-b.eibrain.org
ssh-copy-id rabbit-c.eibrain.org

# 3. Setup ausführen (kopiert .env automatisch auf alle Server)
./scripts/setup-production.sh
```

**Voraussetzungen:**
- SSH-Zugriff auf alle 3 Server
- Docker auf allen Servern installiert
- `.env` **lokal** mit Passwörtern konfiguriert

**Environment Variables (.env):**
```bash
# WICHTIG: Gleiche Passwörter auf ALLEN Servern!
POSTGRES_PASSWORD=...      # Muss identisch sein (Worker verbinden sich zu Hauptserver)
RABBITMQ_PASSWORD=...      # Muss identisch sein (Worker verbinden sich zu Hauptserver)
SESSION_SECRET=...         # Nur für Hauptserver (Web UI)

# Deployment-Optionen
SETUP_WORKER_B=true        # Worker B deployen?
SETUP_WORKER_C=true        # Worker C deployen?

# Worker-Skalierung (Hauptserver)
PRECOMPUTE_WORKERS=4
ASTEROID_WORKERS=2
COMET_WORKERS=2

# Worker-Skalierung (Worker-Server B)
PRECOMPUTE_WORKERS_B=4
ASTEROID_WORKERS_B=2
COMET_WORKERS_B=2

# Worker-Skalierung (Worker-Server C)
PRECOMPUTE_WORKERS_C=4
ASTEROID_WORKERS_C=2
COMET_WORKERS_C=2

# Precompute Settings
ASCII_SKY_PRECOMPUTE_HOURS=720  # 30 Tage vorausberechnen
```

**Was passiert mit .env?**
- ✅ Du erstellst `.env` **lokal** (auf deinem Entwicklungsrechner)
- ✅ `setup-production.sh` kopiert sie **automatisch** auf alle 3 Server
- ✅ Alle Server verwenden die **gleichen Passwörter** (wichtig für Verbindungen!)

---

### update-production.sh

**Zweck:** Code-Updates auf allen Servern

**Was es macht:**
- ✅ Git Pull auf allen Servern
- ✅ Rebuild Docker Images
- ✅ Rolling Restart (kein Downtime)

**Verwendung:**
```bash
./scripts/update-production.sh
```

**Environment Variables (.env):**
```bash
UPDATE_WORKER_B=true  # Optional: Worker B updaten
UPDATE_WORKER_C=true  # Optional: Worker C updaten
```

---

## 🔧 Utility Scripts

### setup-rabbitmq-queues.sh

**Zweck:** RabbitMQ Queues einrichten

**Was es macht:**
- ✅ Erstellt Exchange `computation.direct`
- ✅ Erstellt Queue `asteroid.compute` (Quorum)
- ✅ Erstellt Queue `comet.compute` (Quorum)
- ✅ Erstellt Queue `precompute.tasks` (Quorum, Priority)
- ✅ Erstellt Result/Status Queues

**Verwendung:**
```bash
# Automatisch (wird von setup-*.sh aufgerufen)
./scripts/setup-rabbitmq-queues.sh

# Manuell mit Custom-Container
RABBITMQ_CONTAINER=my-rabbitmq ./scripts/setup-rabbitmq-queues.sh
```

**Environment Variables:**
```bash
RABBITMQ_CONTAINER=asciisky-rabbitmq  # Container-Name
RABBITMQ_USER=admin                   # RabbitMQ User
RABBITMQ_PASSWORD=...                 # RabbitMQ Passwort
```

---

### setup-firewall.sh

**Zweck:** UFW Firewall auf Hauptserver einrichten

**Was es macht:**
- ✅ Ermittelt automatisch Worker-IPs via DNS
- ✅ Beschränkt Port 5672 (RabbitMQ) auf Worker-B/C IPs
- ✅ Beschränkt Port 5432 (PostgreSQL) auf Worker-B/C IPs
- ✅ Beschränkt Port 15672 (RabbitMQ UI) auf localhost (SSH-Tunnel)
- ✅ Worker-Server benötigen KEINE Firewall-Änderungen

**Verwendung:**
```bash
# NUR auf asciisky.eibrain.org ausführen:
sudo ./scripts/setup-firewall.sh
```

**Ports (Hauptserver):**
- 80/443: Web UI (nginx) - öffentlich
- 8000: FastAPI - intern (nginx)
- 5672: RabbitMQ - NUR Worker-B/C IPs
- 5432: PostgreSQL - NUR Worker-B/C IPs
- 15672: RabbitMQ UI - NUR localhost (SSH-Tunnel)

**Worker-Server:**
- Keine Firewall-Änderungen nötig
- Ausgehende Verbindungen bereits erlaubt

---

### init-postgres.sql

**Zweck:** PostgreSQL Schema initialisieren

**Was es macht:**
- ✅ Erstellt Tabellen (asteroid_dataframes, comet_dataframes, cached_positions, data_updates)
- ✅ Erstellt Indizes für schnelle Lookups
- ✅ Erstellt Views (cache_statistics)
- ✅ Erstellt Functions (cleanup_expired_positions)

**Verwendung:**
```bash
# Automatisch (beim ersten PostgreSQL-Start via docker-entrypoint-initdb.d)

# Manuell:
docker exec -i asciisky-postgres psql -U asciisky -d asciisky < scripts/init-postgres.sql
```

---

## 📊 Workflow-Übersicht

### Development Workflow

```
1. ./scripts/setup-dev.sh
   ↓
2. Code ändern (auto-reload)
   ↓
3. Testen auf http://localhost:8000
   ↓
4. Git commit & push
```

### Production Deployment Workflow

```
1. Erstmaliges Setup:
   ./scripts/setup-production.sh
   
2. Code-Updates:
   git push
   ./scripts/update-production.sh
   
3. Firewall (einmalig auf Hauptserver):
   ssh asciisky.eibrain.org
   sudo ./scripts/setup-firewall.sh
```

---

## 🔍 Troubleshooting

### Problem: setup-dev.sh schlägt fehl

**Lösung:**
```bash
# Docker läuft?
docker info

# Alte Container stoppen
docker compose down -v

# Neu starten
./scripts/setup-dev.sh
```

### Problem: setup-production.sh - SSH-Fehler

**Lösung:**
```bash
# SSH-Keys kopieren
ssh-copy-id rabbit-b.eibrain.org
ssh-copy-id rabbit-c.eibrain.org

# Verbindung testen
ssh rabbit-b.eibrain.org "echo OK"
```

### Problem: RabbitMQ Queues nicht erstellt

**Lösung:**
```bash
# Manuell erstellen
export RABBITMQ_CONTAINER=asciisky-rabbitmq
./scripts/setup-rabbitmq-queues.sh

# Prüfen
docker exec asciisky-rabbitmq rabbitmqctl list_queues
```

---

## 📝 Checkliste

### Vor erstem Production-Deployment

- [ ] `.env` **lokal** erstellt und **sichere** Passwörter gesetzt
- [ ] **Gleiche Passwörter** in .env (POSTGRES_PASSWORD, RABBITMQ_PASSWORD)
- [ ] Worker-Skalierung in .env konfiguriert (PRECOMPUTE_WORKERS, etc.)
- [ ] SSH-Keys zu allen Servern kopiert (`ssh-copy-id`)
- [ ] Docker auf allen Servern installiert
- [ ] DNS/Hostnames konfiguriert (asciisky.eibrain.org, rabbit-b/c.eibrain.org)
- [ ] nginx auf Hauptserver konfiguriert (Port 80/443 → 8000)

### Nach Production-Deployment

- [ ] Firewall konfiguriert: `sudo ./scripts/setup-firewall.sh` (auf Hauptserver)
- [ ] RabbitMQ UI via SSH-Tunnel: `ssh -L 15672:localhost:15672 asciisky.eibrain.org`
- [ ] Web UI erreichbar: http://asciisky.eibrain.org (nginx)
- [ ] 20 Worker-Connections in RabbitMQ (12 Precompute + 4 Asteroid + 4 Comet)
- [ ] Queues erstellt: `precompute.tasks`, `asteroid.compute`, `comet.compute`
- [ ] PostgreSQL erreichbar von Worker-Servern: `telnet asciisky.eibrain.org 5432`
- [ ] Logs prüfen: `docker compose -f docker-compose.production.yml logs -f`

---

---

## ❓ FAQ

### Wie viele Worker werden deployed?

**Default (12 Precompute + 4 Asteroid + 4 Comet = 20 Worker):**
- Hauptserver: 4 Precompute Workers
- Worker-B: 4 Precompute + 2 Asteroid + 2 Comet Workers
- Worker-C: 4 Precompute + 2 Asteroid + 2 Comet Workers

**Skalierung via .env:**
```bash
PRECOMPUTE_WORKERS=8        # Hauptserver: 8 statt 4
PRECOMPUTE_WORKERS_B=8      # Worker-B: 8 statt 4
PRECOMPUTE_WORKERS_C=8      # Worker-C: 8 statt 4
# = 24 Precompute Workers total
```

### Muss .env auf allen Servern vorhanden sein?

**Ja!** Aber du musst sie **nicht manuell** kopieren.

**Automatisch (empfohlen):**
```bash
# .env wird automatisch kopiert
./scripts/setup-production.sh
```

**Manuell (falls nötig):**
```bash
scp .env asciisky.eibrain.org:~/asciisky/.env
scp .env rabbit-b.eibrain.org:~/asciisky/.env
scp .env rabbit-c.eibrain.org:~/asciisky/.env
```

### Müssen die Passwörter auf allen Servern gleich sein?

**Ja!** Worker-Server verbinden sich zu PostgreSQL/RabbitMQ auf dem Hauptserver.

```bash
# .env auf ALLEN Servern:
POSTGRES_PASSWORD=DasGleichePasswort123!
RABBITMQ_PASSWORD=DasGleichePasswort456!
```

### Wie greife ich auf RabbitMQ UI zu?

**Via SSH-Tunnel (sicher):**
```bash
# Von deinem lokalen Rechner:
ssh -L 15672:localhost:15672 asciisky.eibrain.org

# Dann im Browser öffnen:
http://localhost:15672

User: admin
Password: <RABBITMQ_PASSWORD aus .env>
```

**Warum nicht direkt?**
- Port 15672 ist nur auf localhost beschränkt (Firewall)
- Sicherer: Kein öffentlicher Zugriff
- SSH-Tunnel verschlüsselt die Verbindung

### Kann ich verschiedene .env für jeden Server haben?

**Ja**, aber die **Passwörter müssen identisch** sein:

```bash
# .env.main (asciisky.eibrain.org)
POSTGRES_PASSWORD=GleichesPasswort123!
RABBITMQ_PASSWORD=GleichesPasswort456!
SESSION_SECRET=abc123...
SETUP_WORKER_B=true

# .env.worker-b (rabbit-b.eibrain.org)
POSTGRES_PASSWORD=GleichesPasswort123!  # ← GLEICH!
RABBITMQ_PASSWORD=GleichesPasswort456!  # ← GLEICH!
# SESSION_SECRET nicht nötig (kein Web UI)
```

### Was passiert wenn Passwörter unterschiedlich sind?

**Worker können sich nicht verbinden:**
```
Error: FATAL: password authentication failed for user "asciisky"
Error: Access refused for user 'admin'
```

**Lösung:** Gleiche Passwörter in allen `.env` Dateien setzen.

---

## 🔗 Weiterführende Dokumentation

- [Production Deployment Guide](../doc/PRODUCTION_DEPLOYMENT.md)
- [Firewall Setup](../doc/FIREWALL_SETUP.md)
- [Precompute RabbitMQ](../doc/PRECOMPUTE_RABBITMQ.md)
