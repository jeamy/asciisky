"""
AsciiSky - ASCII Art Himmelsdarstellung
"""
import os
import json
import pickle
import time
import gzip
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from types import SimpleNamespace

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from skyfield import almanac
from skyfield.api import load, wgs84, Star, Topos, Loader
from skyfield.data import hipparcos, mpc
from skyfield.magnitudelib import planetary_magnitude
from starlette.responses import FileResponse

import settings
import bright_asteroids
import comets

# Initialisiere FastAPI
app = FastAPI(title="AsciiSky API", description="API für die ASCII-Darstellung des Sternenhimmels")

# Statische Dateien und Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# API-Endpunkte
API_ENDPOINT_CELESTIAL = "/api/celestial"
API_ENDPOINT_ASTEROIDS = "/api/asteroids"
API_ENDPOINT_COMETS = "/api/comets"
API_ENDPOINT_BRIGHT_ASTEROIDS = "/api/bright_asteroids"

# Lade Skyfield-Daten
ts = load.timescale()
eph = load('de421.bsp')  # Ephemeris-Datei

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
            "bodies": {},
            "loading": False
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
                    # Starte die Suche vom Beginn des aktuellen Tages (00:00 UTC)
                    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                    t1_start = ts.from_datetime(today_start)
                    # Ende der Suche: 48 Stunden später (zwei volle Tage)
                    t2 = ts.from_datetime(today_start + timedelta(days=2))
                    times, events = almanac.find_discrete(t1_start, t2, f)
                    
                    rise_time = None
                    set_time = None
                    
                    for time, event in zip(times, events):
                        # Konvertiere UTC zu lokaler Zeit mit expliziter Zeitzone
                        utc_time = time.utc_datetime().replace(tzinfo=timezone.utc)
                        local_time = utc_time.astimezone()
                        # Formatiere die Zeit als HH:MM
                        formatted_time = local_time.strftime('%H:%M')
                        # print(f"Converted time for {name}: {utc_time.strftime('%H:%M')} UTC -> {formatted_time} local ({local_time.tzinfo})")
                        
                        if event == 1:  # Aufgang
                            rise_time = formatted_time
                        else:  # Untergang
                            set_time = formatted_time
                            
                    # Berechne die Transitzeit (Kulmination)
                    transit_time = None
                    try:
                        # Wenn Auf- und Untergangszeit bekannt sind, suche im Zeitraum dazwischen
                        if rise_time and set_time:
                            # Hole die aktuelle Zeit mit Zeitzone
                            now = datetime.now().astimezone()
                            local_tz = now.tzinfo
                            today = now.date()
                            
                            # Konvertiere Zeiten zu Datetime-Objekten mit lokaler Zeitzone
                            rise_dt = datetime.strptime(rise_time, '%H:%M').replace(
                                year=today.year, month=today.month, day=today.day, tzinfo=local_tz)
                            set_dt = datetime.strptime(set_time, '%H:%M').replace(
                                year=today.year, month=today.month, day=today.day, tzinfo=local_tz)
                            
                            # Wenn der Untergang vor dem Aufgang liegt, ist er am nächsten Tag
                            if set_dt < rise_dt:
                                set_dt = set_dt.replace(day=today.day + 1)
                            
                            # Berechne die Mitte zwischen Auf- und Untergang als Näherung für die Transitzeit
                            transit_dt = rise_dt + (set_dt - rise_dt) / 2
                            transit_time = transit_dt.strftime('%H:%M')
                            # print(f"Transit time for {name}: {transit_time} local ({local_tz})")
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

# Die load_asteroid_data Funktion wurde entfernt, da sie nicht mehr benötigt wird

@app.on_event("startup")
async def startup_event():
    """Load data on startup."""
    # Lade Kometendaten
    comets.load_comet_dataframe()
    
    # Lade Benutzereinstellungen
    settings.load_settings()
    
    # Stelle sicher, dass das Cache-Verzeichnis existiert
    os.makedirs("cache", exist_ok=True)

@app.get(API_ENDPOINT_BRIGHT_ASTEROIDS)
async def get_bright_asteroids(lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False):
    """Get positions of the brightest minor planets (asteroids)."""
    try:
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
        
        # Erstelle Skyfield-Objekte
        t = ts.now()
        location = wgs84.latlon(lat, lon, elevation_m=elevation)
        observer = eph['earth'] + location
        
        # Lade die hellsten Asteroiden
        loader = Loader('.')
        # Übergebe die Standortdaten als Dictionary
        location_dict = {
            'latitude': lat,
            'longitude': lon,
            'elevation': elevation
        }
        bright_asteroid_list = bright_asteroids.load_bright_asteroids(
            loader, ts, eph, location_dict, max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE
        )
        
        result = {
            "time": t.utc_datetime().isoformat(),
            "location": {
                "latitude": lat,
                "longitude": lon,
                "elevation": elevation
            },
            "bodies": {},
            "loading": False
        }
        
        # Füge die Asteroiden zum Ergebnis hinzu
        for i, asteroid in enumerate(bright_asteroid_list):
            # Überprüfe, ob das Asteroid-Objekt ein Dictionary ist
            if isinstance(asteroid, dict) and "name" in asteroid:
                # Verwende einen eindeutigen Schlüssel für jeden Asteroiden
                key = f"bright_asteroid_{i}_{asteroid['name']}"
                result["bodies"][key] = asteroid
            else:
                print(f"Skipping invalid asteroid data at index {i}: {asteroid}")
        
        print(f"Returning {len(result['bodies'])} bright asteroids")
        return result
        
    except Exception as e:
        print(f"Error in get_bright_asteroids: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get(API_ENDPOINT_ASTEROIDS)
async def get_asteroids(lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False):
    """Get visible asteroids."""
    try:
        # Verwende den Wert aus bright_asteroids.py
        max_magnitude = bright_asteroids.MAX_APPARENT_MAGNITUDE
        
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
        
        # print(f"Getting asteroids with magnitude 1 <= {max_magnitude} at lat={lat}, lon={lon}, elevation={elevation}")
        t = ts.now()
        
        # Erstelle ein Dictionary mit den Standortdaten
        location = {
            "latitude": lat,
            "longitude": lon,
            "elevation": elevation
        }
        
        # Rufe die Funktion aus bright_asteroids.py auf
        asteroid_list = bright_asteroids.load_bright_asteroids(load, ts, eph, location, max_magnitude=max_magnitude)
        
        result = {
            "time": t.utc_datetime().isoformat(),
            "max_magnitude": max_magnitude,
            "bodies": {}
        }
        
        # Formatiere die Daten für die API-Antwort
        for i, asteroid in enumerate(asteroid_list):
            if isinstance(asteroid, dict) and "name" in asteroid:
                # Verwende einen eindeutigen Schlüssel für jeden Asteroiden
                key = f"asteroid_{i}_{asteroid['name']}"
                result["bodies"][key] = {
                    "name": asteroid["name"],
                    "symbol": "•",  # Small dot for asteroids
                    "type": "asteroid",
                    "visible": True,  # Immer sichtbar, auch unter dem Horizont
                    "altitude": float(asteroid["altitude"]),
                    "azimuth": float(asteroid["azimuth"]),
                    "distance": float(asteroid["distance"]),  # Entfernung in AU (keine Umrechnung)
                    "magnitude": float(asteroid["magnitude"]),
                    "rise_time": asteroid["rise_time"],
                    "set_time": asteroid["set_time"],
                    "transit_time": asteroid["transit_time"]
                }
            else:
                print(f"Skipping invalid asteroid data at index {i}: {asteroid}")
        
        print(f"Returning {len(result['bodies'])} asteroids")
        return result
        
    except Exception as e:
        print(f"Error in get_asteroids: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get(API_ENDPOINT_COMETS)
async def get_comets(lat: float = None, lon: float = None, elevation: float = None, location_name: str = None, save_location: bool = False, max_comets: int = 1000):
    """Get comets with real MPC data and rise/set/transit times.
    Supports optional 'max_comets' query parameter to limit processing for performance (default: 1000).
    """
    try:
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

        t = ts.now()

        # Standort als Dictionary (kompatibel mit comets.load_comets)
        location_dict = {
            'latitude': lat,
            'longitude': lon,
            'elevation': elevation
        }

        # Kometen berechnen mit Photometrie-Filtern (wie bei Kleinplaneten)
        comet_list = comets.load_comets(ts, eph, location_dict, max_comets=max_comets)

        result = {
            "time": t.utc_datetime().isoformat(),
            "location": {
                "latitude": lat,
                "longitude": lon,
                "elevation": elevation
            },
            "bodies": {},
            "loading": False
        }

        for i, comet in enumerate(comet_list):
            if isinstance(comet, dict) and "name" in comet:
                key = f"comet_{i}_{comet['name']}"
                result["bodies"][key] = comet
            else:
                print(f"Skipping invalid comet data at index {i}: {comet}")

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
