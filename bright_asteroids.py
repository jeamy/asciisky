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

# IAU H-G asteroid magnitude system
def asteroid_apparent_magnitude(H, G, r, delta, phase_angle_deg):
    """
    Compute apparent V magnitude using the IAU H-G phase function.
    V = H + 5 log10(r * delta) - 2.5 log10((1 - G) * Phi1 + G * Phi2)
    with Phi1 = exp(-3.33 * tan(alpha/2)^0.63) and Phi2 = exp(-1.87 * tan(alpha/2)^1.22)
    """
    try:
        alpha = math.radians(phase_angle_deg)
        tan_half = math.tan(alpha / 2.0)
        # Phase functions
        phi1 = math.exp(-3.33 * (tan_half ** 0.63))
        phi2 = math.exp(-1.87 * (tan_half ** 1.22))
        # Avoid log of zero
        flux_term = max((1.0 - float(G)) * phi1 + float(G) * phi2, 1e-12)
        value = float(H) + 5.0 * math.log10(max(r * delta, 1e-12)) - 2.5 * math.log10(flux_term)
        return value
    except Exception:
        # Conservative fallback if anything goes wrong
        return float(H) + 5.0 * math.log10(max(r * delta, 1e-12))

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
        # Process DataFrame directly (same logic as before)
        from skyfield.data import mpc
        from skyfield.toposlib import Topos
        from skyfield import almanac
        
        # Use passed parameters (don't create new ones!)
        sun = eph['sun']
        
        dt_utc = current_dt or datetime.now(timezone.utc)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        t = ts.from_datetime(dt_utc)
        topos = Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=elevation)
        observer = eph['earth'] + topos
        
        asteroid_list = []
        events_computed = 0
        
        for idx, row in df_filtered.iterrows():
            try:
                # Create Skyfield orbit object from DataFrame row
                orbit = mpc.mpcorb_orbit(row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)
                
                # QUICK PRE-FILTER
                rough_apparent_mag = row['magnitude_H'] + 5.0
                if rough_apparent_mag > 22.0:
                    continue
                
                # Determine target
                center_code = int(getattr(orbit, 'center', 10))
                target = (sun + orbit) if center_code != 0 else orbit
                
                # Calculate position
                astrometric = observer.at(t).observe(target)
                
                # Extract distances for magnitude calculation
                r = astrometric.distance().au
                delta = astrometric.radec()[2].au
                phase_angle = math.degrees(math.acos(
                    max(-1, min(1, (r**2 + delta**2 - 1) / (2 * r * delta)))
                ))
                
                # Calculate apparent magnitude
                H = row['magnitude_H']
                G = row.get('magnitude_G', 0.15)
                apparent_mag = asteroid_apparent_magnitude(H, G, r, delta, phase_angle)
                
                # Filter by magnitude
                if apparent_mag > max_magnitude:
                    continue
                
                # Get RA/Dec
                ra, dec, _ = astrometric.radec()
                
                # Altitude/Azimuth
                alt, az, _ = astrometric.apparent().altaz()
                
                # Rise/Set/Transit times (from legacy code)
                rise_time, set_time, transit_time = None, None, None
                if events_computed < 50:
                    try:
                        # Start/end window anchored at simulated day's UTC midnight
                        start_time = ts.utc(t.utc_datetime().replace(hour=0, minute=0, second=0, microsecond=0))
                        end_time = ts.utc(start_time.utc_datetime() + timedelta(days=2))
                        rise_set_func = almanac.risings_and_settings(eph, target, topos)
                        times, events = almanac.find_discrete(start_time, end_time, rise_set_func)

                        for ti, event in zip(times, events):
                            if event == 1 and rise_time is None: 
                                rise_time = ti.utc_datetime()
                            elif event == 0 and set_time is None: 
                                set_time = ti.utc_datetime()
                        
                        # Transit time calculation
                        f = almanac.meridian_transits(eph, target, topos)
                        t_times, t_events = almanac.find_discrete(start_time, end_time, f)
                        if len(t_times):
                            now_utc = current_dt if current_dt.tzinfo is not None else current_dt.replace(tzinfo=timezone.utc)
                            candidates = []
                            for ti, ev in zip(t_times, t_events):
                                utc_dt = ti.utc_datetime().replace(tzinfo=timezone.utc)
                                try:
                                    alt_deg = observer.at(ti).observe(target).apparent().altaz()[0].degrees
                                except Exception:
                                    alt_deg = float('-inf')
                                candidates.append((utc_dt, alt_deg, int(ev)))
                            
                            # Prefer future events
                            pool = [c for c in candidates if c[0] >= now_utc]
                            if not pool:
                                pool = candidates
                            if pool:
                                pool.sort(key=lambda x: (-x[1], x[0]))
                                transit_time = pool[0][0]
                        
                        events_computed += 1
                    except Exception:
                        pass
                
                # Format times (datetime -> string)
                def format_time_str(dt, tz):
                    if dt is None:
                        return None
                    if not hasattr(dt, 'tzinfo') or dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.astimezone(tz).strftime('%H:%M')
                
                asteroid_data = {
                    'name': row['designation'],
                    'ra': ra.hours,
                    'dec': dec.degrees,
                    'magnitude': round(apparent_mag, 1),
                    'altitude': alt.degrees,
                    'azimuth': az.degrees,
                    'distance': round(delta, 3),
                    'rise_time': format_time_str(rise_time, tz),
                    'transit_time': format_time_str(transit_time, tz),
                    'set_time': format_time_str(set_time, tz),
                    'type': 'asteroid',
                    'symbol': '⚸'
                }
                
                # Debug first asteroid
                if len(asteroid_list) == 0:
                    print(f"DEBUG First asteroid: {asteroid_data['name']}, distance={asteroid_data['distance']}, rise={asteroid_data['rise_time']}")
                
                asteroid_list.append(asteroid_data)
                
            except Exception as e:
                # Log error for debugging (but continue processing other asteroids)
                # print(f"Error processing asteroid {row.get('designation', 'unknown')}: {e}")
                continue
        
        # Cache the results for future requests
        if use_cache:
            from cache_utils import normalize_location, location_key, time_bucket_utc
            lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
            loc_key = location_key(lat_norm, lon_norm, elev_norm)
            time_bucket = time_bucket_utc(current_dt, ASTEROID_CACHE_BUCKET_HOURS)
            
            try:
                from db_utils import store_asteroid_positions
                # Use 0 as representative ID (all asteroids share same location/time)
                representative_id = 0
                store_asteroid_positions(
                    representative_id, loc_key, time_bucket,
                    lat, lon, elevation, asteroid_list
                )
            except Exception as e:
                print(f"Failed to cache asteroid positions: {e}")
        
        return asteroid_list
    else:
        # No data available
        return []

    # --- Calculations ---
    # Use simulated time if provided; else current UTC
    dt_utc = current_dt or datetime.now(timezone.utc)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    t = ts.from_datetime(dt_utc)
    topos = Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=elevation)
    observer = eph['earth'] + topos
    sun = eph['sun']
    
    try:
        df.dropna(subset=['magnitude_H'], inplace=True)
        candidates_df = df[df['magnitude_H'] < MAX_ABSOLUTE_MAGNITUDE].copy()
        print(f"Found {len(candidates_df)} candidates with H < {MAX_ABSOLUTE_MAGNITUDE}")

        apparent_magnitudes = []
        for index, row in candidates_df.iterrows():
            try:
                orbit = mpc.mpcorb_orbit(row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)
                # Build barycentric target (explicit center check)
                center_code = int(getattr(orbit, 'center', 10))
                target = (sun + orbit) if center_code != 0 else orbit

                astrometric = observer.at(t).observe(target)
                # Distances
                delta = astrometric.distance().au
                sun_vec = sun.at(t).observe(target)
                r = sun_vec.distance().au
                phase_angle = astrometric.phase_angle(sun).degrees
                # Compute apparent magnitude using IAU H-G model
                apparent_mag = asteroid_apparent_magnitude(
                    H=row['magnitude_H'], G=row['magnitude_G'], r=r, delta=delta, phase_angle_deg=phase_angle
                )
                apparent_magnitudes.append(apparent_mag)
            except Exception as e:
                print(f"  - Error processing {row.get('designation', 'N/A')}: {e}")
                apparent_magnitudes.append(float('inf'))
        
        candidates_df['apparent_magnitude'] = apparent_magnitudes
        # Cache with mag 20.0 to include all asteroids, filtering happens in API route
        bright_df = candidates_df[candidates_df['apparent_magnitude'] <= 20.0].sort_values('apparent_magnitude')
        top_df = bright_df.head(MAX_ASTEROIDS)
        print(f"Found {len(top_df)} asteroids with apparent mag <= 20.0 (user filter: {max_magnitude})")

        asteroid_list = []
        events_computed = 0
        for index, row in top_df.iterrows():
            try:
                orbit = mpc.mpcorb_orbit(row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)
                # Build barycentric target (explicit center check)
                center_code = int(getattr(orbit, 'center', 10))
                target = (sun + orbit) if center_code != 0 else orbit
                astrometric = observer.at(t).observe(target)
                apparent = astrometric.apparent()
                ra, dec, distance = apparent.radec()
                alt, az, _ = apparent.altaz()

                # Event times limited to reduce CPU
                rise_time, set_time, transit_time = None, None, None
                if events_computed < ASTEROIDS_EVENTS_MAX:
                    # Start/end window anchored at simulated day's UTC midnight
                    start_time = ts.utc(t.utc_datetime().replace(hour=0, minute=0, second=0, microsecond=0))
                    end_time = ts.utc(start_time.utc_datetime() + timedelta(days=2))
                    rise_set_func = almanac.risings_and_settings(eph, target, topos)
                    times, events = almanac.find_discrete(start_time, end_time, rise_set_func)
                    
                    for ti, event in zip(times, events):
                        if event == 1 and rise_time is None: rise_time = ti.utc_datetime()
                        elif event == 0 and set_time is None: set_time = ti.utc_datetime()
                    # Bestimme die nächste Nacht (Rise->Set) nach dt_utc als Fenster für die obere Kulmination
                    night_start_utc, night_end_utc = None, None
                    last_rise_utc = None
                    for ti_rs, ev_rs in zip(times, events):
                        ev_dt_utc = ti_rs.utc_datetime().replace(tzinfo=timezone.utc)
                        if ev_rs == 1:  # rise
                            last_rise_utc = ev_dt_utc
                        elif ev_rs == 0 and last_rise_utc is not None:  # set paired with last rise
                            # wähle das erste Rise->Set Paar, dessen Set in der Zukunft liegt
                            if ev_dt_utc >= (dt_utc if dt_utc.tzinfo else dt_utc.replace(tzinfo=timezone.utc)):
                                night_start_utc, night_end_utc = last_rise_utc, ev_dt_utc
                                break
                    if night_start_utc is None or night_end_utc is None:
                        # Fallback: benutze die zuerst gefundenen rise/set Zeiten, wenn vorhanden
                        night_start_utc, night_end_utc = rise_time, set_time
                    
                    f = almanac.meridian_transits(eph, target, topos)
                    t_times, t_events = almanac.find_discrete(start_time, end_time, f)
                    # Wähle die nächste obere Kulmination innerhalb des Nachtfensters (UTC-basiert)
                    chosen_time_utc = None
                    if len(t_times):
                        now_utc = dt_utc if dt_utc.tzinfo is not None else dt_utc.replace(tzinfo=timezone.utc)
                        candidates = []
                        for ti, ev in zip(t_times, t_events):
                            utc_dt = ti.utc_datetime().replace(tzinfo=timezone.utc)
                            # Altitude am Transit-Zeitpunkt bestimmen (höher = obere Kulmination)
                            try:
                                alt_deg = observer.at(ti).observe(target).apparent().altaz()[0].degrees
                            except Exception:
                                alt_deg = float('-inf')
                            candidates.append((utc_dt, alt_deg, int(ev)))
                        # Filtere auf das Nachtfenster (falls vorhanden)
                        if night_start_utc is not None and night_end_utc is not None:
                            pool = [c for c in candidates if c[0] >= night_start_utc and c[0] <= night_end_utc]
                        else:
                            # Bevorzuge zukünftige Ereignisse
                            pool = [c for c in candidates if c[0] >= now_utc]
                            if not pool:
                                pool = candidates
                        if pool:
                            pool.sort(key=lambda x: (-x[1], x[0]))
                            chosen_time_utc = pool[0][0]
                    transit_time = chosen_time_utc
                    events_computed += 1

                asteroid_list.append({
                    "name": row['designation'], "number": str(row.name),
                    "magnitude": round(float(row['apparent_magnitude']), 1),
                    "ra": ra.hours * 15.0, "dec": dec.degrees,
                    "altitude": alt.degrees, "azimuth": az.degrees,
                    "distance": round(distance.au, 3), "rise_time": format_time(rise_time, tz),
                    "set_time": format_time(set_time, tz), "transit_time": format_time(transit_time, tz),
                    "type": "asteroid", "symbol": "⚸"  # Unicode U+26B8 (Asteroid)
                })
            except Exception as e:
                print(f"Error in final processing for {row['designation']}: {e}")
                continue
        
        return asteroid_list

    except Exception as e:
        print(f"An unexpected error occurred during asteroid calculation: {e}")
        return []
