# RabbitMQ Migration - Lokales Testing auf einem Rechner

## Übersicht

Diese Anleitung zeigt, wie du die RabbitMQ-Migration **komplett auf einem Rechner** testen kannst.

## ⚠️ WICHTIG: Asynchrone Architektur

Die RabbitMQ-Integration arbeitet **asynchron mit Cache**:

1. **API-Request** → Liest aus Cache (SQLite + Pickle)
2. **Cache Miss** → Triggert RabbitMQ Background Task + Return `{"bodies": {}}`
3. **Worker** → Berechnet Daten (2-3 Min) + Speichert in Cache
4. **Frontend** → Pollt nach 60s → Cache hat Daten → Anzeige

**Keine Timeouts mehr!** Worker können so lange rechnen wie nötig.

## Voraussetzungen

- Docker und Docker Compose installiert
- Ports 5672 (RabbitMQ) und 15672 (Management UI) frei

## Quick Start (3 Befehle!)

```bash
# 1. Alles starten (RabbitMQ + 4 Worker: 2x Asteroid, 2x Comet)
docker compose up -d

# 2. Queues erstellen
./scripts/setup-rabbitmq-queues.sh

# 3. Testen!
curl "http://localhost:8000/api/bright_asteroids?lat=48.2&lon=16.3"
curl "http://localhost:8000/api/comets?lat=48.2&lon=16.3"
```

**Hinweis:** Celestial & Zodiac nutzen KEIN RabbitMQ (zu schnell, < 1s)

Das war's! 🎉

## Detaillierte Anleitung

### Schritt 1: RabbitMQ und alle Services starten

```bash
# Startet automatisch:
# - RabbitMQ Container
# - Web Service (100% RabbitMQ, kein Fallback)
# - Alle 6 Worker (asteroid, comet, celestial, constellation)

docker compose up -d
```

**Was passiert:**
- RabbitMQ startet auf Port 5672 (AMQP) und 15672 (Management UI)
- Web Service wartet auf RabbitMQ (healthcheck)
- 6 Worker starten und verbinden sich mit RabbitMQ

### Schritt 2: Queues erstellen

```bash
# Automatisches Setup-Script
./scripts/setup-rabbitmq-queues.sh

# Oder manuell:
docker exec asciisky-rabbitmq rabbitmqadmin declare exchange \
  name=computation.direct type=direct durable=true

docker exec asciisky-rabbitmq rabbitmqadmin declare queue \
  name=asteroid.compute durable=true \
  arguments='{"x-queue-type":"quorum","x-max-priority":10}'

# ... (weitere Queues)
```

### Schritt 3: Testen

#### 3.1 RabbitMQ Management UI öffnen

```bash
# Browser öffnen
open http://localhost:15672

# Login:
# Username: admin
# Password: password
```

**Prüfen:**
- Queues → Sollten 6 Queues sichtbar sein
- Connections → Sollten 6 Worker-Connections sehen
- Exchanges → `computation.direct` sollte existieren

#### 3.2 API testen

```bash
# Asteroid-Daten abrufen (100% über RabbitMQ)
curl "http://localhost:8000/api/bright_asteroids?lat=48.2&lon=16.3&elevation=170"

# Mehrmals aufrufen
for i in {1..10}; do
  curl -s "http://localhost:8000/api/bright_asteroids?lat=48.2&lon=16.3" > /dev/null
  echo "Request $i done"
done
```

#### 3.3 Logs prüfen

```bash
# Web Service Logs (Feature Flag Entscheidungen)
docker compose logs -f web | grep -E "(Using RabbitMQ|Using old|Falling back)"

# Worker Logs (Task-Verarbeitung)
docker compose logs -f asteroid-worker-1

# Alle Worker Logs
docker compose logs -f | grep "worker-"

# RabbitMQ Logs
docker logs asciisky-rabbitmq -f
```

**Was du sehen solltest:**
```
web-1  | Using RabbitMQ for asteroids: lat=48.2, lon=16.3
asteroid-worker-1  | Processing task asteroid_1729281234_abc123
asteroid-worker-1  | Task asteroid_1729281234_abc123 completed in 2.34s
```

### Schritt 4: Konfiguration anpassen (optional)

Du kannst die Konfiguration in `docker-compose.yml` anpassen:

```yaml
# docker-compose.yml - Web Service Environment:
services:
  web:
    environment:
      - RABBITMQ_PERCENTAGE=100         # 100% Traffic (Standard)
      - FALLBACK_TO_OLD_ON_ERROR=false  # Kein Fallback (Standard)
      - RABBITMQ_TIMEOUT=30             # Timeout in Sekunden
```

Nach Änderung:
```bash
docker compose up -d web
```

## Monitoring

### Queue-Status prüfen

```bash
# Alle Queues anzeigen
docker exec asciisky-rabbitmq rabbitmqctl list_queues name messages consumers

# Erwartete Ausgabe:
# asteroid.compute     0    2
# comet.compute        0    2
# celestial.compute    0    1
# constellation.compute 0   1
```

### Worker-Status prüfen

```bash
# Alle Worker anzeigen
docker compose ps | grep worker

# Sollte zeigen:
# asteroid-worker-1      running
# asteroid-worker-2      running
# comet-worker-1         running
# comet-worker-2         running
# celestial-worker-1     running
# constellation-worker-1 running
```

### Performance-Vergleich

```bash
# Test-Script für Performance-Vergleich
cat > test-performance.sh << 'EOF'
#!/bin/bash

echo "Testing OLD architecture (RABBITMQ_PERCENTAGE=0)..."
# Temporär auf 0% setzen
docker compose exec -e RABBITMQ_PERCENTAGE=0 web bash -c "
  for i in {1..10}; do
    time curl -s 'http://localhost:8000/api/bright_asteroids?lat=48.2&lon=16.3' > /dev/null
  done
"

echo ""
echo "Testing NEW architecture (RABBITMQ_PERCENTAGE=100)..."
# Auf 100% setzen
docker compose exec -e RABBITMQ_PERCENTAGE=100 web bash -c "
  for i in {1..10}; do
    time curl -s 'http://localhost:8000/api/bright_asteroids?lat=48.2&lon=16.3' > /dev/null
  done
"
EOF

chmod +x test-performance.sh
./test-performance.sh
```

## Troubleshooting

### Problem: Worker verbinden sich nicht

```bash
# RabbitMQ erreichbar?
docker exec asciisky-rabbitmq rabbitmqctl status

# Network prüfen
docker network inspect asciisky_default | grep -A 5 rabbitmq

# Worker Logs prüfen
docker compose logs asteroid-worker-1 | grep -i error
```

### Problem: Keine Messages in Queues

```bash
# Bindings prüfen
docker exec asciisky-rabbitmq rabbitmqctl list_bindings

# Exchange prüfen
docker exec asciisky-rabbitmq rabbitmqctl list_exchanges

# Feature Flags prüfen
docker compose exec web env | grep RABBITMQ
```

### Problem: Hohe Fehlerrate

```bash
# Fallback aktiviert?
docker compose logs web | grep -i "falling back"

# Timeout erhöhen
# In docker-compose.yml:
#   - RABBITMQ_TIMEOUT=60

# Mehr Worker starten (Skalierung)
docker compose up -d --scale asteroid-worker-1=4
```

## Rollback

### Rollback zur alten Architektur

```bash
# docker-compose.yml anpassen:
# - USE_RABBITMQ=false
# - FALLBACK_TO_OLD_ON_ERROR=true

# Oder alte docker-compose-legacy.yml nutzen:
docker compose -f docker-compose-legacy.yml up -d

# RabbitMQ komplett stoppen
docker compose down
```

## Aufräumen

```bash
# Alles stoppen und entfernen
docker compose down -v

# RabbitMQ-Daten löschen (falls Volume bleibt)
docker volume rm asciisky_rabbitmq_data
```

## Nächste Schritte

### Für Produktion

Wenn lokales Testing erfolgreich war:

1. **Multi-Host Setup**: Siehe `doc/rabbitmq/003-rabbitmq-4.1-multi-host-setup.md`
2. **HAProxy**: Load Balancer für RabbitMQ
3. **SSL/TLS**: Verschlüsselte Verbindungen
4. **Monitoring**: Prometheus + Grafana
5. **Backup**: Automatische Backups

### Migration ist abgeschlossen! ✅

Die neue `docker-compose.yml` nutzt bereits:
- ✅ **100% RabbitMQ Traffic** (RABBITMQ_PERCENTAGE=100)
- ✅ **Kein Fallback** (FALLBACK_TO_OLD_ON_ERROR=false)
- ✅ **Alle Worker aktiv** (6 RabbitMQ Worker)

**Alte Worker sind nicht mehr nötig** - sie existieren nur noch in `docker-compose-legacy.yml` als Backup.

Für **schrittweises Rollout in Produktion** siehe `doc/rabbitmq/004-migrationsplan.md`.

## Zusammenfassung

**Die Migration ist komplett und läuft auf einem Rechner!**

✅ RabbitMQ läuft im Docker Container  
✅ Alle 6 Worker laufen im gleichen Docker Network  
✅ Web Service kommuniziert über Container-Namen  
✅ 100% RabbitMQ Traffic, kein Fallback  
✅ Nur noch 3 Befehle zum Starten  

**Vorteil:** Einfaches Setup, produktionsreife Architektur! 🎉
