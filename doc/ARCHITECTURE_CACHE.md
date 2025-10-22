# Cache-Strategie

## Cache-Hierarchie

```
Level 1: Precomputed Snapshots (PostgreSQL)
┌────────────────────────────────────────────────────────────────┐
│ Tabelle: precomputed_snapshots                                 │
│ Key: (location_id, timestamp)                                  │
│ TTL: 48 Stunden                                                │
│ Inhalt: Komplette Snapshot (Asteroiden + Kometen + Planeten)  │
│ Erstellt von: Precompute Worker (stündlich)                   │
│ Verwendet von: Alle API-Requests (erste Prüfung)              │
└────────────────────────────────────────────────────────────────┘
         │ Cache MISS
         ▼
Level 2: DataFrame Cache (PostgreSQL)
┌────────────────────────────────────────────────────────────────┐
│ Tabellen: asteroids, comets                                    │
│ TTL: 31 Tage                                                   │
│ Inhalt: Rohdaten von MPC (Orbital Elements)                    │
│ Erstellt von: Worker beim ersten Load                          │
│ Verwendet von: Worker für Position-Berechnungen                │
└────────────────────────────────────────────────────────────────┘
         │ Cache MISS
         ▼
Level 3: Position Cache (PostgreSQL)
┌────────────────────────────────────────────────────────────────┐
│ Tabellen: asteroid_positions, comet_positions                  │
│ Key: (location_hash, timestamp)                                │
│ TTL: 24 Stunden                                                │
│ Inhalt: Berechnete Positionen für Location/Time               │
└────────────────────────────────────────────────────────────────┘
         │ Cache MISS
         ▼
Level 4: Download von MPC
┌────────────────────────────────────────────────────────────────┐
│ URLs:                                                          │
│ - https://www.minorplanetcenter.net/iau/MPCORB/MPCORB.DAT     │
│ Dauer: 5-30 Sekunden                                           │
└────────────────────────────────────────────────────────────────┘
```

## Cache-Invalidierung

```
User ändert Magnitude-Filter (z.B. 14 → 18)
         │
         │ POST /api/filters
         ▼
┌────────────────────────────────────────────────────────────────┐
│ 1. Speichere neue Filter in user_settings.json                │
│    settings.py:set_magnitude_filters()                         │
└────────┬───────────────────────────────────────────────────────┘
         ▼
┌────────────────────────────────────────────────────────────────┐
│ 2. Lösche In-Memory Caches                                     │
│    bright_asteroids.py:clear_in_memory_cache()                 │
└────────┬───────────────────────────────────────────────────────┘
         ▼
┌────────────────────────────────────────────────────────────────┐
│ 3. Lösche gefilterte PostgreSQL Caches                        │
│    DELETE FROM asteroid_positions;                             │
│    DELETE FROM comet_positions;                                │
│    DELETE FROM precomputed_snapshots;                          │
│                                                                │
│    NICHT gelöscht: asteroids, comets                           │
│    (Enthalten ALLE Objekte bis Mag 20, wiederverwendbar!)     │
└────────┬───────────────────────────────────────────────────────┘
         ▼
┌────────────────────────────────────────────────────────────────┐
│ 4. Nächster Request                                            │
│    - DataFrame-Cache vorhanden (Mag 20.0)                     │
│    - Keine Position-Caches                                     │
│    - Worker berechnet Positionen neu                           │
│    - API-Route filtert auf neues Limit (z.B. 18)              │
│    - Neue Objekte (14-18) erscheinen!                         │
└────────────────────────────────────────────────────────────────┘
```

**Code:** `api/routes/filters.py:44-71`

### Cache-Strategie bei Filter-Änderung

**Architektur:**
- Worker laden **immer** mit Mag 20.0 (hart-codiert)
- DataFrame-Cache enthält **alle** Objekte bis Mag 20
- Filterung passiert **nur** in API-Routen basierend auf `user_settings.json`
- **Ein Cache für alle Benutzer-Filter!**

**Was passiert bei Filter-Änderung:**

Bei Filter-Änderung (z.B. 14 → 18) werden **nur** die gefilterten Caches gelöscht:

```
DELETE FROM asteroid_positions;     ← Enthält gefilterte Positionen
DELETE FROM comet_positions;        ← Enthält gefilterte Positionen
DELETE FROM precomputed_snapshots;  ← Enthält gefilterte Snapshots
```

**Was NICHT gelöscht wird:**
```
asteroids   ← Bleibt! (Enthält alle Objekte bis Mag 20)
comets      ← Bleibt! (Enthält alle Objekte bis Mag 20)
```

**Ablauf nach Filter-Änderung:**
1. User ändert Filter von 14 → 18
2. Gefilterte Caches werden gelöscht
3. Nächster Request:
   - DataFrame-Cache vorhanden (Mag 20.0)
   - Keine Position-Caches
   - Worker berechnet Positionen neu
   - API filtert auf Mag 18.0
   - Objekte 14-18 erscheinen!

**Code-Referenzen:**
- `workers/precompute_worker.py:305` - `max_magnitude=20.0`
- `workers/asteroid_worker.py:40` - `max_magnitude=20.0`
- `bright_asteroids.py:361-520` - `load_bright_asteroids(max_magnitude=20.0)`
- `comets.py:748-850` - `load_comets(max_magnitude=20.0)`
- `api/routes/asteroids.py:75-78` - Filterung auf user_settings
- `api/routes/comets.py:75-78` - Filterung auf user_settings
- `settings.py:get_magnitude_filters()` - Liest user_settings.json

## Performance-Metriken

| Szenario | Cache | Zeit |
|----------|-------|------|
| Precomputed Hit | Level 1 | 10-50ms |
| Position Cache | Level 3 | 100-200ms |
| DataFrame Cache | Level 2 | 2-5s |
| Cold Start | Level 4 | 10-30s |
