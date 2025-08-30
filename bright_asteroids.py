"""
Module for calculating positions of bright minor planets (asteroids)
"""
from skyfield.api import Topos, load
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2
import pandas as pd
from skyfield import almanac
import numpy as np
import os
import pickle
from datetime import datetime, timedelta, timezone
import gzip
import urllib.request
from skyfield.data import mpc
import math
from types import SimpleNamespace

# Konstanten für Cache-Dateien
ASTEROID_DF_CACHE_FILE = 'cache/asteroids_dataframe.pkl'
BRIGHT_ASTEROID_CACHE_FILE = 'cache/bright_asteroid_cache.pkl'
COMET_CACHE_FILE = 'cache/comet_cache.pkl'
MPCORB_FILE = 'cache/MPCORB.DAT.gz'
MPCORB_URL = 'https://www.minorplanetcenter.net/iau/MPCORB/MPCORB.DAT.gz'
MAX_ASTEROIDS = 20000
# Magnitude thresholds (restored defaults)
# H-limit for prefiltering by absolute magnitude (smaller = brighter)
MAX_ABSOLUTE_MAGNITUDE = 12.0
# V-limit for final apparent magnitude filtering
MAX_APPARENT_MAGNITUDE = 10.0
# Backward-compatibility alias (legacy name used earlier in this module)
MAX_ASTEROIDS_MAGNITUDE = MAX_ABSOLUTE_MAGNITUDE
# Gravitationskonstante der Sonne für Skyfield
GM_SUN = 1.32712440041e20

# Cache-Gültigkeitsdauer in Stunden
CACHE_VALIDITY_HOURS = 6

# Ensure cache directory exists
os.makedirs("cache", exist_ok=True)

def format_time(dt):
    """
    Formatiert ein datetime-Objekt als lokale Zeit im Format 'HH:MM'.
    Gibt None zurück, wenn dt None ist.
    Hinweis: Die UI hängt die lokalisierte Stundenbezeichnung an (z.B. 'Uhr').
    """
    if dt is None:
        return None
    
    # Konvertiere zu lokaler Zeit und gebe nur HH:MM zurück (ohne 'Uhr')
    local_time = dt.astimezone()
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
        os.makedirs(os.path.dirname(MPCORB_FILE), exist_ok=True)
        
        # Datei herunterladen mit Fortschrittsanzeige
        print("Starting download...")
        with urllib.request.urlopen(MPCORB_URL) as response, open(MPCORB_FILE, 'wb') as out_file:
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
        if os.path.exists(MPCORB_FILE) and os.path.getsize(MPCORB_FILE) > 0:
            print(f"File size: {os.path.getsize(MPCORB_FILE) / (1024*1024):.1f} MB")
            return True
        else:
            print("Download failed: File is empty or does not exist")
            return False
    except Exception as e:
        print(f"Error downloading MPCORB.DAT.gz: {e}")
        return False
    return True

def load_bright_asteroids(loader, ts, eph, observer_location, max_magnitude=MAX_APPARENT_MAGNITUDE, use_cache=True):
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

    # Check for final cached asteroid list
    if use_cache and os.path.exists(BRIGHT_ASTEROID_CACHE_FILE):
        cache_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(BRIGHT_ASTEROID_CACHE_FILE))
        if cache_age.total_seconds() < CACHE_VALIDITY_HOURS * 3600:
            print(f"Loading {BRIGHT_ASTEROID_CACHE_FILE} (valid cache)")
            with open(BRIGHT_ASTEROID_CACHE_FILE, 'rb') as f:
                return pickle.load(f)
        else:
            print("Bright asteroid cache is too old.")

    # --- DataFrame Loading --- 
    df = None
    # Always re-parse for now to avoid complex cache validation logic
    force_reload = True 
    if not force_reload and os.path.exists(ASTEROID_DF_CACHE_FILE):
        print(f"Loading asteroid DataFrame from cache: {ASTEROID_DF_CACHE_FILE}")
        with open(ASTEROID_DF_CACHE_FILE, 'rb') as f:
            df = pickle.load(f)
    else:
        if not os.path.exists(MPCORB_FILE):
            if not download_mpcorb_file():
                return []
        try:
            print(f"Loading and parsing asteroid data from {MPCORB_FILE}...")
            with gzip.open(MPCORB_FILE, 'rb') as f:
                df = mpc.load_mpcorb_dataframe(f)
            
            df = df.iloc[:MAX_ASTEROIDS]
            
            # Convert types
            numeric_cols = [
                'magnitude_H', 'magnitude_G', 'mean_anomaly_degrees', 'argument_of_perihelion_degrees',
                'longitude_of_ascending_node_degrees', 'inclination_degrees', 'eccentricity',
                'mean_daily_motion_degrees', 'semimajor_axis_au'
            ]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df['magnitude_G'] = df['magnitude_G'].fillna(0.15)

            with open(ASTEROID_DF_CACHE_FILE, 'wb') as f:
                pickle.dump(df, f)
            print(f"Saved {len(df)} asteroids to DataFrame cache.")
        except Exception as e:
            print(f"Error processing MPCORB data: {e}")
            return []

    if df is None:
        return []

    # --- Calculations ---
    t = ts.now()
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
                astrometric = observer.at(t).observe(sun + orbit)
                # Distances
                delta = astrometric.distance().au
                sun_vec = sun.at(t).observe(sun + orbit)
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
        bright_df = candidates_df[candidates_df['apparent_magnitude'] <= max_magnitude].sort_values('apparent_magnitude')
        top_df = bright_df.head(MAX_ASTEROIDS)
        print(f"Found {len(top_df)} asteroids with apparent mag <= {max_magnitude}")

        asteroid_list = []
        for index, row in top_df.iterrows():
            try:
                orbit = mpc.mpcorb_orbit(row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)
                astrometric = observer.at(t).observe(sun + orbit)
                apparent = astrometric.apparent()
                ra, dec, distance = apparent.radec()
                alt, az, _ = apparent.altaz()

                start_time = ts.utc(t.utc_datetime().replace(hour=0, minute=0, second=0, microsecond=0))
                end_time = ts.utc(start_time.utc_datetime() + timedelta(days=2))
                rise_set_func = almanac.risings_and_settings(eph, sun + orbit, topos)
                times, events = almanac.find_discrete(start_time, end_time, rise_set_func)
                
                rise_time, set_time = None, None
                for ti, event in zip(times, events):
                    if event == 1 and rise_time is None: rise_time = ti.utc_datetime()
                    elif event == 0 and set_time is None: set_time = ti.utc_datetime()
                
                f = almanac.meridian_transits(eph, sun + orbit, topos)
                t_times, t_events = almanac.find_discrete(start_time, end_time, f)
                # Wähle die obere Kulmination (höchste Altitude) für den lokalen Tag
                chosen_local_dt = None
                if len(t_times):
                    now_local = datetime.now().astimezone()
                    today_local = now_local.date()
                    candidates = []
                    for ti, ev in zip(t_times, t_events):
                        # UTC -> lokal
                        utc_dt = ti.utc_datetime().replace(tzinfo=timezone.utc)
                        local_dt = utc_dt.astimezone()
                        # Altitude am Transit-Zeitpunkt bestimmen
                        try:
                            alt_deg = observer.at(ti).observe(sun + orbit).apparent().altaz()[0].degrees
                        except Exception:
                            alt_deg = float('-inf')
                        candidates.append((local_dt, alt_deg, int(ev)))
                    # Kandidaten auf heutigen lokalen Tag beschränken
                    today_candidates = [c for c in candidates if c[0].date() == today_local]
                    pool = today_candidates if today_candidates else candidates
                    if pool:
                        # Höchste Altitude zuerst, bei Gleichstand früheste Zeit
                        pool.sort(key=lambda x: (-x[1], x[0]))
                        chosen_local_dt = pool[0][0]
                transit_time = chosen_local_dt

                asteroid_list.append({
                    "name": row['designation'], "number": str(row.name),
                    "magnitude": round(float(row['apparent_magnitude']), 1),
                    "ra": ra.hours * 15.0, "dec": dec.degrees,
                    "altitude": alt.degrees, "azimuth": az.degrees,
                    "distance": round(distance.au, 3), "rise_time": format_time(rise_time),
                    "set_time": format_time(set_time), "transit_time": format_time(transit_time),
                    "type": "asteroid", "symbol": "•"
                })
            except Exception as e:
                print(f"Error in final processing for {row['designation']}: {e}")
                continue

        with open(BRIGHT_ASTEROID_CACHE_FILE, 'wb') as f:
            pickle.dump(asteroid_list, f)
        print(f"Saved {len(asteroid_list)} bright asteroids to cache.")
        
        return asteroid_list

    except Exception as e:
        print(f"An unexpected error occurred during asteroid calculation: {e}")
        return []
