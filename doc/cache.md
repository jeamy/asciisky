# AsciiSky Cache-System Dokumentation

## Überblick

Das AsciiSky Cache-System verwendet eine hierarchische Struktur zur effizienten Speicherung astronomischer Berechnungen. Das System basiert auf **standort- und zeitbasierten Buckets** mit **Pickle-Serialisierung**.

## Cache-Verzeichnisstruktur

```
cache/
├── celestial/                    # Planeten und Sterne
│   └── lat+52.5200_lon+13.4050_el+0040/
│       ├── 20250906T00.pkl      # 00:00-05:59 UTC
│       ├── 20250906T06.pkl      # 06:00-11:59 UTC
│       ├── 20250906T12.pkl      # 12:00-17:59 UTC
│       └── 20250906T18.pkl      # 18:00-23:59 UTC
├── asteroids/                   # Asteroiden
│   └── lat+52.5200_lon+13.4050_el+0040/
│       ├── 20250906T00.pkl      # Stündliche Buckets
│       ├── 20250906T01.pkl
│       └── ...
├── comets/                      # Kometen
│   └── lat+52.5200_lon+13.4050_el+0040/
│       ├── 20250906T00.pkl      # Stündliche Buckets
│       ├── 20250906T01.pkl
│       └── ...
├── asteroids_dataframe.pkl     # Globaler Asteroiden-Katalog
├── comets_dataframe.pkl        # Globaler Kometen-Katalog
├── MPCORB.DAT                  # Minor Planet Center Daten
└── CometEls.txt                # Kometen-Elemente
```

## Standort-Normalisierung

### Location Key Format
```
lat{±DD.DDDD}_lon{±DD.DDDD}_el{±DDDDD}
```

**Beispiel:** `lat+52.5200_lon+13.4050_el+0040`

### Normalisierungsregeln
```python
# cache_utils.py: normalize_location()
lat_n = round(lat, 4)           # 4 Dezimalstellen (~11m Genauigkeit)
lon_n = round(lon, 4)           # 4 Dezimalstellen (~11m Genauigkeit)  
elev_n = math.ceil(elev / 10) * 10  # Aufrunden auf nächste 10m
```

**Beispiele:**
- `405m` → `410m`
- `415m` → `420m`
- `425m` → `430m`

## Zeit-Bucketing

### Bucket-Größen nach Datentyp

| Datentyp | Bucket-Größe | Grund |
|----------|--------------|-------|
| **celestial** | 6 Stunden | Langsame Änderung der Planetenpositionen |
| **asteroids** | 1 Stunde | Schnellere Bewegung, präzisere Tracking |
| **comets** | 1 Stunde | Schnellere Bewegung, präzisere Tracking |

### Bucket-Label Format
```
YYYYMMDDTHH
```

**Beispiele:**
- `20250906T00` = 06.09.2025, 00:00-05:59 UTC (celestial)
- `20250906T13` = 06.09.2025, 13:00-13:59 UTC (asteroids/comets)

### Bucket-Berechnung
```python
# cache_utils.py: time_bucket_utc()
bucket_hour = (dt.hour // bucket_hours) * bucket_hours
return f"{dt:%Y%m%d}T{bucket_hour:02d}"
```

## Cache-Dateien Inhalt

### Celestial Cache (.pkl)
```python
{
    "time": "2025-09-06T12:00:00+00:00",
    "location": {
        "latitude": 52.5200,
        "longitude": 13.4050, 
        "elevation": 40
    },
    "bodies": {
        "sun": {"alt": 45.2, "az": 180.5, "magnitude": -26.7},
        "moon": {"alt": -12.3, "az": 95.1, "magnitude": -12.1, "phase": 0.85},
        "mercury": {"alt": 5.2, "az": 200.1, "magnitude": 0.1},
        # ... weitere Planeten
    },
    "loading": false
}
```

### Asteroids/Comets Cache (.pkl)
```python
[
    {
        "name": "1 Ceres",
        "magnitude": 8.2,
        "alt": 25.5,
        "az": 145.2,
        "rise_time": "2025-09-06T18:30:00+02:00",
        "set_time": "2025-09-07T06:15:00+02:00",
        "transit_time": "2025-09-07T00:22:00+02:00"
    },
    # ... weitere Objekte
]
```

## Cache-Verwaltung

### TTL (Time To Live)

| Cache-Typ | TTL | Grund |
|-----------|-----|-------|
| **celestial** | 6 Stunden | Bucket-Größe |
| **asteroids** | 49 Stunden | Precompute-Fenster + Puffer |
| **comets** | 49 Stunden | Precompute-Fenster + Puffer |
| **dataframes** | 12 Stunden | Katalog-Updates |

### Automatische Bereinigung
```yaml
# docker-compose.yml
ASCII_SKY_RETENTION_DAYS: 30  # Lösche Dateien älter als 30 Tage
```

## Precompute Worker

### Konfiguration
```yaml
# docker-compose.yml
ASCII_SKY_PRECOMPUTE_HOURS: 144      # 6 Tage Vorlauf
ASCII_SKY_PRECOMPUTE_KINDS: celestial,asteroids,comets
ASCII_SKY_PRECOMPUTE_WORKERS: 4      # Parallel-Threads
ASCII_SKY_ADAPTIVE_WORKERS: 1        # Dynamische Skalierung
```

### Standort-Discovery
Der Worker findet Zielstandorte aus drei Quellen:

1. **Benutzer-Standort** (`settings.get_location()`)
2. **Konfigurierte Listen** (ENV/Datei)
3. **Existierende Caches** (scannt `cache/<kind>/*` Verzeichnisse)

### Rolling Window
- **Fenster:** 144 Stunden (6 Tage)
- **Update:** Stündlich
- **Strategie:** Vorwärts wenn `dt >= now`, sonst rückwärts

## API Integration

### Cache-Status Endpoint
```
GET /api/cache_status?lat=52.52&lon=13.41&elevation=35
```

**Response:**
```json
{
    "now_utc": "2025-09-06T12:00:00+00:00",
    "precompute_horizon_hours": 48,
    "window": {
        "start": "2025-09-06T12:00:00+00:00",
        "end": "2025-09-08T12:00:00+00:00"
    },
    "kinds": ["celestial", "asteroids", "comets"],
    "locations": [{
        "latitude": 52.5200,
        "longitude": 13.4050,
        "elevation": 40,
        "loc_key": "lat+52.5200_lon+13.4050_el+0040",
        "counts": {
            "celestial": 8,   # 48h / 6h = 8 Buckets
            "asteroids": 48,  # 48h / 1h = 48 Buckets  
            "comets": 48      # 48h / 1h = 48 Buckets
        },
        "earliest": {
            "celestial": "2025-09-06T12:00:00+00:00",
            "asteroids": "2025-09-06T12:00:00+00:00",
            "comets": "2025-09-06T12:00:00+00:00"
        },
        "latest": {
            "celestial": "2025-09-08T06:00:00+00:00",
            "asteroids": "2025-09-08T11:00:00+00:00", 
            "comets": "2025-09-08T11:00:00+00:00"
        }
    }],
    "totals": {
        "celestial": 8,
        "asteroids": 48,
        "comets": 48
    }
}
```

## Cache-Pfad Generierung

### Funktionen
```python
# cache_utils.py
def build_cache_path(kind, lat, lon, elevation, dt=None, bucket_hours=6):
    lat_n, lon_n, elev_n = normalize_location(lat, lon, elevation)
    loc_key = location_key(lat_n, lon_n, elev_n)
    bucket = time_bucket_utc(dt=dt, bucket_hours=bucket_hours)
    return f"cache/{kind}/{loc_key}/{bucket}.pkl"
```

### Beispiel-Aufruf
```python
path = build_cache_path(
    'celestial', 
    52.5200, 13.4050, 35,
    datetime(2025, 9, 6, 14, 30, tzinfo=timezone.utc),
    bucket_hours=6
)
# → "cache/celestial/lat+52.5200_lon+13.4050_el+0040/20250906T12.pkl"
```

## Atomare Schreibvorgänge

```python
# cache_utils.py: atomic_write_pickle()
def atomic_write_pickle(path, data):
    tmp_path = f"{path}.tmp-{os.getpid()}-{int(time.time())}"
    with open(tmp_path, 'wb') as f:
        pickle.dump(data, f)
    os.replace(tmp_path, path)  # Atomarer Austausch
```

**Vorteile:**
- Keine korrupten Dateien bei Unterbrechungen
- Thread-sicher
- Konsistente Daten

## Performance-Optimierungen

### Lazy Loading
- Dataframes werden nur bei Bedarf geladen
- In-Memory Caching für häufig verwendete Daten

### Parallele Verarbeitung
- Multi-Threading im Precompute Worker
- Adaptive Worker-Skalierung basierend auf Systemlast

### Effiziente Suche
- Hierarchische Verzeichnisstruktur
- Schnelle Standort-Normalisierung
- Zeit-Bucket Alignment

## Fehlerbehandlung

### Cache Miss Strategien
1. **Real-time:** Berechne on-demand und schreibe in Cache
2. **Simulated-time:** Nur aus Cache lesen, kein Fallback
3. **Background:** Trigger Precompute für fehlendes Zeitfenster

### Korrupte Dateien
- Automatisches Überspringen bei Pickle-Fehlern
- Neuberechnung bei nächstem Zugriff
- Logging für Debugging

## Monitoring

### Cache-Statistiken
- Anzahl Snapshots pro Standort/Art
- Zeitspanne der verfügbaren Daten
- Cache-Hit/Miss Raten

### Worker-Status
- Fortschritt der Vorberechnung
- Verarbeitete Stunden
- Fehlerrate pro Standort/Art
