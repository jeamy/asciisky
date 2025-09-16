"""
Module for calculating positions of comets using real MPC data.
- Loads MPC comet dataframe and caches it (~6h) to disk and memory
- Builds comet orbits from pandas rows (not dict) to avoid attribute errors
- Computes apparent position, optional magnitude estimate (M1/k1), and rise/set/transit times
- Returns a list of comet dicts compatible with the frontend (like bright_asteroids.py)
"""
from skyfield.api import Topos, load
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2
from skyfield.data import mpc
from skyfield import almanac

import os
import time
import pickle
import logging
import urllib.request
from datetime import datetime, timezone
from typing import List, Optional

import pandas as pd
import numpy as np
from skyfield import almanac
from skyfield.api import Loader, wgs84
from skyfield.data import mpc
from skyfield.magnitudelib import planetary_magnitude

from cache_utils import build_cache_path, read_pickle_if_fresh, atomic_write_pickle, CACHE_ROOT, normalize_location, location_key, time_bucket_utc
from db_utils import get_db_connection
from timezone_utils import get_tzinfo

def should_update_comet_file():
    """
    Überprüft ob Kometen-Datei aktualisiert werden sollte (täglich)
    """
    if not os.path.exists(COMETS_FILE):
        return True
    
    # Prüfe Alter der Datei
    file_age = time.time() - os.path.getmtime(COMETS_FILE)
    # Aktualisiere täglich (24 Stunden = 86400 Sekunden)
    return file_age > 86400

COMET_DF_CACHE_FILE = 'cache/comets_dataframe.pkl'
CACHE_VALIDITY_SECONDS = 12 * 3600  # 12h
COMETS_FILE = 'cache/CometEls.txt'
# Final comet list cache (mirror bright_asteroids behavior)
BRIGHT_COMET_CACHE_FILE = 'cache/bright_comet_cache.pkl'
# Photometric filters (align with bright_asteroids thresholds)
# Limit number of final returned comets; we will iterate candidates until we collect up to this many
MAX_COMETS_DEFAULT = 200
# Pre-filter by comet absolute magnitude parameter (M1); smaller = brighter
MAX_ABSOLUTE_MAGNITUDE = 18.0
# Final filter by estimated apparent magnitude at current time/location
MAX_APPARENT_MAGNITUDE = 16.0

# Module-specific cache granularity for per-location/time comet list
# Use a 1-hour bucket; TTL should span the 48h precompute window so that
# snapshots remain valid when served from cache-only endpoints.
COMET_CACHE_BUCKET_HOURS = 1
COMET_CACHE_TTL_SECONDS = 49 * 3600

# SQLite backend configuration
COMET_USE_SQLITE = os.getenv('COMET_USE_SQLITE', 'true').lower() == 'true'

# Ensure cache directory exists
os.makedirs('cache', exist_ok=True)

# In-memory cache
_comet_df_cache = None
_comet_df_timestamp = None

# Logger
logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now()


def _standardize_comet_df(comets: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize MPC comet DataFrame to expected schema and safe dtypes.
    - Keep latest per designation by 'reference'
    - Create/normalize aliases: 'i' from 'incl', 'node' from 'om', 'peri' from 'w'
    - Coerce numeric columns to floats
    - Drop rows missing essential elements
    - Require at least one of 'epoch_tt' or 'Tp'
    - Index by 'designation'
    """
    df = comets.copy()

    # Ensure 'designation' is not both an index level and a column label.
    # 1) If any index level is named 'designation', bring it to columns.
    try:
        idx_names = []
        try:
            idx_names = list(df.index.names)
        except Exception:
            name = getattr(df.index, 'name', None)
            if name is not None:
                idx_names = [name]
        if 'designation' in idx_names:
            df = df.reset_index()
    except Exception:
        # Continue even if index inspection/reset fails
        pass

    # 2) Drop duplicate column labels (keep first) to avoid ambiguity, especially 'designation'.
    try:
        if isinstance(df.columns, pd.Index):
            dup_mask = df.columns.duplicated(keep='first')
            if dup_mask.any():
                df = df.loc[:, ~dup_mask]
    except Exception:
        pass

    # Defer selection of latest per designation until after numeric coercion
    # (so we can choose the latest row that still has valid e and q)

    # Ensure essential and alias columns exist (create as NaN if missing)
    for col in ['e', 'q', 'incl', 'i', 'om', 'w', 'node', 'peri', 'epoch_tt', 'Tp', 'M1', 'k1']:
        if col not in df.columns:
            df[col] = np.nan

    # Map MPC column names to expected aliases used by comet_orbit
    # Numeric coercion will follow; here we only copy values where target is missing
    try:
        if 'eccentricity' in df.columns:
            df['e'] = df['e'].fillna(pd.to_numeric(df['eccentricity'], errors='coerce'))
        if 'perihelion_distance_au' in df.columns:
            df['q'] = df['q'].fillna(pd.to_numeric(df['perihelion_distance_au'], errors='coerce'))
        if 'inclination_degrees' in df.columns:
            src_incl = pd.to_numeric(df['inclination_degrees'], errors='coerce')
            df['i'] = df['i'].fillna(src_incl)
            df['incl'] = df['incl'].fillna(src_incl)
        if 'longitude_of_ascending_node_degrees' in df.columns:
            src_om = pd.to_numeric(df['longitude_of_ascending_node_degrees'], errors='coerce')
            df['om'] = df['om'].fillna(src_om)
            df['node'] = df['node'].fillna(src_om)
        if 'argument_of_perihelion_degrees' in df.columns:
            src_w = pd.to_numeric(df['argument_of_perihelion_degrees'], errors='coerce')
            df['w'] = df['w'].fillna(src_w)
            df['peri'] = df['peri'].fillna(src_w)
        # Comet magnitude parameters
        if 'magnitude_g' in df.columns:
            df['M1'] = df['M1'].fillna(pd.to_numeric(df['magnitude_g'], errors='coerce'))
        if 'magnitude_k' in df.columns:
            df['k1'] = df['k1'].fillna(pd.to_numeric(df['magnitude_k'], errors='coerce'))
    except Exception as e:
        logger.debug(f"Alias mapping for MPC comet DF failed (continuing): {e}")

    # Coerce numeric columns
    numeric_cols = ['e', 'q', 'incl', 'i', 'om', 'node', 'w', 'peri', 'epoch_tt', 'Tp', 'M1', 'k1', 'M2', 'k2',
                    'perihelion_year', 'perihelion_month', 'perihelion_day', 'epoch_year', 'epoch_month', 'epoch_day']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Fill aliases from source columns if available
    if 'om' in df.columns:
        df['node'] = df['node'].fillna(df['om'])
    if 'w' in df.columns:
        df['peri'] = df['peri'].fillna(df['w'])

    # Now select latest per designation using 'reference', preferring rows
    # where both 'e' and 'q' are present (non-NaN). If no such row exists
    # for a designation, fall back to the last row by reference.
    if {'designation', 'reference'}.issubset(df.columns):
        df = df.sort_values('reference')
        def _pick_last_valid(g: pd.DataFrame) -> pd.DataFrame:
            mask = g['e'].notna() & g['q'].notna()
            if mask.any():
                return g[mask].iloc[-1:]
            else:
                return g.iloc[-1:]
        df = df.groupby('designation', group_keys=False).apply(_pick_last_valid)

    # Ensure designation is index if present (do not keep it as a duplicate column)
    if 'designation' in df.columns:
        df = df.set_index('designation', drop=True)

    # Drop rows missing essentials; at this stage only require 'e' and 'q'.
    # Angle completeness (i/om/w) is validated later per-row before orbit build.
    node_col = 'node' if 'node' in df.columns else ('om' if 'om' in df.columns else None)
    peri_col = 'peri' if 'peri' in df.columns else ('w' if 'w' in df.columns else None)
    essentials = [c for c in ['e', 'q'] if c in df.columns]
    # Debug: before-drop counts for 'e'/'q'
    try:
        if 'e' in df.columns and 'q' in df.columns:
            e_na = int(df['e'].isna().sum())
            q_na = int(df['q'].isna().sum())
            logger.debug(f"Comet DF pre-drop: NaN e={e_na}, NaN q={q_na}, total={len(df)}")
    except Exception:
        pass
    if essentials:
        before = len(df)
        df = df.dropna(subset=essentials)
        after = len(df)
        if before != after:
            logger.debug(f"Dropped rows missing e/q: {before - after} removed, {after} remain")

    # Require some time reference: epoch_tt or Tp or perihelion Y/M/D
    try:
        has_epoch = df['epoch_tt'].notna() if 'epoch_tt' in df.columns else pd.Series(False, index=df.index)
        has_tp = df['Tp'].notna() if 'Tp' in df.columns else pd.Series(False, index=df.index)
        has_peri_date = (
            ('perihelion_year' in df.columns and 'perihelion_month' in df.columns and 'perihelion_day' in df.columns)
            and df['perihelion_year'].notna() & df['perihelion_month'].notna() & df['perihelion_day'].notna()
        )
        if isinstance(has_peri_date, bool):
            # If columns missing, ensure a Series of False
            has_peri_date = pd.Series(False, index=df.index)
        before = len(df)
        df = df[has_epoch | has_tp | has_peri_date]
        after = len(df)
        if before != after:
            logger.debug(f"Filtered comets without any time reference (epoch/Tp/peri Y-M-D): {before - after} dropped, {after} remain")
    except Exception as e:
        logger.debug(f"Time-reference filtering failed (continuing without drop): {e}")
    
    return df

def load_comet_dataframe(use_cache: bool = True) -> pd.DataFrame:
    """
    Load comet orbital elements from MPC and cache the parsed dataframe.
    Keeps the latest entry per 'designation' based on 'reference'.
    Ensures numeric columns are floats and fills aliases 'node'/'peri' from 'om'/'w'.
    """
    global _comet_df_cache, _comet_df_timestamp

    # In-memory cache
    if use_cache and _comet_df_cache is not None and _comet_df_timestamp is not None:
        if (_now() - _comet_df_timestamp).total_seconds() < CACHE_VALIDITY_SECONDS:
            logger.debug("Using cached comet dataframe (memory)")
            try:
                cols = list(_comet_df_cache.columns)
                logger.debug(f"Comet DF (memory cache) columns: {cols}")
                for c in ['e','q','i','incl','om','w','node','peri','epoch_tt','Tp']:
                    if c in _comet_df_cache.columns:
                        s = _comet_df_cache[c]
                        logger.debug(f"mem col {c}: dtype={s.dtype}, nonnull={int(s.notna().sum())}")
                logger.debug(f"Comet DF (memory cache) size: {len(_comet_df_cache)} rows")
                # Invalidate empty/invalid cache (no usable e/q)
                valid_eq = False
                try:
                    valid_eq = (
                        ('e' in _comet_df_cache.columns and 'q' in _comet_df_cache.columns)
                        and int(_comet_df_cache['e'].notna().sum()) > 0
                        and int(_comet_df_cache['q'].notna().sum()) > 0
                        and len(_comet_df_cache) > 0
                    )
                except Exception:
                    valid_eq = False
                if not valid_eq:
                    logger.debug("Memory comet cache invalid (empty or no valid e/q). Will refetch.")
                else:
                    return _comet_df_cache
            except Exception as de:
                logger.debug(f"Comet DF memory debug failed: {de}")

    # Disk cache
    if use_cache and os.path.exists(COMET_DF_CACHE_FILE):
        try:
            with open(COMET_DF_CACHE_FILE, 'rb') as f:
                payload = pickle.load(f)
            if isinstance(payload, dict) and 'timestamp' in payload and 'data' in payload:
                if (_now() - payload['timestamp']).total_seconds() < CACHE_VALIDITY_SECONDS:
                    logger.debug("Using cached comet dataframe (pickle)")
                    # Sanitize cached dataframe as formats can change upstream
                    cached = payload['data']
                    try:
                        cached = _standardize_comet_df(cached)
                    except Exception as se:
                        logger.warning(f"Standardizing cached comet DF failed: {se}")
                    # Validate sanitized cache; if invalid, skip returning and fetch fresh
                    is_valid = False
                    try:
                        is_valid = (
                            cached is not None and not cached.empty and
                            ('e' in cached.columns and 'q' in cached.columns) and
                            int(cached['e'].notna().sum()) > 0 and int(cached['q'].notna().sum()) > 0
                        )
                    except Exception:
                        is_valid = False

                    if is_valid:
                        _comet_df_cache = cached
                        _comet_df_timestamp = payload['timestamp']
                        # Re-save sanitized cache silently
                        try:
                            with open(COMET_DF_CACHE_FILE, 'wb') as wf:
                                pickle.dump({'timestamp': _comet_df_timestamp, 'data': _comet_df_cache}, wf)
                        except Exception:
                            pass
                        # Debug summary for disk cache
                        try:
                            cols = list(_comet_df_cache.columns)
                            logger.debug(f"Comet DF (disk cache) columns: {cols}")
                            for c in ['e','q','i','incl','om','w','node','peri','epoch_tt','Tp']:
                                if c in _comet_df_cache.columns:
                                    s = _comet_df_cache[c]
                                    logger.debug(f"disk col {c}: dtype={s.dtype}, nonnull={int(s.notna().sum())}")
                            logger.debug(f"Comet DF (disk cache) size: {len(_comet_df_cache)} rows")
                        except Exception as de:
                            logger.debug(f"Comet DF disk debug failed: {de}")
                        return _comet_df_cache
                    else:
                        logger.debug("Disk comet cache invalid (empty or no valid e/q). Will refetch.")
        except Exception as e:
            logger.warning(f"Error reading comet dataframe cache: {e}")

    # Fetch fresh (prefer local MPC file cache if available)
    try:
        # Check if daily update is needed
        if should_update_comet_file():
            logger.debug("Comet file needs daily update, downloading...")
            try:
                with urllib.request.urlopen(mpc.COMET_URL, timeout=30) as rf:
                    content = rf.read()
                if content:
                    os.makedirs('cache', exist_ok=True)
                    try:
                        with open(COMETS_FILE, 'wb') as wf:
                            wf.write(content)
                        logger.debug(f"Updated comet file: {COMETS_FILE}")
                    except Exception as we:
                        logger.warning(f"Failed to write {COMETS_FILE}: {we}")
            except Exception as ne:
                logger.error(f"Error downloading MPC comet elements: {ne}")
        
        # Load from local file
        if os.path.exists(COMETS_FILE):
            with open(COMETS_FILE, 'rb') as f:
                df = mpc.load_comets_dataframe(f)
        else:
            logger.error("No comet data file available")
            return pd.DataFrame()
            
        _comet_df_cache = df
        comets = _standardize_comet_df(df)

        # Debug: print columns and counts for essential fields
        try:
            cols = list(comets.columns)
            logger.debug(f"Comet DF columns: {cols}")
            for c in ['e','q','i','incl','om','w','node','peri','epoch_tt','Tp','M1','k1']:
                if c in comets.columns:
                    s = comets[c]
                    logger.debug(f"col {c}: dtype={s.dtype}, nonnull={int(s.notna().sum())}")
            logger.debug(f"Comet DF size after standardize: {len(comets)} rows")
        except Exception as de:
            logger.debug(f"Comet DF debug failed: {de}")

        _comet_df_cache = comets
        _comet_df_timestamp = _now()
        with open(COMET_DF_CACHE_FILE, 'wb') as f:
            pickle.dump({'timestamp': _comet_df_timestamp, 'data': _comet_df_cache}, f)

        logger.debug(f"Loaded {len(comets)} comets from MPC and cached.")
        return _comet_df_cache
    except Exception as e:
        logger.error(f"Error loading comet data: {e}")
        # Do not return demo/fallback data per project policy
        return pd.DataFrame(columns=['designation'])


def load_comets(ts, eph, observer_location, max_comets: int = MAX_COMETS_DEFAULT, use_cache: bool = True, current_dt: Optional[datetime] = None) -> List[dict]:
    """
    Compute comet positions and times for the given observer location.
    Uses photometric filters similar to bright_asteroids: prefilter by M1<=MAX_ABSOLUTE_MAGNITUDE and
    final apparent magnitude <= MAX_APPARENT_MAGNITUDE. Iterates until up to max_comets are collected.
    Returns a list of dicts compatible with the frontend.
    """
    # Extract location
    if isinstance(observer_location, dict):
        lat = float(observer_location.get('latitude', 0.0))
        lon = float(observer_location.get('longitude', 0.0))
        elevation = float(observer_location.get('elevation', 0.0))
    else:
        try:
            lat = float(observer_location.latitude.degrees)
            lon = float(observer_location.longitude.degrees)
            elevation = float(observer_location.elevation.m)
        except AttributeError:
            logger.warning("Could not extract location data from observer_location")
            lat, lon, elevation = 0.0, 0.0, 0.0

    # Choose evaluation time: simulated or current UTC
    dt_utc = current_dt or datetime.now(timezone.utc)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)

    # Per-location/time-bucket cache for final comet list (bucket based on simulated time if provided)
    if use_cache:
        if COMET_USE_SQLITE:
            # Try SQLite cache first
            lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
            loc_key = location_key(lat_norm, lon_norm, elev_norm)
            time_bucket = time_bucket_utc(dt_utc, COMET_CACHE_BUCKET_HOURS)
            
            try:
                from db_utils import get_comet_positions
                cached_positions = get_comet_positions(loc_key, time_bucket, COMET_CACHE_TTL_SECONDS)
                if cached_positions:
                    logger.debug(f"Loading SQLite comet cache for {loc_key}/{time_bucket}")
                    return cached_positions[:max_comets]
            except Exception as e:
                logger.debug(f"SQLite comet cache failed: {e}")
        
        # Fallback to pickle cache
        cache_file = build_cache_path('comets', lat, lon, elevation, dt=dt_utc, bucket_hours=COMET_CACHE_BUCKET_HOURS)
        try:
            cached_list = read_pickle_if_fresh(cache_file, COMET_CACHE_TTL_SECONDS)
            if isinstance(cached_list, list):
                logger.debug(f"Loading {cache_file} (valid per-location/time cache)")
                return cached_list[:max_comets]
            # Fallback to legacy global cache for migration
            legacy = read_pickle_if_fresh(BRIGHT_COMET_CACHE_FILE, COMET_CACHE_TTL_SECONDS)
            if isinstance(legacy, list):
                logger.debug(f"Loading legacy comet cache {BRIGHT_COMET_CACHE_FILE}")
                return legacy[:max_comets]
        except Exception as e:
            logger.debug(f"Error reading comet caches: {e}")

    # Load comet dataframe and store in SQLite if enabled
    df = load_comet_dataframe()
    if df is None or df.empty:
        return []
    
    # Store comet data in SQLite for future use
    if COMET_USE_SQLITE:
        try:
            from db_utils import store_comet_dataframe
            stored_count = store_comet_dataframe(df)
            logger.debug(f"Stored {stored_count} comets in SQLite database")
        except Exception as e:
            logger.debug(f"Failed to store comets in SQLite: {e}")

    # Prefilter by photometric parameters to reduce heavy computations
    try:
        # Do not require k1; use default n=4.0 later if missing (align with example in c.py)
        df_pref = df[(df['M1'].notna()) & (df['M1'] <= MAX_ABSOLUTE_MAGNITUDE)].copy()
        # Process intrinsically brighter comets first
        if 'M1' in df_pref.columns:
            df_pref = df_pref.sort_values('M1')
        logger.debug(f"Prefiltered comets by M1<= {MAX_ABSOLUTE_MAGNITUDE}: {len(df_pref)} candidates from {len(df)}")
    except Exception as e:
        logger.warning(f"Comet prefilter failed, processing all: {e}")
        df_pref = df

    t = ts.from_datetime(dt_utc)
    topos = Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=elevation)
    observer = eph['earth'] + topos
    sun = eph['sun']
    # Determine observer timezone for formatting and local-day selection
    tz = get_tzinfo(lat, lon)

    comet_list: List[dict] = []
    count = 0

    for designation, row in df_pref.iterrows():
        if count >= max_comets:
            break
        try:
            # Prepare row with expected aliases
            row2 = row.copy()
            # Coerce numeric fields at row level to avoid stray strings from upstream/caches
            row_numeric_cols = ['e', 'q', 'incl', 'i', 'om', 'node', 'w', 'peri', 'epoch_tt', 'Tp', 'M1', 'k1', 'M2', 'k2']
            for col in row_numeric_cols:
                if col in row2.index:
                    val = row2.get(col)
                    try:
                        if pd.notna(val):
                            row2[col] = float(val)
                        else:
                            row2[col] = np.nan
                    except Exception:
                        row2[col] = np.nan
            # Backfill aliases in both directions for robustness
            om_val = row2.get('om')
            node_val = row2.get('node')
            if pd.isna(node_val) and om_val is not None and pd.notna(om_val):
                row2['node'] = om_val
            if pd.isna(om_val) and node_val is not None and pd.notna(node_val):
                row2['om'] = node_val
            w_val = row2.get('w')
            peri_val = row2.get('peri')
            if pd.isna(peri_val) and w_val is not None and pd.notna(w_val):
                row2['peri'] = w_val
            if pd.isna(w_val) and peri_val is not None and pd.notna(peri_val):
                row2['w'] = peri_val
            i_val = row2.get('i')
            incl_val = row2.get('incl')
            if pd.isna(i_val) and incl_val is not None and pd.notna(incl_val):
                row2['i'] = incl_val
            if pd.isna(incl_val) and i_val is not None and pd.notna(i_val):
                row2['incl'] = i_val
            # Map MPC raw names at row level if present
            if pd.isna(row2.get('e')) and pd.notna(row2.get('eccentricity')):
                row2['e'] = float(row2.get('eccentricity'))
            if pd.isna(row2.get('q')) and pd.notna(row2.get('perihelion_distance_au')):
                row2['q'] = float(row2.get('perihelion_distance_au'))
            if pd.isna(row2.get('om')) and pd.notna(row2.get('longitude_of_ascending_node_degrees')):
                row2['om'] = float(row2.get('longitude_of_ascending_node_degrees'))
            if pd.isna(row2.get('w')) and pd.notna(row2.get('argument_of_perihelion_degrees')):
                row2['w'] = float(row2.get('argument_of_perihelion_degrees'))
            if pd.isna(row2.get('i')) and pd.notna(row2.get('inclination_degrees')):
                row2['i'] = float(row2.get('inclination_degrees'))
            if pd.isna(row2.get('M1')) and pd.notna(row2.get('magnitude_g')):
                row2['M1'] = float(row2.get('magnitude_g'))
            if pd.isna(row2.get('k1')) and pd.notna(row2.get('magnitude_k')):
                row2['k1'] = float(row2.get('magnitude_k'))

            # If Tp missing but perihelion date provided, build Tp using TS
            try:
                if (('Tp' not in row2.index) or pd.isna(row2.get('Tp'))):
                    if all(c in row2.index for c in ['perihelion_year','perihelion_month','perihelion_day']):
                        y = row2.get('perihelion_year')
                        m = row2.get('perihelion_month')
                        d = row2.get('perihelion_day')
                        if pd.notna(y) and pd.notna(m) and pd.notna(d):
                            tt = ts.tt(int(y), int(m), int(d))
                            row2['Tp'] = float(tt.tt)
            except Exception:
                pass
            # If epoch_tt missing but epoch Y/M/D provided, build epoch_tt
            try:
                if (('epoch_tt' not in row2.index) or pd.isna(row2.get('epoch_tt'))):
                    if all(c in row2.index for c in ['epoch_year','epoch_month','epoch_day']):
                        y = row2.get('epoch_year')
                        m = row2.get('epoch_month')
                        d = row2.get('epoch_day')
                        if pd.notna(y) and pd.notna(m) and pd.notna(d):
                            tt = ts.tt(int(y), int(m), int(d))
                            row2['epoch_tt'] = float(tt.tt)
            except Exception:
                pass

            # Validate essentials before orbit build
            essentials = ['e', 'q']
            for c in ['i', 'incl']:
                if c in row2.index:
                    essentials.append(c)
                    break
            essentials += [c for c in ['om', 'w'] if c in row2.index]
            if any(pd.isna(row2.get(c)) for c in essentials):
                raise ValueError(f"Missing essential elements in row for {designation}: {[c for c in essentials if pd.isna(row2.get(c))]}")

            # Build comet orbit from pandas row (not dict)
            orbit = mpc.comet_orbit(row2, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)

            # Ensure barycentric target like in c.py: if orbit is Sun-centered, shift to SSB by adding Sun
            try:
                center_code = int(getattr(orbit, 'center', 10))
            except Exception:
                center_code = 10
            target = (sun + orbit) if center_code != 0 else orbit

            # Compute geometry and estimate magnitude BEFORE heavy rise/set/transit
            astrometric = observer.at(t).observe(target)
            apparent_magnitude = None
            try:
                r = sun.at(t).observe(target).distance().au
                delta = astrometric.distance().au
                if pd.notna(row2.get('M1')):
                    M1 = float(row2.get('M1'))
                    n_raw = row2.get('k1')
                    n = float(n_raw) if (n_raw is not None and pd.notna(n_raw)) else 4.0
                    apparent_magnitude = (
                        float(M1)
                        + 5.0 * math.log10(max(delta, 1e-12))
                        + 2.5 * float(n) * math.log10(max(r, 1e-12))
                    )
            except Exception:
                pass

            # Apply apparent magnitude filter; skip faint comets early
            if not isinstance(apparent_magnitude, (int, float)) or apparent_magnitude > MAX_APPARENT_MAGNITUDE:
                continue

            # Apparent position only for passing comets
            apparent = astrometric.apparent()
            ra, dec, distance = apparent.radec()
            alt, az, _ = apparent.altaz()

            # Rise/Set over next 48h starting at UTC midnight (mirror bright_asteroids)
            try:
                start_time = ts.utc(t.utc_datetime().replace(hour=0, minute=0, second=0, microsecond=0))
                end_time = ts.utc(start_time.utc_datetime() + timedelta(hours=24))
                rise_set_func = almanac.risings_and_settings(eph, target, topos)
                times, events = almanac.find_discrete(start_time, end_time, rise_set_func)

                rise_time, set_time = None, None
                for ti, event in zip(times, events):
                    if event == 1 and rise_time is None:
                        rise_time = ti.utc_datetime()
                    elif event == 0 and set_time is None:
                        set_time = ti.utc_datetime()

                # Transit time (choose highest altitude for local day)
                f = almanac.meridian_transits(eph, target, topos)
                t_times, t_events = almanac.find_discrete(start_time, end_time, f)
                chosen_local_dt = None
                if len(t_times):
                    now_local = dt_utc.astimezone(tz)
                    today_local = now_local.date()
                    candidates = []
                    for ti, ev in zip(t_times, t_events):
                        utc_dt = ti.utc_datetime().replace(tzinfo=timezone.utc)
                        try:
                            alt_deg = observer.at(ti).observe(target).apparent().altaz()[0].degrees
                        except Exception:
                            alt_deg = float('-inf')
                        candidates.append((utc_dt, alt_deg, int(ev)))
                    # Kandidaten auf heutigen lokalen Tag beschränken
                    today_candidates = []
                    for utc_dt, alt_deg, ev in candidates:
                        local_dt = utc_dt.astimezone(tz)
                        if local_dt.date() == today_local:
                            today_candidates.append((utc_dt, alt_deg, ev))
                    pool = today_candidates if today_candidates else candidates
                    if pool:
                        pool.sort(key=lambda x: (-x[1], x[0]))
                        chosen_local_dt = pool[0][0]
                transit_time = chosen_local_dt
            except Exception as e:
                logger.debug(f"Rise/Set/Transit calculation failed for {designation}: {e}")
                rise_time = None
                set_time = None
                transit_time = None
        except Exception as e:
            logger.debug(f"Error processing comet {designation}: {e}")
            continue
        else:
            # Name or designation
            if 'name' in row2 and pd.notna(row2['name']) and str(row2['name']).strip():
                name = str(row2['name'])
            else:
                name = designation

            comet_list.append({
                'name': name,
                'symbol': '☄️',
                'type': 'comet',
                'ra': ra.hours * 15.0,
                'dec': dec.degrees,
                'altitude': alt.degrees,
                'azimuth': az.degrees,
                'distance': round(distance.au, 3),
                'magnitude': round(float(apparent_magnitude), 1) if isinstance(apparent_magnitude, (int, float)) else None,
                'rise_time': format_time(rise_time, tz),
                'set_time': format_time(set_time, tz),
                'transit_time': format_time(transit_time, tz)
            })
            count += 1

    # Save final list to cache for faster subsequent loads
    if COMET_USE_SQLITE:
        # Store in SQLite cache
        try:
            from db_utils import store_comet_positions
            lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
            loc_key = location_key(lat_norm, lon_norm, elev_norm)
            time_bucket = time_bucket_utc(dt_utc, COMET_CACHE_BUCKET_HOURS)
            
            # We need comet IDs for SQLite storage - use a dummy approach for now
            # In a full implementation, we'd match comets to database IDs
            store_comet_positions(0, loc_key, time_bucket, lat, lon, elevation, comet_list)
            logger.debug(f"Saved {len(comet_list)} bright comets to SQLite cache ({loc_key}/{time_bucket})")
        except Exception as e:
            logger.debug(f"Failed to write SQLite comet cache: {e}")
    
    # Also save to pickle cache as fallback
    try:
        cache_file = build_cache_path('comets', lat, lon, elevation, dt=dt_utc, bucket_hours=COMET_CACHE_BUCKET_HOURS)
        atomic_write_pickle(cache_file, comet_list)
        logger.debug(f"Saved {len(comet_list)} bright comets to pickle cache ({cache_file})")
    except Exception as e:
        logger.debug(f"Failed to write comet pickle cache {cache_file}: {e}")

    return comet_list
