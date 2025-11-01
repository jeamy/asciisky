# Environment Variables Analysis
# Detaillierte Analyse aller ENV-Variablen

## Smart Interpolation Variables (.env.interpolation.example)

### ✅ AKTIV VERWENDET

| Variable | Verwendet in | Funktion |
|----------|--------------|----------|
| `ENABLE_SMART_INTERPOLATION` | `config/interpolation_config.py:47`<br>`api/smart_interpolation.py:45` | Master-Switch für Smart Interpolation<br>true=Interpolation, false=Nearest Bucket |
| `INTERPOLATION_STRATEGY` | `config/interpolation_config.py:60`<br>`api/smart_interpolation.py:49` | Strategie: nearest_bucket, smart_interpolation, on_demand_only |
| `ENABLE_ON_DEMAND_COMPUTATION` | `config/interpolation_config.py:50` | Aktiviert On-Demand Berechnung fehlender Buckets |
| `ON_DEMAND_CACHE_TTL` | `api/on_demand_computation.py:71` | Cache TTL für On-Demand Buckets (Sekunden) |
| `ON_DEMAND_MAX_COMPUTATION_TIME` | `api/on_demand_computation.py:72` | Timeout für On-Demand Berechnung (Sekunden) |
| `ON_DEMAND_MAX_MAGNITUDE_ASTEROIDS` | `api/on_demand_computation.py:74` | Max Magnitude für Asteroiden |
| `ON_DEMAND_MAX_COMETS` | `api/on_demand_computation.py:75` | Max Anzahl Kometen |
| `ENABLE_ASTRONOMICAL_CORRECTIONS` | `config/interpolation_config.py:53` | Aktiviert astronomische Korrekturen |
| `ASTRONOMICAL_CORRECTION_LEVEL` | `config/interpolation_config.py:63` | Level: none, basic, standard, advanced |
| `INTERPOLATION_MAX_ERROR_DEGREES` | `config/interpolation_config.py:79` | Max akzeptabler Fehler (Grad) |
| `INTERPOLATION_CACHE_TTL` | `config/interpolation_config.py:70` | Cache TTL für Interpolation (Sekunden) |
| `INTERPOLATION_MAX_FUTURE_HOURS` | `config/interpolation_config.py:73`<br>`api/smart_interpolation.py:47` | Max Stunden in Zukunft für Cache |
| `INTERPOLATION_MIN_QUALITY_THRESHOLD` | `config/interpolation_config.py:77` | Min Qualitätsschwelle (0.0-1.0) |
| `INTERPOLATION_ENABLE_RETRY` | `config/interpolation_config.py:91` | Aktiviert Retry bei Fehler |
| `INTERPOLATION_MAX_RETRIES` | `config/interpolation_config.py:94` | Max Anzahl Retries |
| `INTERPOLATION_RETRY_DELAY` | `config/interpolation_config.py:97` | Delay zwischen Retries (Sekunden) |
| `INTERPOLATION_ENABLE_METRICS` | `config/interpolation_config.py:101` | Aktiviert Performance Metrics |
| `INTERPOLATION_DEBUG_LOGGING` | `config/interpolation_config.py:104` | Aktiviert Debug Logging |
| `INTERPOLATION_LOG_PERFORMANCE_WARNINGS` | `config/interpolation_config.py:107` | Loggt Performance Warnings |
| `INTERPOLATION_ENABLED_USER_IDS` | `config/interpolation_config.py:111` | Komma-separierte User IDs für Rollout |
| `INTERPOLATION_ENABLED_PERCENTAGE` | `config/interpolation_config.py:114` | Prozent der User (0-100) für Rollout |
| `ENABLE_INTERPOLATION_BACKGROUND_TASKS` | `config/interpolation_config.py:56`<br>`api/smart_interpolation.py:203,225,261` | **WICHTIG**: ASYNC RabbitMQ Worker statt SYNC |
| `INTERPOLATION_CACHE_COMPUTED` | `api/smart_interpolation.py:48` | Cached On-Demand berechnete Buckets |

### ❌ NICHT VERWENDET (nur in .env.interpolation.example definiert)

| Variable | Status |
|----------|--------|
| `INTERPOLATION_BACKGROUND_PRIORITY` | Nicht im Code gefunden - [FUTURE] |
| `INTERPOLATION_MAX_CONCURRENT_COMPUTATIONS` | Nicht im Code gefunden - [FUTURE] |
| `INTERPOLATION_MEMORY_CACHE_SIZE` | Nicht im Code gefunden - [FUTURE] |
| `INTERPOLATION_CLEANUP_INTERVAL` | Nicht im Code gefunden - [FUTURE] |

## Empfehlungen

### 1. Entferne nicht verwendete Variablen
Markiere als `[FUTURE]` oder entferne komplett:
- `INTERPOLATION_BACKGROUND_PRIORITY`
- `INTERPOLATION_MAX_CONCURRENT_COMPUTATIONS`
- `INTERPOLATION_MEMORY_CACHE_SIZE`
- `INTERPOLATION_CLEANUP_INTERVAL`

### 2. Wichtigste Variablen für Production
```bash
ENABLE_SMART_INTERPOLATION=true
INTERPOLATION_STRATEGY=smart_interpolation
ENABLE_ON_DEMAND_COMPUTATION=true
ENABLE_INTERPOLATION_BACKGROUND_TASKS=true  # ASYNC!
INTERPOLATION_CACHE_COMPUTED=true
INTERPOLATION_ENABLED_PERCENTAGE=100.0
```

### 3. Debugging
```bash
INTERPOLATION_DEBUG_LOGGING=true
INTERPOLATION_ENABLE_METRICS=true
```
