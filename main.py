from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import math
from datetime import datetime, timedelta
from skyfield.api import load, wgs84, Topos, Star
from skyfield import almanac
from skyfield.data import mpc
from skyfield.magnitudelib import planetary_magnitude
import pytz
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel

class CelestialBody(str, Enum):
    MOON = "moon"
    SUN = "sun"
    MERCURY = "mercury"
    VENUS = "venus"
    MARS = "mars"
    JUPITER = "jupiter"
    SATURN = "saturn"
    URANUS = "uranus"
    NEPTUNE = "neptune"

class CelestialObject(BaseModel):
    name: str
    symbol: str
    type: str
    visible: bool
    altitude: float
    azimuth: float
    distance: float
    magnitude: Optional[float] = None
    phase: Optional[float] = None
    phase_name: Optional[str] = None
    rise_time: Optional[str] = None
    set_time: Optional[str] = None
    transit_time: Optional[str] = None

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Load ephemeris data
eph = load('de421.bsp')
ts = load.timescale()

# Constants - synchronized with static/js/constants.js
# Vienna coordinates (latitude, longitude, elevation)
VIENNA = wgs84.latlon(48.2082, 16.3738, elevation_m=171)

# API endpoints - must match API_ENDPOINTS in constants.js
API_ENDPOINT_CELESTIAL = "/api/celestial"
API_ENDPOINT_CELESTIAL_OBJECT = "/api/celestial/{body_id}"

# Default values - must match ASTRO_CONSTANTS in constants.js
SUN_MAGNITUDE = -26.74  # Standard apparent magnitude of the Sun
MOON_MAGNITUDE = -12.6  # Approximate full moon magnitude

# Celestial objects data
CELESTIAL_OBJECTS = {
    CelestialBody.MOON: {
        'name': 'Moon',
        'symbol': '🌙',
        'type': 'moon'
    },
    CelestialBody.SUN: {
        'name': 'Sun',
        'symbol': '☀️',
        'type': 'star'
    },
    CelestialBody.MERCURY: {
        'name': 'Mercury',
        'symbol': '☿',
        'type': 'planet'
    },
    CelestialBody.VENUS: {
        'name': 'Venus',
        'symbol': '♀',
        'type': 'planet'
    },
    CelestialBody.MARS: {
        'name': 'Mars',
        'symbol': '♂',
        'type': 'planet'
    },
    CelestialBody.JUPITER: {
        'name': 'Jupiter',
        'symbol': '♃',
        'type': 'planet'
    },
    CelestialBody.SATURN: {
        'name': 'Saturn',
        'symbol': '♄',
        'type': 'planet'
    },
    CelestialBody.URANUS: {
        'name': 'Uranus',
        'symbol': '♅',
        'type': 'planet'
    },
    CelestialBody.NEPTUNE: {
        'name': 'Neptune',
        'symbol': '♆',
        'type': 'planet'
    }
}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

def get_celestial_body_data(body_id, t, observer):
    """Helper function to get data for a specific celestial body."""
    try:
        if body_id == CelestialBody.SUN:
            astrometric = observer.at(t).observe(eph['sun'])
            distance = astrometric.distance().km
            apparent = astrometric.apparent()
            alt, az, _ = apparent.altaz()
            
            # Berechne Auf- und Untergangszeiten
            rise_time, set_time, transit_time = calculate_rise_set_times('sun', t, observer)
            
            return {
                "name": "Sun",
                "symbol": "☀️",
                "type": "star",
                "visible": True,  # Immer sichtbar machen
                "altitude": float(alt.degrees),
                "azimuth": float(az.degrees),
                "distance": float(distance),
                "magnitude": float(SUN_MAGNITUDE),
                "rise_time": rise_time,
                "set_time": set_time,
                "transit_time": transit_time
            }
            
        elif body_id == CelestialBody.MOON:
            astrometric = observer.at(t).observe(eph['moon'])
            distance = astrometric.distance().km
            apparent = astrometric.apparent()
            alt, az, _ = apparent.altaz()
            
            # Calculate moon phase
            e = eph['earth'].at(t)
            s = e.observe(eph['sun']).apparent()
            m = e.observe(eph['moon']).apparent()
            phase_angle = s.separation_from(m).degrees
            phase = 0.5 * (1.0 - math.cos(math.radians(phase_angle)))
            
            # Berechne Auf- und Untergangszeiten
            rise_time, set_time, transit_time = calculate_rise_set_times('moon', t, observer)
            
            return {
                "name": "Moon",
                "symbol": "🌙",
                "type": "moon",
                "visible": True,  # Immer sichtbar machen
                "altitude": float(alt.degrees),
                "azimuth": float(az.degrees),
                "distance": float(distance),
                "magnitude": MOON_MAGNITUDE,
                "phase": float(phase),
                "phase_name": get_moon_phase_name(phase),
                "rise_time": rise_time,
                "set_time": set_time,
                "transit_time": transit_time
            }
            
        else:  # Planets
            # Map body_id to the correct ephemeris name
            planet_map = {
                CelestialBody.MERCURY: 'mercury',
                CelestialBody.VENUS: 'venus',
                CelestialBody.MARS: 'mars',
                CelestialBody.JUPITER: 'jupiter barycenter',
                CelestialBody.SATURN: 'saturn barycenter',
                CelestialBody.URANUS: 'uranus barycenter',
                CelestialBody.NEPTUNE: 'neptune barycenter'
            }
            
            planet_name = planet_map.get(body_id)
            if not planet_name:
                raise ValueError(f"Unknown planet: {body_id}")
                
            try:
                planet = eph[planet_name]
                astrometric = observer.at(t).observe(planet)
                distance = astrometric.distance().km
                apparent = astrometric.apparent()
                alt, az, _ = apparent.altaz()
                
                # Get magnitude
                try:
                    mag = float(planetary_magnitude(astrometric))
                except Exception as e:
                    print(f"Error getting magnitude for {body_id}: {str(e)}")
                    mag = None
                
                # Berechne Auf- und Untergangszeiten
                # Verwende den einfachen Namen ohne 'barycenter' für die Berechnung
                planet_eph_name = body_id.value
                rise_time, set_time, transit_time = calculate_rise_set_times(planet_eph_name, t, observer)
                
                return {
                    "name": body_id.value.capitalize(),
                    "symbol": {
                        'mercury': '☿',
                        'venus': '♀',
                        'mars': '♂',
                        'jupiter': '♃',
                        'saturn': '♄',
                        'uranus': '♅',
                        'neptune': '♆'
                    }.get(body_id.value, '★'),
                    "type": "planet",
                    "visible": True,  # Immer sichtbar machen
                    "altitude": float(alt.degrees),
                    "azimuth": float(az.degrees),
                    "distance": float(distance),
                    "magnitude": float(mag) if mag is not None else None,
                    "rise_time": rise_time,
                    "set_time": set_time,
                    "transit_time": transit_time
                }
            except Exception as e:
                print(f"Error processing {body_id}: {str(e)}")
                return None
            
    except Exception as e:
        print(f"Error getting data for {body_id}: {str(e)}")
        return None

@app.get(API_ENDPOINT_CELESTIAL_OBJECT)
async def get_celestial_body(body_id: CelestialBody):
    """Get position and information for a specific celestial body."""
    try:
        print(f"Getting data for {body_id}")
        t = ts.now()
        observer = eph['earth'] + VIENNA
        print(f"Observer: {observer}")
        
        body_data = get_celestial_body_data(body_id, t, observer)
        
        if body_data is None:
            error_msg = f"No data returned for celestial body {body_id}"
            print(error_msg)
            raise HTTPException(status_code=404, detail=error_msg)
            
        print(f"Successfully retrieved data for {body_id}")
        return body_data
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        error_msg = f"Error getting data for {body_id}: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=error_msg)

@app.get(API_ENDPOINT_CELESTIAL)
async def get_all_celestial_bodies():
    """Get positions for all celestial bodies."""
    try:
        print("Getting data for all celestial bodies")
        t = ts.now()
        observer = eph['earth'] + VIENNA
        print(f"Observer: {observer}")
        
        result = {
            "time": t.utc_datetime().isoformat(),
            "bodies": {}
        }
        
        # Get data for each celestial body
        for body_id in CelestialBody:
            try:
                print(f"Processing {body_id}...")
                body_data = get_celestial_body_data(body_id, t, observer)
                if body_data is not None:
                    result["bodies"][body_id.value] = body_data
                    print(f"  ✓ Added {body_id}")
                else:
                    print(f"  ✗ No data for {body_id}")
                    # Skip this body if no data is available
                    continue
                    
            except Exception as e:
                print(f"  ! Error processing {body_id}: {str(e)}")
                result["bodies"][body_id.value] = {
                    "name": body_id.value.capitalize(),
                    "visible": False,
                    "error": str(e)
                }
        
        return result
        
    except Exception as e:
        print(f"Error in get_all_celestial_bodies: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

def get_moon_phase_name(phase: float) -> str:
    """Convert moon phase (0-1) to a human-readable name."""
    if phase < 0.03 or phase > 0.97:
        return "New Moon"
    elif phase < 0.22:
        return "Waxing Crescent"
    elif phase < 0.28:
        return "First Quarter"
    elif phase < 0.47:
        return "Waxing Gibbous"
    elif phase < 0.53:
        return "Full Moon"
    elif phase < 0.72:
        return "Waning Gibbous"
    elif phase < 0.78:
        return "Last Quarter"
    else:
        return "Waning Crescent"

def get_cardinal_direction(azimuth: float) -> str:
    """Convert azimuth in degrees to cardinal direction."""
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    index = round(azimuth / (360. / len(directions))) % len(directions)
    return directions[index]

def calculate_rise_set_times(body_name, t, observer):
    """Calculate rise, set, and transit times for a celestial body."""
    try:
        # Lokale Zeitzone für Wien
        vienna_tz = pytz.timezone('Europe/Vienna')
        
        # Aktuelles Datum in UTC
        today_utc = t.utc_datetime().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_utc = today_utc + timedelta(days=1)
        
        # Zeitspanne für die Berechnung (24 Stunden)
        t0 = ts.from_datetime(today_utc)
        t1 = ts.from_datetime(tomorrow_utc)
        
        # Verwende Topos direkt für den Observer, nicht den zusammengesetzten Vektor
        topos_observer = VIENNA
        
        # Funktion für Auf- und Untergang
        if body_name == 'sun':
            f = almanac.sunrise_sunset(eph, topos_observer)
        else:
            # Für Mond und Planeten
            if body_name == 'moon':
                body = eph['moon']
            elif body_name in ['jupiter', 'saturn', 'uranus', 'neptune']:
                # Für äußere Planeten das Barycenter verwenden
                body = eph[f'{body_name.upper()} BARYCENTER']
            else:
                # Für innere Planeten
                body = eph[body_name.upper()]
            f = almanac.risings_and_settings(eph, body, topos_observer)
        
        # Berechne Auf- und Untergangszeiten
        times, events = almanac.find_discrete(t0, t1, f)
        
        rise_time = None
        set_time = None
        
        for time, event in zip(times, events):
            # Konvertiere zu lokaler Zeit
            local_time = time.astimezone(vienna_tz)
            formatted_time = local_time.strftime('%H:%M')
            
            if body_name == 'sun':
                # Für die Sonne: event=1 ist Aufgang, event=0 ist Untergang
                if event and not rise_time:
                    rise_time = formatted_time
                elif not event and not set_time:
                    set_time = formatted_time
            else:
                # Für andere Körper: event=1 ist Aufgang, event=0 ist Untergang
                if event and not rise_time:
                    rise_time = formatted_time
                elif not event and not set_time:
                    set_time = formatted_time
        
        # Berechne Transit (Höchststand)
        transit_time = None
        try:
            if body_name == 'sun':
                # Für die Sonne
                transit_f = almanac.meridian_transits(eph, eph['sun'], topos_observer)
            else:
                # Für andere Körper
                if body_name == 'moon':
                    body = eph['moon']
                elif body_name in ['jupiter', 'saturn', 'uranus', 'neptune']:
                    # Für äußere Planeten das Barycenter verwenden
                    body = eph[f'{body_name.upper()} BARYCENTER']
                else:
                    # Für innere Planeten
                    body = eph[body_name.upper()]
                transit_f = almanac.meridian_transits(eph, body, topos_observer)
            
            transit_times, transit_events = almanac.find_discrete(t0, t1, transit_f)
            
            for time, event in zip(transit_times, transit_events):
                # event=1 ist südlicher Transit (Höchststand)
                if event == 1:
                    local_time = time.astimezone(vienna_tz)
                    transit_time = local_time.strftime('%H:%M')
                    break
        except Exception as e:
            print(f"Error calculating transit for {body_name}: {str(e)}")
        
        return rise_time, set_time, transit_time
    
    except Exception as e:
        print(f"Error calculating rise/set times for {body_name}: {str(e)}")
        return None, None, None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
