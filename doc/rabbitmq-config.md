# RabbitMQ 4.1 Konfiguration

## Deprecation Warning behoben

**Problem:**
```
[warning] Deprecated features: `management_metrics_collection`: Feature `management_metrics_collection` is deprecated.
```

**Lösung:**
Die Konfigurationsdatei `config/rabbitmq.conf` wurde erstellt mit:
```
deprecated_features.permit.management_metrics_collection = false
```

## Konfigurationsdatei

Die Datei `config/rabbitmq.conf` wird in `docker-compose.yml` eingebunden:
```yaml
volumes:
  - rabbitmq_data:/var/lib/rabbitmq
  - ./config/rabbitmq.conf:/etc/rabbitmq/rabbitmq.conf:ro
```

## Wichtige Einstellungen

### Deprecated Features
- `management_metrics_collection` ist explizit deaktiviert
- Keine Warnungen mehr beim Start

### Performance
- `vm_memory_high_watermark.relative = 0.6` (60% RAM-Nutzung)
- `disk_free_limit.absolute = 2GB` (mindestens 2 GB freier Speicher)
- `channel_max = 2048` (max. 2048 Channels pro Connection)

### Logging
- Console Logging: `warning` Level
- File Logging: deaktiviert (Docker Logs werden verwendet)

## Neustart erforderlich

Nach Änderungen an `config/rabbitmq.conf`:
```bash
docker compose restart rabbitmq
```

## Weitere Informationen

- [RabbitMQ 4.1 Configuration](https://www.rabbitmq.com/docs/configure)
- [Deprecated Features](https://www.rabbitmq.com/docs/deprecated-features)
- [Management Plugin](https://www.rabbitmq.com/docs/management)
