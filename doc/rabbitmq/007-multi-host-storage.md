# Multi-Host Storage für ASCII Sky

## Problem

Bei Multi-Host Setups schreiben Worker auf verschiedenen Hosts in **lokale** SQLite-Datenbanken:

```
┌─────────────────┐     ┌─────────────────┐
│    Host 1       │     │    Host 2       │
├─────────────────┤     ├─────────────────┤
│ Web (API)       │     │ Asteroid Worker │
│ asteroids.db    │     │ asteroids.db    │ ❌ Verschiedene!
│ comets.db       │     │ comets.db       │
└─────────────────┘     └─────────────────┘
```

**Problem:**
- ❌ Worker schreiben auf Host 2
- ❌ Web liest von Host 1
- ❌ Daten sind NICHT synchronisiert!

**Hinweis:** Pickle-Cache wurde entfernt - nur noch SQLite!

## Lösung 1: Shared Storage (NFS/GlusterFS) ✅ EMPFOHLEN

### Architektur

```
┌─────────────────┐     ┌─────────────────┐
│    Host 1       │     │    Host 2       │
├─────────────────┤     ├─────────────────┤
│ Web (API)       │     │ Asteroid Worker │
│                 │     │                 │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
         ┌───────────────────────┐
         │   Shared Storage      │
         │   (NFS/GlusterFS)     │
         ├───────────────────────┤
         │ asteroids.db          │
         │ comets.db             │
         └───────────────────────┘
```

### Setup mit NFS

#### 1. NFS Server (z.B. Host 1)

```bash
# NFS Server installieren
sudo apt-get update
sudo apt-get install -y nfs-kernel-server

# Verzeichnis erstellen
sudo mkdir -p /srv/asciisky-cache
sudo chown -R 1000:1000 /srv/asciisky-cache

# NFS Export konfigurieren
echo "/srv/asciisky-cache 192.168.1.0/24(rw,sync,no_subtree_check,no_root_squash)" | sudo tee -a /etc/exports

# NFS neu laden
sudo exportfs -ra
sudo systemctl restart nfs-kernel-server
```

#### 2. NFS Clients (alle Worker-Hosts)

```bash
# NFS Client installieren
sudo apt-get update
sudo apt-get install -y nfs-common

# Mount Point erstellen
sudo mkdir -p /mnt/asciisky-cache

# Mounten
sudo mount 192.168.1.10:/srv/asciisky-cache /mnt/asciisky-cache

# Automatisches Mount bei Boot
echo "192.168.1.10:/srv/asciisky-cache /mnt/asciisky-cache nfs defaults 0 0" | sudo tee -a /etc/fstab
```

#### 3. Docker Compose anpassen

**Auf allen Hosts:**

```yaml
services:
  web:
    volumes:
      - /mnt/asciisky-cache:/app/cache  # Shared Storage!
      
  asteroid-worker-1:
    volumes:
      - /mnt/asciisky-cache:/app/cache  # Shared Storage!
      
  comet-worker-1:
    volumes:
      - /mnt/asciisky-cache:/app/cache  # Shared Storage!
```

### Vorteile NFS

- ✅ Einfaches Setup
- ✅ Alle Hosts sehen dieselben Daten
- ✅ SQLite funktioniert (mit Einschränkungen)
- ✅ Keine Code-Änderungen nötig

### Nachteile NFS

- ⚠️ SQLite über NFS kann langsam sein
- ⚠️ Netzwerk-Latenz
- ⚠️ Single Point of Failure (NFS Server)
- ⚠️ SQLite Locks können problematisch sein

## Lösung 2: PostgreSQL/MySQL ✅ PRODUKTION

### ❓ Wo PostgreSQL installieren?

**Die Platzierung ist wichtig!** PostgreSQL sollte strategisch platziert werden:

| Setup | PostgreSQL auf | Vorteile | Nachteile |
|-------|----------------|----------|-----------|
| **Kleine Prod (2-3 Hosts)** | Host 1 (mit Web) | ✅ Weniger Hosts<br>✅ Günstiger | ⚠️ Web + DB konkurrieren |
| **Mittlere Prod (3-4 Hosts)** | Host 4 (mit RabbitMQ) | ✅ Nutzt vorhandenen Host<br>✅ Gute Performance | ⚠️ Shared Resources |
| **Große Prod (5+ Hosts)** | Host 5 (dediziert) | ✅ Beste Performance<br>✅ Einfaches Backup<br>✅ Skalierbar | ⚠️ Zusätzlicher Host |
| **Enterprise** | Host 5+6 (Cluster) | ✅ Hochverfügbarkeit<br>✅ Replikation<br>✅ Load Balancing | ⚠️ Komplex + teuer |

**Empfehlung für ASCII Sky:**
- 🏠 **Kleine Produktion:** Web + PostgreSQL auf Host 1
- 🌐 **Mittlere Produktion:** RabbitMQ + PostgreSQL auf Host 4
- 🚀 **Große Produktion:** Dedizierter PostgreSQL-Server (Host 5)

**Nicht empfohlen:** PostgreSQL auf Worker-Hosts (konkurriert um CPU für Berechnungen)

### Architektur

```
┌─────────────────┐     ┌─────────────────┐
│    Host 1       │     │    Host 2       │
├─────────────────┤     ├─────────────────┤
│ Web (API)       │     │ Asteroid Worker │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
         ┌───────────────────────┐
         │   PostgreSQL/MySQL    │
         │   (Zentrale DB)       │
         ├───────────────────────┤
         │ asteroid_positions    │
         │ comet_positions       │
         │ asteroid_dataframes   │
         │ comet_dataframes      │
         └───────────────────────┘
```

### Setup mit PostgreSQL

#### 1. PostgreSQL Server installieren

```bash
# Docker Compose erweitern
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: asciisky
      POSTGRES_USER: asciisky
      POSTGRES_PASSWORD: your_secure_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped

volumes:
  postgres_data:
```

#### 2. Code anpassen

**db_utils.py** bereits unterstützt PostgreSQL! Nur Connection-String ändern:

```python
# In config oder Environment Variable
DATABASE_URL = "postgresql://asciisky:password@postgres:5432/asciisky"

# Statt SQLite:
# DATABASE_URL = "sqlite:///cache/asteroids.db"
```

#### 3. Environment Variables setzen

```yaml
services:
  web:
    environment:
      - DATABASE_URL=postgresql://asciisky:password@postgres:5432/asciisky
      
  asteroid-worker-1:
    environment:
      - DATABASE_URL=postgresql://asciisky:password@postgres:5432/asciisky
```

### Vorteile PostgreSQL

- ✅ Echte Multi-Host Unterstützung
- ✅ Schnelle Queries
- ✅ ACID-Garantien
- ✅ Keine Netzwerk-Latenz-Probleme
- ✅ Backup/Restore einfach
- ✅ Skalierbar

### Nachteile PostgreSQL

- ⚠️ Zusätzlicher Service
- ⚠️ Code-Änderungen nötig (minimal)
- ⚠️ Mehr Ressourcen

## Lösung 3: PostgreSQL mit Replikation ✅ BESTE LÖSUNG

### Architektur

```
┌─────────────────┐     ┌─────────────────┐
│    Host 1       │     │    Host 2       │
├─────────────────┤     ├─────────────────┤
│ Web (API)       │     │ Asteroid Worker │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
         ┌───────────────────────┐
         │ PostgreSQL Cluster    │
         │ (Primary + Replica)   │
         ├───────────────────────┤
         │ asteroid_positions    │
         │ comet_positions       │
         │ asteroid_dataframes   │
         │ comet_dataframes      │
         └───────────────────────┘
```

**Beste Lösung:**
- ✅ PostgreSQL für alle Daten
- ✅ Replikation für Hochverfügbarkeit
- ✅ Schnell + Zuverlässig + Skalierbar

## Empfehlung für ASCII Sky

### Entwicklung / Testing
```bash
# Single Host - kein Shared Storage nötig
docker compose up -d
```

### Kleine Produktion (2-3 Hosts)
```bash
# NFS für Cache
# Einfach, funktioniert sofort
```

### Große Produktion (4+ Hosts)
```bash
# PostgreSQL mit Replikation
# Beste Performance + Zuverlässigkeit
```

## Aktuelle Implementierung

**Status:** Aktuell nutzt ASCII Sky **lokale SQLite**.

**Dateien:**
- `asteroids.db` - SQLite DB für Asteroid-Positionen & Dataframes
- `comets.db` - SQLite DB für Comet-Positionen & Dataframes

**Code-Stellen:**
- `cache_utils.py` - Location/Time-Utilities
- `db_utils.py` - SQLite Connection
- `bright_asteroids.py` - Schreibt in SQLite
- `comets.py` - Schreibt in SQLite

**Hinweis:** Pickle-Cache wurde entfernt - nur noch SQLite!

## Migration zu Shared Storage

### Schritt 1: NFS Setup (siehe oben)

### Schritt 2: Docker Compose anpassen

```yaml
# Auf allen Hosts
services:
  web:
    volumes:
      - /mnt/asciisky-cache:/app/cache
      
  asteroid-worker-1:
    volumes:
      - /mnt/asciisky-cache:/app/cache
```

### Schritt 3: Testen

```bash
# Host 1: Worker startet Task
docker compose logs asteroid-worker-1

# Host 2: Web liest Cache
curl "http://localhost:8000/api/bright_asteroids?lat=48.2&lon=16.3"

# Prüfen ob SQLite DB da ist
ls -la /mnt/asciisky-cache/*.db
```

### Schritt 4: Monitoring

```bash
# NFS Mount prüfen
df -h | grep asciisky-cache

# Cache-Größe überwachen
du -sh /mnt/asciisky-cache/

# SQLite Locks prüfen (bei Problemen)
lsof /mnt/asciisky-cache/*.db
```

## Troubleshooting

### Problem: SQLite Database is locked

**Ursache:** Mehrere Worker greifen gleichzeitig auf SQLite über NFS zu.

**Lösung:**
```python
# In db_utils.py Connection-String anpassen
engine = create_engine(
    'sqlite:///cache/asteroids.db',
    connect_args={
        'timeout': 30,  # Erhöhen!
        'check_same_thread': False
    }
)
```

### Problem: Langsame Writes über NFS

**Ursache:** Netzwerk-Latenz + SQLite über NFS.

**Lösung:**
1. NFS Mount-Optionen optimieren:
   ```bash
   mount -o rw,sync,hard,intr,rsize=8192,wsize=8192 ...
   ```
2. Oder: PostgreSQL nutzen (siehe Lösung 2)

### Problem: Cache inkonsistent

**Ursache:** Race Conditions bei gleichzeitigen SQLite-Writes.

**Lösung:**
- SQLite WAL-Mode aktivieren (Write-Ahead Logging)
- Oder: PostgreSQL mit Transactions (empfohlen)

## Zusammenfassung

| Lösung | Setup | Performance | Zuverlässigkeit | Empfehlung |
|--------|-------|-------------|-----------------|------------|
| **Lokal (SQLite)** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | Dev/Testing |
| **NFS + SQLite** | ⭐⭐ | ⭐⭐ | ⭐⭐ | Kleine Prod |
| **PostgreSQL** | ⭐ | ⭐⭐⭐ | ⭐⭐⭐ | Große Prod |
| **PostgreSQL Cluster** | ⭐ | ⭐⭐⭐ | ⭐⭐⭐ | Beste Lösung |

**Für ASCII Sky empfohlen:**
- 🏠 **Entwicklung:** Lokal SQLite (aktuell)
- 🌐 **Kleine Produktion:** NFS + SQLite (einfach)
- 🚀 **Große Produktion:** PostgreSQL Cluster (beste Performance)
