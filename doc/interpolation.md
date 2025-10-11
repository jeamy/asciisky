# Cache-Interpolation für Kometen und Asteroiden

## Übersicht

Die Cache-Daten für Kometen und Asteroiden werden stündlich zur Minute 0 berechnet (z.B. 14:00, 15:00, 16:00). Wenn eine Darstellung zu einer anderen Uhrzeit angefordert wird (z.B. 14:37), wird zwischen den umgebenden Cache-Buckets interpoliert.

## Cache-Strategie

### Berechnungszeitpunkte

- **Bucket-Größe**: 1 Stunde
- **Berechnungszeitpunkte**: Zur vollen Stunde (Minute 0)
  - Beispiel: 00:00, 01:00, 02:00, ..., 23:00
- **Bucket-Berechnung**: `bucket_hour = (dt.hour // bucket_hours) * bucket_hours`
  - 14:37 → Bucket "20241011T14" (14:00)
  - 15:42 → Bucket "20241011T15" (15:00)

### TTL (Time To Live)

- **Asteroiden**: 49 Stunden (`ASTEROID_CACHE_TTL_SECONDS = 49 * 3600`)
- **Kometen**: 49 Stunden (`COMET_CACHE_TTL_SECONDS = 49 * 3600`)

Die TTL von 49 Stunden ermöglicht es, dass vorberechnete Daten für das 48-Stunden-Precompute-Fenster gültig bleiben.

## Interpolation

### Funktionsweise

Wenn Daten für einen Zeitpunkt zwischen zwei Cache-Buckets angefordert werden:

1. **Bucket-Ermittlung**: Die beiden umgebenden Buckets werden identifiziert
   - Beispiel für 14:37: Bucket1 = 14:00, Bucket2 = 15:00

2. **Interpolationsfaktor**: Berechnung des Faktors zwischen 0.0 und 1.0
   - `factor = (dt - bucket1) / (bucket2 - bucket1)`
   - Beispiel für 14:37: `factor = 37/60 ≈ 0.617`

3. **Daten laden**: Beide Buckets werden aus dem Cache geladen (SQLite oder Pickle)

4. **Interpolation**: Für jedes Objekt werden die Positionen interpoliert
   - Lineare Interpolation für: `altitude`, `azimuth`, `distance`, `magnitude`, `ra`, `dec`
   - Zirkuläre Interpolation für `azimuth` (berücksichtigt 0°/360° Übergang)
   - String-Felder (Name, Aufgangs-/Untergangszeiten) werden nicht interpoliert

### Implementierung

#### Module

- **`api/interpolation.py`**: Kern-Interpolationslogik
  - `interpolate_position()`: Interpoliert einzelne Objektpositionen
  - `interpolate_azimuth()`: Zirkuläre Interpolation für Azimut-Winkel
  - `interpolate_object_list()`: Interpoliert Listen von Objekten
  - `get_interpolation_buckets()`: Berechnet umgebende Buckets und Faktor

- **`api/cache_interpolation.py`**: Cache-Zugriff mit Interpolation
  - `load_asteroids_with_interpolation()`: Lädt und interpoliert Asteroiden-Daten
  - `load_comets_with_interpolation()`: Lädt und interpoliert Kometen-Daten

#### Integration in Routes

Die Interpolation ist in den API-Endpunkten integriert:

- **`/api/bright_asteroids`** (`api/routes/asteroids.py`)
- **`/api/comets`** (`api/routes/comets.py`)

### Fallback-Verhalten

Wenn keine Cache-Daten verfügbar sind:

1. **Interpolation schlägt fehl**: Keine Daten für beide Buckets
2. **Teilweise Daten**: Wenn nur ein Bucket verfügbar ist, werden diese Daten verwendet
3. **Keine Daten**: Leeres Ergebnis wird zurückgegeben, Background-Precompute wird getriggert

## Vorteile

1. **Präzisere Positionen**: Objekte werden für die exakte Anzeigezeit interpoliert
2. **Flüssigere Animation**: Bei Zeitnavigation bewegen sich Objekte kontinuierlich
3. **Effizienz**: Nur stündliche Berechnungen nötig, Zwischenwerte werden interpoliert
4. **Geringer Overhead**: Interpolation ist sehr schnell (nur mathematische Operationen)

## Genauigkeit

Die lineare Interpolation ist für die meisten Himmelsobjekte über 1 Stunde sehr genau:

- **Planeten**: Bewegung ist nahezu linear über 1 Stunde
- **Asteroiden**: Sehr langsame Bewegung, lineare Interpolation ausreichend
- **Kometen**: Etwas schnellere Bewegung, aber über 1 Stunde noch linear genug
- **Azimut**: Zirkuläre Interpolation verhindert Fehler am 0°/360° Übergang

Für höchste Präzision könnten kürzere Bucket-Intervalle verwendet werden (z.B. 30 Minuten), aber 1 Stunde ist ein guter Kompromiss zwischen Genauigkeit und Cache-Größe.

## Konfiguration

Die Interpolation kann durch Anpassung der Bucket-Größe konfiguriert werden:

```python
# In bright_asteroids.py
ASTEROID_CACHE_BUCKET_HOURS = 1  # 1-Stunden-Buckets

# In comets.py
COMET_CACHE_BUCKET_HOURS = 1  # 1-Stunden-Buckets
```

Kleinere Werte (z.B. 0.5 für 30-Minuten-Buckets) erhöhen die Genauigkeit, aber auch die Cache-Größe und Berechnungslast.
