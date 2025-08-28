"""
Module for calculating positions of bright minor planets (asteroids)
"""
from skyfield.api import Topos, load
from skyfield import almanac
import numpy as np
import os
import pickle
from datetime import datetime, timedelta
import gzip
import urllib.request
import urllib.request
from skyfield.data import mpc

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
    Lädt die MPCORB.DAT.gz-Datei herunter, wenn sie nicht existiert
    """
    if not os.path.exists(MPCORB_FILE):
        print(f"Downloading MPCORB.DAT.gz from {MPCORB_URL}...")
        try:
            os.makedirs(os.path.dirname(MPCORB_FILE), exist_ok=True)
            urllib.request.urlretrieve(MPCORB_URL, MPCORB_FILE)
            print(f"Downloaded MPCORB.DAT.gz to {MPCORB_FILE}")
            return True
        except Exception as e:
            print(f"Error downloading MPCORB.DAT.gz: {e}")
            return False
    return True

def load_bright_asteroids(loader, ts, eph, observer_location, max_magnitude=11.0, use_cache=True):
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
        print("No cache file found or cache disabled")
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
                return []
        
        try:
            print(f"Loading asteroid data from {MPCORB_FILE}...")
            
            # Begrenze die Anzahl der zu ladenden Asteroiden
            max_asteroids = 100
            asteroid_list = []
            count = 0
            
            with gzip.open(MPCORB_FILE, 'rt') as f:
                # Überspringe den Header
                for line in f:
                    if line.startswith('00001'):
                        break
                
                # Parse die Daten für die hellsten Asteroiden
                for line in f:
                    if count >= max_asteroids:
                        break
                    
                    try:
                        # Parse die Zeile nach dem MPC-Format
                        number = line[0:7].strip()  # Asteroid-Nummer
                        name = line[166:194].strip()  # Name des Asteroiden
                        
                        # Wenn kein Name vorhanden ist, verwende die provisorische Bezeichnung
                        if not name:
                            name = line[8:18].strip()
                        
                        # Absolute Magnitude (H)
                        h_mag = float(line[8:13].strip())
                        
                        # Nur Asteroiden mit einer Magnitude unter einem bestimmten Wert laden
                        if h_mag > 12.0:  # Nur die hellsten Asteroiden laden
                            continue
                        
                        # Parse die Bahnelemente
                        epoch = line[20:25].strip()
                        mean_anomaly = float(line[26:35].strip())
                        argument_of_perihelion = float(line[37:46].strip())
                        longitude_of_ascending_node = float(line[48:57].strip())
                        inclination = float(line[59:68].strip())
                        eccentricity = float(line[70:79].strip())
                        semimajor_axis = float(line[92:103].strip())
                        
                        # Berechne die Position mit vereinfachten Annahmen
                        # Dies ist eine Approximation, da die vollständige Berechnung komplex ist
                        
                        # Berechne die mittlere Anomalie zum aktuellen Zeitpunkt
                        # Vereinfachte Annahme: Epoche ist J2000.0
                        days_since_j2000 = t.tt - 2451545.0
                        mean_motion = 0.9856076686 / (semimajor_axis ** 1.5)  # Grad pro Tag
                        current_mean_anomaly = (mean_anomaly + mean_motion * days_since_j2000) % 360
                        
                        # Vereinfachte Berechnung der Position in der Bahnebene
                        # Wir verwenden die mittlere Anomalie als Näherung für die wahre Anomalie
                        true_anomaly = current_mean_anomaly * np.pi / 180.0
                        
                        # Berechne die Position in der Bahnebene
                        r = semimajor_axis * (1 - eccentricity**2) / (1 + eccentricity * np.cos(true_anomaly))
                        
                        # Berechne die Position im ekliptischen Koordinatensystem
                        x = r * (np.cos(longitude_of_ascending_node * np.pi/180) * np.cos(true_anomaly + argument_of_perihelion * np.pi/180) - 
                              np.sin(longitude_of_ascending_node * np.pi/180) * np.sin(true_anomaly + argument_of_perihelion * np.pi/180) * np.cos(inclination * np.pi/180))
                        y = r * (np.sin(longitude_of_ascending_node * np.pi/180) * np.cos(true_anomaly + argument_of_perihelion * np.pi/180) + 
                              np.cos(longitude_of_ascending_node * np.pi/180) * np.sin(true_anomaly + argument_of_perihelion * np.pi/180) * np.cos(inclination * np.pi/180))
                        z = r * np.sin(true_anomaly + argument_of_perihelion * np.pi/180) * np.sin(inclination * np.pi/180)
                        
                        # Konvertiere in äquatoriale Koordinaten
                        # Vereinfachte Annahme: Ekliptik-Neigung ist 23.4 Grad
                        epsilon = 23.4 * np.pi / 180.0
                        xeq = x
                        yeq = y * np.cos(epsilon) - z * np.sin(epsilon)
                        zeq = y * np.sin(epsilon) + z * np.cos(epsilon)
                        
                        # Berechne Rektaszension und Deklination
                        ra_rad = np.arctan2(yeq, xeq)
                        if ra_rad < 0:
                            ra_rad += 2 * np.pi
                        ra_deg = ra_rad * 180.0 / np.pi
                        
                        dec_rad = np.arcsin(zeq / np.sqrt(xeq**2 + yeq**2 + zeq**2))
                        dec_deg = dec_rad * 180.0 / np.pi
                        
                        # Berechne die Entfernung
                        distance_au = np.sqrt(xeq**2 + yeq**2 + zeq**2)
                        
                        # Berechne die scheinbare Magnitude
                        apparent_magnitude = h_mag + 5 * np.log10(distance_au)
                        
                        # Berechne Aufgangs-, Untergangs- und Transitzeiten
                        # Vereinfachte Berechnung
                        hour_angle = (t.gmst.hours * 15 - ra_deg) % 360
                        if hour_angle > 180:
                            hour_angle -= 360
                        
                        # Berechne die Stunden bis zum Transit
                        hours_to_transit = -hour_angle / 15
                        if hours_to_transit < -12:
                            hours_to_transit += 24
                        if hours_to_transit > 12:
                            hours_to_transit -= 24
                        
                        # Berechne die Transit-, Aufgangs- und Untergangszeiten
                        transit_time = t.utc_datetime() + timedelta(hours=hours_to_transit)
                        rise_time = transit_time - timedelta(hours=6)
                        set_time = transit_time + timedelta(hours=6)
                        
                        # Füge den Asteroiden zur Liste hinzu
                        asteroid_data = {
                            "name": name if name else f"Asteroid {number}",
                            "number": number,
                            "magnitude": apparent_magnitude,
                            "ra": ra_deg,
                            "dec": dec_deg,
                            "distance": distance_au,
                            "rise_time": rise_time.isoformat(),
                            "set_time": set_time.isoformat(),
                            "transit_time": transit_time.isoformat(),
                            "type": "asteroid"
                        }
                        
                        asteroid_list.append(asteroid_data)
                        count += 1
                        
                        if count % 10 == 0:
                            print(f"Processed {count} asteroids...")
                        
                    except Exception as e:
                        print(f"Error parsing asteroid line: {e}")
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
