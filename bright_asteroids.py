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
# Maximale absolute Magnitude für Asteroiden (kleinere Werte = hellere Objekte)
MAX_ASTEROIDS_MAGNITUDE = 8.0
# Gravitationskonstante der Sonne für Skyfield
GM_SUN = 1.32712440041e20

# Cache-Gültigkeitsdauer in Stunden
CACHE_VALIDITY_HOURS = 6

# Ensure cache directory exists
os.makedirs("cache", exist_ok=True)

def format_time(dt):
    """
    Formatiert ein datetime-Objekt als lokale Zeit im Format 'HH:MM Uhr'
    Gibt None zurück, wenn dt None ist
    """
    if dt is None:
        return None
    
    # Konvertiere zu lokalem Zeitformat
    local_time = dt.astimezone()
    return f"{local_time.hour:02d}:{local_time.minute:02d} Uhr"

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
                        
                        # Verwende Skyfield für präzise Berechnungen der Asteroiden-Position
                        try:
                            # Erstelle ein Orbit-Objekt mit Skyfield für den Asteroiden
                            asteroid_data = {
                                'designation': name,
                                'name': name,
                                'H': h_mag,
                                'G': 0.15,  # Standardwert für den Steigungsparameter
                                'epoch': epoch,
                                'M': mean_anomaly,
                                'peri': argument_of_perihelion,
                                'node': longitude_of_ascending_node,
                                'incl': inclination,
                                'e': eccentricity,
                                'a': semimajor_axis,
                                'epoch_year': 2000.0  # J2000.0 Epoche
                            }
                            
                            # Erstelle ein Orbit-Objekt mit Skyfield
                            asteroid_orbit = mpc.mpcorb_orbit(asteroid_data, ts, GM_SUN)
                            
                            # Berechne die Position des Asteroiden relativ zur Sonne
                            sun = eph['sun']
                            asteroid = sun + asteroid_orbit
                            
                            # Beobachte den Asteroiden von der Erde aus
                            # Berücksichtigt automatisch die Lichtlaufzeit
                            astrometric = observer.at(t).observe(asteroid)
                            
                            # Berechne die scheinbare Position (mit Aberration und Lichtablenkung)
                            apparent = astrometric.apparent()
                            
                            # Berechne Rektaszension und Deklination
                            ra, dec, distance = apparent.radec()
                            ra_deg = ra.hours * 15.0  # Umrechnung von Stunden in Grad
                            dec_deg = dec.degrees
                            
                            # Berechne die Entfernung in AU und runde auf 3 Dezimalstellen
                            distance_au = round(distance.au, 3)
                            
                            # Berechne die scheinbare Helligkeit
                            # Korrekte Formel für scheinbare Magnitude:
                            # m = H + 5*log10(r*d) - 2.5*log10((1-G)*phi1 + G*phi2)
                            
                            # Berechne die Entfernung zur Sonne
                            sun_distance = np.sqrt(asteroid_orbit.xyz_au(t)[0]**2 + 
                                                  asteroid_orbit.xyz_au(t)[1]**2 + 
                                                  asteroid_orbit.xyz_au(t)[2]**2)
                            
                            # Berechne den Phasenwinkel (Winkel Sonne-Asteroid-Erde)
                            earth_pos = earth.at(t).position.au
                            asteroid_pos = asteroid.at(t).position.au
                            sun_pos = sun.at(t).position.au
                            
                            # Vektoren berechnen
                            earth_to_asteroid = asteroid_pos - earth_pos
                            sun_to_asteroid = asteroid_pos - sun_pos
                            
                            # Normalisieren
                            earth_to_asteroid_norm = earth_to_asteroid / np.linalg.norm(earth_to_asteroid)
                            sun_to_asteroid_norm = sun_to_asteroid / np.linalg.norm(sun_to_asteroid)
                            
                            # Phasenwinkel berechnen
                            phase_angle = np.arccos(np.dot(earth_to_asteroid_norm, sun_to_asteroid_norm))
                            phase_angle_deg = phase_angle * 180.0 / np.pi
                            
                            # Berechne die Phasenfunktionen
                            G = 0.15  # Standardwert für den Steigungsparameter
                            phi1 = np.exp(-3.33 * np.tan(phase_angle/2)**0.63)
                            phi2 = np.exp(-1.87 * np.tan(phase_angle/2)**1.22)
                            
                            # Berechne die scheinbare Magnitude
                            apparent_magnitude = round(h_mag + 5 * np.log10(distance_au * sun_distance) - 
                                                      2.5 * np.log10((1-G)*phi1 + G*phi2), 1)
                        except Exception as e:
                            print(f"Fehler bei der Berechnung für Asteroid {name}: {str(e)}")
                            # Setze Standardwerte bei Fehler
                            ra_deg = 0
                            dec_deg = 0
                            distance_au = 0
                            apparent_magnitude = 99.9  # Sehr dunkel (nicht sichtbar)
                        
                            # Berechne Aufgangs-, Untergangs- und Transitzeiten mit Skyfield
                            # Erstelle ein Zeitfenster für die Berechnung (24 Stunden)
                            start_time = t.utc_datetime()
                            start = ts.utc(start_time.year, start_time.month, start_time.day, 
                                          start_time.hour, start_time.minute, start_time.second)
                            end = ts.utc(start_time.year, start_time.month, start_time.day + 1, 
                                        start_time.hour, start_time.minute, start_time.second)
                            
                            # Erstelle eine Zeitreihe mit 5-Minuten-Intervallen
                            time_range = ts.utc(start.utc_datetime() + 
                                              np.arange(0, 24*60, 5) * timedelta(minutes=1))
                            
                            # Berechne die Höhe des Asteroiden über dem Horizont für jede Zeit
                            altitude_at_times = []
                            for time_i in time_range:
                                pos = observer.at(time_i).observe(asteroid).apparent()
                                alt, az, _ = pos.altaz()
                                altitude_at_times.append((time_i, alt.degrees))
                            
                            # Finde Aufgang, Untergang und Transit
                            rise_time = None
                            set_time = None
                            transit_time = None
                            max_alt = -90
                            
                            # Suche nach Aufgang (Übergang von unter zu über dem Horizont)
                            for i in range(1, len(altitude_at_times)):
                                prev_alt = altitude_at_times[i-1][1]
                                curr_alt = altitude_at_times[i][1]
                                
                                # Aufgang: von unter zu über dem Horizont
                                if prev_alt < 0 and curr_alt >= 0:
                                    # Lineare Interpolation für genauere Zeit
                                    fraction = -prev_alt / (curr_alt - prev_alt)
                                    minutes_diff = 5 * fraction
                                    rise_time = altitude_at_times[i-1][0].utc_datetime() + timedelta(minutes=minutes_diff)
                                
                                # Untergang: von über zu unter dem Horizont
                                if prev_alt >= 0 and curr_alt < 0:
                                    # Lineare Interpolation für genauere Zeit
                                    fraction = prev_alt / (prev_alt - curr_alt)
                                    minutes_diff = 5 * fraction
                                    set_time = altitude_at_times[i-1][0].utc_datetime() + timedelta(minutes=minutes_diff)
                                
                                # Höchststand: höchste Altitude
                                if curr_alt > max_alt:
                                    max_alt = curr_alt
                                    transit_time = altitude_at_times[i][0].utc_datetime()
                            
                            # Fallback für zirkumpolare Objekte oder Objekte, die nie aufgehen
                            if rise_time is None:
                                if max_alt >= 0:  # Zirkumpolar (immer über dem Horizont)
                                    rise_time = start.utc_datetime()
                                else:  # Nie über dem Horizont
                                    rise_time = None
                            
                            if set_time is None:
                                if max_alt >= 0:  # Zirkumpolar (immer über dem Horizont)
                                    set_time = end.utc_datetime()
                                else:  # Nie über dem Horizont
                                    set_time = None
                            
                            if transit_time is None:
                                transit_time = start.utc_datetime() + timedelta(hours=12)  # Fallback
                                
                            # Berechne Altitude und Azimuth mit Skyfield
                            try:
                                alt, az, _ = apparent.altaz()
                                alt_deg = alt.degrees
                                az_deg = az.degrees
                            except Exception as e:
                                print(f"Fehler bei der Berechnung von Alt/Az für Asteroid {name}: {str(e)}")
                                alt_deg = 0
                                az_deg = 0
                        
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
