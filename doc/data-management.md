# Data Management - Asteroids & Comets

## Overview

ASCII Sky uses a **DB-first approach** with automatic nightly updates for asteroid and comet orbital data.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Nightly Data Updater (2:00 AM)                             │
│  Container: data_updater                                     │
├─────────────────────────────────────────────────────────────┤
│  • Downloads MPCORB.DAT (84MB, ~1.2M asteroids)             │
│  • Downloads CometEls.txt (~1200 comets)                    │
│  • Parses and stores in SQLite database                     │
│  • Runs once per day at configured hour (default: 2:00 AM)  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Runtime Data Loading (Fast!)                               │
├─────────────────────────────────────────────────────────────┤
│  1. Try: Load from SQLite database (fast, <1s)              │
│  2. Fallback: Load from file if DB empty (slow, first start)│
│  3. Auto-download file if missing (initial setup)           │
└─────────────────────────────────────────────────────────────┘
```

## First Start (No Data)

When the system starts for the first time:

1. **Asteroids**: 
   - `load_bright_asteroids()` checks SQLite DB → empty
   - Falls back to file loading
   - If file doesn't exist → downloads MPCORB.DAT automatically
   - Parses and stores in SQLite for next time

2. **Comets**:
   - `load_comets()` checks SQLite DB → empty
   - Falls back to file loading
   - If file doesn't exist → downloads CometEls.txt automatically
   - Parses and stores in SQLite for next time

**Initial setup downloads happen automatically on first API request.**

## Daily Updates

### Automatic (Recommended)

The `data_updater` service runs continuously and updates data once per day:

```yaml
data_updater:
  command: ["python", "nightly_data_updater.py"]
  environment:
    - ASCII_SKY_UPDATE_HOUR=2  # 2:00 AM local time
```

**Features:**
- Prevents duplicate updates (tracks last update date)
- Runs at configured hour (default 2:00 AM)
- Downloads fresh data from MPC
- Updates SQLite database
- Logs all operations

### Manual Trigger

To manually trigger an update (e.g., for testing):

```bash
docker exec asciisky-web-1 python nightly_data_updater.py --now
```

## Files vs Database

### When Files Are Used

**Files are only used when:**
1. **First start**: Database is empty, need initial data
2. **Nightly update**: Updater downloads fresh files → parses → stores in DB
3. **Manual operations**: Debugging, testing

### When Database Is Used

**Database is used for:**
1. **All runtime requests**: Fast, no file parsing needed
2. **Precompute workers**: Consistent data across all workers
3. **API endpoints**: `/api/asteroids`, `/api/comets`

## Performance

| Operation | Before (File) | After (DB) | Improvement |
|-----------|---------------|------------|-------------|
| Load asteroids | ~5-10s | <1s | **5-10x faster** |
| Load comets | ~3-5s | <1s | **3-5x faster** |
| Parse MPCORB | Every request | Once per day | **Massive** |

## Configuration

### Environment Variables

```yaml
# When to run nightly update (hour, local time)
ASCII_SKY_UPDATE_HOUR=2

# Magnitude filters
ASCII_SKY_ASTEROID_MAX_ABSOLUTE_MAG=12.0
ASCII_SKY_ASTEROID_MAX_APPARENT_MAG=10.0
ASCII_SKY_COMET_MAX_ABSOLUTE_MAG=20.0
ASCII_SKY_COMET_MAX_APPARENT_MAG=14.0
```

### Database Location

SQLite database: `celestial_cache.db`

Tables:
- `asteroids` - Orbital elements, magnitudes, cached data
- `comets` - Orbital elements, magnitudes, cached data
- `asteroid_positions` - Pre-computed positions per location/time
- `comet_positions` - Pre-computed positions per location/time

## Monitoring

### Check Last Update

```bash
cat cache/last_data_update.txt
# Shows: YYYY-MM-DD of last successful update
```

### View Updater Logs

```bash
docker logs asciisky-data_updater-1 -f
```

### Database Stats

```python
from db_utils import get_database_stats
stats = get_database_stats()
print(f"Asteroids: {stats['asteroids_count']}")
print(f"Comets: {stats['comets_count']}")
```

## Troubleshooting

### No Data After First Start

**Problem**: API returns empty results

**Solution**:
1. Check if files were downloaded:
   ```bash
   ls -lh data/MPCORB.DAT.gz data/CometEls.txt
   ```
2. Check database:
   ```bash
   docker exec asciisky-web-1 python -c "from db_utils import get_database_stats; print(get_database_stats())"
   ```
3. Manually trigger initial load:
   ```bash
   docker exec asciisky-web-1 python nightly_data_updater.py --now
   ```

### Updates Not Running

**Problem**: Data is outdated (>1 day old)

**Solution**:
1. Check if updater container is running:
   ```bash
   docker ps | grep data_updater
   ```
2. Check updater logs:
   ```bash
   docker logs asciisky-data_updater-1 --tail 50
   ```
3. Verify time configuration:
   ```bash
   docker exec asciisky-data_updater-1 date
   # Should show correct local time (Europe/Berlin)
   ```

### Manual Data Refresh

If you need to force a refresh:

```bash
# Stop system
docker compose down

# Remove old data
rm data/MPCORB.DAT.gz data/CometEls.txt
rm celestial_cache.db
rm cache/last_data_update.txt

# Start system (will download fresh data)
docker compose up -d

# Trigger manual update
docker exec asciisky-web-1 python nightly_data_updater.py --now
```

## Migration from Old System

If migrating from the old file-based system:

1. Old pickle caches are automatically migrated
2. First request after migration may be slow (loads from file)
3. Subsequent requests will use DB (fast)
4. Nightly updater takes over from then on

No manual intervention needed!

## Best Practices

1. **Don't disable the data_updater service** - it keeps data fresh
2. **Monitor logs** - watch for download failures
3. **Backup database** - `celestial_cache.db` contains parsed data
4. **Check after updates** - verify data after system updates
5. **Use manual trigger for testing** - don't rely on it for production

## Future Improvements

Potential enhancements:

- [ ] Add health check endpoint (`/api/data_status`)
- [ ] Email notifications on update failures
- [ ] Configurable update frequency (weekly for comets?)
- [ ] Delta updates (only changed asteroids)
- [ ] Compression of stored orbit data
