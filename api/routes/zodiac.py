"""
Zodiac constellation API endpoint
"""
import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException, Query
from skyfield.api import Star
from skyfield.data import hipparcos, stellarium

from api.computation import LOADER
from api.computation import eph as GLOBAL_EPH
from api.computation import ts as GLOBAL_TS
from api.helpers import parse_time_param
from data_paths import CONSTELLATIONSHIP_PATH

# Constants
STELLARIUM_CONSTELLATION_PATH = str(CONSTELLATIONSHIP_PATH)

# Liste der anzuzeigenden Sternbilder (Tierkreis + zusätzliche bekannte Sternbilder)
CONSTELLATION_NAMES = [
    # Tierkreis (Zodiac)
    'Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo',
    'Libra', 'Scorpius', 'Sagittarius', 'Capricornus', 'Aquarius', 'Pisces',
    # Zusätzliche bekannte Sternbilder
    'Ursa Major', 'Ursa Minor', 'Pegasus', 'Andromeda', 'Cassiopeia', 'Orion', 'Canis Major', 'Perseus',
    'Auriga', 'Draco', 'Lyra', 'Cygnus', 'Aquila', 'Bootes'
]

# Deutsche Übersetzungen der Sternbildnamen
CONSTELLATION_TRANSLATIONS = {
    # Tierkreis (Zodiac)
    'Aries': 'Widder', 'Taurus': 'Stier', 'Gemini': 'Zwillinge',
    'Cancer': 'Krebs', 'Leo': 'Löwe', 'Virgo': 'Jungfrau',
    'Libra': 'Waage', 'Scorpius': 'Skorpion', 'Sagittarius': 'Schütze',
    'Capricornus': 'Steinbock', 'Aquarius': 'Wassermann', 'Pisces': 'Fische',
    # Zusätzliche bekannte Sternbilder
    'Ursa Major': 'Großer Bär', 'Ursa Minor': 'Kleiner Bär', 'Pegasus': 'Pegasus',
    'Andromeda': 'Andromeda', 'Cassiopeia': 'Kassiopeia', 'Orion': 'Orion',
    'Canis Major': 'Großer Hund', 'Perseus': 'Perseus',
    'Auriga': 'Fuhrmann', 'Draco': 'Drachen', 'Lyra': 'Leier',
    'Cygnus': 'Schwan', 'Aquila': 'Adler', 'Bootes': 'Bärenhüter'
}

# Zuordnung der Stellarium-Codes zu vollständigen IAU-Namen
STELLARIUM_CODE_TO_NAME = {
    # Tierkreis (Zodiac)
    'Ari': 'Aries', 'Tau': 'Taurus', 'Gem': 'Gemini', 'Cnc': 'Cancer',
    'Leo': 'Leo', 'Vir': 'Virgo', 'Lib': 'Libra', 'Sco': 'Scorpius',
    'Sgr': 'Sagittarius', 'Cap': 'Capricornus', 'Aqr': 'Aquarius', 'Psc': 'Pisces',
    # Zusätzliche bekannte Sternbilder
    'UMa': 'Ursa Major', 'UMi': 'Ursa Minor', 'Peg': 'Pegasus', 'And': 'Andromeda',
    'Cas': 'Cassiopeia', 'Ori': 'Orion', 'CMa': 'Canis Major', 'Per': 'Perseus',
    'Aur': 'Auriga', 'Dra': 'Draco', 'Lyr': 'Lyra',
    'Cyg': 'Cygnus', 'Aql': 'Aquila', 'Boo': 'Bootes'
}

router = APIRouter()
logger = logging.getLogger(__name__)

# Shared Skyfield objects from api.computation
hip_data = None

def init_skyfield():
    """Initialize Hipparcos data using shared Skyfield loader."""
    global hip_data

    if hip_data is not None:
        return  # Already initialized

    try:
        with LOADER.open(hipparcos.URL) as f:
            hip_data = hipparcos.load_dataframe(f)
    except Exception as e:
        hip_data = None
        logger.error(f"Failed to load Hipparcos catalog: {e}")

def get_star_position(hip_id: int, observer_location, time) -> tuple[float, float, float] | None:
    """Get star position (altitude, azimuth, magnitude) for given Hipparcos ID"""
    try:
        # Primary: Hipparcos dataframe
        if 'hip_data' in globals() and hip_data is not None and hip_id in hip_data.index:
            star_data = hip_data.loc[hip_id]
            star = Star.from_dataframe(star_data)
            apparent = observer_location.at(time).observe(star).apparent()
            alt, az, _ = apparent.altaz()
            magnitude = float(star_data.get('magnitude', 5.0))
            return float(alt.degrees), float(az.degrees), magnitude

        logger.debug("HIP %s not available in Hipparcos data", hip_id)
        return None
        
    except Exception as e:
        logger.debug(f"Error calculating position for HIP {hip_id}: {e}")
        return None

def load_stellarium_constellations() -> list | None:
    """Load Stellarium constellation data from local file"""
    if os.path.exists(STELLARIUM_CONSTELLATION_PATH):
        try:
            with open(STELLARIUM_CONSTELLATION_PATH, 'rb') as f:
                return stellarium.parse_constellations(f)
        except Exception as e:
            logger.error(f"Failed to parse Stellarium constellations: {e}")
    return None

def compute_constellations(lat, lon, elevation, dt_utc):
    """
    Berechnet Constellations mit alter Architektur (Fallback)
    
    Args:
        lat, lon, elevation: Location
        dt_utc: datetime object
        
    Returns:
        Result dict
    """
    init_skyfield()
    
    # Calculate constellation data using Skyfield
    skyfield_time = GLOBAL_TS.from_datetime(dt_utc)
    earth = GLOBAL_EPH['earth']
    from skyfield.toposlib import wgs84
    observer_location = earth + wgs84.latlon(lat, lon, elevation_m=elevation)
    
    constellations = []
    
    # Load Stellarium constellation data
    stellarium_data = load_stellarium_constellations()
    if not stellarium_data or hip_data is None:
        return {"constellations": [], "location": {'latitude': lat, 'longitude': lon, 'elevation': elevation}, "time": dt_utc.isoformat(), "count": 0}
    
    # Process Stellarium constellations
    for code, edges in stellarium_data:
        full_name = STELLARIUM_CODE_TO_NAME.get(code)
        if full_name not in CONSTELLATION_NAMES:
            continue
            
        constellation = {
            'name': full_name,
            'name_de': CONSTELLATION_TRANSLATIONS.get(full_name, full_name),
            'stars': [],
            'lines': [[a, b] for (a, b) in edges],
            'boundary_ra': [0, 0],
            'boundary_dec': [0, 0],
        }
        
        # Gather unique star IDs from edges
        star_ids = set()
        for a, b in edges:
            star_ids.add(a)
            star_ids.add(b)
            
        # Calculate star positions
        for hip_id in star_ids:
            star_pos = get_star_position(hip_id, observer_location, skyfield_time)
            if not star_pos:
                continue
            altitude, azimuth, magnitude = star_pos
            constellation['stars'].append({
                'hip_id': hip_id,
                'altitude': altitude,
                'azimuth': azimuth,
                'magnitude': magnitude,
                'visible': altitude > -10,
            })
        constellations.append(constellation)
        
    return {
        'constellations': constellations,
        'location': {'latitude': lat, 'longitude': lon, 'elevation': elevation},
        'time': dt_utc.isoformat(),
        'count': len(constellations)
    }


@router.get("/zodiac")
async def get_zodiac_constellations(
    lat: float = Query(..., description="Latitude in degrees"),
    lon: float = Query(..., description="Longitude in degrees"), 
    elevation: float = Query(0, description="Elevation in meters"),
    time: str | None = Query(None, description="ISO time string (optional)"),
    nocache: bool | None = Query(False, description="Bypass cached zodiac result")
):
    """Get zodiac constellation data with calculated star positions"""
    
    try:
        dt_utc = parse_time_param(time)
        
        # Zodiac calculations are fast, no caching needed
        result = await asyncio.to_thread(compute_constellations, lat, lon, elevation, dt_utc)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in zodiac endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!s}")
