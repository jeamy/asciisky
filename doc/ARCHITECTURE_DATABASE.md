# Datenbank-Schema

## PostgreSQL Tabellen

### 1. asteroids / comets (DataFrame Cache)

Speichert Rohdaten von MPC als Pickle-serialisierte Pandas DataFrames.

```sql
CREATE TABLE asteroids (
    id SERIAL PRIMARY KEY,
    dataframe_pickle BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE comets (
    id SERIAL PRIMARY KEY,
    dataframe_pickle BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Inhalt:** Pickle-serialisierte Pandas DataFrames mit Orbital Elements:
- Designation (Name)
- H (Absolute Magnitude)
- G (Slope Parameter)
- Epoch
- M (Mean Anomaly)
- Peri (Argument of Perihelion)
- Node (Longitude of Ascending Node)
- i (Inclination)
- e (Eccentricity)
- n (Mean Daily Motion)
- a (Semimajor Axis)

**Quelle:**
- Asteroiden: https://minorplanetcenter.net/iau/MPCORB/MPCORB.DAT (~200 MB)
- Kometen: https://minorplanetcenter.net/iau/Ephemerides/Comets/CometEls.txt (~100 KB)

**Code:** `db_utils.py:55-90`

---

### 2. cached_positions (Position Cache)

Speichert berechnete Positionen für spezifische Location/Time Kombinationen.
Verwendet **eine** Tabelle für Asteroiden und Kometen.

```sql
CREATE TABLE cached_positions (
    id SERIAL PRIMARY KEY,
    object_type VARCHAR(20) NOT NULL,      -- 'asteroid' oder 'comet'
    object_id INTEGER NOT NULL,
    location_key VARCHAR(100) NOT NULL,    -- 'lat+XX.XXXX_lon+YY.YYYY_el+ZZZZ'
    time_bucket VARCHAR(20) NOT NULL,      -- 'YYYYMMDDTHH' (1-hour buckets)
    observer_lat DOUBLE PRECISION NOT NULL,
    observer_lon DOUBLE PRECISION NOT NULL,
    observer_elevation DOUBLE PRECISION NOT NULL,
    computed_at TIMESTAMP NOT NULL,
    position_data BYTEA NOT NULL,          -- Pickle-serialisierte Daten
    UNIQUE(object_type, location_key, time_bucket)
);

CREATE INDEX idx_cached_loc_time ON cached_positions(location_key, time_bucket);
CREATE INDEX idx_cached_computed ON cached_positions(computed_at);
CREATE INDEX idx_cached_type ON cached_positions(object_type);
```

**location_key:** Format `lat+XX.XXXX_lon+YY.YYYY_el+ZZZZ`

**Inhalt:** Ungefilterte berechnete Positionen (alle Objekte bis Mag ~22)

**Beispiel-Inhalt:**
```json
[
  {
    "name": "Ceres",
    "magnitude": 7.2,
    "alt": 45.3,
    "az": 180.5,
    "ra": 12.5,
    "dec": 23.8,
    "distance": 2.3,
    "rise_time": "18:30",
    "transit_time": "00:15",
    "set_time": "06:00",
    "type": "asteroid",
    "symbol": "⚸"
  },
  ...
]
```

**Wichtig:** Enthält ALLE berechneten Objekte (ungefiltert)! Filterung passiert in API-Routen.

**Code:** 
- `db_utils.py:store_asteroid_positions()` - Zeilen 90-112
- `db_utils.py:store_comet_positions()` - Zeilen 180-206
- `db_utils.py:get_asteroid_positions()` - Zeilen 114-138
- `db_utils.py:get_comet_positions()` - Zeilen 208-232

---

## Datenfluss

```
MPC Download
├─ MPCORB.DAT (Asteroiden, ~200 MB)
└─ CometEls.txt (Kometen, ~100 KB)
         │
         ▼
Pandas DataFrame (Orbital Elements)
         │
         │ Pickle Serialization
         ▼
PostgreSQL: asteroids/comets Tabellen
         │
         │ Load & Deserialize
         ▼
Skyfield Position Calculation
         │
         │ Für jeden Ort/Zeit
         ▼
PostgreSQL: cached_positions
         │
         │ Ungefiltert (alle Objekte)
         ▼
API Routes (asteroids.py, comets.py)
         │
         │ Filterung basierend auf user_settings.json
         ▼
API Response (JSON, gefiltert)
```

## TTL (Time-To-Live)

| Tabelle | TTL | Grund |
|---------|-----|-------|
| asteroids/comets | 31 Tage | Orbital Elements ändern sich langsam |
| cached_positions | Unbegrenzt | Positionen für spezifischen Zeitpunkt sind unveränderlich |

**Position Cache:**

Positionen für einen **spezifischen Zeitpunkt** (time_bucket) sind **unveränderlich**:
- Die Position von Ceres am 25.12.2025 um 12:00 UTC ändert sich nie mehr
- Werden unbegrenzt gecacht
- Spart massive Rechenzeit für wiederholte Abfragen

**Speicherplatz-Management:**
- Bei Bedarf können alte Positionen manuell gelöscht werden
- Empfehlung: Positionen für `time_bucket` < now() - 1 Jahr löschen
- Typischer Speicherverbrauch: ~10 KB pro Location/Time Kombination

**Planeten:** Werden NICHT gecacht (Direktberechnung bei jedem Request)

## Speicherverbrauch

| Tabelle | Größe (ca.) | Pro Eintrag |
|---------|-------------|-------------|
| asteroids | 20-50 MB | ~20 MB (DataFrame mit ~1M Objekten) |
| comets | 1-5 MB | ~1 MB (DataFrame mit ~1000 Objekten) |
| cached_positions | 100-500 KB | ~10 KB (Pickle Array, ungefiltert) |

**Total:** ~25-60 MB für vollen Cache (ohne Planeten)
