"""
Module for calculating positions of comets using real MPC data.
- Loads MPC comet dataframe and caches it (~6h) to disk and memory
- Builds comet orbits from pandas rows (not dict) to avoid attribute errors
- Computes apparent position, optional magnitude estimate (M1/k1), and rise/set/transit times
"""
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2
from skyfield.data import mpc
from skyfield import almanac

import os
import time
import logging
import pickle
from datetime import datetime, timedelta, timezone
import gzip
import urllib.request
import math
from types import SimpleNamespace
from typing import Optional, List
from functools import lru_cache

import pandas as pd
import numpy as np
from skyfield.magnitudelib import planetary_magnitude

from cache_utils import normalize_location, location_key, time_bucket_utc
from timezone_utils import get_tzinfo
from bright_asteroids import format_time, vectorized_asteroid_apparent_magnitude
import logging
from db_utils import get_db_connection, store_comet_dataframe, store_comet_positions, get_comet_positions
from pathlib import Path
from data_paths import COMET_ELEMENTS_PATH
from api.computation import wgs84

def vectorized_comet_apparent_magnitude(M1, n, delta, r):
    """
    Vectorized apparent magnitude calculation for comets.
    Total magnitude = M1 + 5 * log10(delta) + 2.5 * n * log10(r)
    - M1: Absolute magnitude (parameter g in MPC files)
    - n: Photometric exponent (parameter k in MPC files)
    - delta: Geocentric distance (AU)
    - r: Heliocentric distance (AU)
    """
    # Ensure no log of zero or negative numbers
    delta_safe = np.maximum(delta, 1e-12)
    r_safe = np.maximum(r, 1e-12)

    magnitude = M1 + 5.0 * np.log10(delta_safe) + 2.5 * n * np.log10(r_safe)
    return magnitude

def should_update_comet_file() -> bool:
    """Prueft, ob die Kometen-Elemente-Datei taeglich aktualisiert werden sollte.
    
    NOTE: Daily updates are now handled by nightly_data_updater.py at 2:00 AM.
    This function is kept for manual/utility purposes only.
    """
    if not COMETS_FILE.exists():
        return True

    # Prüfe Alter der Datei
    file_age = time.time() - COMETS_FILE.stat().st_mtime
    # Aktualisiere täglich (24 Stunden = 86400 Sekunden)
    return file_age > 86400

# Configuration
COMETS_FILE = Path(COMET_ELEMENTS_PATH)
COMET_CACHE_TTL_SECONDS = 31 * 24 * 3600  # 31 days (longer than 30-day precompute window)
COMET_CACHE_BUCKET_HOURS = 1
COMET_DF_CACHE_TTL_SECONDS = 31 * 24 * 3600  # 31 days
MAX_COMETS_DEFAULT = 1000
MAX_APPARENT_MAGNITUDE = float(os.environ.get('ASCII_SKY_COMET_MAX_APPARENT_MAG', '14.0'))
MAX_ABSOLUTE_MAGNITUDE = float(os.environ.get('ASCII_SKY_COMET_MAX_ABSOLUTE_MAG', '18.0'))
GM_SUN_Pitjeva_2005_km3_s2 = 1.32712442099e11
COMET_EVENTS_MAX = int(os.environ.get('ASCII_SKY_COMET_EVENTS_MAX', '300'))


# Photometric filters (align with bright_asteroids thresholds)
# Limit number of final returned comets; we will iterate candidates until we collect up to this many

# Ensure cache directory exists
os.makedirs('cache', exist_ok=True)

# In-memory cache
_comet_df_cache = None
_comet_df_timestamp = None

# Logger
logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now()


def _clear_comet_caches():
    """Clear all comet-related cache files when new data is downloaded"""
    import glob
    import shutil
    
    logger.debug("Clearing comet caches")
    
    # Clear in-memory cache
    global _comet_df_cache, _comet_df_timestamp
    _comet_df_cache = None
    _comet_df_timestamp = None

def clear_in_memory_cache():
    """Clear in-memory DataFrame cache - called when filters change"""
    global _comet_df_cache, _comet_df_timestamp
    _comet_df_cache = None
    _comet_df_timestamp = None
    logger.info("Cleared comet in-memory DataFrame cache")


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
        if (_now() - _comet_df_timestamp).total_seconds() < COMET_DF_CACHE_TTL_SECONDS:
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

    # Fetch fresh (prefer local MPC file cache if available)
    try:
        # Download only if file doesn't exist (first start)
        # Daily updates are handled by nightly_data_updater.py
        if not COMETS_FILE.exists():
            logger.info("Comet file not found, downloading for initial setup...")
            try:
                with urllib.request.urlopen(mpc.COMET_URL, timeout=30) as rf:
                    content = rf.read()
                if content:
                    COMETS_FILE.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        with COMETS_FILE.open('wb') as wf:
                            wf.write(content)
                        logger.info(f"Downloaded comet file: {COMETS_FILE}")
                    except Exception as we:
                        logger.warning(f"Failed to write {COMETS_FILE}: {we}")
            except Exception as ne:
                logger.error(f"Error downloading MPC comet elements: {ne}")
        
        # Load from local file
        if COMETS_FILE.exists():
            with COMETS_FILE.open('rb') as f:
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
        
        logger.debug(f"Loaded {len(comets)} comets from MPC (stored in PostgreSQL).")
        return _comet_df_cache
    except Exception as e:
        logger.error(f"Error loading comet data: {e}")
        # Do not return demo/fallback data per project policy
        return pd.DataFrame(columns=['designation'])


def load_comets(ts, eph, observer_location, max_comets: int = MAX_COMETS_DEFAULT, use_cache: bool = True, current_dt: Optional[datetime] = None) -> List[dict]:
    """
    Compute comet positions and times for the given observer location using vectorized calculations.
    """
    from skyfield.toposlib import Topos
    from skyfield.functions import length_of

    # Extract location
    if isinstance(observer_location, dict):
        lat, lon, elevation = (float(observer_location.get(k, 0.0)) for k in ['latitude', 'longitude', 'elevation'])
    else:
        try:
            lat, lon, elevation = observer_location.latitude.degrees, observer_location.longitude.degrees, observer_location.elevation.m
        except AttributeError:
            logger.warning("Could not extract location data from observer_location")
            lat, lon, elevation = 0.0, 0.0, 0.0

    # Choose evaluation time
    dt_utc = current_dt or datetime.now(timezone.utc)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    t = ts.from_datetime(dt_utc)

    # Per-location/time-bucket cache
    if use_cache:
        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        time_bucket = time_bucket_utc(dt_utc, COMET_CACHE_BUCKET_HOURS)
        try:
            cached_positions = get_comet_positions(loc_key, time_bucket, COMET_CACHE_TTL_SECONDS)
            if cached_positions:
                logger.debug(f"Loading PostgreSQL comet cache for {loc_key}/{time_bucket}")
                return cached_positions[:max_comets]
        except Exception as e:
            logger.debug(f"PostgreSQL comet cache failed: {e}")

    # Load comet dataframe from PostgreSQL
    try:
        df_pickle = get_comet_dataframe()
        df = pickle.loads(df_pickle) if df_pickle else pd.DataFrame()
        if df.empty:
            logger.error("No comets in PostgreSQL database! Run data_updater first.")
            return []
        logger.info(f"Loaded {len(df)} comets from PostgreSQL database")
    except Exception as e:
        logger.error(f"Cannot connect to PostgreSQL database: {e}")
        return []

    # Prefilter by absolute magnitude
    df_pref = df[df['M1'].notna() & (df['M1'] <= MAX_ABSOLUTE_MAGNITUDE)].copy()
    if 'M1' in df_pref.columns:
        df_pref = df_pref.sort_values('M1')
    logger.debug(f"Prefiltered to {len(df_pref)} comets with M1 <= {MAX_ABSOLUTE_MAGNITUDE}")

    if df_pref.empty:
        return []

    # --- Vectorized Position and Magnitude Calculation ---
    sun = eph['sun']

    # Create orbit objects for all candidate comets
    # Ensure 'designation' is a column for mpc.comet_orbit
    if 'designation' not in df_pref.columns:
         df_pref['designation'] = df_pref.index
    orbits = [mpc.comet_orbit(row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2) for _, row in df_pref.iterrows()]
    targets = [sun + orbit for orbit in orbits] # Assume all are heliocentric

    # Observe all targets at once
    astrometrics = eph['earth'].at(t).observe(targets)

    # Geocentric distance (delta)
    delta = astrometrics.distance().au

    # Heliocentric distance (r)
    comet_helio_pos = np.array([target.at(t).position.au for target in targets])
    r = length_of(comet_helio_pos)

    # Apparent magnitude (vectorized)
    M1 = df_pref['M1'].to_numpy(dtype=float)
    k1 = df_pref['k1'].to_numpy(dtype=float, na_value=4.0) # Default n=4.0 if k1 is missing
    apparent_magnitudes = vectorized_comet_apparent_magnitude(M1, k1, delta, r)

    # Filter by apparent magnitude
    bright_mask = (apparent_magnitudes <= MAX_APPARENT_MAGNITUDE)
    if not np.any(bright_mask):
        return []

    # Select bright comets
    bright_df = df_pref[bright_mask].copy()
    bright_df['apparent_magnitude'] = apparent_magnitudes[bright_mask]
    bright_astrometrics = astrometrics[bright_mask]

    # Sort by magnitude and limit
    bright_df = bright_df.sort_values('apparent_magnitude').head(max_comets)

    # Get coordinates for bright comets
    location_topo = Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=elevation)
    ra, dec, distance = bright_astrometrics.radec()
    alt, az, _ = bright_astrometrics.apparent().altaz(location=location_topo)

    bright_df['ra_hours'] = ra.hours
    bright_df['dec_degrees'] = dec.degrees
    bright_df['altitude'] = alt.degrees
    bright_df['azimuth'] = az.degrees
    bright_df['distance_au'] = distance.au

    # --- Iterative Rise/Set/Transit for Bright Comets ---
    comet_list = []
    tz = get_tzinfo(lat, lon)

    for _, row in bright_df.iterrows():
        # Recreate the target object for almanac functions
        target = sun + mpc.comet_orbit(row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)

        rise_time, set_time, transit_time = None, None, None
        try:
            local_dt = dt_utc.astimezone(tz)
            local_midnight = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            utc_midnight = local_midnight.astimezone(timezone.utc)
            start_time = ts.from_datetime(utc_midnight)
            end_time = ts.from_datetime(utc_midnight + timedelta(days=2))
            
            # Rise/Set
            rise_set_func = almanac.risings_and_settings(eph, target, location_topo)
            times, events = almanac.find_discrete(start_time, end_time, rise_set_func)
            today_local = local_dt.date()
            for ti, event in zip(times, events):
                event_local = ti.utc_datetime().replace(tzinfo=timezone.utc).astimezone(tz)
                if event_local.date() == today_local:
                    if event == 1 and rise_time is None: rise_time = ti.utc_datetime().replace(tzinfo=timezone.utc)
                    elif event == 0 and set_time is None: set_time = ti.utc_datetime().replace(tzinfo=timezone.utc)

            # Transit
            f = almanac.meridian_transits(eph, target, location_topo)
            t_times, _ = almanac.find_discrete(start_time, end_time, f)
            if len(t_times):
                candidates = []
                for ti in t_times:
                    utc_dt = ti.utc_datetime().replace(tzinfo=timezone.utc)
                    if utc_dt.astimezone(tz).date() == today_local:
                        alt_deg = (eph['earth'] + location_topo).at(ti).observe(target).apparent().altaz()[0].degrees
                        candidates.append((utc_dt, alt_deg))
                if candidates:
                    candidates.sort(key=lambda x: -x[1])
                    transit_time = candidates[0][0]
        except Exception as e:
            logger.debug(f"Event calculation failed for {row.get('designation', 'N/A')}: {e}")

        name = str(row.get('name', '')).strip() or row['designation']
        comet_list.append({
            'name': name,
            'designation': row['designation'],
            'symbol': '☄️',
            'type': 'comet',
            'ra': row['ra_hours'] * 15.0,
            'dec': row['dec_degrees'],
            'altitude': row['altitude'],
            'azimuth': row['azimuth'],
            'distance': round(row['distance_au'], 3),
            'magnitude': round(float(row['apparent_magnitude']), 1),
            'rise_time': format_time(rise_time, tz),
            'set_time': format_time(set_time, tz),
            'transit_time': format_time(transit_time, tz)
        })

    # Cache results
    if use_cache and comet_list:
        try:
            store_comet_positions(0, loc_key, time_bucket, lat, lon, elevation, comet_list)
            logger.debug(f"Saved {len(comet_list)} bright comets to PostgreSQL cache ({loc_key}/{time_bucket})")
        except Exception as e:
            logger.debug(f"Failed to write PostgreSQL comet cache: {e}")

    return comet_list
