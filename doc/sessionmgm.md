# Server-Side Session- und Location-Caching-Plan

Dieser Plan definiert, wie serverseitige Sessions und pro-Standort-Caches für Kometen und (helle) Asteroiden umgesetzt werden. Ziel ist es, für gleiche Locations innerhalb eines Zeitfensters identische Ergebnisse wiederzuverwenden und Rechenzeit zu sparen.

## Ziele
- Separate, wiederverwendbare Datensätze je Beobachterstandort und Zeitfenster.
- Minimale Änderungen an bestehenden Endpoints; Frontend gibt weiterhin Location mit, oder nutzt Session-Fallback.
- TTL-kompatibel (~6h) und stabil gegenüber Nebenläufigkeit.

## Scope
- Kometen (`comets.load_comets()`): per-Location und Zeit-Bucket cachen (finale Liste inkl. Alt/Az, Ereigniszeiten).
- Helle Asteroiden (`bright_asteroids.load_bright_asteroids()`): per-Location und Zeit-Bucket cachen (finale Liste).
- Planeten (in `main.py`): vorerst live berechnen (geringer Aufwand). Optional: kleiner In-Memory-Cache per Location (60–120s).
- Globale DataFrame-Caches (MPC/MPCORB) bleiben unverändert global (~6h) und ortsunabhängig.

## Cache-Key-Strategie
- Location-Normalisierung:
  - Latitude/Longitude: auf 4 Dezimalstellen runden (`~11 m`).
  - Elevation: auf 10 m runden.
  - Beispiel-String: `lat{lat:.4f}_lon{lon:.4f}_el{int(round(elev/10)*10)}`.
- Zeit-Bucket (UTC): 6-Stunden-Fenster passend zur TTL.
  - Buckets: 00, 06, 12, 18 UTC.
  - Format: `YYYYMMDD_HH` (z. B. `20250830_18`).
- Ergebnis: gleicher Standort im selben 6h-Bucket → gleicher Cache.

## Speicherlayout
- Kometen: `cache/bright_comets/<loc_key>/<bucket>.pkl`
- Asteroiden: `cache/bright_asteroids/<loc_key>/<bucket>.pkl`
- Beispiele:
  - `cache/bright_comets/lat48.2082_lon16.3738_el170/20250830_18.pkl`
  - `cache/bright_asteroids/lat48.2082_lon16.3738_el170/20250830_18.pkl`

## TTL und Invalidation
- TTL: ~6h (konsistent mit bestehenden globalen DataFrame-Caches).
- Lesen: Cache als „fresh“, wenn Datei-`mtime` < 6h alt.
- Aufräumen: periodisch alte Bucket-Dateien löschen (z. B. beim Startup und opportunistisch alle N Requests).

## Nebenläufigkeit und atomare Writes
- Schreiben: immer atomar (Tempfile + `os.replace`) um Race Conditions zu vermeiden.
- Optional: Datei-basierte Locks bei sehr hoher Parallelität.

## API-Integration (Backend)
- `comets.py`:
  - Vor Laden/Speichern Cache-Pfad per Location+Bucket bestimmen.
  - Beim Lesen zuerst neuen Pfad prüfen; optional einmaliger Fallback auf alten globalen Cache (Migration).
  - Globale MPC-DataFrame-Caches unverändert lassen.
- `bright_asteroids.py`:
  - Analog zu Kometen: per-Location/Bucket Cache für finalen Datensatz; globaler MPCORB-Cache bleibt.
- `main.py` (Sessions, optional aber empfohlen):
  - SessionMiddleware (Cookie-basiert) hinzufügen.
  - Endpoints:
    - `GET /api/session/location` → gibt gespeicherte Session-Location zurück.
    - `POST /api/session/location` → setzt Session-Location.
  - Bestehende Endpoints (`/api/comets`, `/api/bright_asteroids`, `/api/celestial`):
    - Location aus Query verwenden; falls fehlt → Session-Location als Fallback; falls keine Session → `settings.get_location()`.

WICHTIG (Frontend-Regel): API-Endpunkte immer zentral in `static/js/constants.js` pflegen.

## Frontend-Integration (minimal)
- `static/js/constants.js`: neue Session-Endpunkte hinzufügen.
- `static/js/locationDialog.js`: bei Änderung `POST /api/session/location`.
- `static/js/skyManager.js` (oder Initialisierer): beim Start `GET /api/session/location` laden und als Default setzen.
- Weiterhin dürfen Requests explizite `lat/lon/elevation` Parameter schicken (überschreiben Session-Fallback).

## Utility-Modul: `cache_utils.py`
Gemeinsame Helfer für Kometen und Asteroiden.

```python
# cache_utils.py (Skizze)
from __future__ import annotations
import os, json, tempfile, time, hashlib
from datetime import datetime, timezone
from typing import Any, Optional

CACHE_ROOT = "cache"

def normalize_location(lat: float, lon: float, elev: float) -> str:
    lat_r = round(float(lat), 4)
    lon_r = round(float(lon), 4)
    el_r  = int(round(float(elev) / 10.0) * 10)
    return f"lat{lat_r:.4f}_lon{lon_r:.4f}_el{el_r}"

def time_bucket(now: Optional[datetime] = None, hours: int = 6) -> str:
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    base = now_utc.replace(minute=0, second=0, microsecond=0)
    h = (base.hour // hours) * hours
    return base.replace(hour=h).strftime("%Y%m%d_%H")

def cache_path(kind: str, loc_key: str, bucket: str) -> str:
    # kind ∈ {"bright_comets", "bright_asteroids"}
    dir_path = os.path.join(CACHE_ROOT, kind, loc_key)
    os.makedirs(dir_path, exist_ok=True)
    return os.path.join(dir_path, f"{bucket}.pkl")

def is_fresh(path: str, ttl_seconds: int) -> bool:
    try:
        age = time.time() - os.path.getmtime(path)
        return age >= 0 and age < ttl_seconds
    except FileNotFoundError:
        return False

def read_pickle_if_fresh(path: str, ttl_seconds: int) -> Optional[Any]:
    if is_fresh(path, ttl_seconds):
        import pickle
        with open(path, "rb") as f:
            return pickle.load(f)
    return None

def atomic_write_pickle(path: str, obj: Any) -> None:
    import pickle
    dir_name = os.path.dirname(path)
    os.makedirs(dir_name, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dir_name, delete=False) as tmp:
        pickle.dump(obj, tmp)
        tmp_path = tmp.name
    os.replace(tmp_path, path)  # atomic on same filesystem

def cleanup_cache(kind: str, max_age_hours: int = 24) -> int:
    """Entfernt alte Dateien; gibt Anzahl gelöschter Dateien zurück."""
    import glob
    cutoff = time.time() - max_age_hours * 3600
    root = os.path.join(CACHE_ROOT, kind)
    removed = 0
    for path in glob.glob(os.path.join(root, "**", "*.pkl"), recursive=True):
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except FileNotFoundError:
            pass
    return removed
```

## Implementierungsschritte
1. `cache_utils.py` hinzufügen (gemeinsame Key-/I/O-Funktionen).
2. `comets.py`:
   - Cache-Pfad via `normalize_location()` + `time_bucket()` + `cache_path()` bestimmen.
   - Beim Lesen: neuen Pfad prüfen; optional einmalig globalen Altpfad als Fallback Lesen (Migration), dann im neuen Schema schreiben.
   - Atomare Writes mit `atomic_write_pickle()`.
3. `bright_asteroids.py` analog zu (2).
4. `main.py` (optional Session):
   - `SessionMiddleware` hinzufügen, Secret Key aus Env oder Konstante.
   - `GET/POST /api/session/location` implementieren.
   - In `/api/comets`, `/api/bright_asteroids`, `/api/celestial` Location-Fallback auf Session.
5. Frontend:
   - `static/js/constants.js`: neue Session-Endpoints eintragen.
   - `static/js/locationDialog.js`: `POST /api/session/location` bei Änderung.
   - Initialisierung: `GET /api/session/location` als Default (wenn keine Query-Location).
6. Doku aktualisieren: `README.md`, `doc/plan.md`, `doc/comets.md`, `doc/asteroids.md`.

## Tests & Benchmarking
- Gleiches `lat/lon/elev` + gleicher Bucket: zweiter Aufruf muss Cache-Hit sein (Messung End-to-End-Zeit << erster Aufruf).
- Andere Location: Cache-Miss, aber globaler DataFrame-Cache verwendet (schneller als Kaltstart).
- Nach TTL > 6h: Cache-Miss (Neuberechnung).
- Parallelität: gleichzeitige Anfragen → keine korrupten Dateien, genau eine finale Cache-Datei.

## Migration & Rückwärtskompatibilität
- Beim ersten Zugriff: 
  - Falls neuer Pfad fehlt, optional den bisherigen globalen Cache (`cache/bright_comet_cache.pkl` / `cache/bright_asteroid_cache.pkl`) einmalig lesen, dann unter neuem Schema schreiben.
  - Danach nur noch per-Location/Bucket verwenden.

## Konfiguration (Defaults)
- Location-Rundung: lat/lon 4 Nachkommastellen, elevation auf 10 m.
- Bucket: 6h (UTC), Buckets um 00/06/12/18.
- TTL: 6h.
- Optional In-Memory-LRU: 60–120s pro Location/Bucket um Disk-I/O zu sparen.

## Sicherheit & Datenschutz
- Session speichert nur Standortkoordinaten und optionalen Namen (kein PII darüber hinaus).
- Cookie-signed (kein sensibler Inhalt im Klartext erforderlich; Server verwaltet Session-Store).

## Hinweise
- Alt/Az und Ereigniszeiten hängen von der Zeit ab; durch 6h-Buckets können Werte im Laufe des Buckets driften. Das ist konsistent mit heutigem TTL-Verhalten.
- Erweiterungsidee (später): RA/Dec-orientiertes Caching und Alt/Az-„Reprojection“ zur Antwortzeit, falls feinere Aktualität benötigt wird (komplexer, aber genauer).
