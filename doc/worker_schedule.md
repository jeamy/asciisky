# Precompute Worker - Berechnungsfrequenz

## Übersicht

Der Background Worker (`precompute_worker.py`) berechnet Kometen- und Asteroiden-Daten automatisch im Hintergrund.

## Berechnungsfrequenz

### Worker-Lauf

Der Worker läuft **stündlich** (zur vollen Stunde):

```python
# In precompute_worker.py main loop
while True:
    sweep_start = _now_utc()
    # ... Berechnung ...
    
    # Warte bis zur nächsten vollen Stunde
    next_hour = (sweep_start + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    sleep_seconds = (next_hour - _now_utc()).total_seconds()
    time.sleep(max(sleep_seconds, 60))
```

### Berechnungsfenster

- **Standard**: 144 Stunden (6 Tage) voraus
- **Konfigurierbar**: `ASCII_SKY_PRECOMPUTE_HOURS` (docker-compose.yml)

### Was wird berechnet?

Bei jedem Worker-Lauf:

1. **Standorte ermitteln**:
   - Gespeicherter Benutzerstandort (`settings.get_location()`)
   - Umgebungsvariable `ASCII_SKY_PRECOMPUTE_LOCATIONS`
   - Alle bereits gecachten Standorte (aus `cache/asteroids/*` und `cache/comets/*`)

2. **Zeitpunkte ermitteln**:
   - Aktuelle Stunde (abgerundet)
   - Nächste 144 Stunden (stündlich)
   - Beispiel um 14:37: 14:00, 15:00, 16:00, ..., bis 14:00 in 6 Tagen

3. **Für jeden Standort und Zeitpunkt**:
   - Prüfe ob Cache existiert (SQLite oder Pickle)
   - Falls nicht: Berechne und speichere

## Arten (Kinds)

Konfiguriert in `ASCII_SKY_PRECOMPUTE_KINDS`:

```yaml
# docker-compose.yml
environment:
  - ASCII_SKY_PRECOMPUTE_KINDS=asteroids,comets
```

### Asteroiden

- **Berechnung**: `ensure_asteroids(lat, lon, elevation, dt_utc)`
- **Cache-Check**: 
  1. SQLite: `has_asteroid_positions(loc_key, time_bucket, TTL)`
  2. Fallback: Pickle-Datei existiert
- **Ausgabe**: `[asteroids] wrote SQLite cache for {loc_key}/{time_bucket} (X objects)`

### Kometen

- **Berechnung**: `ensure_comets(lat, lon, elevation, dt_utc)`
- **Cache-Check**:
  1. SQLite: `has_comet_positions(loc_key, time_bucket, TTL)`
  2. Fallback: Pickle-Datei existiert
- **Ausgabe**: `[comets] wrote SQLite cache for {loc_key}/{time_bucket} (X objects)`

## Beispiel-Ablauf

```
14:00 - Worker startet
14:00 - Lade Standorte: 2 gefunden
14:00 - Zeitfenster: 14:00 bis 14:00 (+6 Tage) = 145 Stunden
14:00 - Prüfe Asteroiden für Standort 1, 14:00 → Cache existiert
14:00 - Prüfe Asteroiden für Standort 1, 15:00 → Cache fehlt, berechne
14:01 - [asteroids] wrote SQLite cache for lat+46.7632_lon+14.8416_el+0410/20251017T15 (6 objects)
14:01 - Prüfe Kometen für Standort 1, 14:00 → Cache existiert
14:01 - Prüfe Kometen für Standort 1, 15:00 → Cache fehlt, berechne
14:02 - [comets] wrote SQLite cache for lat+46.7632_lon+14.8416_el+0410/20251017T15 (12 objects)
...
14:30 - Sweep abgeschlossen: 145 Stunden × 2 Standorte × 2 Arten = 580 Checks
14:30 - Erstellt: 20 neue Caches
14:30 - Warte bis 15:00
15:00 - Worker startet erneut
```

## Häufigkeit pro Objekt

### Erste Berechnung

Wenn ein neuer Standort hinzugefügt wird:
- **Sofort**: Alle 145 Stunden werden beim nächsten Worker-Lauf berechnet
- **Dauer**: ~1-5 Minuten (abhängig von Anzahl der Objekte)

### Laufende Updates

Für bestehende Standorte:
- **Stündlich**: Nur die neue Stunde am Ende des Fensters wird berechnet
- **Beispiel**: Um 15:00 wird nur 15:00 (+6 Tage) berechnet
- **Dauer**: ~1-5 Sekunden pro Standort

### Cache-Lebensdauer

- **TTL**: 49 Stunden (beide: Asteroiden und Kometen)
- **Bedeutung**: Caches bleiben 49h gültig, auch wenn sie älter sind
- **Grund**: Ermöglicht 48h-Fenster + 1h Puffer

## Parallelisierung

```yaml
# docker-compose.yml
environment:
  - ASCII_SKY_PRECOMPUTE_WORKERS=4  # 4 parallele Threads
```

- **Standorte** werden parallel verarbeitet
- **Zeitpunkte** werden sequenziell verarbeitet (pro Standort)
- **Arten** (asteroids/comets) werden sequenziell verarbeitet

## Retention (Aufbewahrung)

```yaml
environment:
  - ASCII_SKY_RETENTION_DAYS=30  # Lösche Caches älter als 30 Tage
```

Alte Caches werden automatisch gelöscht, um Speicherplatz zu sparen.

## Monitoring

### Log-Ausgaben

```bash
# Worker-Logs anzeigen
docker compose logs worker -f

# Nur Kometen
docker compose logs worker -f | grep comet

# Nur Asteroiden
docker compose logs worker -f | grep asteroid
```

### Erwartete Ausgaben

**Start eines Sweeps:**
```
Precompute sweep start: 2 locations, 144 hours, kinds=['asteroids', 'comets']
```

**Während der Berechnung:**
```
[asteroids] wrote SQLite cache for lat+46.7632_lon+14.8416_el+0410/20251017T15 (6 objects)
[comets] wrote SQLite cache for lat+46.7632_lon+14.8416_el+0410/20251017T15 (12 objects)
```

**Ende eines Sweeps:**
```
Precompute sweep done: created=20, checked=580, elapsed=45.2s
```

## Fehlerbehebung

### Kometen werden nicht berechnet

**Problem**: Logs zeigen nur Asteroiden, keine Kometen

**Ursache**: Worker prüfte nur Pickle-Dateien, nicht SQLite-Cache

**Lösung**: ✅ Behoben - Worker prüft jetzt SQLite-Cache korrekt

### Zu viele Berechnungen

**Problem**: Worker berechnet ständig neu

**Mögliche Ursachen**:
1. TTL zu kurz (sollte 49h sein)
2. SQLite-Cache wird nicht gefunden
3. Cache-Verzeichnis wird gelöscht

**Prüfen**:
```bash
# Cache-Status prüfen
ls -lh cache/asteroids/lat+46.7632_lon+14.8416_el+0410/
ls -lh cache/comets/lat+46.7632_lon+14.8416_el+0410/

# SQLite-Datenbank prüfen
sqlite3 cache/asciisky.db "SELECT COUNT(*) FROM asteroid_positions;"
sqlite3 cache/asciisky.db "SELECT COUNT(*) FROM comet_positions;"
```

### Worker läuft nicht

**Prüfen**:
```bash
docker compose ps
docker compose logs worker --tail 50
```

**Neustart**:
```bash
docker compose restart worker
```
