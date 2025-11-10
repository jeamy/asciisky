# Unified Worker Migration Guide

## Problem
Die alte Konfiguration mit separaten Worker-Typen (PRECOMPUTE_WORKERS + ASTEROID_WORKERS + COMET_WORKERS) wurde **addiert**, was zu zu vielen Worker-Instanzen führte:

**Vorher:**
```bash
# .env.b
PRECOMPUTE_WORKERS=8
ASTEROID_WORKERS=4
COMET_WORKERS=4
# → Resultat: 16 Worker (8+4+4) ❌
```

## Lösung
**Unified Workers** können **ALLE** Task-Typen übernehmen (Precompute, Asteroids, Comets). Die Anzahl muss **NICHT** addiert werden!

**Jetzt:**
```bash
# .env.b
UNIFIED_WORKERS=8
# → Resultat: 8 Worker ✅
```

## Migration Steps

### 1. Update .env Files

**Server B (.env.b):**
```bash
# Alt:
PRECOMPUTE_WORKERS=8
ASTEROID_WORKERS=4
COMET_WORKERS=4

# Neu:
UNIFIED_WORKERS=8
```

**Server C (.env.c):**
```bash
# Alt:
PRECOMPUTE_WORKERS=2
ASTEROID_WORKERS=1
COMET_WORKERS=1

# Neu:
UNIFIED_WORKERS=4
```

### 2. Empfohlene Worker-Anzahl

**Faustregel:** 1-2 Worker pro CPU-Kern

**Server B (8 Cores):**
- `UNIFIED_WORKERS=8` ✅ (optimal)
- ~~`UNIFIED_WORKERS=16`~~ ❌ (zu viele!)

**Server C (4 Cores):**
- `UNIFIED_WORKERS=4` ✅ (optimal)
- ~~`UNIFIED_WORKERS=8`~~ ❌ (zu viele!)

### 3. Deploy Changes

```bash
# Aktualisiere alle Server
./scripts/update-production.sh

# Oder manuell auf Worker B:
ssh worker-b "cd ~/asciisky && docker compose -f docker-compose.workers.yml up -d --scale unified_worker=8"

# Auf Worker C:
ssh worker-c "cd ~/asciisky && docker compose -f docker-compose.workers.yml up -d --scale unified_worker=4"
```

### 4. Verifizierung

```bash
# Prüfe Worker-Anzahl auf Server B:
ssh worker-b "docker compose -f docker-compose.workers.yml ps | grep unified_worker | wc -l"
# Sollte ausgeben: 8

# Prüfe Worker-Anzahl auf Server C:
ssh worker-c "docker compose -f docker-compose.workers.yml ps | grep unified_worker | wc -l"
# Sollte ausgeben: 4
```

## Vorteile

✅ **Weniger Worker** = Weniger Memory-Verbrauch
✅ **Flexibler** = Worker können alle Task-Typen übernehmen
✅ **Einfacher** = Nur eine Variable statt drei
✅ **Bessere Performance** = Optimal auf Hardware abgestimmt

## Backward Compatibility

Die Scripts verwenden ein Fallback:
```bash
--scale unified_worker=${UNIFIED_WORKERS:-${PRECOMPUTE_WORKERS:-8}}
```

Das bedeutet:
1. Wenn `UNIFIED_WORKERS` gesetzt → verwende diesen Wert ✅
2. Sonst wenn `PRECOMPUTE_WORKERS` gesetzt → verwende diesen Wert
3. Sonst → Default 8

## Monitoring

Prüfe die Worker-Performance mit dem Worker Monitor:

```bash
# Starte Monitor (auf Worker B oder C)
docker compose -f docker-compose.workers.yml logs -f worker_monitor
```

Oder verwende das Standalone-Tool:
```bash
python workers/worker_monitor.py
```
