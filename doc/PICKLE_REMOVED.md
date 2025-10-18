# Pickle Cache Removed

**Status:** ✅ KOMPLETT ENTFERNT (2025-10-19)

## Was wurde entfernt

Alle Pickle-basierten Cache-Mechanismen wurden entfernt. ASCII Sky nutzt jetzt **ausschließlich SQLite** für Caching.

### Entfernte Komponenten

- ❌ Pickle-Cache-Dateien (`*.pkl`)
- ❌ `cache/asteroids/` Verzeichnis
- ❌ `cache/comets/` Verzeichnis  
- ❌ `CACHE_ROOT` Konstante
- ❌ `atomic_write_pickle()` Funktion
- ❌ `read_pickle_if_fresh()` Funktion
- ❌ `build_cache_path()` Funktion (für Pickle)
- ❌ `DISABLE_PICKLE` Environment Variable
- ❌ `ASTEROID_ENABLE_LEGACY_FALLBACK` Flag
- ❌ `migrate_from_pickle_cache()` Funktion

### Geänderte Dateien

**Core:**
- `cache_utils.py` - Nur noch Location/Time-Utilities
- `db_utils.py` - `migrate_from_pickle_cache()` entfernt
- `bright_asteroids.py` - Alle Pickle-Referenzen entfernt
- `comets.py` - Alle Pickle-Referenzen entfernt
- `precompute_worker.py` - Pickle-Cache-Checks entfernt

**API:**
- `api/helpers.py` - Pickle-Logik entfernt
- `api/cache_interpolation.py` - SQLite only
- `api/routes/filters.py` - Pickle-Verzeichnis-Löschung entfernt
- `api/routes/asteroids.py` - `disable_pickle` Parameter ignoriert
- `api/routes/comets.py` - `disable_pickle` Parameter ignoriert

**Dokumentation:**
- `doc/rabbitmq/007-multi-host-storage.md` - Pickle-Referenzen entfernt

## Aktuelle Architektur

```
ASCII Sky Cache (SQLite only)
├── asteroids.db
│   ├── asteroids (dataframes)
│   └── asteroid_positions (computed positions)
└── comets.db
    ├── comets (dataframes)
    └── comet_positions (computed positions)
```

## Vorteile

- ✅ **Einfacher:** Nur eine Storage-Technologie
- ✅ **Sicherer:** Keine Pickle-Deserialisierung (Sicherheitsrisiko)
- ✅ **Wartbarer:** Weniger Code, klare Struktur
- ✅ **Multi-Host ready:** NFS oder PostgreSQL möglich
- ✅ **Performanter:** SQLite ist schneller als Pickle für Queries
- ✅ **Zuverlässiger:** ACID-Garantien, keine Datei-Korruption

## Migration

**Keine Migration nötig!** 

Alte Pickle-Caches werden einfach ignoriert und können gelöscht werden:

```bash
# Optional: Alte Pickle-Caches löschen
rm -rf cache/asteroids/
rm -rf cache/comets/
rm -f cache/*.pkl
```

## Hinweis zu Pickle in db_utils.py

`db_utils.py` nutzt weiterhin `pickle` für **interne Serialisierung** in SQLite:
- Orbit-Daten werden als BLOB gespeichert
- Position-Daten werden als BLOB gespeichert

Das ist **OK** und **sicher**, weil:
- ✅ Daten werden vom eigenen Code erstellt
- ✅ Keine User-Input-Deserialisierung
- ✅ Nur internes Format, nicht exponiert
- ✅ Kann später durch JSON/MessagePack ersetzt werden

## Veraltete Dokumentation

Die folgenden Dokumentationsdateien enthalten noch Pickle-Referenzen (historisch):
- `doc/cache.md`
- `doc/remove_pickle_plan.md`
- `doc/cache_comparison.md`
- `doc/asteroids.md`
- `doc/comets.md`
- `doc/sqlite.md`

**Diese Dateien sind veraltet und sollten nicht mehr als Referenz genutzt werden.**

Aktuelle Dokumentation:
- `doc/rabbitmq/007-multi-host-storage.md` - Multi-Host Setup
- `doc/rabbitmq/RABBITMQ_MIGRATION.md` - RabbitMQ Architektur
- `doc/rabbitmq/API_MIGRATION_STATUS.md` - Aktueller Status

## Siehe auch

- [Multi-Host Storage](rabbitmq/007-multi-host-storage.md)
- [RabbitMQ Migration](rabbitmq/RABBITMQ_MIGRATION.md)
- [API Migration Status](rabbitmq/API_MIGRATION_STATUS.md)
