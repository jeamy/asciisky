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
from skyfield.data import mpc
import math

# Konstanten für Cache-Dateien
BRIGHT_ASTEROID_CACHE_FILE = 'cache/bright_asteroid_cache.pkl'
COMET_CACHE_FILE = 'cache/comet_cache.pkl'
MPCORB_FILE = 'cache/MPCORB.DAT.gz'
MPCORB_URL = 'https://www.minorplanetcenter.net/iau/MPCORB/MPCORB.DAT.gz'
MAX_ASTEROIDS = 5000
MAX_ASTEROIDS_MAGNITUDE = 8.0

# Cache-Gültigkeitsdauer in Stunden
CACHE_VALIDITY_HOURS = 6

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

def load_bright_asteroids(loader, ts, eph, observer_location, max_magnitude=MAX_ASTEROIDS_MAGNITUDE, use_cache=True):
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
            
            # Begrenze die Anzahl der zu ladenden Asteroiden
            max_asteroids = MAX_ASTEROIDS
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
                        
                        # Absolute Magnitude (H) - Spalten 9-13 laut MPC-Format
                        try:
                            h_mag_str = line[8:13].strip()
                            if h_mag_str:
                                h_mag = float(h_mag_str)
                            else:
                                print(f"Skipping asteroid {name or number}: Missing H magnitude")
                                continue
                        except (ValueError, IndexError) as e:
                            print(f"Skipping asteroid {name or number}: Invalid H magnitude - {str(e)}")
                            continue
                        
                        # Nur Asteroiden mit einer Magnitude unter einem bestimmten Wert laden
                        if h_mag > MAX_ASTEROIDS_MAGNITUDE:  # Nur die hellsten Asteroiden laden
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
                        # Konvertiere in AU (Astronomische Einheiten) und runde auf 3 Dezimalstellen
                        distance_au = round(np.sqrt(xeq**2 + yeq**2 + zeq**2), 3)
                        
                        # Berechne die scheinbare Magnitude
                        # Korrekte Formel: m = H + 5*log10(r*d) - 2.5*log10((1-G)*phi1 + G*phi2)
                        # Vereinfachte Version: m = H + 5*log10(r*d)
                        # Wobei r = Entfernung zum Asteroiden, d = Entfernung zur Sonne
                        # G ist der Steigungsparameter (typischerweise 0.15)
                        # Für eine bessere Approximation berücksichtigen wir die Phasenwinkel-Effekte
                        
                        # Vereinfachte Berechnung der scheinbaren Magnitude
                        phase_angle_correction = 0.0  # Vereinfachte Annahme
                        apparent_magnitude = round(h_mag + 5 * np.log10(distance_au) - phase_angle_correction, 1)
                        
                        # Berechne Aufgangs-, Untergangs- und Transitzeiten
                        # Vereinfachte Berechnung
                        # t.gmst ist ein numerischer Wert in Stunden, kein Objekt mit hours-Attribut
                        hour_angle = (t.gmst * 15 - ra_deg) % 360
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
                        
                        # Berechne Aufgangs- und Untergangszeiten basierend auf der Deklination
                        # Für Objekte nahe dem Äquator ist die Zeit vom Aufgang bis zum Transit etwa 6 Stunden
                        # Für Objekte weiter nördlich oder südlich variiert diese Zeit
                        
                        # Berechne den Kosinus des Stundenwinkels beim Aufgang/Untergang
                        lat_rad = lat * math.pi / 180.0
                        cos_ha = -math.tan(lat_rad) * math.tan(dec_rad)
                        
                        # Begrenze den Wert auf [-1, 1] für den Fall, dass das Objekt zirkumpolar ist
                        cos_ha = max(-1.0, min(1.0, cos_ha))
                        
                        # Berechne den Stundenwinkel in Stunden
                        ha_hours_at_horizon = math.acos(cos_ha) * 12.0 / math.pi
                        
                        # Berechne Aufgangs- und Untergangszeiten
                        rise_time = transit_time - timedelta(hours=ha_hours_at_horizon)
                        set_time = transit_time + timedelta(hours=ha_hours_at_horizon)
                        
                        # Berechne Altitude und Azimuth für den Beobachterstandort
                        # Konvertiere RA/Dec zu Altitude/Azimuth
                        
                        # Konvertiere RA/Dec zu Stunden/Winkel
                        ra_hours = ra_deg / 15.0
                        dec_rad = dec_deg * math.pi / 180.0
                        
                        # Berechne den Stundenwinkel direkt ohne GMST
                        # Vereinfachte Berechnung des Stundenwinkels
                        current_time = t.utc_datetime()
                        hours_since_midnight = current_time.hour + current_time.minute/60.0 + current_time.second/3600.0
                        local_sidereal_time = (hours_since_midnight + lon/15.0) % 24
                        ha_hours = (local_sidereal_time - ra_hours) % 24
                        if ha_hours > 12:
                            ha_hours -= 24
                        ha_deg = ha_hours * 15.0
                        ha_rad = ha_deg * math.pi / 180.0
                        
                        # Konvertiere Breite zu Radiant
                        lat_rad = lat * math.pi / 180.0
                        
                        # Berechne Altitude
                        sin_alt = math.sin(dec_rad) * math.sin(lat_rad) + math.cos(dec_rad) * math.cos(lat_rad) * math.cos(ha_rad)
                        alt_rad = math.asin(sin_alt)
                        alt_deg = alt_rad * 180.0 / math.pi
                        
                        # Berechne Azimuth
                        cos_az = (math.sin(dec_rad) - math.sin(alt_rad) * math.sin(lat_rad)) / (math.cos(alt_rad) * math.cos(lat_rad))
                        cos_az = max(-1.0, min(1.0, cos_az))  # Begrenze auf [-1, 1]
                        az_rad = math.acos(cos_az)
                        
                        # Korrigiere den Quadranten für Azimuth
                        if math.sin(ha_rad) >= 0:
                            az_rad = 2 * math.pi - az_rad
                        
                        az_deg = az_rad * 180.0 / math.pi
                        
                        # Füge den Asteroiden zur Liste hinzu
                        # Formatiere die Zeiten für die Anzeige
                        # Format: "HH:MM Uhr" für die lokale Zeit
                        def format_time(dt):
                            # Konvertiere zu lokalem Zeitformat ohne Zeitzone und ISO-Format
                            local_time = dt.astimezone()
                            return f"{local_time.hour:02d}:{local_time.minute:02d} Uhr"
                        
                        asteroid_data = {
                            "name": name if name else f"Asteroid {number}",
                            "number": number,
                            "magnitude": apparent_magnitude,
                            "ra": ra_deg,
                            "dec": dec_deg,
                            "altitude": alt_deg,  # Höhe über dem Horizont
                            "azimuth": az_deg,    # Azimut (0=Nord, 90=Ost, 180=Süd, 270=West)
                            "distance": distance_au,
                            "rise_time": format_time(rise_time),
                            "set_time": format_time(set_time),
                            "transit_time": format_time(transit_time),
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
