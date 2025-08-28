"""
Module for calculating positions of bright minor planets (asteroids)
"""
from skyfield.api import Topos, load
from skyfield import almanac
import numpy as np
import os
import pickle
from datetime import datetime, timedelta, timezone
import gzip
import urllib.request
from skyfield.data import mpc
import math

# Konstanten für Cache-Dateien
ASTEROID_CACHE_FILE = 'cache/asteroid_cache.pkl'
BRIGHT_ASTEROID_CACHE_FILE = 'cache/bright_asteroid_cache.pkl'
COMET_CACHE_FILE = 'cache/comet_cache.pkl'
MPCORB_FILE = 'cache/MPCORB.DAT.gz'
MPCORB_URL = 'https://www.minorplanetcenter.net/iau/MPCORB/MPCORB.DAT.gz'

# Cache-Gültigkeitsdauer in Stunden
CACHE_VALIDITY_HOURS = 24

# Ensure cache directory exists
os.makedirs("cache", exist_ok=True)

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

def load_bright_asteroids(loader, ts, eph, observer_location, max_magnitude=12.0, use_cache=True):
    """
    Load and calculate positions, magnitudes, and rise/set times of the brightest minor planets
    
    Args:
        loader: Skyfield loader
        ts: Skyfield timescale
        eph: Skyfield ephemeris
        observer_location: Skyfield observer location (earth + topos) or lat/lon/elevation parameters
        max_magnitude: Maximum magnitude to include (default: 11.0)
        use_cache: Whether to use cached data if available (default: True)
        
    Returns:
        List of dictionaries with asteroid data
    """
    # Extrahiere die Standortdaten
    if isinstance(observer_location, dict):
        # Wenn ein Dictionary übergeben wurde, extrahiere die Werte
        lat = observer_location.get('latitude', 0.0)
        lon = observer_location.get('longitude', 0.0)
        elevation = observer_location.get('elevation', 0.0)
    else:
        # Wenn ein Skyfield-Objekt übergeben wurde, extrahiere die Werte
        try:
            lat = observer_location.latitude.degrees
            lon = observer_location.longitude.degrees
            elevation = observer_location.elevation.m
        except AttributeError:
            # Fallback zu Standardwerten
            print("Warning: Could not extract location data from observer_location")
            lat = 0.0
            lon = 0.0
            elevation = 0.0
    
    print(f"Getting asteroids with magnitude <= {max_magnitude} at lat={lat}, lon={lon}, elevation={elevation}.")
    
    # Überprüfe, ob ein gültiger Cache vorhanden ist
    if use_cache and os.path.exists(BRIGHT_ASTEROID_CACHE_FILE):
        # Überprüfe das Alter des Caches
        cache_time = datetime.fromtimestamp(os.path.getmtime(BRIGHT_ASTEROID_CACHE_FILE))
        now = datetime.now()
        cache_age = now - cache_time
        
        # Wenn der Cache älter als CACHE_VALIDITY_HOURS ist, verwende ihn nicht
        if cache_age.total_seconds() > CACHE_VALIDITY_HOURS * 3600:
            print(f"Cache is too old ({cache_age.total_seconds() / 3600:.1f} hours), not using it")
            use_cache = False
        else:
            print(f"Cache is valid (age: {cache_age.total_seconds() / 3600:.1f} hours)")
    else:
        print("No cache file found or cache disabled")
        use_cache = False
        
    # Wenn MPCORB_FILE nicht existiert, erzwinge das Herunterladen, unabhängig vom Cache
    if not os.path.exists(MPCORB_FILE):
        print(f"MPCORB.DAT.gz file not found at {MPCORB_FILE}, forcing download")
        use_cache = False
    
    asteroid_list = []
    
    if use_cache:
        try:
            with open(BRIGHT_ASTEROID_CACHE_FILE, 'rb') as f:
                cached_data = pickle.load(f)
                # Überprüfe, ob die Daten im richtigen Format sind
                if isinstance(cached_data, list):
                    print(f"Loaded {len(cached_data)} asteroids from cache")
                    asteroid_list = cached_data
                else:
                    print(f"Cache format is invalid, expected list but got {type(cached_data)}")
                    use_cache = False
                    asteroid_list = []
        except Exception as e:
            print(f"Error loading from cache: {e}")
            use_cache = False
            asteroid_list = []
    
    if not use_cache:
        # Lade echte Asteroiden-Daten
        t = ts.now()
        earth = eph['earth']
        sun = eph['sun']
        
        # Erstelle ein Topos-Objekt für den Beobachterstandort
        topos = Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=elevation)
        observer = earth + topos
        
        # Überprüfe, ob die MPCORB.DAT.gz-Datei existiert oder lade sie herunter
        if not os.path.exists(MPCORB_FILE):
            print(f"MPCORB.DAT.gz file not found at {MPCORB_FILE}")
            if not download_mpcorb_file():
                print("Failed to download MPCORB.DAT.gz")
                # Keine Demo-Daten verwenden, stattdessen leere Liste zurückgeben
                return []
        
        try:
            print(f"Loading asteroid data from {MPCORB_FILE}...")
            # Begrenze die Anzahl der zu verarbeitenden Asteroiden
            max_asteroids = 100
            asteroid_list = []
            count = 0

            # Lade das MPCORB-DataFrame mit Skyfield – gzipped Datei im Binärmodus öffnen (bytes)
            with gzip.open(MPCORB_FILE, 'rb') as f:
                df = mpc.load_mpcorb_dataframe(f)

            # Filtere gültige Einträge mit H und sortiere nach Helligkeit (kleiner = heller)
            if 'H' in df.columns:
                df = df.dropna(subset=['H']).sort_values(by='H')
            else:
                print("MPCORB dataframe missing 'H' column; returning empty list")
                return []

            # Verarbeite die hellsten Einträge
            for idx, row in df.iterrows():
                if count >= max_asteroids:
                    break
                try:
                    # Skyfield-Orbit für das Objekt
                    asteroid_obj = mpc.mpcorb_orbit(row, ts, eph)

                    # Beobachtete Position und Alt/Az
                    apparent = observer.at(t).observe(asteroid_obj).apparent()
                    alt, az, distance = apparent.altaz()

                    # Distanzen in AU
                    delta_au = float(distance.au)
                    r_au = float(sun.at(t).observe(asteroid_obj).distance().au)

                    # Magnitude (vereinfachtes HG0-Modell ohne Phasenfunktion)
                    h_mag = float(row['H'])
                    apparent_magnitude = h_mag + 5.0 * np.log10(max(r_au * delta_au, 1e-6))

                    # Auf-/Untergang berechnen (lokale Zeiten HH:MM)
                    rise_time = None
                    set_time = None
                    transit_time = None
                    try:
                        f_rs = almanac.risings_and_settings(eph, asteroid_obj, topos)
                        # Suche vom heutigen 00:00 UTC bis +2 Tage
                        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                        t1 = ts.from_datetime(today_start)
                        t2 = ts.from_datetime(today_start + timedelta(days=2))
                        times, events = almanac.find_discrete(t1, t2, f_rs)
                        for time_i, event in zip(times, events):
                            local_time = time_i.utc_datetime().replace(tzinfo=timezone.utc).astimezone()
                            formatted = local_time.strftime('%H:%M')
                            if event == 1:
                                rise_time = formatted
                            else:
                                set_time = formatted
                        # Transit als Mitte zwischen Auf- und Untergang (falls beide vorhanden)
                        if rise_time and set_time:
                            now_local = datetime.now().astimezone()
                            today = now_local.date()
                            rt = datetime.strptime(rise_time, '%H:%M').replace(year=today.year, month=today.month, day=today.day, tzinfo=now_local.tzinfo)
                            st = datetime.strptime(set_time, '%H:%M').replace(year=today.year, month=today.month, day=today.day, tzinfo=now_local.tzinfo)
                            if st < rt:
                                st += timedelta(days=1)
                            transit_dt = rt + (st - rt) / 2
                            transit_time = transit_dt.strftime('%H:%M')
                    except Exception as e:
                        # Zeiten sind optional; bei Fehlern weiterfahren
                        pass

                    name = str(row.get('designation', '')).strip() or str(row.get('name', '')).strip() or f"Asteroid_{idx}"
                    asteroid_data = {
                        "name": name,
                        "symbol": "\u2022",
                        "type": "asteroid",
                        "magnitude": float(apparent_magnitude),
                        "altitude": float(alt.degrees),
                        "azimuth": float(az.degrees),
                        "distance": float(delta_au),
                        "rise_time": rise_time,
                        "set_time": set_time,
                        "transit_time": transit_time
                    }
                    asteroid_list.append(asteroid_data)
                    count += 1

                    if count % 10 == 0:
                        print(f"Processed {count} asteroids...")
                except Exception as e:
                    print(f"Error processing asteroid row {idx}: {e}")
                    continue

            print(f"Loaded {len(asteroid_list)} asteroids from MPCORB.DAT.gz")
        
        except Exception as e:
            print(f"Error loading asteroid data from MPCORB.DAT.gz: {e}")
            print("Failed to load asteroid data, returning empty list")
            return []
        
        # Cache speichern für zukünftige Verwendung
        if asteroid_list:
            try:
                with open(BRIGHT_ASTEROID_CACHE_FILE, 'wb') as f:
                    pickle.dump(asteroid_list, f)
                print(f"Saved {len(asteroid_list)} asteroids to cache")
            except Exception as e:
                print(f"Error saving to cache: {e}")
    
    # Filtere nach Magnitude
    if asteroid_list and isinstance(asteroid_list, list):
        filtered_asteroids = []
        for a in asteroid_list:
            if isinstance(a, dict) and "magnitude" in a:
                if a["magnitude"] <= max_magnitude:
                    filtered_asteroids.append(a)
        asteroid_list = filtered_asteroids
    
    print(f"Returning {len(asteroid_list)} bright asteroids")
    return asteroid_list
