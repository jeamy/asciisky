# Vergleich: Cache-Berechnung Kometen vs. Asteroiden

## Übersicht

Beide Systeme verwenden eine **zweistufige Cache-Strategie**:
1. **DataFrame-Cache**: Rohdaten vom MPC (Minor Planet Center)
2. **Positions-Cache**: Berechnete Positionen pro Standort/Zeit

## Detaillierter Vergleich

### 1. Rohdaten-Cache (DataFrame)

| Aspekt | Asteroiden | Kometen |
|--------|-----------|---------|
| **Konstante** | `ASTEROID_DF_CACHE_FILE` | `COMET_DF_CACHE_FILE` |
| **Datei** | `cache/asteroids_dataframe.pkl` | `cache/comets_dataframe.pkl` |
| **TTL** | `ASTEROID_DF_CACHE_TTL_SECONDS = 49h` | `COMET_DF_CACHE_TTL_SECONDS = 49h` |
| **Quelle** | MPCORB.DAT.gz | CometEls.txt |
| **Update-Frequenz** | Täglich (24h) | Täglich (24h) |
| **Funktion** | `should_update_mpcorb_file()` | `should_update_comet_file()` |
| **Cache-Format** | Dict mit Timestamp `{'timestamp': dt, 'data': df}` | Dict mit Timestamp `{'timestamp': dt, 'data': df}` |
| **In-Memory Cache** | Ja (`_asteroid_df_cache`, `_asteroid_df_timestamp`) | Ja (`_comet_df_cache`, `_comet_df_timestamp`) |

**Status**: ✅ Vollständig identisch - beide verwenden strukturiertes Cache-Format mit Timestamp-Validierung und In-Memory-Cache.

### 2. Positions-Cache (Berechnete Daten)

| Aspekt | Asteroiden | Kometen | Status |
|--------|-----------|---------|--------|
| **Bucket-Größe** | `ASTEROID_CACHE_BUCKET_HOURS = 1` | `COMET_CACHE_BUCKET_HOURS = 1` | ✅ Identisch |
| **TTL** | `ASTEROID_CACHE_TTL_SECONDS = 49h` | `COMET_CACHE_TTL_SECONDS = 49h` | ✅ Identisch |
| **Berechnungszeitpunkte** | Stündlich zur Minute 0 | Stündlich zur Minute 0 | ✅ Identisch |
| **Cache-Pfad** | `cache/asteroids/<loc>/<bucket>.pkl` | `cache/comets/<loc>/<bucket>.pkl` | ✅ Identisch |
| **SQLite Backend** | `ASTEROID_USE_SQLITE = True` | `COMET_USE_SQLITE = True` | ✅ Identisch |
| **Pickle Fallback** | Ja (wenn SQLite fehlschlägt) | Ja (wenn SQLite fehlschlägt) | ✅ Identisch |
| **Disable Pickle** | `DISABLE_PICKLE` env var | `DISABLE_PICKLE` env var | ✅ Identisch |

**Status**: Vollständig identisch seit der Korrektur!

### 3. Berechnungslogik

#### Asteroiden (`load_bright_asteroids`)

```python
# 1. Cache-Check (SQLite oder Pickle)
if use_cache:
    cached = get_asteroid_positions(loc_key, time_bucket, TTL)
    if cached: return cached

# 2. DataFrame laden (mit täglichem Update-Check)
if should_update_mpcorb_file():  # Täglich
    download_mpcorb_file()

df = load_from_pickle(ASTEROID_DF_CACHE_FILE)
if not df:
    df = load_from_mpcorb()
    save_to_pickle(df)

# 3. Positionen berechnen
for asteroid in df:
    - Orbit erstellen
    - Position berechnen (alt, az, distance)
    - Magnitude berechnen (H-G System)
    - Rise/Set/Transit berechnen

# 4. Cache speichern
store_asteroid_positions(loc_key, time_bucket, results)
```

#### Kometen (`load_comets`)

```python
# 1. Cache-Check (SQLite oder Pickle)
if use_cache:
    cached = get_comet_positions(loc_key, time_bucket, TTL)
    if cached: return cached

# 2. DataFrame laden (mit wöchentlichem Update-Check)
df = load_comet_dataframe()
    # Prüft In-Memory Cache
    # Prüft Disk Cache mit Timestamp
    # Falls abgelaufen oder nicht vorhanden:
    if should_update_comet_file():  # Wöchentlich
        download_from_mpc()
    df = load_from_file()
    save_with_timestamp({'timestamp': now, 'data': df})

# 3. Positionen berechnen
for comet in df:
    - Orbit erstellen
    - Position berechnen (alt, az, distance)
    - Magnitude berechnen (M1 + k1 System)
    - Rise/Set/Transit berechnen

# 4. Cache speichern
store_comet_positions(loc_key, time_bucket, results)
```

### 4. Magnitude-Berechnung

| Aspekt | Asteroiden | Kometen |
|--------|-----------|---------|
| **System** | H-G (IAU) | M1 + k1 (Exponent) |
| **Formel** | `V = H + 5log(rΔ) - 2.5log(Φ)` | `V = M1 + 5log(Δ) + 2.5k1·log(r)` |
| **Parameter** | H (abs. mag), G (slope) | M1 (abs. mag), k1 (exponent) |
| **Phasenfunktion** | Ja (Φ1, Φ2) | Nein |
| **Komplexität** | Höher (Phasenwinkel) | Einfacher (nur Distanzen) |

### 5. Event-Berechnung (Rise/Set/Transit)

| Aspekt | Asteroiden | Kometen | Status |
|--------|-----------|---------|--------|
| **Max. Events** | `ASTEROIDS_EVENTS_MAX = 50` | `COMET_EVENTS_MAX = 50` | ✅ Identisch |
| **Suchfenster** | 2 Tage ab Mitternacht UTC | 2 Tage ab Mitternacht UTC | ✅ Identisch |
| **Zeitzone** | Konvertiert zu lokaler Zeit | Konvertiert zu lokaler Zeit | ✅ Identisch |
| **Format** | `HH:MM` | `HH:MM` | ✅ Identisch |

### 6. Precompute-Integration

Beide werden vom **Background Worker** (`precompute_worker.py`) identisch behandelt:

```python
# Für beide gilt:
- 48-Stunden-Fenster vorausberechnen
- Stündliche Buckets (zur Minute 0)
- Gleiche Priorität
- Parallele Verarbeitung möglich
```

## Wichtige Unterschiede

### 1. Magnitude-System

- **Asteroiden**: Komplexeres H-G-System mit Phasenwinkel
- **Kometen**: Einfacheres M1+k1-System (Kometen reflektieren anders)

**Grund**: Physikalische Unterschiede (feste Oberfläche vs. Gas/Staub).

## Konsistenz-Status

| Kategorie | Status | Bemerkung |
|-----------|--------|-----------|
| **Positions-Cache** | ✅ Vollständig konsistent | Bucket-Größe, TTL, Format identisch |
| **Rohdaten-Update** | ✅ Identisch | Beide täglich (24h) |
| **Cache-Format** | ✅ Identisch | Beide mit Timestamp + In-Memory-Cache |
| **Berechnung** | ✅ Konsistent | Gleiche Logik, nur Magnitude-Formel unterschiedlich |
| **Interpolation** | ✅ Identisch | Beide nutzen neue Interpolation |

## Zusammenfassung

**Positions-Cache**: ✅ **Vollständig identisch** seit der TTL-Korrektur
- Beide: 1h Buckets, 49h TTL, stündliche Berechnung zur Minute 0
- Beide: SQLite + Pickle Fallback
- Beide: Interpolation zwischen Buckets

**Rohdaten-Cache**: ✅ **Vollständig identisch**
- Beide: Timestamp-Validierung mit `{'timestamp': dt, 'data': df}` Format
- Beide: In-Memory-Cache für schnelleren Zugriff
- Beide: Tägliche Updates (24h)
- Beide: 49h TTL für DataFrame-Cache

**Berechnung**: ✅ **Konsistent**
- Gleiche Event-Berechnung (Rise/Set/Transit)
- Unterschiedliche Magnitude-Formeln sind physikalisch korrekt (H-G vs. M1+k1)
- Gleiche Integration in Precompute-System
- Identische Interpolation zwischen Buckets
