# Cache Strategy

## Cache Hierarchy

```
Level 1: Position Cache (PostgreSQL)
┌────────────────────────────────────────────────────────────────┐
│ Table: cached_positions                                      │
│ Key: (object_type, location_key, time_bucket)                  │
│ Application TTL: 31 days for lookup/interpolation              │
│ Contents: Computed positions (unfiltered)                      │
│ Created by: Precompute workers (hourly) + on-demand workers    │
│ Used by: All API requests (first check)                        │
│ Celestial (Sun/Moon/planets): NOT cached (direct via/celestial)│
└────────────────────────────────────────────────────────────────┘
         │ Cache MISS
         ▼
Level 2: DataFrame Cache (Filesystem)
┌────────────────────────────────────────────────────────────────┐
│ Files: asteroid_dataframe.pkl, comet_dataframe.pkl             │
│ Staleness: loader-dependent; database helpers default to ~49 h │
│ Content: raw MPC data (orbital elements)                      │
│ Created by: nightly updater / db_utils.store_*_dataframe      │
│ Used by: bright_asteroids/comets for position computation     │
└────────────────────────────────────────────────────────────────┘
         │ Cache MISS
         ▼
Level 3: MPC download
┌────────────────────────────────────────────────────────────────┐
│ URLs:                                                          │
│ - Asteroids: https://minorplanetcenter.net/iau/MPCORB/...      │
│   MPCORB.DAT (~200 MB, ~1M objects)                            │
│ - Comets: https://minorplanetcenter.net/iau/Ephemerides/...    │
│   Comets/CometEls.txt (~100 KB, ~1000 objects)                 │
│ Network and parse time depend on the MPC service and hardware  │
└────────────────────────────────────────────────────────────────┘
```

## Cache Invalidation

```
User changes Magnitude Filter (e.g., 14 → 18)
         │
         │ POST /api/filters
         ▼
┌────────────────────────────────────────────────────────────────┐
│ 1. Store new filters in user_settings.json                     │
│    settings.py:set_magnitude_filters()                         │
└────────┬───────────────────────────────────────────────────────┘
         ▼
┌────────────────────────────────────────────────────────────────┐
│ 2. Existing position/DataFrame caches are retained             │
└────────┬───────────────────────────────────────────────────────┘
         ▼
┌────────────────────────────────────────────────────────────────┐
│ 3. NO PostgreSQL caches are deleted!                           │
│                                                                │
│    All caches remain:                                          │
│    - cached_positions rows for asteroids and comets            │
│    - asteroids (MPC MPCORB.DAT, mag 20.0)                      │
│    - comets (MPC CometEls.txt, mag 20.0)                       │
│                                                                │
│    Filtering happens in API routes!                            │
└────────┬───────────────────────────────────────────────────────┘
         ▼
┌────────────────────────────────────────────────────────────────┐
│ 4. Next Request                                                │
│    - DataFrame cache available (mag 20.0)                      │
│    - Position cache available (unfiltered)                     │
│    - API filters to mag 18.0                                   │
│    - Objects 14–18 appear immediately!                         │
│    - No recomputation required!                                │ 
└────────────────────────────────────────────────────────────────┘
```

**Code:** `api/routes/filters.py`

### Cache Strategy when Filters Change

**Architecture:**
- On-demand publishers request a broad computation limit (asteroids currently 20.0; comets publish 14.0, while the comet worker uses its configured pipeline limit)
- DataFrame caches contain orbital-element candidates, not a user-specific result set
- Filtering happens **only** in API routes based on `user_settings.json`
- **One cache for all user filters!**

**What happens when filters change:**

On filter change (e.g., 14 → 18) **NO** PostgreSQL caches are deleted!

**All caches remain:**
```
cached_positions    ← Unfiltered computed result lists, keyed by object type
asteroid_dataframe  ← MPCORB.DAT-based orbital data (filesystem)
comet_dataframe     ← MPC comet elements orbital data (filesystem)
```

**Why are caches NOT deleted?**

All caches used by workers contain **unfiltered** data:
- Position cache (`cached_positions`): the result set produced with the worker's active limits
- DataFrame cache files: orbital-element candidates retained by the loader's absolute-magnitude prefilter
- Filtering happens **only** in API routes (based on `user_settings.json`)
- **Reusable for all filter settings!**

**Sequence after a filter change:**
1. User changes filter from 14 → 18
2. **No** caches are deleted
3. Next request:
   - DataFrame cache available (mag 20.0) ✅
   - Position cache available (unfiltered) ✅
   - API filters to mag 18.0
   - Objects 14–18 appear **immediately**!
   - **No recomputation required!** 🚀

**Celestial objects (Sun, Moon, planets):**
- Are **not** cached
- Direct computation for each request (~50–200ms) via `/api/celestial`
- Only a small fixed set of bodies, fast enough without cache

**Code references:**
- `workers/unified_worker.py` — computation and storage (`precompute_worker.py` is a compatibility entry point)
- `bright_asteroids.py` / `comets.py` — candidate selection and vectorized computation
- `api/routes/asteroids.py` / `api/routes/comets.py` — response filtering
- `api/helpers.py:resolve_magnitude_filter()` — resolves query, account, or local defaults

## Performance

A PostgreSQL position-cache hit avoids orbit propagation and event calculation. A DataFrame-cache hit avoids downloading and parsing MPC source text but still requires the astronomy calculation. Cold-start time additionally depends on MPC availability and dataset size. The repository does not contain a controlled benchmark that supports fixed response-time ranges, so measure these paths on the deployment hardware.

Cached rows are not physically immortal: `cleanup_cached_positions()` and the SQL `cleanup_old_positions()` function can prune them. Lookup functions also apply the astronomy module's cache TTL (currently 31 days), even though the underlying row remains until cleanup.

The nightly updater compares the newly serialized MPC DataFrame with the current
one. It invalidates only `asteroid` or `comet` rows when that corresponding source
dataset changed; an unchanged nightly download retains computed positions.

Last reviewed against the code: 2026-06-30.
