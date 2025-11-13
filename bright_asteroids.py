"""
Module for calculating positions of bright minor planets (asteroids)
"""
from pathlib import Path

from skyfield.api import Topos, Loader
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2
import pandas as pd
from skyfield import almanac
import numpy as np
import os
import time
from datetime import datetime, timedelta, timezone
import gzip
import urllib.request
from skyfield.data import mpc
import math
from types import SimpleNamespace
from typing import Optional
from cache_utils import normalize_location, location_key, time_bucket_utc
from timezone_utils import get_tzinfo
from db_utils import (
    store_asteroid_dataframe, store_asteroid_positions,
    get_asteroid_positions
)
from data_paths import DATA_DIR, DE421_PATH, MPCORB_PATH

# Konstanten
MPCORB_FILE = Path(MPCORB_PATH)
MPCORB_URL = 'https://www.minorplanetcenter.net/iau/MPCORB/MPCORB.DAT.gz'
MAX_ASTEROIDS = 5000
# Magnitude thresholds (restored defaults)
# H-limit for prefiltering by absolute magnitude (smaller = brighter)
MAX_ABSOLUTE_MAGNITUDE = float(os.environ.get('ASCII_SKY_ASTEROID_MAX_ABSOLUTE_MAG', '12.0'))
# V-limit for final apparent magnitude filtering
MAX_APPARENT_MAGNITUDE = float(os.environ.get('ASCII_SKY_ASTEROID_MAX_APPARENT_MAG', '10.0'))
# Gravitationskonstante der Sonne für Skyfield
GM_SUN = 1.32712440041e20

# Cache-Gültigkeitsdauer in Stunden
CACHE_VALIDITY_HOURS = 12

# Module-specific cache granularity for per-location/time asteroid list
# Use a 1-hour time bucket; TTL must cover the 30-day precompute window
# so that snapshots created up to 30 days earlier remain valid.
ASTEROID_CACHE_BUCKET_HOURS = 1
ASTEROID_CACHE_TTL_SECONDS = 31 * 24 * 3600  # 31 days
# Cache kind for consistency with celestial/comets naming
ASTEROID_CACHE_KIND = 'asteroids'

# Limit number of event computations (rise/set/transit) per request to reduce CPU peaks
ASTEROIDS_EVENTS_MAX = int(os.environ.get('ASCII_SKY_ASTEROIDS_EVENTS_MAX', '50'))

# In-memory cache for asteroid DataFrame
_asteroid_df_cache = None
_asteroid_df_timestamp = None
ASTEROID_DF_CACHE_TTL_SECONDS = 49 * 3600  # 49 hours (matches positions cache TTL)

def clear_in_memory_cache():
    """Clear in-memory DataFrame cache - called when filters change"""
    global _asteroid_df_cache, _asteroid_df_timestamp
    _asteroid_df_cache = None
    _asteroid_df_timestamp = None
    print("Cleared asteroid in-memory DataFrame cache")

def format_time(dt, tz=None):
    """
    Formatiert ein datetime-Objekt als lokale Zeit im Format 'HH:MM'.
    Gibt None zurück, wenn dt None ist.
    Wenn tz übergeben wird, wird in diese Zeitzone konvertiert. Naive dt
    wird als UTC interpretiert.
    """
    if dt is None:
        return None
    # Stelle sicher, dass dt tz-aware ist (interpretiere naive als UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if tz is None:
        local_time = dt.astimezone()
    else:
        local_time = dt.astimezone(tz)
    return f"{local_time.hour:02d}:{local_time.minute:02d}"

# IAU H-G asteroid magnitude system (vectorized)
def vectorized_asteroid_apparent_magnitude(H, G, r, delta, phase_angle_deg):
    """
    Compute apparent V magnitude using the IAU H-G phase function (vectorized).
    V = H + 5 log10(r * delta) - 2.5 log10((1 - G) * Phi1 + G * Phi2)
    """
    alpha = np.radians(phase_angle_deg)
    tan_half = np.tan(alpha / 2.0)

    # Phase functions (ensure base is non-negative)
    tan_half_safe = np.maximum(tan_half, 0)
    phi1 = np.exp(-3.33 * (tan_half_safe ** 0.63))
    phi2 = np.exp(-1.87 * (tan_half_safe ** 1.22))

    # Flux term
    flux_term = (1.0 - G) * phi1 + G * phi2

    # Avoid log of zero
    flux_term = np.maximum(flux_term, 1e-12)
    distance_term = np.maximum(r * delta, 1e-12)

    value = H + 5.0 * np.log10(distance_term) - 2.5 * np.log10(flux_term)
    return value

def download_mpcorb_file():
    """
    Lädt die MPCORB.DAT.gz-Datei von der Minor Planet Center-Website herunter
    """
    try:
        print(f"Downloading MPCORB.DAT.gz from {MPCORB_URL}...")
        # Stelle sicher, dass das Verzeichnis existiert
        MPCORB_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Datei herunterladen mit Fortschrittsanzeige
        print("Starting download...")
        with urllib.request.urlopen(MPCORB_URL, timeout=300) as response, MPCORB_FILE.open('wb') as out_file:
            file_size = int(response.info().get('Content-Length', 0))
            print(f"File size: {file_size / (1024*1024):.1f} MB")
            
            downloaded = 0
            block_size = 8192
            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                    
                downloaded += len(buffer)
                out_file.write(buffer)
                
                # Fortschritt alle 1MB anzeigen
                if downloaded % (1024*1024) < block_size:
                    print(f"Downloaded: {downloaded / (1024*1024):.1f} MB ({downloaded * 100 / file_size:.1f}%)")
        
        print(f"Download complete. File saved to {MPCORB_FILE}")
        
        # Überprüfe, ob die Datei korrekt heruntergeladen wurde
        if MPCORB_FILE.exists() and MPCORB_FILE.stat().st_size > 0:
            print(f"File size: {MPCORB_FILE.stat().st_size / (1024*1024):.1f} MB")
            return True
        else:
            print("Download failed: File is empty or does not exist")
            return False
    except Exception as e:
        print(f"Error downloading MPCORB.DAT.gz: {e}")
        return False
    return True

def should_update_mpcorb_file():
    """
    Überprüft ob MPCORB-Datei aktualisiert werden sollte (täglich)
    
    NOTE: Daily updates are now handled by nightly_data_updater.py at 2:00 AM.
    This function is kept for manual/utility purposes only.
    """
    if not MPCORB_FILE.exists():
        return True
    
    # Prüfe Alter der Datei
    file_age = time.time() - MPCORB_FILE.stat().st_mtime
    # Aktualisiere täglich (24 Stunden = 86400 Sekunden)
    return file_age > 86400

def load_bright_asteroids(loader, ts, eph, observer_location, max_magnitude=MAX_APPARENT_MAGNITUDE, use_cache=True, current_dt: Optional[datetime] = None):
    """
    Load and calculate positions, magnitudes, and rise/set times of the brightest minor planets
    """
    if isinstance(observer_location, dict):
        lat, lon, elevation = observer_location.get('latitude', 0.0), observer_location.get('longitude', 0.0), observer_location.get('elevation', 0.0)
    else:
        try:
            lat, lon, elevation = observer_location.latitude.degrees, observer_location.longitude.degrees, observer_location.elevation.m
        except AttributeError:
            print("Warning: Could not extract location data from observer_location")
            lat, lon, elevation = 0.0, 0.0, 0.0

    print(f"Getting asteroids with magnitude <= {max_magnitude} at lat={lat}, lon={lon}, elevation={elevation}.")
    # Determine observer timezone from coordinates
    tz = get_tzinfo(lat, lon)

    # Check PostgreSQL cache
    if use_cache:
        # PostgreSQL backend: check for cached positions
        from cache_utils import normalize_location, location_key, time_bucket_utc
        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        time_bucket = time_bucket_utc(current_dt, ASTEROID_CACHE_BUCKET_HOURS)
        
    # --- PostgreSQL Loading (ONLY source) ---
    import pickle
    from db_utils import get_asteroid_dataframe
    
    try:
        df_pickle = get_asteroid_dataframe()
        if not df_pickle:
            print("ERROR: No asteroids in PostgreSQL database! Run data_updater first.")
            return []
        
        df = pickle.loads(df_pickle)
        print(f"Loaded {len(df)} asteroids from PostgreSQL database")
        
        # Filter by magnitude
        df_filtered = df[df['magnitude_H'] <= MAX_ABSOLUTE_MAGNITUDE].copy()
        df_filtered = df_filtered.sort_values('magnitude_H')
        df_filtered = df_filtered.head(MAX_ASTEROIDS * 2)
        
        print(f"Filtered to {len(df_filtered)} asteroids with H <= {MAX_ABSOLUTE_MAGNITUDE}")
        
    except Exception as e:
        print(f"ERROR: Cannot connect to PostgreSQL database: {e}")
        print("Make sure POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD are set correctly.")
        return []

    # Process asteroids from DataFrame
    if df_filtered is not None and not df_filtered.empty:
        from skyfield.data import mpc
        from skyfield.toposlib import Topos
        from skyfield.framelib import itrs
        from skyfield.functions import from_spherical, length_of

        sun = eph['sun']
        dt_utc = current_dt or datetime.now(timezone.utc)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        t = ts.from_datetime(dt_utc)
        
        # Build observer from lat/lon/elevation
        # Note: Using ITRS frame directly for observer position is more efficient
        # than creating a Topos object for each observation.
        observer_pos = eph['earth'].at(t).frame_xyz(itrs).au
        
        # Vectorized orbit creation
        orbits = [mpc.mpcorb_orbit(row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2) for _, row in df_filtered.iterrows()]
        
        # Vectorized target creation
        # Note: assumes all are heliocentric; mpc.mpcorb should ensure this
        targets = [sun + orbit for orbit in orbits]
        
        # --- Vectorized Position and Magnitude Calculation ---
        astrometrics = eph['earth'].at(t).observe(targets)

        # Distances
        delta = astrometrics.distance().au
        # Heliocentric positions of asteroids
        asteroid_helio_pos = np.array([target.at(t).position.au for target in targets])
        # Heliocentric positions of observer (Earth)
        observer_helio_pos = eph['earth'].at(t).position.au
        # Vector from asteroids to observer
        vec_to_observer = observer_helio_pos - asteroid_helio_pos
        # Heliocentric distance `r`
        r = length_of(asteroid_helio_pos)

        # Phase angle calculation (vectorized)
        phase_angle_rad = np.arccos(
            np.clip((r**2 + delta**2 - 1) / (2 * r * delta), -1, 1)
        )
        phase_angle_deg = np.degrees(phase_angle_rad)

        # Apparent magnitude (vectorized)
        H = df_filtered['magnitude_H'].to_numpy(dtype=float)
        G = df_filtered['magnitude_G'].to_numpy(dtype=float, na_value=0.15)
        apparent_magnitudes = vectorized_asteroid_apparent_magnitude(H, G, r, delta, phase_angle_deg)

        # Filter by apparent magnitude
        bright_mask = (apparent_magnitudes <= max_magnitude)

        if not np.any(bright_mask):
            return []

        # Select only bright asteroids for final processing
        bright_df = df_filtered[bright_mask].copy()
        bright_df['apparent_magnitude'] = apparent_magnitudes[bright_mask]

        # Reduce targets and astrometric data to only bright ones
        bright_targets = [targets[i] for i in range(len(targets)) if bright_mask[i]]
        bright_astrometrics = astrometrics[bright_mask]

        # Sort by apparent magnitude
        bright_df = bright_df.sort_values('apparent_magnitude').head(MAX_ASTEROIDS)

        # Get coordinates for bright asteroids
        ra, dec, _ = bright_astrometrics.radec()
        alt, az, _ = bright_astrometrics.apparent().altaz(location=Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=elevation))
        
        bright_df['ra_hours'] = ra.hours
        bright_df['dec_degrees'] = dec.degrees
        bright_df['altitude'] = alt.degrees
        bright_df['azimuth'] = az.degrees
        bright_df['distance_au'] = delta[bright_mask]

        # --- Iterative Rise/Set/Transit for Bright Asteroids ---
        asteroid_list = []
        events_computed = 0

        topos = Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=elevation)

        for idx, row in bright_df.iterrows():
            target = sun + mpc.mpcorb_orbit(row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)

            rise_time, set_time, transit_time = None, None, None
            if events_computed < ASTEROIDS_EVENTS_MAX:
                try:
                    start_time = ts.utc(t.utc_datetime().replace(hour=0, minute=0, second=0, microsecond=0))
                    end_time = ts.utc(start_time.utc_datetime() + timedelta(days=2))

                    # Rise/Set
                    rise_set_func = almanac.risings_and_settings(eph, target, topos)
                    times, events = almanac.find_discrete(start_time, end_time, rise_set_func)
                    for ti, event in zip(times, events):
                        if event == 1 and rise_time is None: rise_time = ti.utc_datetime()
                        elif event == 0 and set_time is None: set_time = ti.utc_datetime()

                    # Transit
                    f = almanac.meridian_transits(eph, target, topos)
                    t_times, t_events = almanac.find_discrete(start_time, end_time, f)
                    if len(t_times):
                        now_utc = current_dt if current_dt.tzinfo is not None else current_dt.replace(tzinfo=timezone.utc)
                        candidates = []
                        for ti, ev in zip(t_times, t_events):
                            utc_dt = ti.utc_datetime().replace(tzinfo=timezone.utc)
                            try:
                                alt_deg = (eph['earth'] + topos).at(ti).observe(target).apparent().altaz()[0].degrees
                            except Exception:
                                alt_deg = float('-inf')
                            candidates.append((utc_dt, alt_deg, int(ev)))

                        pool = [c for c in candidates if c[0] >= now_utc]
                        if not pool: pool = candidates
                        if pool:
                            pool.sort(key=lambda x: (-x[1], x[0]))
                            transit_time = pool[0][0]

                    events_computed += 1
                except Exception:
                    pass

            def format_time_str(dt, tz):
                if dt is None: return None
                if not hasattr(dt, 'tzinfo') or dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(tz).strftime('%H:%M')

            asteroid_data = {
                'name': row['designation'],
                'ra': row['ra_hours'],
                'dec': row['dec_degrees'],
                'magnitude': round(row['apparent_magnitude'], 1),
                'altitude': row['altitude'],
                'azimuth': row['azimuth'],
                'distance': round(row['distance_au'], 3),
                'rise_time': format_time_str(rise_time, tz),
                'transit_time': format_time_str(transit_time, tz),
                'set_time': format_time_str(set_time, tz),
                'type': 'asteroid',
                'symbol': '⚸'
            }
            asteroid_list.append(asteroid_data)

        # Cache results
        if use_cache and asteroid_list:
            lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
            loc_key = location_key(lat_norm, lon_norm, elev_norm)
            time_bucket = time_bucket_utc(current_dt, ASTEROID_CACHE_BUCKET_HOURS)
            try:
                store_asteroid_positions(0, loc_key, time_bucket, lat, lon, elevation, asteroid_list)
            except Exception as e:
                print(f"Failed to cache asteroid positions: {e}")
        
        return asteroid_list
    else:
        # No data available
        return []
