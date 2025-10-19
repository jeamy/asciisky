# ASCII Sky - Production Deployment Guide

## 🏗️ Multi-Host Architektur

### Server-Übersicht

```
┌─────────────────────────────────────────────────────────────┐
│ asciisky.eibrain.org (Hauptserver)                          │
│ ┌─────────────┐  ┌──────────────┐  ┌──────────────┐        │
│ │   Web UI    │  │  RabbitMQ    │  │  PostgreSQL  │        │
│ │   (Flask)   │  │   (4.1)      │  │    (16)      │        │
│ │   Port 8000 │  │   Port 5672  │  │   Port 5432  │        │
│ └─────────────┘  └──────────────┘  └──────────────┘        │
│ ┌─────────────┐                                             │
│ │Data Updater │                                             │
│ │  (Nightly)  │                                             │
│ └─────────────┘                                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ AMQP + PostgreSQL
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
        ▼                                       ▼
┌──────────────────────┐            ┌──────────────────────┐
│ rabbit-b.eibrain.org │            │ rabbit-c.eibrain.org │
│ ┌──────────────────┐ │            │ ┌──────────────────┐ │
│ │ Asteroid Worker 1│ │            │ │ Asteroid Worker 3│ │
│ │ Asteroid Worker 2│ │            │ │ Asteroid Worker 4│ │
│ │ Comet Worker 1   │ │            │ │ Comet Worker 3   │ │
│ │ Comet Worker 2   │ │            │ │ Comet Worker 4   │ │
│ └──────────────────┘ │            │ └──────────────────┘ │
└──────────────────────┘            └──────────────────────┘
```

### Komponenten-Verteilung

| Server | Komponenten | Ports | Zweck |
|--------|-------------|-------|-------|
| **asciisky.eibrain.org** | Web, RabbitMQ, PostgreSQL, Data Updater | 8000, 5672, 15672, 5432 | Hauptserver mit UI und Datenbanken |
| **rabbit-b.eibrain.org** | 4 Worker (2 Asteroid, 2 Comet) | - | Worker-Pool B |
| **rabbit-c.eibrain.org** | 4 Worker (2 Asteroid, 2 Comet) | - | Worker-Pool C |

**Gesamt: 8 Worker** (4 Asteroid + 4 Comet)

---

## 📋 Voraussetzungen

### Auf allen Servern

- Docker Engine 24.0+
- Docker Compose v2.20+
- SSH-Zugriff (für Remote-Deployment)
- Mindestens 2 GB RAM pro Server
- 10 GB freier Speicher

### Netzwerk-Anforderungen

**Firewall-Regeln:**

```bash
# asciisky.eibrain.org → Internet
Ausgehend: 80, 443 (HTTP/HTTPS für Daten-Downloads)

# asciisky.eibrain.org → rabbit-b/c.eibrain.org
Eingehend: 5432 (PostgreSQL), 5672 (RabbitMQ)

# rabbit-b/c.eibrain.org → asciisky.eibrain.org
Ausgehend: 5432 (PostgreSQL), 5672 (RabbitMQ)
```

---

## 🚀 Installation

### 1. Vorbereitung

```bash
# Auf dem Entwicklungsrechner (LOKAL)
cd /path/to/asciisky

# Erstelle .env aus Vorlage
cp .env.example .env

# Bearbeite .env und setze sichere Passwörter
nano .env
```

**⚠️ WICHTIG: .env Konfiguration**

Die `.env` Datei wird **automatisch** auf alle Server kopiert!

**Setze starke Passwörter für:**
- `POSTGRES_PASSWORD` - **Muss auf allen Servern identisch sein!**
- `RABBITMQ_PASSWORD` - **Muss auf allen Servern identisch sein!**
- `SESSION_SECRET` - Nur für Hauptserver (generiere mit: `openssl rand -hex 32`)

**Warum identische Passwörter?**
- Worker-Server (rabbit-b/c) verbinden sich zu PostgreSQL auf Hauptserver
- Worker-Server (rabbit-b/c) verbinden sich zu RabbitMQ auf Hauptserver
- Authentifizierung funktioniert nur mit gleichen Credentials

**Beispiel .env:**
```bash
# Gleiche Passwörter auf ALLEN Servern
POSTGRES_PASSWORD=SuperSicheres_PG_Passwort_123!
RABBITMQ_PASSWORD=SuperSicheres_RMQ_Passwort_456!
SESSION_SECRET=a1b2c3d4e5f6...  # openssl rand -hex 32

# Deployment-Optionen
SETUP_WORKER_B=true
SETUP_WORKER_C=true
```

### 2. SSH-Zugriff einrichten

```bash
# SSH-Keys zu Worker-Servern kopieren
ssh-copy-id rabbit-b.eibrain.org
ssh-copy-id rabbit-c.eibrain.org

# Teste Verbindung
ssh rabbit-b.eibrain.org "echo 'Connection OK'"
ssh rabbit-c.eibrain.org "echo 'Connection OK'"
```

### 3. Automatisches Deployment

```bash
# Setup-Skript ausführbar machen
chmod +x scripts/setup-production.sh

# Deployment starten
./scripts/setup-production.sh
```

Das Skript:
1. ✅ Baut Docker-Images
2. ✅ Startet PostgreSQL und RabbitMQ auf asciisky.eibrain.org
3. ✅ Initialisiert PostgreSQL-Schema
4. ✅ Erstellt RabbitMQ-Queues
5. ✅ **Kopiert .env auf rabbit-b.eibrain.org** (automatisch via scp)
6. ✅ Deployed Worker auf rabbit-b.eibrain.org
7. ✅ **Kopiert .env auf rabbit-c.eibrain.org** (automatisch via scp)
8. ✅ Deployed Worker auf rabbit-c.eibrain.org

**Wichtig:** Die `.env` Datei wird automatisch von deinem lokalen Rechner auf alle Server kopiert. Du musst sie **nicht manuell** auf jeden Server kopieren!

---

## 🔧 Manuelle Installation

### Auf asciisky.eibrain.org

```bash
# 1. Repository klonen
git clone <repo-url> ~/asciisky
cd ~/asciisky

# 2. .env erstellen
cp .env.example .env
nano .env

# 3. Services starten
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d

# 4. RabbitMQ Queues einrichten
./scripts/setup-rabbitmq-queues.sh

# 5. Initiale Daten laden
docker exec asciisky-data-updater python nightly_data_updater.py
```

### Auf rabbit-b.eibrain.org

```bash
# 1. Repository klonen
git clone <repo-url> ~/asciisky
cd ~/asciisky

# 2. .env von Hauptserver kopieren
scp asciisky.eibrain.org:~/asciisky/.env .env

# 3. Worker starten
docker compose -f docker-compose.worker-b.yml build
docker compose -f docker-compose.worker-b.yml up -d
```

### Auf rabbit-c.eibrain.org

```bash
# 1. Repository klonen
git clone <repo-url> ~/asciisky
cd ~/asciisky

# 2. .env von Hauptserver kopieren
scp asciisky.eibrain.org:~/asciisky/.env .env

# 3. Worker starten
docker compose -f docker-compose.worker-c.yml build
docker compose -f docker-compose.worker-c.yml up -d
```

---

## 🔍 Monitoring

### Service-Status prüfen

```bash
# Auf asciisky.eibrain.org
docker compose -f docker-compose.production.yml ps
docker compose -f docker-compose.production.yml logs -f web

# Auf rabbit-b.eibrain.org
ssh rabbit-b.eibrain.org "cd ~/asciisky && docker compose -f docker-compose.worker-b.yml ps"

# Auf rabbit-c.eibrain.org
ssh rabbit-c.eibrain.org "cd ~/asciisky && docker compose -f docker-compose.worker-c.yml ps"
```

### RabbitMQ Management UI

```
URL: http://asciisky.eibrain.org:15672
User: admin
Password: <RABBITMQ_PASSWORD aus .env>
```

**Prüfe:**
- ✅ 8 Worker verbunden (Connections)
- ✅ Queues: `asteroid.compute`, `comet.compute`
- ✅ Messages werden verarbeitet

### PostgreSQL Status

```bash
# Verbindung testen
docker exec asciisky-postgres psql -U asciisky -d asciisky -c "SELECT version();"

# Datenbank-Statistiken
docker exec asciisky-postgres psql -U asciisky -d asciisky -c "
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"

# Cache-Statistiken
docker exec asciisky-postgres psql -U asciisky -d asciisky -c "SELECT * FROM cache_statistics;"
```

---

## 🔄 Updates

### Code-Update auf allen Servern

```bash
# Auf Entwicklungsrechner
cd /path/to/asciisky

# Update-Skript erstellen
cat > scripts/update-production.sh << 'EOF'
#!/bin/bash
set -e

echo "🔄 Updating ASCII Sky on all servers..."

# Hauptserver
echo "📦 Updating asciisky.eibrain.org..."
git pull
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d

# Worker B
echo "📦 Updating rabbit-b.eibrain.org..."
ssh rabbit-b.eibrain.org "cd ~/asciisky && git pull && docker compose -f docker-compose.worker-b.yml build && docker compose -f docker-compose.worker-b.yml up -d"

# Worker C
echo "📦 Updating rabbit-c.eibrain.org..."
ssh rabbit-c.eibrain.org "cd ~/asciisky && git pull && docker compose -f docker-compose.worker-c.yml build && docker compose -f docker-compose.worker-c.yml up -d"

echo "✅ Update complete!"
EOF

chmod +x scripts/update-production.sh
./scripts/update-production.sh
```

---

## 🛠️ Wartung

### Cache leeren

```bash
# PostgreSQL Cache leeren
docker exec asciisky-postgres psql -U asciisky -d asciisky -c "
DELETE FROM cached_positions WHERE expires_at < CURRENT_TIMESTAMP;
"
```

### Logs rotieren

```bash
# Docker Logs begrenzen (in docker-compose*.yml)
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

### Backup

```bash
# PostgreSQL Backup
docker exec asciisky-postgres pg_dump -U asciisky asciisky > backup_$(date +%Y%m%d).sql

# Restore
cat backup_20250119.sql | docker exec -i asciisky-postgres psql -U asciisky asciisky
```

---

## 🚨 Troubleshooting

### Worker verbinden sich nicht

```bash
# Prüfe Netzwerk-Verbindung
ssh rabbit-b.eibrain.org "telnet asciisky.eibrain.org 5672"

# Prüfe RabbitMQ Logs
docker logs asciisky-rabbitmq

# Prüfe Worker Logs
ssh rabbit-b.eibrain.org "docker logs asciisky-asteroid-worker-1"
```

### PostgreSQL Verbindungsfehler

```bash
# Prüfe PostgreSQL läuft
docker exec asciisky-postgres pg_isready -U asciisky

# Prüfe Firewall
sudo ufw status

# Prüfe PostgreSQL Config
docker exec asciisky-postgres cat /var/lib/postgresql/data/pg_hba.conf
```

### Performance-Probleme

```bash
# PostgreSQL Connections
docker exec asciisky-postgres psql -U asciisky -d asciisky -c "
SELECT count(*) FROM pg_stat_activity WHERE state = 'active';
"

# RabbitMQ Queue Länge
docker exec asciisky-rabbitmq rabbitmqctl list_queues name messages consumers
```

---

## 📊 Performance-Erwartungen

| Metrik | Wert |
|--------|------|
| Worker-Durchsatz | ~50-100 Berechnungen/Minute |
| API-Response-Zeit | < 200ms (cached) |
| Cache-Hit-Rate | > 90% |
| PostgreSQL Connections | < 20 gleichzeitig |
| RabbitMQ Messages/sec | ~10-20 |

---

## 🔐 Sicherheit

### Empfohlene Maßnahmen

1. **Firewall konfigurieren**
   ```bash
   # Nur notwendige Ports öffnen
   sudo ufw allow 8000/tcp   # Web UI
   sudo ufw allow 15672/tcp  # RabbitMQ UI (nur aus vertrautem Netz)
   sudo ufw enable
   ```

2. **PostgreSQL Zugriff beschränken**
   - Nur von Worker-IPs erlauben
   - SSL/TLS für Verbindungen aktivieren

3. **RabbitMQ absichern**
   - Starkes Passwort verwenden
   - Management UI nur über VPN/SSH-Tunnel

4. **Regelmäßige Updates**
   ```bash
   docker compose pull
   docker compose up -d
   ```

---

## 📞 Support

Bei Problemen:
1. Prüfe Logs: `docker compose logs -f`
2. Prüfe RabbitMQ UI: http://asciisky.eibrain.org:15672
3. Prüfe PostgreSQL: `docker exec asciisky-postgres psql -U asciisky`
