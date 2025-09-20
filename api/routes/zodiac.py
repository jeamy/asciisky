"""
Zodiac constellation API endpoint for ASCII Sky.
Provides zodiac constellation data with star positions calculated using Skyfield.
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
from zodiac_data import ZODIAC_CONSTELLATIONS, ZODIAC_TRANSLATIONS, KNOWN_STAR_COORDINATES

router = APIRouter()
logger = logging.getLogger(__name__)

# Global Skyfield objects
ts = None
eph = None
hip_data = None
constellations_data = None
star_names = None

def init_skyfield():
    """Initialize Skyfield objects for zodiac calculations"""
    global ts, eph, hip_data, constellations_data, star_names
    
    try:
        # Load time scale and ephemeris
        ts = load.timescale()
        eph = load('de421.bsp')
        
        # Load Hipparcos catalog
        try:
            with load.open(hipparcos.URL) as f:
                hip_data = hipparcos.load_dataframe(f)
            logger.info(f"Loaded Hipparcos catalog with {len(hip_data)} stars")
        except Exception as hip_error:
            logger.warning(f"Could not load Hipparcos catalog: {hip_error}")
            hip_data = None
        
        # Try to load Stellarium constellation outlines using Skyfield-provided paths first
        def try_load_skyfield_stellarium() -> Optional[list]:
            attrs = (
                'CONSTELLATION_PATH', 'CONSTELLATIONS_PATH',
                'CONSTELLATION_URL', 'CONSTELLATIONS_URL'
            )
            for attr in attrs:
                try:
                    if hasattr(stellarium, attr):
                        target = getattr(stellarium, attr)
                        with load.open(target) as f:
                            return stellarium.parse_constellations(f)
                except Exception as e:
                    logger.warning(f"Failed loading Stellarium outlines via {attr}: {e}")
            return None

        # If that fails, try to load from a local file (NEOWISE approach)
        # We look in a few common locations inside the container/project.
        def try_load_local_stellarium() -> Optional[list]:
            search_paths = [
                os.path.join(os.getcwd(), 'data', 'constellations', 'constellationship.fab'),
                os.path.join(os.getcwd(), 'static', 'data', 'constellationship.fab'),
                os.path.join('/app', 'data', 'constellations', 'constellationship.fab'),
                os.path.join('/app', 'static', 'data', 'constellationship.fab'),
            ]
            for p in search_paths:
                try:
                    if os.path.exists(p):
                        with open(p, 'r', encoding='utf-8') as f:
                            return stellarium.parse_constellations(f)
                except Exception as e:
                    logger.warning(f"Failed parsing Stellarium constellations at {p}: {e}")
            return None

        constellations = try_load_skyfield_stellarium()
        if not constellations:
            constellations = try_load_local_stellarium()
        if constellations:
            constellations_data = constellations
            logger.info(f"Loaded {len(constellations_data)} Stellarium constellation outlines from local file")
        else:
            constellations_data = None
            logger.info("No local Stellarium constellationship.fab found; will fall back to zodiac_data definitions")
        
        # Load star names
        try:
            url = 'https://raw.githubusercontent.com/astronexus/HYG-Database/master/hygdata_v3.csv'
            # For now, we'll use a simpler approach with known zodiac stars
            star_names = {}
            logger.info("Star names system initialized")
        except Exception as names_error:
            logger.warning(f"Could not load star names: {names_error}")
            star_names = {}
            
    except Exception as e:
        logger.error(f"Failed to initialize Skyfield for zodiac: {e}")

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

@router.get("/zodiac")
async def get_zodiac_constellations(
    lat: Optional[float] = Query(None, description="Latitude in degrees"),
    lon: Optional[float] = Query(None, description="Longitude in degrees"), 
    elevation: Optional[float] = Query(None, description="Elevation in meters"),
    time: Optional[str] = Query(None, description="ISO 8601 time string")
):
    """Get zodiac constellation data with calculated star positions"""
    
    # Initialize Skyfield if needed
    if ts is None:
        init_skyfield()
        
    if ts is None:
        raise HTTPException(status_code=500, detail="Skyfield initialization failed")
    
    try:
        # Get location parameters - use direct values or defaults
        if lat is None or lon is None or elevation is None:
            import settings
            location_settings = settings.get_location()
            lat = lat if lat is not None else location_settings["latitude"]
            lon = lon if lon is not None else location_settings["longitude"]
            elevation = elevation if elevation is not None else location_settings["elevation"]
        
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
            
        # Check cache
        cache_path = build_cache_path('zodiac', lat, lon, elevation, dt=dt_utc, bucket_hours=1)
        cache_ttl = 3600  # 1 hour TTL
        
        cached_data = get_cache_data(cache_path, cache_ttl)
        if cached_data:
            return cached_data
            
        # Calculate constellation data using Skyfield
        skyfield_time = ts.from_datetime(dt_utc)
        earth = eph['earth']
        from skyfield.toposlib import wgs84
        observer_location = earth + wgs84.latlon(lat, lon, elevation_m=elevation)
        
        constellations = []
        
        # Define zodiac constellation names (we only want these 12)
        zodiac_names = [
            'Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo',
            'Libra', 'Scorpius', 'Sagittarius', 'Capricornus', 'Aquarius', 'Pisces'
        ]
        
        zodiac_translations = {
            'Aries': 'Widder', 'Taurus': 'Stier', 'Gemini': 'Zwillinge',
            'Cancer': 'Krebs', 'Leo': 'Löwe', 'Virgo': 'Jungfrau',
            'Libra': 'Waage', 'Scorpius': 'Skorpion', 'Sagittarius': 'Schütze',
            'Capricornus': 'Steinbock', 'Aquarius': 'Wassermann', 'Pisces': 'Fische'
        }
        
        # Prefer official Stellarium constellation outlines if available; fallback to local zodiac_data
        outlines_used = False
        # Only use Stellarium outlines when we have Hipparcos data to resolve their HIP ids broadly
        # Otherwise fall back to local zodiac_data (which has a curated set we can partially cover via KNOWN_STAR_COORDINATES)
        if constellations_data and hip_data is not None:
            # Map Stellarium 3-letter codes to full IAU names
            code_to_full = {
                'Ari': 'Aries', 'Tau': 'Taurus', 'Gem': 'Gemini', 'Cnc': 'Cancer',
                'Leo': 'Leo', 'Vir': 'Virgo', 'Lib': 'Libra', 'Sco': 'Scorpius',
                'Sgr': 'Sagittarius', 'Cap': 'Capricornus', 'Aqr': 'Aquarius', 'Psc': 'Pisces'
            }
            # stellarium.parse_constellations returns: [(code, [(hip1, hip2), ...]), ...]
            for code, edges in constellations_data:
                full = code_to_full.get(code)
                if full not in zodiac_names:
                    continue
                constellation = {
                    'name': full,
                    'name_de': ZODIAC_TRANSLATIONS.get(full, full),
                    'stars': [],
                    'lines': [[a, b] for (a, b) in edges],
                    'boundary_ra': [0, 0],  # not used by frontend
                    'boundary_dec': [0, 0],
                }
                # Gather unique hip ids from edges
                star_ids = set()
                for a, b in edges:
                    star_ids.add(a)
                    star_ids.add(b)
                # Compute positions with Skyfield
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
                outlines_used = True

        if not outlines_used:
            logger.info("Falling back to zodiac_data definitions")
            for const_name, const_data in ZODIAC_CONSTELLATIONS.items():
                constellation = {
                    'name': const_name,
                    'name_de': ZODIAC_TRANSLATIONS.get(const_name, const_name),
                    'stars': [],
                    'lines': const_data['lines'],
                    'boundary_ra': const_data['boundary_ra'],
                    'boundary_dec': const_data['boundary_dec']
                }
                for hip_id in const_data['stars']:
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
            'location': {
                'latitude': lat,
                'longitude': lon,
                'elevation': elevation
            },
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