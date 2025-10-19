# ASCII Sky - Aktuelle Architektur-Analyse

## Übersicht der aktuellen Architektur

### Komponenten

#### 1. Web Service (FastAPI)
- **Funktion**: REST API Server
- **Port**: 8000
- **Technologie**: Python, FastAPI, Uvicorn
- **Aufgaben**:
  - Empfängt HTTP-Requests vom Frontend
  - Liefert vorberechnete Daten aus Cache/SQLite
  - Triggert Background-Tasks für fehlende Daten
  - Session-Management

#### 2. Worker Service (Precompute Worker)
- **Funktion**: Kontinuierliche Cache-Generierung
- **Technologie**: Python, Skyfield
- **Aufgaben**:
  - Berechnet Himmelsdaten für 720 Stunden (30 Tage) im Voraus
  - Läuft stündlich und aktualisiert rollendes Zeitfenster
  - Nutzt 4 parallele Worker-Threads
  - Adaptive Worker-Skalierung basierend auf CPU-Last
  - Retention-Pruning (löscht Daten älter als 30 Tage)

#### 3. Task Worker (Precompute Task Worker)
- **Funktion**: On-Demand Berechnung für spezifische Zeiträume
- **Technologie**: Python, Skyfield
- **Aufgaben**:
  - Wird vom Web Service per `docker exec` gestartet
  - Berechnet Daten für benutzerdefinierte Zeiträume
  - Prioritätsbasierte Verarbeitung (aktuell → Zukunft → Vergangenheit)
  - Schreibt Status in JSON-Dateien

#### 4. Data Updater Service
- **Funktion**: Nächtliche Datenaktualisierung
- **Technologie**: Python
- **Aufgaben**:
  - Läuft täglich um 2:00 Uhr
  - Lädt aktuelle Orbital-Elemente von MPC
  - Aktualisiert SQLite-Datenbank

#### 5. Task Cleanup Service
- **Funktion**: Aufräumen alter Task-Dateien
- **Technologie**: Python
- **Aufgaben**:
  - Läuft alle 60 Sekunden
  - Löscht alte Task- und Status-Dateien

### Datenfluss (aktuell)

```
┌─────────────────┐
│   Frontend      │
│  (Browser)      │
└────────┬────────┘
         │ HTTP Request
         ▼
┌─────────────────┐
│   Web Service   │◄──────┐
│   (FastAPI)     │       │
└────────┬────────┘       │
         │                │
         ├─ Read Cache ───┤
         │                │
         ▼                │
┌─────────────────┐       │
│  SQLite DB +    │       │
│  Pickle Cache   │       │
└────────┬────────┘       │
         │                │
         │ Cache Miss     │
         ▼                │
┌─────────────────┐       │
│  Background     │       │
│  Trigger        │       │
└────────┬────────┘       │
         │                │
         ▼                │
┌─────────────────┐       │
│  Task Worker    │       │
│  (docker exec)  │       │
└────────┬────────┘       │
         │                │
         │ Compute        │
         │ (Skyfield)     │
         │                │
         ├─ Write Cache ──┘
         │
         ▼
┌─────────────────┐
│  Precompute     │
│  Worker         │
│  (continuous)   │
└─────────────────┘
```

### Datentypen und Berechnungen

#### Asteroiden (bright_asteroids.py)
- **Quelle**: MPCORB.DAT von MPC
- **Anzahl**: ~2200 Objekte (H ≤ 12.0)
- **Berechnung**:
  - Orbital-Elemente → Skyfield KeplerOrbit
  - Position (Alt/Az) für Standort/Zeit
  - Apparent Magnitude (H-G System)
  - Rise/Set/Transit Zeiten
- **Cache-Granularität**: 1 Stunde
- **Cache-TTL**: 31 Tage

#### Kometen (comets.py)
- **Quelle**: COMET_ELEMENTS.txt von MPC
- **Anzahl**: ~1200 Objekte (M1 ≤ 18.0)
- **Berechnung**:
  - Orbital-Elemente → Skyfield KeplerOrbit
  - Position (Alt/Az) für Standort/Zeit
  - Apparent Magnitude (M1/k1 Modell)
  - Rise/Set/Transit Zeiten
- **Cache-Granularität**: 1 Stunde
- **Cache-TTL**: 31 Tage

#### Planeten & Himmelskörper (api/computation.py)
- **Quelle**: JPL Ephemeris (de421.bsp)
- **Objekte**: Sonne, Mond, Merkur, Venus, Mars, Jupiter, Saturn, Uranus, Neptun
- **Berechnung**:
  - Echtzeit-Berechnung (kein Cache)
  - Position (Alt/Az) für Standort/Zeit
  - Magnitude (Skyfield planetary_magnitude)
  - Rise/Set/Transit Zeiten
  - Mondphase

#### Sternbilder (api/routes/zodiac.py)
- **Quelle**: constellationship.fab (Stellarium)
- **Anzahl**: 18 Sternbilder
- **Berechnung**:
  - Stern-Positionen aus Hipparcos-Katalog
  - Linien zwischen Sternen
  - Echtzeit-Berechnung

### Cache-Strategie

#### SQLite Datenbank (celestial_cache.db)
- **Tabellen**:
  - `asteroids`: DataFrame mit Orbital-Elementen
  - `comets`: DataFrame mit Orbital-Elementen
  - `asteroid_positions`: Vorberechnete Positionen (location_key, time_bucket)
  - `comet_positions`: Vorberechnete Positionen (location_key, time_bucket)

#### Pickle Cache (Fallback)
- **Struktur**: `cache/{kind}/{location_key}/{time_bucket}.pkl`
- **Location Key**: `lat+48.2082_lon+16.3738_el+0170`
- **Time Bucket**: `20250117T14` (YYYYMMDDTHH)

#### Cache-Hierarchie
1. **SQLite** (primär, schnell)
2. **Pickle** (Fallback, kann deaktiviert werden)
3. **On-Demand Berechnung** (bei Cache Miss)

### Skalierungsprobleme

#### 1. Shared Filesystem
- Alle Container teilen Volume für Cache
- Keine echte Verteilung möglich
- Single Point of Failure

#### 2. Tight Coupling
- Web Service startet Task Worker per `docker exec`
- Keine Entkopplung zwischen Komponenten
- Schwierig zu skalieren

#### 3. Polling-basierte Kommunikation
- Task Status über JSON-Dateien
- Keine Event-basierte Architektur
- Ineffizient bei vielen Requests

#### 4. Standort-spezifische Caches
- Jeder Standort benötigt eigenen Cache
- Keine Wiederverwendung zwischen Standorten
- Cache-Explosion bei vielen Nutzern

#### 5. Synchrone Berechnungen
- Task Worker blockiert während Berechnung
- Keine Parallelisierung über Container hinweg
- Begrenzte Durchsatzrate

### Stärken der aktuellen Architektur

1. **Skyfield Integration**: Bewährte, präzise Berechnungen
2. **Precompute-Strategie**: Reduziert Latenz für häufige Anfragen
3. **Prioritätsbasierte Verarbeitung**: Aktuelle Daten zuerst
4. **Adaptive Worker-Skalierung**: Passt sich an Systemlast an
5. **Retention-Management**: Automatisches Aufräumen alter Daten
6. **SQLite-Backend**: Schneller als Pickle, strukturiert

### Schwächen für Kafka-Migration

1. **Monolithische Worker**: Berechnen alle Datentypen
2. **Keine Message Queue**: Direkte Prozess-Kommunikation
3. **Keine Event-Sourcing**: Zustandsänderungen nicht nachvollziehbar
4. **Keine Consumer Groups**: Keine parallele Verarbeitung
5. **Keine Replay-Fähigkeit**: Daten können nicht neu verarbeitet werden
6. **Keine Stream Processing**: Batch-orientiert statt Stream-orientiert
