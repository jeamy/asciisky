# Cache-Strategie

## Cache-Hierarchie

```
Level 1: Position Cache (PostgreSQL)
┌────────────────────────────────────────────────────────────────┐
│ Tabellen: asteroid_positions, comet_positions                  │
│ Key: (location_key, time_bucket)                               │
│ TTL: 49 Stunden                                                │
│ Inhalt: Berechnete Positionen (ungefiltert)                    │
│ Erstellt von: Precompute Worker (stündlich) + On-Demand       │
│ Verwendet von: Alle API-Requests (erste Prüfung)              │
│ Planeten: NICHT gecacht (Direktberechnung)                     │
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
Level 3: Download von MPC
┌────────────────────────────────────────────────────────────────┐
│ URLs:                                                          │
│ - Asteroiden: https://minorplanetcenter.net/iau/MPCORB/...    │
│   MPCORB.DAT (~200 MB, ~1M Objekte)                           │
│ - Kometen: https://minorplanetcenter.net/iau/Ephemerides/...  │
│   Comets/CometEls.txt (~100 KB, ~1000 Objekte)                │
│ Dauer: 5-30 Sekunden (Asteroiden), 1-5 Sekunden (Kometen)     │
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
│ 3. KEINE PostgreSQL Caches gelöscht!                          │
│                                                                │
│    Alle Caches bleiben:                                       │
│    - asteroid_positions (ungefiltert, wiederverwendbar)        │
│    - comet_positions (ungefiltert, wiederverwendbar)           │
│    - asteroids (MPC MPCORB.DAT, Mag 20.0)                      │
│    - comets (MPC CometEls.txt, Mag 20.0)                       │
│                                                                │
│    Filterung passiert in API-Routen!                          │
└────────┬───────────────────────────────────────────────────────┘
         ▼
┌────────────────────────────────────────────────────────────────┐
│ 4. Nächster Request                                            │
│    - DataFrame-Cache vorhanden (Mag 20.0)                     │
│    - Position-Cache vorhanden (ungefiltert)                    │
│    - API-Route filtert auf neues Limit (z.B. 18)              │
│    - Neue Objekte (14-18) erscheinen sofort!                  │
│    - Keine Neuberechnung nötig!                                │
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

Bei Filter-Änderung (z.B. 14 → 18) werden **KEINE** PostgreSQL Caches gelöscht!

**Alle Caches bleiben:**
```
asteroid_positions  ← Ungefiltert, enthält ALLE berechneten Positionen
comet_positions     ← Ungefiltert, enthält ALLE berechneten Positionen
asteroids           ← MPC MPCORB.DAT - Orbitaldaten, Mag 20
comets              ← MPC CometEls.txt - Orbitaldaten, Mag 20
```

**Warum werden Caches NICHT gelöscht?**

Alle PostgreSQL Caches enthalten **ungefilterte** Daten:
- Position-Caches: Alle berechneten Positionen (bis Mag ~22)
- DataFrame-Caches: Alle Objekte bis Mag 20.0
- Filterung passiert **nur** in API-Routen (Zeile 188-189 in `asteroids.py`)
- **Wiederverwendbar für alle Filter-Einstellungen!**

**Ablauf nach Filter-Änderung:**
1. User ändert Filter von 14 → 18
2. **Keine** Caches werden gelöscht
3. Nächster Request:
   - DataFrame-Cache vorhanden (Mag 20.0) ✅
   - Position-Cache vorhanden (ungefiltert) ✅
   - API filtert auf Mag 18.0
   - Objekte 14-18 erscheinen **sofort**!
   - **Keine Neuberechnung nötig!** 🚀

**Planeten:**
- Werden **nicht** gecacht
- Direktberechnung bei jedem Request (~50-200ms)
- Nur 8 Objekte, schnell genug ohne Cache

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
