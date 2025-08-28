"""
AsciiSky - ASCII Art Himmelsdarstellung
"""
import os
import json
import pickle
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from skyfield import almanac
from skyfield.api import load, wgs84, Star
from skyfield.data import hipparcos, mpc
from skyfield.magnitudelib import planetary_magnitude
from starlette.responses import FileResponse

import settings

# Initialisiere FastAPI
app = FastAPI(title="AsciiSky API", description="API für die ASCII-Darstellung des Sternenhimmels")

# Statische Dateien und Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# API-Endpunkte
API_ENDPOINT_CELESTIAL = "/api/celestial"
API_ENDPOINT_ASTEROIDS = "/api/asteroids"
API_ENDPOINT_COMETS = "/api/comets"

# Lade Skyfield-Daten
ts = load.timescale()
eph = load('de421.bsp')  # Ephemeris-Datei

# Cache für Asteroiden- und Kometendaten
asteroid_data_cache = None
comet_data_cache = None
asteroid_cache_timestamp = None
comet_cache_timestamp = None

# Cache-Dateien
ASTEROID_CACHE_FILE = "cache/asteroid_cache.pkl"
COMET_CACHE_FILE = "cache/comet_cache.pkl"

# Stellen Sie sicher, dass das Cache-Verzeichnis existiert
os.makedirs("cache", exist_ok=True)

# Planeten und andere Himmelskörper
CELESTIAL_BODIES = {
    'sun': eph['sun'],
    'moon': eph['moon'],
    'mercury': eph['mercury'],
    'venus': eph['venus'],
    'mars': eph['mars'],
    'jupiter': eph['jupiter barycenter'],
    'saturn': eph['saturn barycenter'],
    'uranus': eph['uranus barycenter'],
    'neptune': eph['neptune barycenter']
}

# Symbole für Himmelskörper
BODY_SYMBOLS = {
    'sun': '☀️',
    'moon': '🌙',
    'mercury': '☿',
    'venus': '♀',
    'mars': '♂',
    'jupiter': '♃',
    'saturn': '♄',
    'uranus': '♅',
    'neptune': '♆',
    'asteroid': '•',
    'comet': '☄️'
}

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Render the main page."""
    return FileResponse("templates/index.html")

@app.get(API_ENDPOINT_CELESTIAL)
async def get_celestial_objects(lat: float = None, lon: float = None, elevation: float = None):
    """Get positions of celestial objects."""
    try:
        # Hole Standortdaten aus den Einstellungen, wenn nicht übergeben
        location_settings = settings.get_location()
        if lat is None:
            lat = location_settings["latitude"]
        if lon is None:
            lon = location_settings["longitude"]
        if elevation is None:
            elevation = location_settings["elevation"]
        
        t = ts.now()
        location = wgs84.latlon(lat, lon, elevation_m=elevation)
        observer = eph['earth'] + location
        
        result = {
            "time": t.utc_datetime().isoformat(),
            "location": {
                "latitude": lat,
                "longitude": lon,
                "elevation": elevation
            },
            "bodies": {}
        }
        
        # Berechne Position und Helligkeit für jeden Himmelskörper
        for name, body in CELESTIAL_BODIES.items():
            try:
                # Berechne Position vom Beobachter aus
                astrometric = observer.at(t).observe(body)
                apparent = astrometric.apparent()
                alt, az, distance = apparent.altaz()
                
                # Berechne Entfernung vom Erdmittelpunkt aus
                earth_center = eph['earth'].at(t)
                earth_to_body = earth_center.observe(body)
                # Entfernung in astronomischen Einheiten (AU)
                earth_distance = earth_to_body.distance().au
                
                # Berechne Helligkeit (Magnitude)
                # Fester Wert für die Sonne, dynamische Berechnung für den Mond
                if name == 'sun':
                    mag = -26.74  # Standardwert für die Sonne
                elif name == 'moon':
                    # Berechne die Mondphase
                    sun_astrometric = observer.at(t).observe(eph['sun'])
                    moon_phase = almanac.moon_phase(eph, t)
                    moon_phase_angle = float(moon_phase.radians)
                    
                    # Berechne die Mond-Magnitude basierend auf der Phase
                    # Formel: M = -12.7 + 2.5 * log10(0.5 * (1 - cos(phase_angle)))
                    import math
                    phase_factor = 0.5 * (1 - math.cos(moon_phase_angle))
                    if phase_factor > 0:
                        mag = -12.7 + 2.5 * math.log10(phase_factor)
                    else:
                        mag = -12.7  # Fallback für Vollmond
                elif name in ['mercury', 'venus', 'mars', 'jupiter', 'saturn']:
                    try:
                        mag = planetary_magnitude(astrometric)
                    except Exception as e:
                        print(f"Fehler bei der Magnitude-Berechnung für {name}: {str(e)}")
                        # Fallback-Werte für Planeten
                        mag_fallback = {
                            'mercury': 0.23,
                            'venus': -4.14,
                            'mars': 1.66,
                            'jupiter': -2.2,
                            'saturn': 0.46
                        }
                        mag = mag_fallback.get(name, 0)
                else:
                    # Für andere Körper verwenden wir Standardwerte
                    mag_values = {
                        'uranus': 5.7,
                        'neptune': 7.8
                    }
                    mag = mag_values.get(name, 0)
                
                # Berechne Auf- und Untergangszeiten
                try:
                    f = almanac.risings_and_settings(eph, body, location)
                    
                    # Suche nach dem nächsten Aufgang
                    t1 = ts.now()
                    # Verwende UTC für die Zeitberechnung
                    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
                    t2 = ts.from_datetime(tomorrow)
                    times, events = almanac.find_discrete(t1, t2, f)
                    
                    rise_time = None
                    set_time = None
                    
                    for time, event in zip(times, events):
                        # Konvertiere UTC zu lokaler Zeit
                        local_time = time.utc_datetime().replace(tzinfo=timezone.utc).astimezone()
                        # Formatiere die Zeit als HH:MM
                        formatted_time = local_time.strftime('%H:%M')
                        
                        if event == 1:  # Aufgang
                            rise_time = formatted_time
                        else:  # Untergang
                            set_time = formatted_time
                            
                    # Berechne die Transitzeit (Kulmination)
                    transit_time = None
                    try:
                        # Wenn Auf- und Untergangszeit bekannt sind, suche im Zeitraum dazwischen
                        if rise_time and set_time:
                            # Konvertiere Zeiten zu Datetime-Objekten
                            now = datetime.now()
                            rise_dt = datetime.strptime(rise_time, '%H:%M').replace(year=now.year, month=now.month, day=now.day)
                            set_dt = datetime.strptime(set_time, '%H:%M').replace(year=now.year, month=now.month, day=now.day)
                            
                            # Wenn der Untergang vor dem Aufgang liegt, ist er am nächsten Tag
                            if set_dt < rise_dt:
                                set_dt += timedelta(days=1)
                            
                            # Berechne die Mitte zwischen Auf- und Untergang als Näherung für die Transitzeit
                            transit_dt = rise_dt + (set_dt - rise_dt) / 2
                            transit_time = transit_dt.strftime('%H:%M')
                        else:
                            # Grobe Schätzung: Transitzeit in 12 Stunden
                            transit_dt = datetime.now() + timedelta(hours=12)
                            transit_time = transit_dt.strftime('%H:%M')
                    except Exception as e:
                        print(f"Fehler bei der Berechnung der Transitzeit für {name}: {str(e)}")
                        transit_time = None
                except Exception as e:
                    print(f"Fehler bei der Berechnung der Auf-/Untergangszeiten für {name}: {str(e)}")
                    rise_time = None
                    set_time = None
                    transit_time = None
                
                # Füge Daten zum Ergebnis hinzu
                result["bodies"][name] = {
                    "name": name,
                    "symbol": BODY_SYMBOLS.get(name, "?"),
                    "altitude": float(alt.degrees),
                    "azimuth": float(az.degrees),
                    "distance": float(earth_distance),  # Entfernung vom Erdmittelpunkt
                    "magnitude": float(mag),
                    "visible": True,  # Immer sichtbar, auch unter dem Horizont
                    "transit_time": transit_time,
                    "rise_time": rise_time,
                    "set_time": set_time
                }
            except Exception as e:
                print(f"Error calculating position for {name}: {str(e)}")
                continue
        
        return result
    except Exception as e:
        print(f"Error in get_celestial_objects: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get(f"{API_ENDPOINT_CELESTIAL}/{{body_id}}")
async def get_celestial_object(body_id: str, lat: float = None, lon: float = None, elevation: float = None):
    """Get position of a specific celestial object."""
    try:
        # Überprüfe, ob der angeforderte Körper existiert
        if body_id not in CELESTIAL_BODIES:
            raise HTTPException(status_code=404, detail=f"Celestial body '{body_id}' not found")
        
        # Hole Standortdaten aus den Einstellungen, wenn nicht übergeben
        location_settings = settings.get_location()
        if lat is None:
            lat = location_settings["latitude"]
        if lon is None:
            lon = location_settings["longitude"]
        if elevation is None:
            elevation = location_settings["elevation"]
        
        t = ts.now()
        location = wgs84.latlon(lat, lon, elevation_m=elevation)
        observer = eph['earth'] + location
        
        body = CELESTIAL_BODIES[body_id]
        
        # Berechne Position vom Beobachter aus
        astrometric = observer.at(t).observe(body)
        apparent = astrometric.apparent()
        alt, az, distance = apparent.altaz()
        
        # Berechne Entfernung vom Erdmittelpunkt aus
        earth_center = eph['earth'].at(t)
        earth_to_body = earth_center.observe(body)
        # Entfernung in astronomischen Einheiten (AU)
        earth_distance = earth_to_body.distance().au
        
        # Berechne Helligkeit (Magnitude)
        # Fester Wert für die Sonne, dynamische Berechnung für den Mond
        if body_id == 'sun':
            mag = -26.74  # Standardwert für die Sonne
        elif body_id == 'moon':
            # Berechne die Mondphase
            sun_astrometric = observer.at(t).observe(eph['sun'])
            moon_phase = almanac.moon_phase(eph, t)
            moon_phase_angle = float(moon_phase.radians)
            
            # Berechne die Mond-Magnitude basierend auf der Phase
            # Formel: M = -12.7 + 2.5 * log10(0.5 * (1 - cos(phase_angle)))
            import math
            phase_factor = 0.5 * (1 - math.cos(moon_phase_angle))
            if phase_factor > 0:
                mag = -12.7 + 2.5 * math.log10(phase_factor)
            else:
                mag = -12.7  # Fallback für Vollmond
                
            # Füge die Mondphase als Prozent zum Ergebnis hinzu
            phase_percent = (1 - phase_factor * 2) * 100  # 0% = Neumond, 100% = Vollmond
        elif body_id in ['mercury', 'venus', 'mars', 'jupiter', 'saturn']:
            try:
                mag = planetary_magnitude(astrometric)
            except Exception as e:
                print(f"Fehler bei der Magnitude-Berechnung für {body_id}: {str(e)}")
                # Fallback-Werte für Planeten
                mag_fallback = {
                    'mercury': 0.23,
                    'venus': -4.14,
                    'mars': 1.66,
                    'jupiter': -2.2,
                    'saturn': 0.46
                }
                mag = mag_fallback.get(body_id, 0)
        else:
            # Für andere Körper verwenden wir Standardwerte
            mag_values = {
                'uranus': 5.7,
                'neptune': 7.8
            }
            mag = mag_values.get(body_id, 0)
        
        # Berechne Auf- und Untergangszeiten
        f = almanac.risings_and_settings(eph, body, location)
        
        # Suche nach dem nächsten Aufgang
        t1 = ts.now()
        # Verwende UTC für die Zeitberechnung
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        t2 = ts.from_datetime(tomorrow)
        times, events = almanac.find_discrete(t1, t2, f)
        
        rise_time = None
        set_time = None
        
        for time, event in zip(times, events):
            # Konvertiere UTC zu lokaler Zeit
            local_time = time.utc_datetime().replace(tzinfo=timezone.utc).astimezone()
            # Formatiere die Zeit als HH:MM
            formatted_time = local_time.strftime('%H:%M')
            
            if event == 1:  # Aufgang
                rise_time = formatted_time
            else:  # Untergang
                set_time = formatted_time
                
        # Berechne die Transitzeit (Kulmination)
        transit_time = None
        try:
            # Finde den Zeitpunkt der höchsten Elevation
            def culmination_at(t):
                astrometric = observer.at(t).observe(body)
                apparent = astrometric.apparent()
                alt, az, distance = apparent.altaz()
                return alt.degrees
            
            # Suche nach der Kulmination im Zeitraum zwischen jetzt und morgen
            t_start = ts.now()
            t_end = ts.from_datetime(datetime.now(timezone.utc) + timedelta(days=1))
            
            # Wenn Auf- und Untergangszeit bekannt sind, suche im Zeitraum dazwischen
            if rise_time and set_time:
                # Konvertiere Zeiten zu Datetime-Objekten
                now = datetime.now()
                rise_dt = datetime.strptime(rise_time, '%H:%M').replace(year=now.year, month=now.month, day=now.day)
                set_dt = datetime.strptime(set_time, '%H:%M').replace(year=now.year, month=now.month, day=now.day)
                
                # Wenn der Untergang vor dem Aufgang liegt, ist er am nächsten Tag
                if set_dt < rise_dt:
                    set_dt += timedelta(days=1)
                
                # Berechne die Mitte zwischen Auf- und Untergang als Näherung für die Transitzeit
                transit_dt = rise_dt + (set_dt - rise_dt) / 2
                transit_time = transit_dt.strftime('%H:%M')
            else:
                # Wenn keine Auf-/Untergangszeiten bekannt sind, verwende die aktuelle Position
                # und prüfe, ob der Körper auf- oder absteigt
                t_now = ts.now()
                t_later = ts.from_datetime(datetime.now(timezone.utc) + timedelta(hours=1))
                
                alt_now = culmination_at(t_now)
                alt_later = culmination_at(t_later)
                
                # Wenn der Körper aufsteigt, liegt die Transitzeit in der Zukunft
                if alt_later > alt_now:
                    # Grobe Schätzung: Transitzeit in 6 Stunden
                    transit_dt = datetime.now() + timedelta(hours=6)
                else:
                    # Grobe Schätzung: Transitzeit in 18 Stunden
                    transit_dt = datetime.now() + timedelta(hours=18)
                
                transit_time = transit_dt.strftime('%H:%M')
        except Exception as e:
            print(f"Fehler bei der Berechnung der Transitzeit für {body_id}: {str(e)}")
            transit_time = None
        
        result = {
            "id": body_id,
            "name": body_id,
            "symbol": BODY_SYMBOLS.get(body_id, "?"),
            "altitude": float(alt.degrees),
            "azimuth": float(az.degrees),
            "distance": float(earth_distance),  # Entfernung vom Erdmittelpunkt
            "magnitude": float(mag),
            "visible": True,  # Immer sichtbar, auch unter dem Horizont
            "transit_time": transit_time,
            "rise_time": rise_time,
            "set_time": set_time
        }
        
        # Füge Mondphase hinzu, wenn es sich um den Mond handelt
        if body_id == 'moon':
            # Berechne Mondphase in Prozent (0% = Neumond, 100% = Vollmond)
            phase_percent = (1 - phase_factor * 2) * 100
            if phase_percent < 0:
                phase_percent = 0
            if phase_percent > 100:
                phase_percent = 100
                
            # Bestimme die Phasenbezeichnung
            if phase_percent < 5:
                phase_name = "new_moon"  # Neumond
            elif phase_percent < 45:
                phase_name = "waxing_crescent"  # zunehmender Halbmond
            elif phase_percent < 55:
                phase_name = "first_quarter"  # erstes Viertel
            elif phase_percent < 95:
                phase_name = "waxing_gibbous"  # zunehmender Mond
            elif phase_percent < 100:
                phase_name = "full_moon"  # Vollmond
            elif phase_percent < 145:
                phase_name = "waning_gibbous"  # abnehmender Mond
            elif phase_percent < 155:
                phase_name = "last_quarter"  # letztes Viertel
            else:
                phase_name = "waning_crescent"  # abnehmender Halbmond
                
            result["phase"] = phase_percent / 100  # Als Dezimalzahl zwischen 0 und 1
            result["phase_name"] = phase_name
        
        return result
    except Exception as e:
        print(f"Error in get_celestial_object: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def load_asteroid_data():
    """Lade Asteroidendaten aus dem MPC."""
    global asteroid_data_cache, asteroid_cache_timestamp
    
    try:
        # Prüfe, ob ein Cache existiert und nicht zu alt ist
        if os.path.exists(ASTEROID_CACHE_FILE):
            try:
                with open(ASTEROID_CACHE_FILE, 'rb') as f:
                    cache_data = pickle.load(f)
                    asteroid_cache_timestamp = cache_data.get('timestamp')
                    cached_data = cache_data.get('data')
                    
                    # Wenn der Cache nicht zu alt ist (< 24 Stunden), verwende ihn
                    if asteroid_cache_timestamp and (datetime.now() - asteroid_cache_timestamp).total_seconds() < 86400:
                        print("Using cached asteroid data")
                        asteroid_data_cache = cached_data
                        return asteroid_data_cache
            except Exception as cache_error:
                print(f"Error loading asteroid cache: {str(cache_error)}")
        
        print("Downloading fresh asteroid data...")
        # Lade die hellsten Asteroiden
        asteroid_data = mpc.load_mpcorb_dataframe('bright')
        
        # Speichere den Zeitstempel und die Daten
        asteroid_cache_timestamp = datetime.now()
        asteroid_data_cache = asteroid_data
        
        # Speichere den Cache
        try:
            with open(ASTEROID_CACHE_FILE, 'wb') as f:
                pickle.dump({
                    'timestamp': asteroid_cache_timestamp,
                    'data': asteroid_data_cache
                }, f)
            print("Asteroid data saved to disk cache")
        except Exception as save_error:
            print(f"Error saving asteroid cache: {str(save_error)}")
        
        return asteroid_data_cache
    except Exception as e:
        print(f"Error loading asteroid data: {str(e)}")
        # Return an empty DataFrame instead of None to avoid errors
        import pandas as pd
        return pd.DataFrame(columns=['designation', 'H'])

def load_comet_data():
    """Lade Kometendaten aus dem MPC."""
    global comet_data_cache, comet_cache_timestamp
    
    try:
        # Prüfe, ob ein Cache existiert und nicht zu alt ist
        if os.path.exists(COMET_CACHE_FILE):
            try:
                with open(COMET_CACHE_FILE, 'rb') as f:
                    cache_data = pickle.load(f)
                    comet_cache_timestamp = cache_data.get('timestamp')
                    cached_data = cache_data.get('data')
                    
                    # Wenn der Cache nicht zu alt ist (< 24 Stunden), verwende ihn
                    if comet_cache_timestamp and (datetime.now() - comet_cache_timestamp).total_seconds() < 86400:
                        print("Using cached comet data")
                        comet_data_cache = cached_data
                        return comet_data_cache
            except Exception as cache_error:
                print(f"Error loading comet cache: {str(cache_error)}")
        
        print("Downloading fresh comet data...")
        # Lade Kometendaten
        comet_data = mpc.load_comets_dataframe()
        
        # Speichere den Zeitstempel und die Daten
        comet_cache_timestamp = datetime.now()
        comet_data_cache = comet_data
        
        # Speichere den Cache
        try:
            with open(COMET_CACHE_FILE, 'wb') as f:
                pickle.dump({
                    'timestamp': comet_cache_timestamp,
                    'data': comet_data_cache
                }, f)
            print("Comet data saved to disk cache")
        except Exception as save_error:
            print(f"Error saving comet cache: {str(save_error)}")
        
        return comet_data_cache
    except Exception as e:
        print(f"Error loading comet data: {str(e)}")
        # Return an empty DataFrame instead of None to avoid errors
        import pandas as pd
        return pd.DataFrame(columns=['designation', 'magnitude_H'])

@app.on_event("startup")
async def startup_event():
    """Load data on startup."""
    # Lade Asteroiden- und Kometendaten
    load_asteroid_data()
    load_comet_data()
    
    # Lade Benutzereinstellungen
    settings.load_settings()

@app.get(API_ENDPOINT_ASTEROIDS)
async def get_asteroids(lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False):
    """Get visible asteroids."""
    try:
        # Verwende einen festen Wert für die maximale Magnitude
        max_magnitude = 9.0  # Fester Wert für Asteroiden
        
        # Hole Standortdaten aus den Einstellungen, wenn nicht übergeben
        location_settings = settings.get_location()
        if lat is None:
            lat = location_settings["latitude"]
        if lon is None:
            lon = location_settings["longitude"]
        if elevation is None:
            elevation = location_settings["elevation"]
        
        # Speichere die Standortdaten, wenn gewünscht
        if save_location and lat is not None and lon is not None and elevation is not None:
            settings.set_location(lat, lon, elevation, location_name)
            print(f"Saved location settings: lat={lat}, lon={lon}, elevation={elevation}, name={location_name}")
        
        print(f"Getting asteroids with magnitude <= {max_magnitude} at lat={lat}, lon={lon}, elevation={elevation}")
        t = ts.now()
        # Benutze die Standortparameter
        location = wgs84.latlon(lat, lon, elevation_m=elevation)
        observer = eph['earth'] + location
        
        global asteroid_data_cache
        if asteroid_data_cache is None:
            asteroid_data_cache = load_asteroid_data()
        
        result = {
            "time": t.utc_datetime().isoformat(),
            "max_magnitude": max_magnitude,
            "bodies": {}
        }
        
        # Verarbeite Asteroiden
        count = 0
        for _, asteroid in asteroid_data_cache.iterrows():
            try:
                # Hole die Bezeichnung und absolute Magnitude
                designation = asteroid['designation']
                h_mag = float(asteroid['H'])
                
                # Überspringe Asteroiden, die zu dunkel sind
                if h_mag > max_magnitude:
                    continue
                
                # Create skyfield object
                asteroid_obj = mpc.mpcorb_orbit(asteroid, ts, eph)
                
                # Calculate position
                astrometric = observer.at(t).observe(asteroid_obj)
                apparent = astrometric.apparent()
                alt, az, distance = apparent.altaz()
                
                # Calculate apparent magnitude (approximate)
                # This is a simplified calculation
                mag = h_mag  # Use absolute magnitude as approximation
                
                # Create asteroid object
                asteroid_data = {
                    "name": designation,
                    "symbol": "•",  # Small dot for asteroids
                    "type": "asteroid",
                    "visible": True,  # Immer sichtbar, auch unter dem Horizont
                    "altitude": float(alt.degrees),
                    "azimuth": float(az.degrees),
                    "distance": float(distance.km),
                    "magnitude": float(mag)
                }
                
                # Add to bodies dictionary with designation as key
                result["bodies"][f"asteroid_{designation}"] = asteroid_data
                count += 1
                
                # Limit to 50 asteroids for performance
                if count >= 50:
                    break
                    
            except Exception as e:
                print(f"Error processing asteroid {asteroid['designation']}: {str(e)}")
                continue
        
        print(f"Returning {len(result['bodies'])} asteroids")
        return result
        
    except Exception as e:
        print(f"Error in get_asteroids: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get(API_ENDPOINT_COMETS)
async def get_comets(lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False):
    """Get visible comets."""
    try:
        # Verwende einen festen Wert für die maximale Magnitude
        max_magnitude = 12.0  # Fester Wert für Kometen
        
        # Hole Standortdaten aus den Einstellungen, wenn nicht übergeben
        location_settings = settings.get_location()
        if lat is None:
            lat = location_settings["latitude"]
        if lon is None:
            lon = location_settings["longitude"]
        if elevation is None:
            elevation = location_settings["elevation"]
        
        # Speichere die Standortdaten, wenn gewünscht
        if save_location and lat is not None and lon is not None and elevation is not None:
            settings.set_location(lat, lon, elevation, location_name)
            print(f"Saved location settings: lat={lat}, lon={lon}, elevation={elevation}, name={location_name}")
        
        print(f"Getting comets with magnitude <= {max_magnitude} at lat={lat}, lon={lon}, elevation={elevation}")
        t = ts.now()
        # Benutze die Standortparameter
        location = wgs84.latlon(lat, lon, elevation_m=elevation)
        observer = eph['earth'] + location
        
        global comet_data_cache
        if comet_data_cache is None:
            comet_data_cache = load_comet_data()
        
        # Even if the data is empty, we'll return an empty result rather than an error
        
        result = {
            "time": t.utc_datetime().isoformat(),
            "max_magnitude": max_magnitude,
            "bodies": {}
        }
        
        # Import constants for comet orbit calculation
        from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2 as GM_SUN
        
        # Get the sun object for comet position calculation
        sun = eph['sun']
        
        # Process comets - we'll limit to a reasonable number to avoid performance issues
        comet_count = 0
        max_comets = 100  # Limit to prevent performance issues
        
        # Process each comet in the dataframe
        for designation, comet_row in comet_data_cache.iterrows():
            try:
                # Skip if we've reached our limit
                if comet_count >= max_comets:
                    print(f"Reached maximum comet count ({max_comets}), stopping processing")
                    break
                    
                # Get the magnitude if available
                try:
                    if 'magnitude_H' in comet_row and pd.notna(comet_row['magnitude_H']):
                        mag = float(comet_row['magnitude_H'])
                    else:
                        mag = 15.0  # Default magnitude
                except (ValueError, TypeError):
                    mag = 15.0  # Default if conversion fails
                
                # Skip if magnitude is greater than max_magnitude
                if mag > max_magnitude:
                    continue
                
                # Create the comet orbit object directly from the row
                # This follows the Skyfield documentation approach
                try:
                    # Konvertiere alle erforderlichen Felder explizit zu float
                    # Dies behebt den Typfehler bei der Addition in Skyfield
                    # Erweitere die Liste der zu konvertierenden Felder
                    numeric_fields = ['e', 'q', 'i', 'om', 'w', 'epoch_tt', 'Tp', 'peri', 'node', 'incl']
                    
                    # Erstelle eine Kopie der Daten, um die Originaldaten nicht zu verändern
                    comet_data = {}
                    
                    # Konvertiere alle Felder in der Zeile zu den richtigen Typen
                    for field, value in comet_row.items():
                        if pd.notna(value):
                            if field in numeric_fields or isinstance(value, (str, np.str_)) and value.replace('.', '', 1).isdigit():
                                try:
                                    comet_data[field] = float(value)
                                except (ValueError, TypeError):
                                    comet_data[field] = value
                            else:
                                comet_data[field] = value
                        else:
                            comet_data[field] = None
                    
                    # Create the comet orbit object mit den konvertierten Daten
                    comet_obj = sun + mpc.comet_orbit(comet_data, ts, GM_SUN)
                except Exception as e:
                    print(f"Error processing comet {designation}: {str(e)}")
                    continue
                
                # Calculate position
                astrometric = observer.at(t).observe(comet_obj)
                apparent = astrometric.apparent()
                alt, az, distance = apparent.altaz()
                
                # We already have the magnitude from earlier
                apparent_magnitude = mag
                
                # Get RA/Dec
                ra, dec, _ = apparent.radec()
                
                # Get name or designation
                if 'name' in comet_row and comet_row['name'] and pd.notna(comet_row['name']):
                    name = str(comet_row['name'])
                else:
                    name = designation
                
                # Add to result
                result["bodies"][designation] = {
                    "name": name,
                    "ra": ra._degrees,
                    "dec": dec.degrees,
                    "alt": alt.degrees,
                    "az": az.degrees,
                    "distance": distance.au,
                    "magnitude": apparent_magnitude,
                    "type": "comet"
                }
                
                # Increment our counter
                comet_count += 1
            except Exception as e:
                print(f"Error processing comet {designation}: {str(e)}")
                continue
        
        print(f"Returning {len(result['bodies'])} comets")
        return result
        
    except Exception as e:
        print(f"Error in get_comets: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
