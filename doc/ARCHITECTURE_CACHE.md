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
│ 3. Lösche PostgreSQL Caches                                    │
│    DELETE FROM asteroid_positions;                             │
│    DELETE FROM asteroids;                                      │
└────────┬───────────────────────────────────────────────────────┘
         ▼
┌────────────────────────────────────────────────────────────────┐
│ 4. Nächster Request lädt neu mit Mag 20.0                     │
│    Filterung auf neues Limit → neue Objekte erscheinen!       │
└────────────────────────────────────────────────────────────────┘
```

**Code:** `api/routes/filters.py:44-71`

## Performance-Metriken

| Szenario | Cache | Zeit |
|----------|-------|------|
| Precomputed Hit | Level 1 | 10-50ms |
| Position Cache | Level 3 | 100-200ms |
| DataFrame Cache | Level 2 | 2-5s |
| Cold Start | Level 4 | 10-30s |
