"""
Zodiac constellation API endpoint
"""
import os
import logging
from typing import Dict, List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Query
from skyfield.api import load, Star
from skyfield.data import hipparcos, stellarium
from skyfield.positionlib import Apparent
import numpy as np
from datetime import datetime, timezone

from api.helpers import get_location_params, get_cache_data, store_cache_data
from cache_utils import build_cache_path, time_bucket_utc

# Constants
STELLARIUM_CONSTELLATION_PATH = '/app/cache/constellations/constellationship.fab'

ZODIAC_NAMES = [
    'Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo',
    'Libra', 'Scorpius', 'Sagittarius', 'Capricornus', 'Aquarius', 'Pisces'
]

ZODIAC_TRANSLATIONS = {
    'Aries': 'Widder', 'Taurus': 'Stier', 'Gemini': 'Zwillinge',
    'Cancer': 'Krebs', 'Leo': 'Löwe', 'Virgo': 'Jungfrau',
    'Libra': 'Waage', 'Scorpius': 'Skorpion', 'Sagittarius': 'Schütze',
    'Capricornus': 'Steinbock', 'Aquarius': 'Wassermann', 'Pisces': 'Fische'
}

STELLARIUM_CODE_TO_NAME = {
    'Ari': 'Aries', 'Tau': 'Taurus', 'Gem': 'Gemini', 'Cnc': 'Cancer',
    'Leo': 'Leo', 'Vir': 'Virgo', 'Lib': 'Libra', 'Sco': 'Scorpius',
    'Sgr': 'Sagittarius', 'Cap': 'Capricornus', 'Aqr': 'Aquarius', 'Psc': 'Pisces'
}

router = APIRouter()
logger = logging.getLogger(__name__)

# Global Skyfield objects
ts = None
eph = None
hip_data = None

def init_skyfield():
    """Initialize Skyfield objects"""
    global ts, eph, hip_data
    
    if ts is not None:
        return  # Already initialized
    
    try:
        ts = load.timescale()
        eph = load('de421.bsp')
        
        # Load Hipparcos catalog
        try:
            with load.open(hipparcos.URL) as f:
                hip_data = hipparcos.load_dataframe(f)
        except Exception:
            hip_data = None
            
    except Exception as e:
        logger.error(f"Failed to initialize Skyfield: {e}")
        ts = None
        eph = None

def get_star_position(hip_id: int, observer_location, time) -> Optional[Tuple[float, float, float]]:
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

        # Fallback: known RA/Dec for bright zodiac stars
        if hip_id in KNOWN_STAR_COORDINATES:
            ra_hours, dec_degrees, mag = KNOWN_STAR_COORDINATES[hip_id]
            star = Star(ra_hours=ra_hours, dec_degrees=dec_degrees)
            apparent = observer_location.at(time).observe(star).apparent()
            alt, az, _ = apparent.altaz()
            return float(alt.degrees), float(az.degrees), float(mag)

        logger.debug(f"HIP {hip_id} not available in hip_data and no fallback coordinates found")
        return None
        
    except Exception as e:
        logger.debug(f"Error calculating position for HIP {hip_id}: {e}")
        return None

def load_stellarium_constellations() -> Optional[List]:
    """Load Stellarium constellation data from local file"""
    if os.path.exists(STELLARIUM_CONSTELLATION_PATH):
        try:
            with open(STELLARIUM_CONSTELLATION_PATH, 'rb') as f:
                return stellarium.parse_constellations(f)
        except Exception as e:
            logger.error(f"Failed to parse Stellarium constellations: {e}")
    return None

@router.get("/zodiac")
async def get_zodiac_constellations(
    lat: float = Query(..., description="Latitude in degrees"),
    lon: float = Query(..., description="Longitude in degrees"), 
    elevation: float = Query(0, description="Elevation in meters"),
    time: Optional[str] = Query(None, description="ISO time string (optional)")
):
    """Get zodiac constellation data with calculated star positions"""
    
    # Initialize Skyfield if needed
    if ts is None:
        init_skyfield()
        
    if ts is None:
        raise HTTPException(status_code=500, detail="Skyfield initialization failed")
    
    try:
        # Parse time parameter
        if time:
            try:
                if time.endswith('Z'):
                    dt_utc = datetime.fromisoformat(time[:-1]).replace(tzinfo=timezone.utc)
                else:
                    dt_utc = datetime.fromisoformat(time).replace(tzinfo=timezone.utc)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid time format")
        else:
            dt_utc = datetime.now(timezone.utc)
        
        # Check cache first
        cache_path = build_cache_path(str(lat), str(lon), str(elevation), time_bucket_utc(dt_utc))
        cached_result = get_cache_data(cache_path, 'zodiac')
        if cached_result:
            return cached_result
            
        # Calculate constellation data using Skyfield
        skyfield_time = ts.from_datetime(dt_utc)
        earth = eph['earth']
        from skyfield.toposlib import wgs84
        observer_location = earth + wgs84.latlon(lat, lon, elevation_m=elevation)
        
        constellations = []
        
        # Load Stellarium constellation data
        stellarium_data = load_stellarium_constellations()
        if not stellarium_data or hip_data is None:
            return {"constellations": []}
        
        # Process Stellarium constellations
        for code, edges in stellarium_data:
            full_name = STELLARIUM_CODE_TO_NAME.get(code)
            if full_name not in ZODIAC_NAMES:
                continue
                
            constellation = {
                'name': full_name,
                'name_de': ZODIAC_TRANSLATIONS.get(full_name, full_name),
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
            
        result = {
            'constellations': constellations,
            'location': {'latitude': lat, 'longitude': lon, 'elevation': elevation},
            'time': dt_utc.isoformat(),
            'count': len(constellations)
        }
        
        # Store in cache
        store_cache_data(result, cache_path)
        return result
        
    except Exception as e:
        logger.error(f"Error in zodiac endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Initialize Skyfield when module is loaded
init_skyfield()