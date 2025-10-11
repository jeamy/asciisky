# SQLite-Speicherung für Standort-spezifische Daten

## Übersicht

Alle berechneten Positionen für Asteroiden und Kometen werden **direkt in der SQLite-Datenbank** gespeichert, organisiert nach **Standort** und **Zeit**.

## Datenbank-Struktur

### Datei
```
cache/asciisky.db
```

### Tabellen

#### 1. `asteroid_positions` - Berechnete Asteroiden-Positionen

```sql
CREATE TABLE asteroid_positions (
    asteroid_id INTEGER,           -- Referenz zu asteroids.id
    location_key TEXT,             -- z.B. "lat+46.7632_lon+14.8417_el+0410"
    time_bucket TEXT,              -- z.B. "20251011T18" (Stunde)
    observer_lat REAL,             -- 46.7632
    observer_lon REAL,             -- 14.8417
    observer_elevation REAL,       -- 410.0
    computed_at TIMESTAMP,         -- Wann berechnet
    position_data BLOB,            -- Pickle: {name, altitude, azimuth, distance, magnitude, rise, set, transit}
    PRIMARY KEY (asteroid_id, location_key, time_bucket)
)
```

#### 2. `comet_positions` - Berechnete Kometen-Positionen

```sql
CREATE TABLE comet_positions (
    comet_id INTEGER,              -- Referenz zu comets.id
    location_key TEXT,             -- z.B. "lat+46.7632_lon+14.8417_el+0410"
    time_bucket TEXT,              -- z.B. "20251011T18" (Stunde)
    observer_lat REAL,             -- 46.7632
    observer_lon REAL,             -- 14.8417
    observer_elevation REAL,       -- 410.0
    computed_at TIMESTAMP,         -- Wann berechnet
    position_data BLOB,            -- Pickle: {name, altitude, azimuth, distance, magnitude, rise, set, transit}
    PRIMARY KEY (comet_id, location_key, time_bucket)
)
```

#### 3. `celestial_snapshots` - Planeten, Sonne, Mond

```sql
CREATE TABLE celestial_snapshots (
    location_key TEXT,             -- z.B. "lat+46.7632_lon+14.8417_el+0410"
    time_bucket TEXT,              -- z.B. "20251011T18" (Stunde)
    observer_lat REAL,             -- 46.7632
    observer_lon REAL,             -- 14.8417
    observer_elevation REAL,       -- 410.0
    computed_at TIMESTAMP,         -- Wann berechnet
    snapshot_data BLOB,            -- Pickle: {sun, moon, planets...}
    PRIMARY KEY (location_key, time_bucket)
)
```

#### 4. `asteroids` - Rohdaten (Bahnelemente)

```sql
CREATE TABLE asteroids (
    id INTEGER PRIMARY KEY,
    designation TEXT UNIQUE,       -- z.B. "Ceres", "Vesta"
    magnitude_h REAL,              -- Absolute Helligkeit
    magnitude_g REAL,              -- Slope parameter
    eccentricity REAL,             -- Exzentrizität
    semimajor_axis REAL,           -- Große Halbachse
    orbit_data BLOB,               -- Vollständige Bahnelemente
    last_updated TIMESTAMP
)
```

#### 5. `comets` - Rohdaten (Bahnelemente)

```sql
CREATE TABLE comets (
    id INTEGER PRIMARY KEY,
    designation TEXT UNIQUE,       -- z.B. "12P/Pons-Brooks"
    name TEXT,
    magnitude_h REAL,              -- M1
    perihelion_distance REAL,      -- q
    eccentricity REAL,             -- e
    orbit_data BLOB,               -- Vollständige Bahnelemente
    last_updated TIMESTAMP
)
```

## Speicherung pro Standort

### Location Key Format

```python
location_key = f"lat{lat:+.4f}_lon{lon:+.4f}_el{int(elevation):+05d}"
```

**Beispiele**:
- `lat+46.7632_lon+14.8417_el+0410` (Dein Standort)
- `lat+52.5200_lon+13.4050_el+0040` (Berlin)
- `lat-33.8688_lon+151.2093_el+0010` (Sydney)

### Time Bucket Format

```python
time_bucket = f"{dt:%Y%m%d}T{bucket_hour:02d}"
```

**Beispiele**:
- `20251011T18` (11. Oktober 2025, 18:00 UTC)
- `20251011T19` (11. Oktober 2025, 19:00 UTC)
- `20251012T00` (12. Oktober 2025, 00:00 UTC)

## Datenfluss

### 1. Speichern (Worker)

```python
# Worker berechnet für Standort + Zeit
location_key = "lat+46.7632_lon+14.8417_el+0410"
time_bucket = "20251011T18"

# Berechne Positionen
asteroid_list = compute_asteroids(lat, lon, elevation, dt)

# Speichere in SQLite
for asteroid in asteroid_list:
    store_asteroid_positions(
        asteroid_id=asteroid['id'],
        location_key=location_key,
        time_bucket=time_bucket,
        lat=46.7632,
        lon=14.8417,
        elevation=410.0,
        position_data=pickle.dumps(asteroid)
    )
```

### 2. Laden (API)

```python
# API-Request für Standort + Zeit
location_key = "lat+46.7632_lon+14.8417_el+0410"
time_bucket = "20251011T18"

# Lade aus SQLite
positions = get_asteroid_positions(location_key, time_bucket, ttl=49*3600)

# Wenn vorhanden und nicht abgelaufen → Verwenden
if positions:
    return positions

# Sonst: Neu berechnen oder warten auf Worker
```

## Vorteile gegenüber Pickle-Dateien

### 1. **Effizienz**
- ✅ Keine Verzeichnis-Scans nötig
- ✅ Schnelle Abfragen per Index
- ✅ Nur relevante Daten laden

### 2. **Konsistenz**
- ✅ ACID-Transaktionen
- ✅ Keine Datei-Locks
- ✅ Concurrent Reads möglich

### 3. **Wartung**
- ✅ Einfaches Cleanup alter Daten
- ✅ Statistiken per SQL
- ✅ Keine Verzeichnis-Struktur-Probleme

### 4. **Speicherplatz**
- ✅ Kompakter (keine Verzeichnis-Overhead)
- ✅ Automatische Kompression
- ✅ Einfaches Backup (eine Datei)

## Beispiel-Abfragen

### Anzahl gecachter Positionen

```sql
-- Asteroiden pro Standort
SELECT location_key, COUNT(*) as count
FROM asteroid_positions
GROUP BY location_key;

-- Kometen pro Standort
SELECT location_key, COUNT(*) as count
FROM comet_positions
GROUP BY location_key;
```

### Verfügbare Zeitpunkte für einen Standort

```sql
SELECT time_bucket, computed_at
FROM asteroid_positions
WHERE location_key = 'lat+46.7632_lon+14.8417_el+0410'
ORDER BY time_bucket;
```

### Cache-Größe

```sql
-- Gesamtgröße
SELECT 
    (SELECT COUNT(*) FROM asteroid_positions) as asteroids,
    (SELECT COUNT(*) FROM comet_positions) as comets,
    (SELECT COUNT(*) FROM celestial_snapshots) as celestial;
```

## Cleanup

### Alte Daten löschen

```python
# In db_utils.py: cleanup_old_positions()
cutoff_date = datetime.now() - timedelta(days=30)

conn.execute("""
    DELETE FROM asteroid_positions
    WHERE computed_at < ?
""", (cutoff_date,))

conn.execute("""
    DELETE FROM comet_positions
    WHERE computed_at < ?
""", (cutoff_date,))
```

### Automatisches Cleanup

- Worker prüft bei jedem Lauf
- Löscht Daten älter als `ASCII_SKY_RETENTION_DAYS` (default: 30 Tage)
- Läuft automatisch im Hintergrund

## Zusammenfassung

**Ja, alle Daten für spezielle Orte werden direkt in der SQLite-Datenbank gespeichert:**

- ✅ **Ein Eintrag** pro Asteroid/Komet + Standort + Stunde
- ✅ **Location Key** identifiziert den Standort eindeutig
- ✅ **Time Bucket** identifiziert die Stunde
- ✅ **Position Data** enthält alle berechneten Werte (Pickle)
- ✅ **Keine Pickle-Dateien** mehr nötig (außer DataFrame-Caches)
