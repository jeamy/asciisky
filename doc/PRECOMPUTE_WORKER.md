# Precompute Worker - Dokumentation

## 🎯 Zweck

Der Precompute-Worker berechnet Asteroid- und Kometen-Positionen **im Voraus** und speichert sie im Cache (PostgreSQL). Dadurch sind API-Anfragen **sofort schnell**, ohne auf Berechnungen warten zu müssen.

**Architektur:**
- **Coordinator** (Hauptserver): Erstellt Tasks und publiziert in RabbitMQ Queue
- **Worker** (alle Server): Holen Tasks aus Queue, berechnen, speichern in PostgreSQL
- **Skalierbar**: Mehr Worker = schneller fertig (via `.env`)

---

## ⚙️ Konfiguration

### Environment Variables

**Worker-Skalierung (via .env):**
```bash
PRECOMPUTE_WORKERS=4        # Hauptserver
PRECOMPUTE_WORKERS_B=4      # Worker-B
PRECOMPUTE_WORKERS_C=4      # Worker-C
```

**Coordinator Environment Variables:**

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `ASCII_SKY_PRECOMPUTE_HOURS` | 720 | Zeitfenster in Stunden (720 = 30 Tage) |
| `PRECOMPUTE_COORDINATOR_INTERVAL` | 3600 | Wie oft Tasks erstellen (Sekunden) |
| `RABBITMQ_URL` | amqp://... | RabbitMQ Verbindung |

**Worker Environment Variables:**

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `RABBITMQ_URL` | amqp://... | RabbitMQ Verbindung |
| `RABBITMQ_PREFETCH_COUNT` | 1 | Wie viele Tasks gleichzeitig |
| `POSTGRES_HOST` | postgres | PostgreSQL Server |

### Aktuelle Konfiguration (docker-compose.yml)

```yaml
precompute_worker:
  command: ["python", "precompute_worker.py"]
  environment:
    - ASCII_SKY_PRECOMPUTE_HOURS=720      # 30 Tage im Voraus
    - ASCII_SKY_PRECOMPUTE_KINDS=asteroids,comets
    - ASCII_SKY_PRECOMPUTE_WORKERS=3      # 3 parallele Threads
    - ASCII_SKY_ADAPTIVE_WORKERS=1        # Automatische Anpassung
    - ASCII_SKY_RETENTION_DAYS=7          # Alte Caches nach 7 Tagen löschen
```

---

## 🔄 Funktionsweise

### 1. Stündlicher Sweep

Der Worker läuft **jede Stunde zur vollen Stunde** und prüft:
- Welche Locations müssen berechnet werden?
- Welche Zeitfenster fehlen im Cache?
- Welche Berechnungen sind veraltet?

### 2. Priorisierung

**High Priority (sofort, mehr Worker):**
- Aktuelle Stunde + nächste 6 Stunden (7h total)
- Wichtig für sofortige API-Anfragen

**Low Priority (später, weniger Worker):**
- Stunden 7 bis 720 (oder konfigurierter Wert)
- Für zukünftige Anfragen

### 3. Locations

Der Worker berechnet für folgende Standorte:

**Quellen (in Reihenfolge):**
1. **User-Location** aus `settings.get_location()`
2. **Environment Variable** `ASCII_SKY_PRECOMPUTE_LOCATIONS`:
   ```bash
   # JSON Format
   ASCII_SKY_PRECOMPUTE_LOCATIONS='[
     {"latitude": 48.2082, "longitude": 16.3738, "elevation": 170, "name": "Wien"},
     {"latitude": 52.5200, "longitude": 13.4050, "elevation": 34, "name": "Berlin"}
   ]'
   
   # CSV Format
   ASCII_SKY_PRECOMPUTE_LOCATIONS="48.2082,16.3738,170;52.5200,13.4050,34"
   ```
3. **Datei** `precompute_locations.json` im Projekt-Root:
   ```json
   [
     {"latitude": 48.2082, "longitude": 16.3738, "elevation": 170, "name": "Wien"},
     {"latitude": 52.5200, "longitude": 13.4050, "elevation": 34, "name": "Berlin"}
   ]
   ```
4. **Existierende Cache-Verzeichnisse** (Legacy)

### 4. Cache-Speicherung

**PostgreSQL (Standard):**
- Tabelle: `cached_positions`
- Location Key: `lat+48.2082_lon+16.3738_el+0170`
- Time Bucket: `20251019T12` (6-Stunden-Buckets)
- TTL: 6 Stunden

**PostgreSQL (Production):**
- Gleiche Struktur wie PostgreSQL
- Multi-Host-fähig
- Bessere Concurrency

---

## 📊 Beispiel-Ablauf

### Szenario: 30 Tage Vorausberechnung für Wien

**Konfiguration:**
```yaml
ASCII_SKY_PRECOMPUTE_HOURS=720  # 30 Tage
ASCII_SKY_PRECOMPUTE_KINDS=asteroids,comets
```

**Locations:**
```json
[{"latitude": 48.2082, "longitude": 16.3738, "elevation": 170, "name": "Wien"}]
```

**Ablauf (jede Stunde):**

1. **12:00 Uhr - Sweep startet**
   ```
   High Priority: 12:00-18:00 (7 Stunden)
   Low Priority:  19:00-12:00+30d (713 Stunden)
   ```

2. **Prüfung für jede Stunde:**
   - Existiert Cache für Wien @ 12:00? → Nein → Berechnen
   - Existiert Cache für Wien @ 13:00? → Ja → Überspringen
   - Existiert Cache für Wien @ 14:00? → Nein → Berechnen
   - ... (für alle 720 Stunden)

3. **Berechnung:**
   - Asteroids: ~100 Objekte (je nach Magnitude-Filter)
   - Comets: ~50 Objekte
   - Pro Stunde: ~150 Berechnungen
   - Gesamt: 720h × 150 = **108.000 Berechnungen**

4. **Speicherung:**
   - PostgreSQL: `cached_positions` Tabelle
   - Jede Position als BLOB (pickle-serialisiert)

5. **Cleanup (nach 7 Tagen):**
   - Alte Caches werden gelöscht
   - Nur relevante Zeitfenster bleiben

---

## 🚀 Performance

### Ressourcen-Verbrauch

**CPU:**
- Initial Sweep: Hoch (alle 720h berechnen)
- Stündlich: Niedrig (nur neue Stunden)
- Adaptive Workers passen sich an System-Last an

**RAM:**
- ~500 MB für Worker-Prozess
- ~200 MB für Skyfield-Daten
- Garbage Collection nach jedem Batch

**Disk:**
- PostgreSQL: ~50-100 MB für 30 Tage Cache
- PostgreSQL: Ähnlich, aber besser komprimiert

### Durchsatz

**Mit 3 Workern:**
- ~10-20 Stunden/Minute berechnet
- Initial Sweep (720h): ~30-60 Minuten
- Stündlicher Sweep (1h neu): ~5-10 Sekunden

**Mit Adaptive Workers:**
- Bei niedriger Last: Bis zu 6 Worker
- Bei hoher Last: Reduziert auf 1-2 Worker

---

## 🔍 Monitoring

### Logs prüfen

```bash
# Live-Logs
docker logs -f asciisky-precompute-worker

# Letzte 100 Zeilen
docker logs --tail 100 asciisky-precompute-worker
```

**Wichtige Log-Meldungen:**
```
AsciiSky precompute worker starting...
  kinds=['asteroids', 'comets']
  horizon_hours=720
  max_workers=3
  adaptive_workers=True
  PostgreSQL database: 150 asteroids, 45 comets
  Database size: 85.3 MB

Precompute sweep start: 1 locations, 7+713 hours, kinds=['asteroids', 'comets']
Processing HIGH PRIORITY hours (7h) with 3 workers...
  - done Wien (created=14, checked=7)
Processing LOW PRIORITY hours (713h) with 1 workers...
  - done Wien (created=1426, checked=713)
Precompute sweep complete: created=1440, checked=720

Sleeping 3542s until next hour...
```

### Cache-Statistiken

**PostgreSQL:**
```bash
docker exec asciisky-precompute-worker python -c "
from db_utils import get_database_stats
import json
print(json.dumps(get_database_stats(), indent=2))
"
```

**PostgreSQL:**
```bash
docker exec asciisky-postgres psql -U asciisky -d asciisky -c "
SELECT * FROM cache_statistics;
"
```

---

## 🛠️ Troubleshooting

### Problem: Worker berechnet nichts

**Ursache:** Keine Locations konfiguriert

**Lösung:**
```bash
# Prüfe Locations
docker exec asciisky-precompute-worker python -c "
import precompute_worker
locs = precompute_worker.get_target_locations()
print(f'Locations: {len(locs)}')
for loc in locs:
    print(f'  - {loc}')
"

# Füge Location hinzu
# Option 1: precompute_locations.json erstellen
echo '[{"latitude": 48.2082, "longitude": 16.3738, "elevation": 170, "name": "Wien"}]' > precompute_locations.json

# Option 2: Environment Variable setzen
# In docker-compose.yml:
- ASCII_SKY_PRECOMPUTE_LOCATIONS=[{"latitude": 48.2082, "longitude": 16.3738, "elevation": 170}]
```

### Problem: Hohe CPU-Last

**Ursache:** Zu viele Worker oder zu großes Zeitfenster

**Lösung:**
```yaml
# Reduziere Worker
- ASCII_SKY_PRECOMPUTE_WORKERS=2

# Reduziere Zeitfenster
- ASCII_SKY_PRECOMPUTE_HOURS=168  # 7 Tage statt 30

# Deaktiviere Adaptive Workers
- ASCII_SKY_ADAPTIVE_WORKERS=0
```

### Problem: Disk voll

**Ursache:** Alte Caches werden nicht gelöscht

**Lösung:**
```yaml
# Aktiviere Retention
- ASCII_SKY_RETENTION_DAYS=7  # Lösche nach 7 Tagen

# Manuelles Cleanup
docker exec asciisky-precompute-worker python -c "
from db_utils import cleanup_old_positions
deleted = cleanup_old_positions(retention_days=7)
print(f'Deleted {deleted} old positions')
"
```

### Problem: Worker startet nicht

**Ursache:** Fehlende Abhängigkeiten oder Datenbankfehler

**Lösung:**
```bash
# Prüfe Logs
docker logs asciisky-precompute-worker

# Prüfe Datenbank
docker exec asciisky-precompute-worker python -c "
from db_utils import get_database_stats
print(get_database_stats())
"

# Neustart
docker restart asciisky-precompute-worker
```

---

## 📝 Best Practices

### 1. Zeitfenster sinnvoll wählen

**Empfehlungen:**
- **Entwicklung:** 48-72h (2-3 Tage)
- **Staging:** 168h (7 Tage)
- **Production:** 720h (30 Tage)

**Warum nicht mehr?**
- Orbital-Daten werden wöchentlich aktualisiert
- Alte Berechnungen werden ungenau
- Unnötiger Speicherverbrauch

### 2. Locations begrenzen

**Pro Location:**
- 720h × 150 Objekte = 108.000 Berechnungen
- ~50 MB Cache-Speicher

**Empfehlung:**
- Nur häufig genutzte Locations
- Max. 5-10 Locations für Production

### 3. Retention aktivieren

```yaml
- ASCII_SKY_RETENTION_DAYS=7
```

**Warum?**
- Verhindert Disk-Overflow
- Alte Daten sind ohnehin ungenau
- Bessere Performance

### 4. Monitoring einrichten

```bash
# Cron-Job für tägliche Statistiken
0 6 * * * docker exec asciisky-precompute-worker python -c "from db_utils import get_database_stats; print(get_database_stats())" >> /var/log/asciisky-cache-stats.log
```

---

## 🔗 Zusammenspiel mit RabbitMQ-Workern

**Precompute-Worker:**
- Berechnet **im Voraus** für bekannte Locations
- Läuft **stündlich** automatisch
- Füllt Cache **proaktiv**

**RabbitMQ-Worker:**
- Berechnen **on-demand** für beliebige Locations
- Werden **getriggert** durch API-Anfragen
- Füllen Cache **reaktiv**

**Zusammen:**
- ✅ Bekannte Locations: **Sofort schnell** (Precompute)
- ✅ Neue Locations: **Schnell nach erster Anfrage** (RabbitMQ)
- ✅ Beste User Experience

---

## 📊 Zusammenfassung

| Feature | Wert |
|---------|------|
| **Zeitfenster** | 720 Stunden (30 Tage) |
| **Objekte** | Asteroids + Comets (~150 pro Stunde) |
| **Locations** | Konfigurierbar (JSON/CSV/Env) |
| **Ausführung** | Stündlich zur vollen Stunde |
| **Priorisierung** | High: 0-6h, Low: 7-720h |
| **Worker** | 3 (adaptiv 1-6) |
| **Retention** | 7 Tage |
| **Cache** | PostgreSQL/PostgreSQL |
| **Speicher** | ~50-100 MB für 30 Tage |

**Status:** ✅ Aktiv in `docker-compose.yml`
