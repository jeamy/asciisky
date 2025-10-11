# Plan: Pickle-Cache entfernen

## Übersicht

SQLite ist jetzt das primäre Cache-Backend. Pickle-Dateien sind redundant und können entfernt werden.

## Aktuelle Situation

### Pickle wird verwendet für:

1. **Positions-Cache** (Asteroiden/Kometen pro Standort/Zeit)
   - Als Fallback wenn SQLite fehlschlägt
   - Wird parallel zu SQLite geschrieben

2. **DataFrame-Cache** (Rohdaten vom MPC)
   - `cache/asteroids_dataframe.pkl`
   - `cache/comets_dataframe.pkl`
   - **WICHTIG**: Diese sollten BEHALTEN werden!

3. **Legacy-Caches**
   - `cache/bright_asteroid_cache.pkl`
   - `cache/bright_comet_cache.pkl`
   - Können entfernt werden

## Was BEHALTEN werden sollte

### DataFrame-Caches (BEHALTEN!)

```python
# Diese Caches speichern die Rohdaten vom MPC
ASTEROID_DF_CACHE_FILE = 'cache/asteroids_dataframe.pkl'  # ✅ BEHALTEN
COMET_DF_CACHE_FILE = 'cache/comets_dataframe.pkl'        # ✅ BEHALTEN
```

**Grund**: 
- Speichern die gesamten MPCORB/CometEls Daten (~2000-5000 Objekte)
- Vermeiden wiederholtes Parsen großer Dateien
- SQLite speichert nur gefilterte Objekte (H < 12.0)
- Werden für Berechnungen benötigt

## Was ENTFERNT werden kann

### 1. Positions-Cache Pickle-Dateien

```
cache/asteroids/<loc>/<bucket>.pkl  # ❌ ENTFERNEN (SQLite ersetzt)
cache/comets/<loc>/<bucket>.pkl     # ❌ ENTFERNEN (SQLite ersetzt)
```

### 2. Legacy Global Caches

```python
BRIGHT_ASTEROID_CACHE_FILE = 'cache/bright_asteroid_cache.pkl'  # ❌ ENTFERNEN
BRIGHT_COMET_CACHE_FILE = 'cache/bright_comet_cache.pkl'        # ❌ ENTFERNEN
```

### 3. Code-Änderungen

#### Dateien mit Pickle-Fallback-Code:

1. **`bright_asteroids.py`**
   - Zeile 198-210: Pickle-Fallback beim Laden
   - Zeile 350-356: Pickle-Schreiben nach SQLite
   - Zeile 493-495: Legacy Pickle-Schreiben

2. **`comets.py`**
   - Zeile 517-528: Pickle-Fallback beim Laden
   - Zeile 827-833: Pickle-Schreiben nach SQLite

3. **`api/cache_interpolation.py`**
   - Zeile 120-126: Pickle-Fallback für Asteroiden
   - Zeile 157-163: Pickle-Fallback für Kometen

4. **`api/routes/cache.py`**
   - Zeile 206-208: Pickle-Check für Asteroiden
   - Zeile 224-226: Pickle-Check für Kometen

5. **`precompute_worker.py`**
   - Zeile 292-295: Pickle-Check für Asteroiden
   - Zeile 334-337: Pickle-Check für Kometen

6. **`api/helpers.py`**
   - Zeile 125-127: Pickle-Fallback in get_cache_data()
   - Zeile 173-176: Pickle-Schreiben in store_cache_data()

## Empfehlung

### Option 1: Pickle komplett entfernen (EMPFOHLEN)

**Vorteile**:
- Einfacherer Code
- Keine redundanten Schreibvorgänge
- Weniger Speicherplatz
- Klare Architektur (nur SQLite)

**Risiko**:
- Wenn SQLite fehlschlägt, kein Fallback
- **Aber**: SQLite ist sehr stabil und wird bereits produktiv genutzt

### Option 2: Nur Pickle-Schreiben entfernen (KONSERVATIV)

**Vorteile**:
- Pickle-Lesen bleibt als Fallback für alte Caches
- Sicherer Übergang

**Nachteil**:
- Code bleibt komplexer
- Alte Pickle-Dateien bleiben liegen

### Option 3: Pickle-Flag nutzen (AKTUELL)

```yaml
# docker-compose.yml
environment:
  - ASCII_SKY_DISABLE_PICKLE=1  # Pickle deaktivieren
```

**Vorteile**:
- Sofort aktivierbar ohne Code-Änderungen
- Reversibel

**Nachteil**:
- Code bleibt im Repository
- Pickle-Dateien bleiben auf Disk

## Migrations-Plan

### Phase 1: Pickle deaktivieren (SOFORT)

```yaml
# docker-compose.yml
environment:
  - ASCII_SKY_DISABLE_PICKLE=1
```

```bash
docker compose restart web worker
```

### Phase 2: Alte Pickle-Dateien löschen (NACH 1 WOCHE)

```bash
# Nur Positions-Caches löschen, DataFrame-Caches behalten!
find cache/asteroids -name "*.pkl" -type f -delete
find cache/comets -name "*.pkl" -type f -delete

# Legacy-Caches löschen
rm -f cache/bright_asteroid_cache.pkl
rm -f cache/bright_comet_cache.pkl

# DataFrame-Caches BEHALTEN!
# cache/asteroids_dataframe.pkl
# cache/comets_dataframe.pkl
```

### Phase 3: Code aufräumen (NACH 1 MONAT)

Wenn alles stabil läuft:

1. Pickle-Fallback-Code entfernen
2. `DISABLE_PICKLE` Flag entfernen
3. `atomic_write_pickle` / `read_pickle_if_fresh` nur für DataFrame-Caches behalten

## Zusammenfassung

**BEHALTEN**:
- ✅ DataFrame-Caches (`*_dataframe.pkl`)
- ✅ `cache_utils.py` (für DataFrame-Caches)

**ENTFERNEN**:
- ❌ Positions-Cache Pickle-Dateien
- ❌ Legacy Global Caches
- ❌ Pickle-Fallback-Code (nach Testphase)

**SOFORT AKTIVIEREN**:
```yaml
ASCII_SKY_DISABLE_PICKLE=1
```
