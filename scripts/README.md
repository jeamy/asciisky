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
- ✅ Optional: Lädt initiale Daten

**Verwendung:**
```bash
./scripts/setup-dev.sh
```

**Voraussetzungen:**
- Docker & Docker Compose v2
- Keine weiteren Abhängigkeiten

**Services nach Setup:**
- Web UI: http://localhost:8000
- RabbitMQ UI: http://localhost:15672
- PostgreSQL: localhost:5432

---

## 🏭 Production (Multi-Host)

### setup-production.sh

**Zweck:** Production-Deployment auf 3 Servern

**Was es macht:**
- ✅ Deployed auf asciisky.eibrain.org (Hauptserver)
- ✅ Deployed auf rabbit-b.eibrain.org (Worker-Server B)
- ✅ Deployed auf rabbit-c.eibrain.org (Worker-Server C)
- ✅ Richtet PostgreSQL ein
- ✅ Richtet RabbitMQ Queues ein

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
SETUP_WORKER_B=true        # Worker B deployen?
SETUP_WORKER_C=true        # Worker C deployen?
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

**Zweck:** UFW Firewall auf Servern einrichten

**Was es macht:**
- ✅ Konfiguriert UFW basierend auf Server-Rolle
- ✅ Öffnet notwendige Ports
- ✅ Setzt sichere Defaults

**Verwendung:**
```bash
# Auf JEDEM Server einzeln ausführen
sudo ./scripts/setup-firewall.sh

# Wähle Server-Rolle:
# 1) Hauptserver (asciisky.eibrain.org)
# 2) Worker Server B (rabbit-b.eibrain.org)
# 3) Worker Server C (rabbit-c.eibrain.org)
```

**Ports:**
- Hauptserver: 22, 8000, 5672, 5432, 15672
- Worker-Server: 22

---

### init-postgres.sql

**Zweck:** PostgreSQL Schema initialisieren

**Was es macht:**
- ✅ Erstellt Tabellen (asteroid_elements, comet_elements, cached_positions, data_updates)
- ✅ Erstellt Indizes
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
   
3. Firewall (einmalig pro Server):
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
- [ ] SSH-Keys zu allen Servern kopiert (`ssh-copy-id`)
- [ ] Docker auf allen Servern installiert
- [ ] Firewall-Regeln geprüft (Ports 5432, 5672 offen zwischen Servern)
- [ ] DNS/Hostnames konfiguriert (asciisky.eibrain.org, rabbit-b/c.eibrain.org)

### Nach Production-Deployment

- [ ] RabbitMQ UI erreichbar (http://asciisky.eibrain.org:15672)
- [ ] Web UI erreichbar (http://asciisky.eibrain.org:8000)
- [ ] 11 Worker-Connections in RabbitMQ (8 compute + 3 precompute)
- [ ] Queues erstellt (asteroid.compute, comet.compute, precompute.tasks)
- [ ] PostgreSQL erreichbar von Worker-Servern
- [ ] Logs prüfen: `docker compose -f docker-compose.production.yml logs -f`

---

---

## ❓ FAQ

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
