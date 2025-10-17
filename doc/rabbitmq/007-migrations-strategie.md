# ASCII Sky - RabbitMQ Migrations-Strategie: Alte vs. Neue Sourcen

## Übersicht

Diese Strategie beschreibt, wie alte und neue Architektur während der RabbitMQ-Migration parallel laufen und schrittweise umgestellt werden.

## Strategie: Strangler Fig Pattern

Das **Strangler Fig Pattern** ermöglicht eine schrittweise Migration ohne Big Bang:

```
┌─────────────────────────────────────────────────────────────┐
│                    Migration Timeline                        │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Woche 0-2:   100% Alt  ████████████████████████████         │
│  Woche 3-5:    90% Alt  ██████████████████████░░             │
│  Woche 6-8:    70% Alt  ████████████████░░░░░░               │
│  Woche 9-11:   40% Alt  ██████████░░░░░░░░░░░░               │
│  Woche 12-14:  10% Alt  ██░░░░░░░░░░░░░░░░░░░░               │
│  Woche 15+:     0% Alt  ░░░░░░░░░░░░░░░░░░░░░░               │
│                                                               │
│  ████ = Alte Architektur    ░░░░ = Neue RabbitMQ-Architektur │
└─────────────────────────────────────────────────────────────┘
```

## Architektur-Trennung

### Verzeichnisstruktur

```
/media/data/programming/asciisky/
├── api/                          # Web Service
│   ├── routes/
│   │   ├── asteroids.py          # WIRD ANGEPASST (Feature Flags)
│   │   ├── comets.py             # WIRD ANGEPASST
│   │   └── celestial.py          # WIRD ANGEPASST
│   ├── computation.py            # ALT (bleibt für Fallback)
│   └── rabbitmq/                 # NEU
│       ├── __init__.py
│       ├── client.py             # RabbitMQ Client
│       ├── rpc_client.py         # RPC Pattern
│       └── config.py             # RabbitMQ Konfiguration
│
├── workers/                      # NEU - RabbitMQ Worker
│   ├── __init__.py
│   ├── base_worker.py            # Basis-Klasse
│   ├── asteroid_worker.py        # Asteroid-Berechnungen
│   ├── comet_worker.py           # Komet-Berechnungen
│   ├── celestial_worker.py       # Planeten/Sonne/Mond
│   └── constellation_worker.py   # Sternbilder
│
├── background.py                 # ALT (wird deprecated)
├── precompute_worker.py          # ALT (wird durch RabbitMQ ersetzt)
│
├── scheduler/                    # NEU - RabbitMQ Scheduler
│   ├── __init__.py
│   └── precompute_scheduler.py   # Ersetzt precompute_worker.py
│
├── config/
│   ├── settings.py               # WIRD ERWEITERT (Feature Flags)
│   └── feature_flags.py          # NEU
│
└── docker-compose.yml            # WIRD ERWEITERT (neue Services)
```

## Feature Flags System

### Implementierung

**Datei**: `config/feature_flags.py`

```python
import os
from enum import Enum

class FeatureFlag(Enum):
    """Feature Flags für schrittweise Migration"""
    USE_RABBITMQ = "USE_RABBITMQ"
    USE_RABBITMQ_ASTEROIDS = "USE_RABBITMQ_ASTEROIDS"
    USE_RABBITMQ_COMETS = "USE_RABBITMQ_COMETS"
    USE_RABBITMQ_CELESTIAL = "USE_RABBITMQ_CELESTIAL"
    USE_RABBITMQ_CONSTELLATIONS = "USE_RABBITMQ_CONSTELLATIONS"
    RABBITMQ_PERCENTAGE = "RABBITMQ_PERCENTAGE"  # 0-100

class FeatureFlags:
    """Zentrale Feature Flag Verwaltung"""
    
    @staticmethod
    def is_enabled(flag: FeatureFlag) -> bool:
        """Prüft ob Feature Flag aktiviert ist"""
        env_value = os.environ.get(flag.value, "false").lower()
        return env_value in ("true", "1", "yes", "on")
    
    @staticmethod
    def get_percentage(flag: FeatureFlag) -> int:
        """Gibt Prozentsatz für graduelle Rollouts zurück"""
        try:
            return int(os.environ.get(flag.value, "0"))
        except ValueError:
            return 0
    
    @staticmethod
    def should_use_rabbitmq(user_id: str = None) -> bool:
        """
        Entscheidet ob RabbitMQ verwendet werden soll.
        Unterstützt graduelles Rollout basierend auf User-ID Hash.
        """
        # Globaler Flag
        if not FeatureFlags.is_enabled(FeatureFlag.USE_RABBITMQ):
            return False
        
        # Prozentbasiertes Rollout
        percentage = FeatureFlags.get_percentage(FeatureFlag.RABBITMQ_PERCENTAGE)
        if percentage == 0:
            return False
        if percentage >= 100:
            return True
        
        # Hash-basierte Verteilung (konsistent pro User)
        if user_id:
            import hashlib
            hash_value = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
            return (hash_value % 100) < percentage
        
        # Fallback: Random
        import random
        return random.randint(0, 99) < percentage

# Globale Instanz
feature_flags = FeatureFlags()
```

**Datei**: `config/settings.py` (erweitern)

```python
import os
from config.feature_flags import FeatureFlags, FeatureFlag

class Settings:
    # Bestehende Settings...
    
    # RabbitMQ Settings
    RABBITMQ_URL = os.environ.get(
        'RABBITMQ_URL',
        'amqp://admin:password@192.168.1.10:5672/'
    )
    RABBITMQ_ENABLED = FeatureFlags.is_enabled(FeatureFlag.USE_RABBITMQ)
    RABBITMQ_TIMEOUT = int(os.environ.get('RABBITMQ_TIMEOUT', '30'))
    RABBITMQ_RETRY_ATTEMPTS = int(os.environ.get('RABBITMQ_RETRY_ATTEMPTS', '3'))
    
    # Feature Flags
    USE_RABBITMQ_ASTEROIDS = FeatureFlags.is_enabled(FeatureFlag.USE_RABBITMQ_ASTEROIDS)
    USE_RABBITMQ_COMETS = FeatureFlags.is_enabled(FeatureFlag.USE_RABBITMQ_COMETS)
    USE_RABBITMQ_CELESTIAL = FeatureFlags.is_enabled(FeatureFlag.USE_RABBITMQ_CELESTIAL)
    
    # Fallback Settings
    FALLBACK_TO_OLD_ON_ERROR = os.environ.get('FALLBACK_TO_OLD_ON_ERROR', 'true').lower() == 'true'

settings = Settings()
```

## API-Anpassungen mit Feature Flags

### Beispiel: Asteroids Endpoint

**Datei**: `api/routes/asteroids.py`

```python
from fastapi import APIRouter, Request, HTTPException
from config.settings import settings
from config.feature_flags import feature_flags, FeatureFlag
import logging

# Alte Imports
from api.computation import compute_asteroids_old
from api.background import trigger_precompute_task

# Neue Imports
from api.rabbitmq.rpc_client import RabbitMQRPCClient

router = APIRouter()
logger = logging.getLogger(__name__)

# RabbitMQ Client (lazy init)
rabbitmq_client = None

def get_rabbitmq_client():
    """Lazy initialization von RabbitMQ Client"""
    global rabbitmq_client
    if rabbitmq_client is None and settings.RABBITMQ_ENABLED:
        from api.rabbitmq.rpc_client import RabbitMQRPCClient
        rabbitmq_client = RabbitMQRPCClient(settings.RABBITMQ_URL)
    return rabbitmq_client

@router.get("/bright_asteroids")
async def get_bright_asteroids(
    request: Request,
    lat: float = None,
    lon: float = None,
    elev: float = None,
    magnitude: float = 10.0
):
    """
    Asteroid-Daten abrufen.
    Verwendet RabbitMQ oder alte Architektur basierend auf Feature Flags.
    """
    # Location ermitteln
    location = get_location(request, lat, lon, elev)
    location_key = build_location_key(location)
    time_bucket = get_time_bucket()
    
    # Cache prüfen (Redis/SQLite - unabhängig von Architektur)
    cached = check_cache(location_key, time_bucket, 'asteroids')
    if cached:
        logger.info(f"Cache hit for asteroids: {location_key}")
        return cached
    
    # Feature Flag prüfen
    use_rabbitmq = (
        settings.RABBITMQ_ENABLED and
        feature_flags.is_enabled(FeatureFlag.USE_RABBITMQ_ASTEROIDS) and
        feature_flags.should_use_rabbitmq(request.session.get('user_id'))
    )
    
    if use_rabbitmq:
        logger.info(f"Using RabbitMQ for asteroids: {location_key}")
        try:
            result = await compute_asteroids_rabbitmq(location, time_bucket, magnitude)
            
            # Cache Update
            update_cache(location_key, time_bucket, 'asteroids', result)
            
            return result
            
        except Exception as e:
            logger.error(f"RabbitMQ error: {e}")
            
            # Fallback zur alten Architektur
            if settings.FALLBACK_TO_OLD_ON_ERROR:
                logger.warning("Falling back to old architecture")
                return await compute_asteroids_old_architecture(location, time_bucket, magnitude)
            else:
                raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    
    else:
        logger.info(f"Using old architecture for asteroids: {location_key}")
        return await compute_asteroids_old_architecture(location, time_bucket, magnitude)

async def compute_asteroids_rabbitmq(location, time_bucket, magnitude):
    """Neue RabbitMQ-basierte Berechnung"""
    client = get_rabbitmq_client()
    
    request_data = {
        'task_id': f"asteroid_{int(time.time())}_{uuid.uuid4().hex[:8]}",
        'type': 'asteroid',
        'location': location,
        'time_bucket': time_bucket,
        'magnitude': magnitude
    }
    
    # RPC Call mit Timeout
    result = client.call(
        queue='asteroid',
        request=request_data,
        priority=10,
        timeout=settings.RABBITMQ_TIMEOUT
    )
    
    return result['asteroids']

async def compute_asteroids_old_architecture(location, time_bucket, magnitude):
    """Alte Architektur (Fallback)"""
    # Cache Miss -> Background Task triggern
    task_id = trigger_precompute_task(location, time_bucket, 'asteroids')
    
    # Synchrone Berechnung als Fallback
    result = compute_asteroids_old(location, time_bucket, magnitude)
    
    return result
```

## Docker Compose Anpassungen

### Erweiterte docker-compose.yml

**Datei**: `docker-compose.yml`

```yaml
version: '3.8'

services:
  # ===== ALTE SERVICES (bleiben während Migration) =====
  
  web:
    build: .
    command: ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
    ports:
      - "8000:8000"
    environment:
      # Feature Flags
      - USE_RABBITMQ=true
      - USE_RABBITMQ_ASTEROIDS=true      # Schrittweise aktivieren
      - USE_RABBITMQ_COMETS=false        # Noch nicht aktiv
      - USE_RABBITMQ_CELESTIAL=false
      - RABBITMQ_PERCENTAGE=50           # 50% der Requests über RabbitMQ
      - FALLBACK_TO_OLD_ON_ERROR=true
      
      # RabbitMQ Connection
      - RABBITMQ_URL=amqp://admin:password@192.168.1.10:5672/
      - RABBITMQ_TIMEOUT=30
    volumes:
      - .:/app
      - cache:/app/cache
    depends_on:
      - rabbitmq-1  # NEU
    restart: unless-stopped
  
  worker:
    build: .
    command: ["python", "precompute_worker.py"]
    environment:
      - USE_RABBITMQ=false  # Alte Worker laufen noch
    volumes:
      - .:/app
      - cache:/app/cache
    restart: unless-stopped
  
  # ===== NEUE RABBITMQ SERVICES =====
  
  # RabbitMQ Worker (neue Architektur)
  asteroid-worker-1:
    build: .
    command: ["python", "workers/asteroid_worker.py"]
    environment:
      - RABBITMQ_URL=amqp://admin:password@192.168.1.10:5672/
      - WORKER_ID=asteroid-worker-1
      - LOG_LEVEL=info
    volumes:
      - .:/app
    restart: unless-stopped
    depends_on:
      - rabbitmq-1
  
  asteroid-worker-2:
    build: .
    command: ["python", "workers/asteroid_worker.py"]
    environment:
      - RABBITMQ_URL=amqp://admin:password@192.168.1.10:5672/
      - WORKER_ID=asteroid-worker-2
    volumes:
      - .:/app
    restart: unless-stopped
    depends_on:
      - rabbitmq-1
  
  comet-worker-1:
    build: .
    command: ["python", "workers/comet_worker.py"]
    environment:
      - RABBITMQ_URL=amqp://admin:password@192.168.1.10:5672/
      - WORKER_ID=comet-worker-1
    volumes:
      - .:/app
    restart: unless-stopped
    depends_on:
      - rabbitmq-1
  
  # RabbitMQ Scheduler (ersetzt precompute_worker.py)
  scheduler:
    build: .
    command: ["python", "scheduler/precompute_scheduler.py"]
    environment:
      - RABBITMQ_URL=amqp://admin:password@192.168.1.10:5672/
      - SCHEDULE_INTERVAL=3600  # Stündlich
    volumes:
      - .:/app
    restart: unless-stopped
    depends_on:
      - rabbitmq-1

volumes:
  cache:
    driver: local
```

## Schrittweises Rollout

### Phase 1: Infrastruktur (Woche 1-2)

```bash
# RabbitMQ Cluster deployen (auf separaten Hosts)
# Siehe 003-rabbitmq-4.1-multi-host-setup.md

# Feature Flags: Alles AUS
export USE_RABBITMQ=false
export USE_RABBITMQ_ASTEROIDS=false
export USE_RABBITMQ_COMETS=false
```

### Phase 2: Asteroid Worker (Woche 3-5)

```bash
# 1. Asteroid Worker deployen
docker compose up -d asteroid-worker-1 asteroid-worker-2

# 2. Feature Flag aktivieren (10% Traffic)
docker compose exec web bash -c "export USE_RABBITMQ=true && \
  export USE_RABBITMQ_ASTEROIDS=true && \
  export RABBITMQ_PERCENTAGE=10"

# 3. Monitoring: Fehlerrate prüfen
docker logs asteroid-worker-1 -f

# 4. Schrittweise erhöhen
# 10% -> 25% -> 50% -> 75% -> 100%
```

### Phase 3: Comet Worker (Woche 6-8)

```bash
# Analog zu Phase 2
docker compose up -d comet-worker-1 comet-worker-2
export USE_RABBITMQ_COMETS=true
export RABBITMQ_PERCENTAGE=10
# ... schrittweise erhöhen
```

### Phase 4: Alte Services deaktivieren (Woche 12-14)

```bash
# Wenn 100% auf RabbitMQ:
docker compose stop worker  # Alte Worker stoppen
docker compose stop worker_once

# Feature Flags aufräumen
export RABBITMQ_PERCENTAGE=100
export FALLBACK_TO_OLD_ON_ERROR=false

# Alte Code-Dateien entfernen (nach Backup!)
# mv background.py background.py.old
# mv precompute_worker.py precompute_worker.py.old
```

## Monitoring während Migration

### Metriken erfassen

**Datei**: `api/monitoring.py`

```python
from prometheus_client import Counter, Histogram, Gauge
import time

# Metriken
requests_total = Counter(
    'asciisky_requests_total',
    'Total requests',
    ['endpoint', 'architecture']  # architecture: 'old' oder 'rabbitmq'
)

request_duration = Histogram(
    'asciisky_request_duration_seconds',
    'Request duration',
    ['endpoint', 'architecture']
)

rabbitmq_errors = Counter(
    'asciisky_rabbitmq_errors_total',
    'RabbitMQ errors',
    ['endpoint', 'error_type']
)

fallback_count = Counter(
    'asciisky_fallback_total',
    'Fallbacks to old architecture',
    ['endpoint', 'reason']
)

architecture_percentage = Gauge(
    'asciisky_architecture_percentage',
    'Percentage of requests using architecture',
    ['architecture']
)

def track_request(endpoint: str, architecture: str):
    """Trackt Request"""
    requests_total.labels(endpoint=endpoint, architecture=architecture).inc()

def track_duration(endpoint: str, architecture: str, duration: float):
    """Trackt Dauer"""
    request_duration.labels(endpoint=endpoint, architecture=architecture).observe(duration)

def track_rabbitmq_error(endpoint: str, error_type: str):
    """Trackt RabbitMQ Fehler"""
    rabbitmq_errors.labels(endpoint=endpoint, error_type=error_type).inc()

def track_fallback(endpoint: str, reason: str):
    """Trackt Fallback"""
    fallback_count.labels(endpoint=endpoint, reason=reason).inc()
```

**In API verwenden**:

```python
from api.monitoring import track_request, track_duration, track_rabbitmq_error, track_fallback

@router.get("/bright_asteroids")
async def get_bright_asteroids(...):
    start_time = time.time()
    architecture = 'rabbitmq' if use_rabbitmq else 'old'
    
    try:
        track_request('asteroids', architecture)
        result = ...
        track_duration('asteroids', architecture, time.time() - start_time)
        return result
    except Exception as e:
        if use_rabbitmq:
            track_rabbitmq_error('asteroids', type(e).__name__)
            track_fallback('asteroids', 'error')
        raise
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "ASCII Sky Migration",
    "panels": [
      {
        "title": "Requests by Architecture",
        "targets": [
          {
            "expr": "rate(asciisky_requests_total[5m])"
          }
        ]
      },
      {
        "title": "RabbitMQ Error Rate",
        "targets": [
          {
            "expr": "rate(asciisky_rabbitmq_errors_total[5m])"
          }
        ]
      },
      {
        "title": "Fallback Rate",
        "targets": [
          {
            "expr": "rate(asciisky_fallback_total[5m])"
          }
        ]
      },
      {
        "title": "Response Time Comparison",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(asciisky_request_duration_seconds_bucket[5m]))"
          }
        ]
      }
    ]
  }
}
```

## Rollback-Strategie

### Schneller Rollback

```bash
# 1. Feature Flags sofort deaktivieren
docker compose exec web bash -c "export USE_RABBITMQ=false"

# 2. Web Service neu starten
docker compose restart web

# 3. Alte Worker sicherstellen
docker compose up -d worker worker_once

# 4. RabbitMQ Worker stoppen (optional)
docker compose stop asteroid-worker-1 asteroid-worker-2
```

### Vollständiger Rollback

```bash
# 1. Git Rollback
git revert <commit-hash>

# 2. Docker Compose zurücksetzen
docker compose -f docker-compose.old.yml up -d

# 3. RabbitMQ Cluster stoppen
ssh user@192.168.1.10 "docker compose -f docker-compose.rabbitmq.yml down"
```

## Testing-Strategie

### Parallele Tests

```python
# test_migration.py
import pytest
from api.routes.asteroids import (
    compute_asteroids_rabbitmq,
    compute_asteroids_old_architecture
)

@pytest.mark.asyncio
async def test_results_identical():
    """Prüft ob alte und neue Architektur identische Ergebnisse liefern"""
    location = {'latitude': 48.2082, 'longitude': 16.3738, 'elevation': 170}
    time_bucket = '20250117T14'
    magnitude = 10.0
    
    # Beide Architekturen testen
    result_old = await compute_asteroids_old_architecture(location, time_bucket, magnitude)
    result_new = await compute_asteroids_rabbitmq(location, time_bucket, magnitude)
    
    # Ergebnisse vergleichen
    assert len(result_old) == len(result_new)
    assert result_old[0]['name'] == result_new[0]['name']
    assert abs(result_old[0]['altitude'] - result_new[0]['altitude']) < 0.01

@pytest.mark.asyncio
async def test_performance_comparison():
    """Vergleicht Performance"""
    import time
    
    # Alte Architektur
    start = time.time()
    await compute_asteroids_old_architecture(...)
    old_duration = time.time() - start
    
    # Neue Architektur
    start = time.time()
    await compute_asteroids_rabbitmq(...)
    new_duration = time.time() - start
    
    print(f"Old: {old_duration:.2f}s, New: {new_duration:.2f}s")
    assert new_duration < old_duration * 1.5  # Max 50% langsamer
```

## Zusammenfassung

### Vorteile dieser Strategie

✅ **Zero Downtime**: Alte Architektur läuft parallel  
✅ **Schrittweise Migration**: Feature Flags ermöglichen graduelles Rollout  
✅ **Sofortiger Rollback**: Feature Flag deaktivieren reicht  
✅ **A/B Testing**: Prozentbasiertes Rollout möglich  
✅ **Monitoring**: Vergleich alte vs. neue Architektur  
✅ **Sicherheit**: Fallback bei Fehlern  

### Checkliste

- [ ] Feature Flags System implementiert
- [ ] API-Endpoints angepasst (mit Fallback)
- [ ] docker-compose.yml erweitert
- [ ] Monitoring aufgesetzt (Prometheus/Grafana)
- [ ] Tests für beide Architekturen
- [ ] Rollback-Plan dokumentiert
- [ ] Team geschult (Feature Flags, Monitoring)
