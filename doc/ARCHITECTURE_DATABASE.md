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

### 2. asteroid_positions / comet_positions (Position Cache)

Speichert berechnete Positionen für spezifische Location/Time Kombinationen.

```sql
CREATE TABLE asteroid_positions (
    id SERIAL PRIMARY KEY,
    location_hash VARCHAR(64) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    positions JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(location_hash, timestamp)
);

CREATE TABLE comet_positions (
    id SERIAL PRIMARY KEY,
    location_hash VARCHAR(64) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    positions JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(location_hash, timestamp)
);

CREATE INDEX idx_asteroid_positions_hash_time 
    ON asteroid_positions(location_hash, timestamp);
CREATE INDEX idx_comet_positions_hash_time 
    ON comet_positions(location_hash, timestamp);
```

**location_hash:** SHA256 von `f"{lat:.2f}_{lon:.2f}"`

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
- `db_utils.py:store_comet_positions()` - Zeilen 180-202
- `db_utils.py:get_asteroid_positions()` - Zeilen 114-134
- `db_utils.py:get_comet_positions()` - Zeilen 204-224

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
PostgreSQL: asteroid_positions/comet_positions
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
| asteroid_positions/comet_positions | Unbegrenzt | Positionen für spezifischen Zeitpunkt sind unveränderlich |

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
| asteroid_positions | 100-500 KB | ~10 KB (JSON Array, ungefiltert) |
| comet_positions | 10-50 KB | ~1 KB (JSON Array, ungefiltert) |

**Total:** ~25-60 MB für vollen Cache (ohne Planeten)
