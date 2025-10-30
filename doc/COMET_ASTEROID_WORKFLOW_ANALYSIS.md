# Workflow-Analyse: Kometen- und Asteroidenberechnung in AsciiSky

Dieses Dokument analysiert den kompletten Workflow für die Berechnung und Anzeige von Kometen- und Asteroidendaten in der AsciiSky-Anwendung.

## Übersicht der Komponenten

### 1. Precompute Coordinator (`precompute_coordinator.py`)
**Zweck**: Erstellt und publiziert Precompute-Tasks für RabbitMQ Worker

**Funktionsweise**:
- Läuft stündlich (konfigurierbar über `PRECOMPUTE_COORDINATOR_INTERVAL`)
- Liest Locations aus drei Quellen:
  1. `user_settings.json` (persönliche Location)
  2. `precompute_locations.json` (konfigurierte Locations)
  3. Environment Variable `ASCII_SKY_PRECOMPUTE_LOCATIONS`
- Erstellt Tasks für die nächsten 720 Stunden (30 Tage, konfigurierbar)
- Prüft vor der Task-Erstellung, ob Daten bereits im Cache vorhanden
- Publiziert Tasks in RabbitMQ Queue `precompute.tasks`
- Vergibt Prioritäten: Nächste 24h = HIGH (10), danach NORMAL (5)

### 2. Precompute Worker (`workers/precompute_worker.py`)
**Zweck**: Holt Tasks aus RabbitMQ und berechnet Asteroiden/Kometen im Voraus

**Funktionsweise**:
- Wartet bis Daten in PostgreSQL vorhanden sind (`wait_for_database()`)
- Verbindet sich mit RabbitMQ und hört auf Queue `precompute.tasks`
- Fair Dispatch: Nur 1 Task gleichzeitig pro Worker
- Verarbeitet Tasks mit `process_task()`:
  - Normalisiert Location-Daten
  - Ruft `bright_asteroids.load_bright_asteroids()` oder `comets.load_comets()` auf
  - Speichert Ergebnisse in PostgreSQL über `store_asteroid_positions()`/`store_comet_positions()`
- Bei Erfolg: ACK, bei Fehler: NACK mit Requeue

### 3. Dedicated Worker (`workers/asteroid_worker.py`, `workers/comet_worker.py`)
**Zweck**: On-Demand Berechnung via RabbitMQ RPC

**Funktionsweise**:
- Spezialisierte Worker für Asteroiden und Kometen
- Lauschen auf Queues `asteroid.compute` und `comet.compute`
- RPC-ähnliche Kommunikation mit Status-Updates
- Speichern Ergebnisse automatisch in Cache/DB
- Timeout-Handling und Retry-Mechanismus

### 4. WebApp API Routes (`api/routes/asteroids.py`, `api/routes/comets.py`)
**Zweck**: HTTP-Endpoints für die Webanwendung

**Funktionsweise**:
- Cache-First Strategie:
  1. Prüfen ob Daten im Cache/DB vorhanden (`load_asteroids_with_interpolation()`)
  2. Bei Cache-HIT: Daten zurückgeben
  3. Bei Cache-MISS: Leere Liste zurückgeben + Background Task starten
- Background Tasks: `trigger_asteroid_worker()` / `trigger_comet_worker()`
- Verwenden magnitude-Filter aus `user_settings.json`
- Feature Flags: RabbitMQ oder alte Architektur

## Datenfluss im Detail

### 1. Initialisierung (WebApp Start)

```
WebApp wird aufgerufen → API Endpoints werden geroutet → 
Cache-Check für aktuelle Zeit/Location → 
Bei Cache-MISS: Background Tasks werden gestartet → 
Precompute Coordinator läuft bereits im Hintergrund
```

### 2. Precompute Prozess

```
Precompute Coordinator (stündlich):
├── Lade Locations aus Konfiguration
├── Erstelle Tasks für jede Location/Stunde-Kombination
├── Prüfe Cache-Status (überspringe vorhandene Daten)
├── Publiziere Tasks in RabbitMQ
└── Warte auf nächsten Lauf

Precompute Worker (kontinuierlich):
├── Hole Tasks aus RabbitMQ Queue
├── Berechne Asteroiden/Kometen mit Skyfield
├── Speichere in PostgreSQL
└── ACK/NACK je nach Erfolg
```

### 3. On-Demand Berechnung

```
User Request → API Route → Cache Check → 
Bei Cache-MISS:
├── Background Task: trigger_asteroid_worker()
├── Publiziere Task in RabbitMQ
├── Dedicated Worker verarbeitet Task
├── Speichert Ergebnis in DB
└── Nächster Request findet Daten im Cache
```

### 4. Simulation Controls (<< < + > >>)

**HTML-Elemente** (`templates/index.html`):
```html
<button id="sim-day-minus" title="-1 Tag">&laquo;</button>
<button id="sim-hour-minus" title="-1 Stunde">&lsaquo;</button>
<button id="sim-now" title="Jetzt">+</button>
<button id="sim-hour-plus" title="+1 Stunde">&rsaquo;</button>
<button id="sim-day-plus" title="+1 Tag">&raquo;</button>
```

**JavaScript-Verarbeitung**:
- `applyDelta(delta)` ändert die simulierte Zeit
- `updateSkyData()` wird mit neuer Zeit aufgerufen
- **Datenabruf**: `load_asteroids_with_interpolation()` und `load_comets_with_interpolation()`
- **Cache-Logik**: Bei Zeitänderung wird zuerst der Cache geprüft

## Was passiert bei fehlenden Daten?

### 1. Cache-MISS bei API Request

```python
# In api/routes/asteroids.py / comets.py
try:
    asteroid_list = load_asteroids_with_interpolation(...)
    if isinstance(asteroid_list, list) and asteroid_list:
        # Cache HIT
        logger.info(f"✅ Cache HIT for asteroids: {len(asteroid_list)} found")
    else:
        # Cache MISS
        logger.warning(f"❌ Cache MISS - triggering asteroid worker")
        background_tasks.add_task(trigger_asteroid_worker, ...)
        asteroid_list = []  # Leere Liste zurückgeben
except Exception as e:
    # Fehler bei Cache-Abfrage
    background_tasks.add_task(trigger_asteroid_worker, ...)
    asteroid_list = []
```

### 2. Simulation ohne Daten

- User klickt auf << < + > >> 
- Neue Zeit wird gesetzt
- `updateSkyData()` ruft API auf
- API prüft Cache für neue Zeit
- Bei Cache-MISS: Background Task wird gestartet
- **User sieht**: Leere Himmelsansicht, Ladeindikator, dann Background-Berechnung
- Nach Berechnung: Daten werden beim nächsten Update angezeigt

### 3. Precompute Coverage Lücken

**Normalfall**: Precompute Coordinator berechnet 30 Tage im Voraus
**Problem**: Wenn Location neu oder Precompute noch nicht gelaufen

**Lösung**: 
- API erkennt Cache-MISS
- Triggered sofortige On-Demand Berechnung
- Precompute füllt die Lücke im nächsten Lauf

## Datenbank-Struktur

### PostgreSQL Tabellen

```sql
-- Asteroiden-Positionen (gecacht)
cached_positions:
├── object_type = 'asteroid'
├── object_id (representative_id)
├── location_key (normalisierte Location)
├── time_bucket (1-Stunden Bucket)
└── position_data (pickled Liste von Asteroiden)

-- Kometen-Positionen (gecacht)  
cached_positions:
├── object_type = 'comet'
├── object_id (representative_id)
├── location_key
├── time_bucket
└── position_data (pickled Liste von Kometen)

-- Rohdaten für Worker
asteroid_dataframes: Pickled DataFrame mit Orbital-Daten
comet_dataframes: Pickled DataFrame mit Kometen-Daten
```

### Cache-Keys

```python
# Location-Key für Cache
location_key = f"{lat_norm:.4f},{lon_norm:.4f},{elev_norm:.0f}"

# Time-Bucket (1 Stunde)
time_bucket = time_bucket_utc(dt_utc, 1)  # Format: YYYY-MM-DDTHH:00:00Z
```

## Performance-Optimierungen

### 1. Interpolation

**Aktueller Status: Interpolation ist DEAKTIVIERT**

Die `load_asteroids_with_interpolation()` und `load_comets_with_interpolation()` Funktionen verwenden derzeit eine **Nearest-Bucket-Strategie** statt echter Interpolation:

```python
# DISABLED INTERPOLATION - Using exact buckets only to avoid position inconsistencies
if list1 and list2:
    # Choose the bucket closer to the requested time
    if factor < 0.5:
        return list1  # Vorheriges Bucket ist näher
    else:
        return list2  # Nächstes Bucket ist näher
```

**Was bei fehlenden Daten passiert:**
- **Nur ein Bucket vorhanden**: Verwendet vorhandenes Bucket
- **Nur zukünftiges Bucket**: Erlaubt bis zu 1h Abweichung, sonst `None`
- **Keine Buckets**: `None` → triggert Background-Berechnung

**Warum deaktiviert?**
- **Positionskonsistenz**: Vermeidung von astronomischen Interpolationsartefakten
- **Azimuth-Wraparound**: Zyklische Interpolation kann Sprünge erzeugen
- **Horizon-Events**: Objekte können nicht-linear am Horizont erscheinen/verschwinden
- **Magnitude-Sprünge**: Helligkeitsänderungen sind oft nicht-linear

**Verfügbare Interpolations-Implementierung (inaktiv):**
- **Lineare Interpolation** für altitude, distance, magnitude, ra, dec
- **Zirkulare Azimuth-Interpolation** mit 0°/360°-Wraparound Handling
- **Objekt-Matching** per Namen mit Behandlung neuer/verschwundener Objekte

### 2. Priority Queues

- RabbitMQ Priority Queue (x-max-priority: 10)
- Nächste 24h bekommen höhere Priorität
- Wichtigere Daten werden zuerst berechnet

### 3. Fair Dispatch

- `prefetch_count=1` verteilt Tasks gleichmäßig
- Verhindert dass ein Worker alle Tasks blockiert
- Ermöglicht horizontale Skalierung

## Fehlerbehandlung und Recovery

### 1. Worker Ausfall

- RabbitMQ sorgt für automatisches Requeuing
- Andere Worker übernehmen die Tasks
- Precompute Coordinator läuft unabhängig weiter

### 2. Datenbank-Ausfall

- Worker warten mit `wait_for_database()`
- API gibt leere Listen zurück
- Background Tasks werden retryed

### 3. Cache-Inkonsistenz

- Precompute prüft vor Task-Erstellung vorhandene Daten
- Doppelte Berechnungen werden vermieden
- On-Demand Berechnung füllt Lücken

## Konfiguration

### Environment Variables

```bash
# Precompute Coordinator
ASCII_SKY_PRECOMPUTE_HOURS=720          # Wie viele Stunden voraus
PRECOMPUTE_COORDINATOR_INTERVAL=3600    # Lauf-Intervall in Sekunden
ASCII_SKY_PRECOMPUTE_LOCATIONS=[]       # JSON-Array mit Locations

# RabbitMQ
RABBITMQ_URL=amqp://admin:changeme@localhost:5672/
RABBITMQ_HEARTBEAT=60
RABBITMQ_PREFETCH_COUNT=1

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=asciisky
POSTGRES_USER=asciisky
POSTGRES_PASSWORD=changeme
```

### Konfigurationsdateien

- `user_settings.json`: Benutzer-Location und Magnitude-Filter
- `precompute_locations.json`: Vordefinierte Locations für Precompute
- `.env.example`: Beispiel-Konfiguration

## Vorschlag: Echte Interpolation Implementierung

### Problemstellung

Die aktuelle Nearest-Bucket-Strategie vermeidet Interpolationsartefakte, erzeugt aber stündliche Sprünge in der Animation. Für flüssige Zeitnavigation (<< < + > >>) wäre echte Interpolation wünschenswert.

### Lösungskonzept: Adaptive Interpolation mit Fallback

#### 1. Interpolations-Strategien je nach Verfügbarkeit

```python
def load_with_smart_interpolation(lat, lon, elevation, dt_utc, bucket_hours, ttl_seconds):
    """Intelligente Interpolation mit mehreren Fallback-Strategien"""
    
    # Bucket-Daten laden
    bucket1_dt, bucket2_dt, factor = get_interpolation_buckets(dt_utc, bucket_hours)
    list1 = load_bucket(lat, lon, elevation, bucket1_dt)
    list2 = load_bucket(lat, lon, elevation, bucket2_dt)
    
    # Fall 1: Beide Buckets vorhanden → Echte Interpolation
    if list1 and list2:
        return interpolate_objects_smart(list1, list2, factor, dt_utc)
    
    # Fall 2: Nur vorheriges Bucket → On-Demand Berechnung + Interpolation  
    if list1 and not list2:
        # Berechne fehlendes Bucket on-demand
        list2 = compute_bucket_on_demand(lat, lon, elevation, bucket2_dt)
        if list2:
            store_bucket(lat, lon, elevation, bucket2_dt, list2)
            return interpolate_objects_smart(list1, list2, factor, dt_utc)
        return list1  # Fallback: Nur vorheriges Bucket
    
    # Fall 3: Nur zukünftiges Bucket → On-Demand Berechnung + Interpolation
    if not list1 and list2:
        # Berechne fehlendes vorheriges Bucket on-demand  
        list1 = compute_bucket_on_demand(lat, lon, elevation, bucket1_dt)
        if list1:
            store_bucket(lat, lon, elevation, bucket1_dt, list1)
            return interpolate_objects_smart(list1, list2, factor, dt_utc)
        # Fallback: Prüfe Zeitabstand
        if (bucket2_dt - dt_utc).total_seconds() <= 3600:  # Max 1h
            return list2
        return None
    
    # Fall 4: Keine Buckets → Berechne beide on-demand
    if not list1 and not list2:
        list1 = compute_bucket_on_demand(lat, lon, elevation, bucket1_dt)
        list2 = compute_bucket_on_demand(lat, lon, elevation, bucket2_dt)
        if list1 and list2:
            store_bucket(lat, lon, elevation, bucket1_dt, list1)
            store_bucket(lat, lon, elevation, bucket2_dt, list2)
            return interpolate_objects_smart(list1, list2, factor, dt_utc)
        return list1 or list2 or None
```

#### 2. Verbesserte Interpolations-Logik

```python
def interpolate_objects_smart(list1, list2, factor, target_dt):
    """Verbesserte Interpolation mit astronomischer Korrektur"""
    
    # Basis-Interpolation
    interpolated = interpolate_object_list(list1, list2, factor)
    
    # Astronomische Korrekturen
    corrected = []
    for obj in interpolated:
        corrected_obj = apply_astronomical_corrections(obj, list1, list2, factor, target_dt)
        corrected.append(corrected_obj)
    
    return corrected

def apply_astronomical_corrections(obj, list1, list2, factor, target_dt):
    """Korrigiert Interpolationsartefakte"""
    
    # 1. Horizon-Event Handling
    if is_horizon_crossing(obj, list1, list2):
        return interpolate_horizon_crossing(obj, list1, list2, factor, target_dt)
    
    # 2. Magnitude Glättung
    if 'magnitude' in obj:
        obj['magnitude'] = smooth_magnitude_interpolation(obj, list1, list2, factor)
    
    # 3. Rise/Set Transit Zeiten neu berechnen
    obj = recalculate_rise_set_transit(obj, target_dt)
    
    return obj

def is_horizon_crossing(obj, list1, list2):
    """Erkennt Horizontüberquerungen zwischen Buckets"""
    obj1_name = find_object_by_name(list1, obj['name'])
    obj2_name = find_object_by_name(list2, obj['name'])
    
    if not obj1_name or not obj2_name:
        return False
    
    alt1 = obj1_name.get('altitude', -999)
    alt2 = obj2_name.get('altitude', -999)
    
    # Horizontüberquerung: ein Bucket über, anderer unter 0°
    return (alt1 > 0 and alt2 <= 0) or (alt1 <= 0 and alt2 > 0)
```

#### 3. On-Demand Bucket Berechnung

```python
def compute_bucket_on_demand(lat, lon, elevation, dt_utc):
    """Berechnet fehlendes Bucket sofort"""
    try:
        # Triggere Background Task für zukünftige Berechnungen
        trigger_background_computation(lat, lon, elevation, dt_utc)
        
        # Synchrone Berechnung für sofortigen Bedarf
        location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        
        # Asteroiden oder Kometen je nach Kontext
        if is_asteroid_request():
            asteroids = bright_asteroids.load_bright_asteroids(
                LOADER, ts, eph, location_dict,
                max_magnitude=20.0,
                current_dt=dt_utc
            )
            return asteroids
        else:
            comets_data = comets.load_comets(
                ts, eph, location_dict,
                max_comets=1000,
                current_dt=dt_utc
            )
            return comets_data
            
    except Exception as e:
        logger.error(f"On-demand bucket computation failed: {e}")
        return None
```

#### 4. Konfiguration

```bash
# Neue Environment Variables
ENABLE_SMART_INTERPOLATION=true          # Echte Interpolation aktivieren
INTERPOLATION_ON_DEMAND=true             # Fehlende Buckets sofort berechnen
INTERPOLATION_MAX_FUTURE_HOURS=2         # Max Zeitabstand für Future-Bucket
INTERPOLATION_CACHE_COMPUTED=true        # On-Demand Berechnungen cachen
```

#### 5. Implementierungs-Schritte

1. **Phase 1**: Smart Interpolation Framework implementieren
2. **Phase 2**: On-Demand Bucket Berechnung integrieren  
3. **Phase 3**: Astronomische Korrekturen entwickeln
4. **Phase 4**: Feature Flag und Testing
5. **Phase 5**: Performance-Optimierung und Monitoring

#### 6. Vorteile dieser Lösung

- **Flüssige Animation**: Echte Interpolation eliminiert stündliche Sprünge
- **Robustheit**: On-Demand Berechnung füllt Cache-Lücken automatisch
- **Konsistenz**: Astronomische Korrekturen vermeiden Interpolationsartefakte
- **Performance**: Berechnete Buckets werden gecacht für zukünftige Nutzung
- **Skalierbarkeit**: Lädt das System nicht unnötig, berechnet nur bei Bedarf

#### 7. Risiken und Mitigations

**Risiko**: Höhere CPU-Auslastung durch On-Demand Berechnungen
**Mitigation**: Intelligente Priorisierung und Background-Processing

**Risiko**: Komplexität der astronomischen Korrekturen
**Mitigation**: Schrittweise Implementierung mit umfangreichem Testing

## Zusammenfassung

Der Workflow ist robust und mehrstufig aufgebaut:

1. **Proaktiv**: Precompute Coordinator berechnet Daten im Voraus
2. **Reaktiv**: API triggert On-Demand Berechnung bei Cache-MISS  
3. **Skalierbar**: RabbitMQ ermöglicht beliebig viele Worker
4. **Fehlertolerant**: Retry-Mechanismen und Fallbacks
5. **Performant**: Cache-First Strategie mit Interpolation

Bei der Simulation (<< < + > >>) werden Daten aus dem PostgreSQL Cache geholt. Fehlende Daten lösen sofort eine Background-Berechnung aus, sodass die Daten beim nächsten Zeitwechsel verfügbar sind. Das System sorgt automatisch für eine vollständige Abdeckung des 30-Tage-Precompute-Fensters.
