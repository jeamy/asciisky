# Datenbank-Schema

## PostgreSQL Tabellen

### 1. precomputed_snapshots

Speichert vorberechnete komplette Snapshots für bekannte Locations.

```sql
CREATE TABLE precomputed_snapshots (
    id SERIAL PRIMARY KEY,
    location_id VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(location_id, timestamp)
);

CREATE INDEX idx_precomputed_location_time 
    ON precomputed_snapshots(location_id, timestamp);
```

**Beispiel-Inhalt:**
```json
{
  "asteroids": [
    {
      "name": "Ceres",
      "magnitude": 7.2,
      "alt": 45.3,
      "az": 180.5,
      "ra": "12h 34m 56s",
      "dec": "+23° 45' 12\"",
      "rise_time": "2025-10-22T18:30:00Z",
      "set_time": "2025-10-23T06:15:00Z"
    }
  ],
  "comets": [...],
  "planets": [...]
}
```

**Code:** `db_utils.py:150-180`

---

### 2. asteroids / comets (DataFrame Cache)

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

**Code:** `db_utils.py:55-90`

---

### 3. asteroid_positions / comet_positions

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

**Beispiel-Inhalt:**
```json
[
  {
    "name": "Ceres",
    "magnitude": 7.2,
    "alt": 45.3,
    "az": 180.5,
    "visible": true
  },
  ...
]
```

**Code:** `db_utils.py:95-145`

---

## Datenfluss

```
MPC Download (MPCORB.DAT)
         │
         ▼
Pandas DataFrame (Orbital Elements)
         │
         │ Pickle Serialization
         ▼
PostgreSQL: asteroids/comets Tabelle
         │
         │ Load & Deserialize
         ▼
Skyfield Position Calculation
         │
         ▼
PostgreSQL: asteroid_positions/comet_positions
         │
         │ Aggregate
         ▼
PostgreSQL: precomputed_snapshots
         │
         ▼
API Response (JSON)
```

## TTL (Time-To-Live)

| Tabelle | TTL | Grund |
|---------|-----|-------|
| precomputed_snapshots | 48h | Rolling Window für Precompute |
| asteroids/comets | 31 Tage | Orbital Elements ändern sich langsam |
| asteroid_positions/comet_positions | 24h | Positionen ändern sich täglich |

## Speicherverbrauch

| Tabelle | Größe (ca.) | Pro Eintrag |
|---------|-------------|-------------|
| precomputed_snapshots | 1-5 MB | ~50 KB (komprimiertes JSON) |
| asteroids | 20-50 MB | ~20 MB (DataFrame mit ~1M Objekten) |
| comets | 1-5 MB | ~1 MB (DataFrame mit ~1000 Objekten) |
| asteroid_positions | 100-500 KB | ~10 KB (JSON Array) |
| comet_positions | 10-50 KB | ~1 KB (JSON Array) |

**Total:** ~50-100 MB für vollen Cache
