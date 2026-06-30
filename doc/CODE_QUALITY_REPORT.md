# Code Quality Report – AsciiSky

> Datiertes Audit-Artefakt (Änderungsprotokoll: 2026-04-15), kein aktueller
> Fehlerkatalog. Zeilennummern und Befunde vor einer Umsetzung am aktuellen Code
> verifizieren.

Erstellt: 2026-04-15  
Scope: Backend (`api/`, `*.py` im Root) + Frontend (`static/js/`, `templates/`)

---

## 🔴 Toter Code (nie aufgerufen)

### `api/routes/asteroids.py`

| Funktion | Zeilen | Problem |
|----------|--------|---------|
| `compute_asteroids_rabbitmq()` | 95–128 | Definiert, nirgends aufgerufen. Ruft `get_rabbitmq_client()` auf, das **nicht importiert** ist → `NameError` bei Aufruf. |
| `compute_asteroids_old()` | 131–149 | Definiert, nirgends aufgerufen. |
| `use_rabbitmq_flag` | 184 | Variable wird berechnet (`use_rabbitmq_for('asteroids', user_id)`), aber in **keiner einzigen Bedingung verwendet**. |

### `api/routes/comets.py`

| Funktion | Zeilen | Problem |
|----------|--------|---------|
| `compute_comets_rabbitmq()` | 95–134 | Definiert, nirgends aufgerufen. Ruft `get_rabbitmq_client()` auf, das **nicht importiert** ist → `NameError` bei Aufruf. |
| `compute_comets_old()` | 137–151 | Definiert, nirgends aufgerufen. |
| `use_rabbitmq_flag` | 189 | Wie in `asteroids.py` berechnet aber nie verwendet. |

### `api/helpers.py`

| Funktion | Zeilen | Problem |
|----------|--------|---------|
| `get_location_from_request()` | 6–58 | Async-Funktion, wird **nirgends importiert oder aufgerufen**. Funktional durch `get_location_params()` (Zeile 76) ersetzt. |
| `get_cache_data()` | 95–119 | Nirgends aufgerufen laut Codebase-Suche. |
| `store_cache_data()` | 121–140 | Nirgends aufgerufen laut Codebase-Suche. |

### `api/routes/filters.py`

| Funktion | Zeilen | Problem |
|----------|--------|---------|
| `invalidate_cache()` | 61–100 | Definiert, nirgends aufgerufen. Enthält außerdem leeren Cursor-Block (öffnet DB-Verbindung, committed aber führt keine Queries aus). |

### `api/computation.py`

| Funktion | Zeilen | Problem |
|----------|--------|---------|
| `load_constellations()` | 414–435 | Gibt nur Metadaten zurück, delegiert die eigentliche Berechnung an `zodiac.py`. Wird im Produktionspfad nicht direkt verwendet. |

### `static/js/cacheStatusPanel.js`

Die Funktion `updateCacheStatusForLocation()` (Zeile 262–266) führt sofort `return;` aus (nach RabbitMQ-Migration deaktiviert). Damit ist **die gesamte Render-Logik des Moduls toter Code**:

- `renderStatus()`, `renderError()`, `toLocalHM()`, `buildLocKey()`, alle `cs-*`-DOM-Builder
- `__debounceTimer` und `updateCacheStatusForLocationDebounced()` — no-op wrapper

**Auswirkung:** Das Modul wird mit allen drei Call-Sites in `index.html` (Zeilen 109, 192, 662) importiert und aufgerufen – ohne jeglichen Effekt.

### `templates/index.html`

| Code | Zeilen | Problem |
|------|--------|---------|
| `saveLocationToLocalStorage()` | 692–699 | Schreibt `asciisky_location` in `localStorage` – diese Schlüssel wird **nirgends per `getItem` gelesen**. Dead write. |
| `localStorage.setItem('asciisky_location', ...)` | 212 | Zweite Schreibstelle desselben ungenutzten Keys. |
| `refreshCacheStatus()` | 104–112 | Ruft `updateCacheStatusForLocationDebounced` auf, das eine no-op-Funktion wrapat. |

---

## 🟠 Doppelter Code

### Location-Auflösung: `comets.py`-Route vs. `get_location_params()`

**`api/routes/comets.py` Zeilen 157–161** reimplementiert die Location-Auflösung manuell:

```python
location_settings = settings.get_location()
session_loc = request.session.get("location", {}) if hasattr(request, "session") else {}
if lat is None: lat = session_loc.get("latitude", location_settings["latitude"])
if lon is None: lon = session_loc.get("longitude", location_settings["longitude"])
if elevation is None: elevation = session_loc.get("elevation", location_settings["elevation"])
```

`api/routes/asteroids.py` nutzt korrekt `get_location_params(request, lat, lon, elevation)` aus `api/helpers.py`. **Fix:** Comets-Route auf `get_location_params()` umstellen.

### Magnitude-Filter-Laden: `asteroids.py` + `comets.py`

Identischer Codeblock in beiden Route-Handlern (je ~12 Zeilen):

```python
if max_magnitude is None:
    user_id = request.session.get('user_id')
    if user_id:
        from api.routes.filters import get_user_filters_from_db
        filters = get_user_filters_from_db(user_id)
        if filters:
            max_magnitude = filters.get("...MaxMagnitude", DEFAULT)
        else:
            max_magnitude = DEFAULT
    else:
        filters = settings.get_magnitude_filters()
        max_magnitude = filters.get("...MaxMagnitude", DEFAULT)
```

**Fix:** In `api/helpers.py` als `resolve_magnitude_filter(request, key, default)` extrahieren.

### `trigger_asteroid_worker()` / `trigger_comet_worker()`

`api/routes/asteroids.py` Zeilen 26–92 und `api/routes/comets.py` Zeilen 26–92 sind nahezu identisch. Unterschiede: `kind` (`'asteroids'`/`'comets'`), `routing_key` (`'compute.asteroid'`/`'compute.comet'`), `magnitude` (20.0/14.0).

**Fix:** Gemeinsame Funktion `trigger_worker(kind, routing_key, magnitude, lat, lon, elevation, dt_utc)`.

### Inline-Imports im Request-Handler

`api/routes/asteroids.py` und `comets.py` verwenden innerhalb des Request-Handler-Bodies wiederholte Inline-Imports:

```python
from config.interpolation_config import is_smart_interpolation_enabled, get_interpolation_strategy
from cache_utils import time_bucket_utc          # bereits top-level importiert!
from cache_utils import normalize_location, location_key  # ebenfalls top-level importiert!
from db_utils import is_computation_in_progress, computation_lock
```

`time_bucket_utc` und `normalize_location`/`location_key` sind **bereits als Top-Level-Imports** in beiden Dateien vorhanden (Zeile 9/14 bzw. 9/10).

---

## 🟡 Logikfehler / subtile Bugs

### `api/computation.py` – Transit-Zeit via `replace(tzinfo=tz)` mit pytz

**Zeilen 112–113:**

```python
rise_dt = datetime.strptime(rise_time, '%H:%M').replace(
    year=local_dt.year, month=local_dt.month, day=local_dt.day, tzinfo=tz
)
```

`replace(tzinfo=tz)` mit einem pytz-Timezone-Objekt ist **falsch** – pytz erwartet `tz.localize(naive_dt)`. `replace()` setzt den Offset ohne DST-Korrektur. Für Sommerzeitübergangsnächte kann die berechnete Transit-Zeit um 1 Stunde abweichen.

**Fix:**
```python
naive = datetime(local_dt.year, local_dt.month, local_dt.day, h, m)
rise_dt = tz.localize(naive) if hasattr(tz, 'localize') else naive.replace(tzinfo=tz)
```

### `api/computation.py` – `import math` im Loop-Body

**Zeile 72:** `import math` steht innerhalb der `for name, body in CELESTIAL_BODIES.items():` Schleife. Python cached Imports, daher kein Performance-Problem, aber schlechter Stil und laut PEP 8 nicht zulässig.

**Fix:** `import math` an den Dateianfang verschieben.

### `api/routes/comets.py` – `max_comets`-Parameter wird ignoriert

Der Endpoint-Parameter `max_comets: int = 1000` (Zeile 154) wird nach dem RabbitMQ-Refactoring **weder an `load_comets_with_interpolation` noch an `trigger_comet_worker` übergeben**. Der Parameter ist öffentlich dokumentiert aber wirkungslos.

### `settings.py` – Statischer `last_updated`-Timestamp im Modul-Scope

**Zeile 36:**
```python
"last_updated": datetime.now().isoformat()
```

`DEFAULT_SETTINGS` wird beim Modul-Import ausgewertet. Der Timestamp ist damit für die gesamte Prozesslaufzeit statisch – nicht der Zeitpunkt des Speicherns. Die `save_settings()`-Funktion (Zeile 72) überschreibt ihn korrekt, aber beim ersten Laden ohne vorhandene Datei ist der Wert irreführend.

### `api/routes/asteroids.py` – `/asteroids` Alias-Endpoint

**Zeilen 262–265:**
```python
async def get_asteroids(request, lat, lon, elevation, location_name, save_location, time, max_magnitude):
    return await get_bright_asteroids(request, lat, lon, elevation, ...)
```

`get_asteroids` hat **keinen `BackgroundTasks`-Parameter**, delegiert aber an `get_bright_asteroids`, das einen hat. FastAPI injiziert bei der Delegation ein neues `BackgroundTasks`-Objekt, das aber nie an den Response-Lifecycle gebunden wird → **Background Tasks aus dem Alias-Endpoint werden nicht ausgeführt.**

---

## 🔵 Sonstige Optimierungsmöglichkeiten

### `static/js/settings.js` – GET-Request mit Nebeneffekt

`syncSettingsToServer()` sendet einen GET-Request an `/api/celestial?save_location=true`. Ein GET sollte keine Zustandsänderungen verursachen (HTTP-Semantik, RFC 9110). Sollte ein POST an `/api/session/location` sein.

### `api/helpers.py` – Async ohne await

`get_location_from_request()` ist als `async def` deklariert, enthält aber kein einziges `await`. Kann `def` sein.

### `api/on_demand_computation.py` – Doppelte Cache-Normalisierung ✅ Erledigt

`_get_cache_key()` und `_store_bucket_persistent()` normalisierten beide unabhängig die Location. Normalisierung wird jetzt einmalig in `_compute_bucket` durchgeführt; `_get_cache_key()` wurde entfernt, `_store_bucket_persistent()` nimmt direkt `loc_key`, `bucket`, und normalisierte Koordinaten entgegen.

### `static/js/skyRenderer.js` – Monolithische Klasse

Die Datei hat ~2400 Zeilen. Die `SkyRenderer`-Klasse übernimmt: Rendering, Dialog-Management, API-Calls, Touch/Mouse-Events, Zoom/Pan, Overlay, Cache-Lookups. Kandidat für Aufspaltung in dedizierte Module (`SkyDialogManager`, `SkyInputHandler`, `SkyApiClient`).

### `comets.py` – `GM_SUN_Pitjeva_2005_km3_s2` doppelt definiert

**Zeile 6:** `from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2` (Import)  
**Zeile 55:** `GM_SUN_Pitjeva_2005_km3_s2 = 1.32712442099e11` (lokale Zuweisung überschreibt Import)

Der Import ist damit wirkungslos.

### `comets.py` – `should_update_comet_file()` vor `COMETS_FILE`-Definition

**Zeile 37–48:** Die Funktion `should_update_comet_file()` referenziert `COMETS_FILE`, das erst auf **Zeile 51** definiert wird. Funktioniert nur weil die Funktion nicht beim Import aufgerufen wird, aber fragil.

---

## Zusammenfassung nach Priorität

| Prio | Datei | Problem | Aufwand | Status |
|------|-------|---------|---------|--------|
| 🔴 | `routes/asteroids.py`, `routes/comets.py` | `compute_*_rabbitmq/old` + `use_rabbitmq_flag` entfernen | Klein | ✅ Erledigt |
| 🔴 | `cacheStatusPanel.js` | Render-Logik ist komplett dead code | Mittel | ✅ Erledigt |
| 🔴 | `routes/asteroids.py` | `/asteroids`-Alias übergibt kein `BackgroundTasks` → BG-Tasks werden nicht ausgeführt | Klein | ✅ Erledigt |
| 🟠 | `helpers.py` | `get_location_from_request`, `get_cache_data`, `store_cache_data` entfernen | Klein | ✅ Erledigt |
| 🟠 | `routes/comets.py` | Location-Auflösung auf `get_location_params()` umstellen | Klein | ✅ Erledigt |
| 🟠 | `routes/asteroids.py` + `comets.py` | `resolve_magnitude_filter` extrahiert, Inline-Imports bereinigt | Mittel | ✅ Erledigt |
| 🟠 | `routes/filters.py` | `invalidate_cache()` entfernen | Klein | ✅ Erledigt |
| 🟡 | `computation.py` | `replace(tzinfo=tz)` → `tz.localize()` für DST-Korrektheit | Klein | ✅ Erledigt |
| 🟡 | `computation.py` | `import math` in Loop | Trivial | ✅ Erledigt |
| 🟡 | `routes/comets.py` | `max_comets`-Parameter entfernen | Klein | ✅ Erledigt |
| 🟡 | `comets.py` | Doppelte `GM_SUN`-Definition, Funktionsreihenfolge | Trivial | ✅ Erledigt |
| 🔵 | `settings.js` | GET mit Nebeneffekt → POST | Klein | ✅ Erledigt |
| 🔵 | `skyRenderer.js` | Aufspaltung der Monolith-Klasse | Groß | Offen |

---

## Änderungsprotokoll (2026-04-15)

Alle Punkte bis auf `skyRenderer.js`-Aufspaltung wurden bereinigt:

- **`api/routes/asteroids.py`**: `compute_asteroids_rabbitmq`, `compute_asteroids_old`, `use_rabbitmq_flag` entfernt; `/asteroids`-Alias um `BackgroundTasks`-Parameter ergänzt; `resolve_magnitude_filter` aus `helpers.py` genutzt; `is_smart_interpolation_enabled`/`get_interpolation_strategy` als Top-Level-Import; doppelte `cache_utils`-Inline-Imports entfernt.
- **`api/routes/comets.py`**: `compute_comets_rabbitmq`, `compute_comets_old`, `use_rabbitmq_flag` entfernt; Location-Auflösung auf `get_location_params()` umgestellt; `resolve_magnitude_filter` genutzt; `max_comets`-Parameter entfernt; Inline-Imports bereinigt.
- **`api/helpers.py`**: `get_location_from_request`, `get_cache_data`, `store_cache_data` entfernt; neuer Helper `resolve_magnitude_filter` hinzugefügt; `import settings` als Top-Level-Import.
- **`api/routes/filters.py`**: `invalidate_cache()` und zugehörige ungenutzte Imports entfernt.
- **`api/computation.py`**: `import math` an Dateianfang verschoben; Transit-Berechnung nutzt `tz.localize()` statt `replace(tzinfo=tz)` für korrekte DST-Behandlung.
- **`static/js/cacheStatusPanel.js`**: Gesamte Render-Logik (~270 Zeilen dead code) entfernt; nur die drei exportierten Stub-Funktionen behalten.
- **`comets.py`**: Doppelte `GM_SUN_Pitjeva_2005_km3_s2`-Konstante (lokale Zuweisung) entfernt (Import bleibt); `should_update_comet_file()` nach `COMETS_FILE`-Definition verschoben.
- **`static/js/settings.js`**: `syncSettingsToServer()` nutzte GET an `/api/celestial?save_location=true` (HTTP-Semantikverletzung, redundant). Ersetzt durch `saveSessionLocation()` (POST) mit `serverSynced`-Guard.
- **`api/on_demand_computation.py`**: `normalize_location()` wurde doppelt aufgerufen (in `_get_cache_key` und `_store_bucket_persistent`). Einmalige Berechnung in `_compute_bucket`; `_get_cache_key()` entfernt, Signatur von `_store_bucket_persistent()` auf vorberechnete Werte umgestellt.
