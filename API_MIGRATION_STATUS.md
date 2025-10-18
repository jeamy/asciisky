# API Migration Status

## Übersicht

Migration zu **100% RabbitMQ** - Nur für Asteroids & Comets (lange Berechnungen).

## Status

### ✅ Komplett fertig - 100% RabbitMQ!

1. **api/routes/asteroids.py**
   - ✅ Cache-First mit `load_asteroids_with_interpolation()`
   - ✅ Background Tasks via `trigger_rabbitmq_precompute()`
   - ✅ Feature Flag Integration
   - ✅ Kein Legacy-Fallback

2. **api/routes/comets.py**
   - ✅ Cache-First mit `load_comets_with_interpolation()`
   - ✅ Background Tasks via `trigger_rabbitmq_precompute_comets()`
   - ✅ Feature Flag Integration
   - ✅ Kein Legacy-Fallback

3. **api/routes/celestial.py**
   - ✅ Direkte Berechnung (< 1s)
   - ✅ Kein RabbitMQ nötig
   - ✅ Kein Cache nötig

4. **api/routes/zodiac.py** (Constellations)
   - ✅ Direkte Berechnung (< 1s)
   - ✅ Kein RabbitMQ nötig
   - ✅ Kein Cache nötig

## Architektur-Entscheidung

**Nur Asteroids & Comets nutzen RabbitMQ**, weil:
- ✅ Lange Berechnungszeit (2-3 Minuten)
- ✅ Großer Datensatz (2000+ Objekte)
- ✅ Cache-System vorhanden (SQLite + Pickle)

**Celestial & Constellations bleiben bei alter Architektur**, weil:
- ✅ Schnelle Berechnung (< 1 Sekunde)
- ✅ Kleiner Datensatz (9 Planeten, ~20 Sternbilder)
- ✅ Kein Cache nötig

## Zusammenfassung

| Route | RabbitMQ | Grund |
|-------|----------|-------|
| `/api/bright_asteroids` | ✅ JA | Lange Berechnung + Cache |
| `/api/comets` | ✅ JA | Lange Berechnung + Cache |
| `/api/celestial` | ❌ NEIN | Schnell, kein Cache |
| `/api/zodiac` | ❌ NEIN | Schnell, kein Cache |

## Gelöschte Legacy-Dateien

- ❌ `api/background.py` - GELÖSCHT (Legacy Background Tasks)
- ❌ `api/routes/cache.py` - GELÖSCHT (Legacy Admin-Endpoints)
- ❌ `api/rabbitmq/rpc_client.py` - GELÖSCHT (Alter RPC Client)
- ❌ `precompute_task_worker.py` - GELÖSCHT (Legacy Worker)
- ❌ `workers/celestial_worker.py` - GELÖSCHT (Nicht nötig)
- ❌ `workers/constellation_worker.py` - GELÖSCHT (Nicht nötig)

## Finale Struktur

```
asciisky/
├── api/
│   ├── rabbitmq/
│   │   ├── __init__.py
│   │   └── task_publisher.py        ✅ Async Publisher
│   └── routes/
│       ├── asteroids.py              ✅ RabbitMQ + Cache
│       ├── comets.py                 ✅ RabbitMQ + Cache
│       ├── celestial.py              ✅ Direkt
│       └── zodiac.py                 ✅ Direkt
├── workers/
│   ├── asteroid_worker.py            ✅ 2 Instanzen
│   └── comet_worker.py               ✅ 2 Instanzen
├── config/
│   └── feature_flags.py              ✅ Flags
└── docker-compose.yml                ✅ 4 Worker + RabbitMQ
```

**Migration ist zu 100% komplett - kein Legacy-Code mehr!** 🎉

## Nützliche Befehle

### Queue Status prüfen
```bash
docker exec asciisky-rabbitmq rabbitmqctl list_queues name messages consumers
```

### Worker Logs
```bash
docker compose logs asteroid-worker-1 --tail=20
docker compose logs comet-worker-1 --tail=20
```

### Management UI
```
http://localhost:15672
Login: admin / password
```

### Testing
```bash
# Asteroids (sollte leere Response geben, dann Tasks in Queue)
curl "http://localhost:8000/api/bright_asteroids?lat=48.2&lon=16.3"

# Comets (sollte leere Response geben, dann Tasks in Queue)
curl "http://localhost:8000/api/comets?lat=48.2&lon=16.3"

# Celestial (sollte sofort Daten liefern)
curl "http://localhost:8000/api/celestial?lat=48.2&lon=16.3"
```
