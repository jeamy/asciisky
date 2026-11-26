"""
Zodiac constellation API endpoint
"""
import asyncio
import logging
import os
import threading

from fastapi import APIRouter, HTTPException, Query
from skyfield.api import Star
from skyfield.data import hipparcos, stellarium
from skyfield.toposlib import wgs84

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

# Catalogs loaded once per process; the lock keeps concurrent first requests
# from loading them twice (the endpoint runs in worker threads).
_catalog_lock = threading.Lock()
hip_data = None
_constellation_edges: list | None = None


def init_skyfield():
    """Load the Hipparcos catalog and the Stellarium figures once."""
    global hip_data, _constellation_edges
    if hip_data is not None and _constellation_edges is not None:
        return
    with _catalog_lock:
        if hip_data is None:
            try:
                with LOADER.open(hipparcos.URL) as f:
                    hip_data = hipparcos.load_dataframe(f)
            except Exception as e:
                logger.error("Failed to load Hipparcos catalog: %s", e)
        if _constellation_edges is None:
            _constellation_edges = load_stellarium_constellations()


def load_stellarium_constellations() -> list | None:
    """Load Stellarium constellation data from the local file."""
    if os.path.exists(STELLARIUM_CONSTELLATION_PATH):
        try:
            with open(STELLARIUM_CONSTELLATION_PATH, 'rb') as f:
                return stellarium.parse_constellations(f)
        except Exception as e:
            logger.error("Failed to parse Stellarium constellations: %s", e)
    return None


def _star_positions(hip_ids: set[int], observer_location, time) -> dict[int, tuple[float, float, float]]:
    """Altitude, azimuth and magnitude of the given Hipparcos stars in one vector call."""
    known = [h for h in hip_ids if h in hip_data.index]
    if not known:
        return {}
    rows = hip_data.loc[known]
    rows = rows[rows['ra_degrees'].notna() & rows['dec_degrees'].notna()]
    if rows.empty:
        return {}
    stars = Star.from_dataframe(rows)
    alt, az, _ = observer_location.at(time).observe(stars).apparent().altaz()
    magnitudes = rows['magnitude'].fillna(5.0).to_numpy()
    return {
        int(hip): (float(a), float(z), float(m))
        for hip, a, z, m in zip(rows.index, alt.degrees, az.degrees, magnitudes)
    }


def compute_constellations(lat, lon, elevation, dt_utc):
    """Constellation figures with the current altitude/azimuth of their stars."""
    init_skyfield()
    location = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
    if not _constellation_edges or hip_data is None:
        return {"constellations": [], "location": location, "time": dt_utc.isoformat(), "count": 0}

    selected = []
    star_ids: set[int] = set()
    for code, edges in _constellation_edges:
        full_name = STELLARIUM_CODE_TO_NAME.get(code)
        if full_name not in CONSTELLATION_NAMES:
            continue
        selected.append((full_name, edges))
        for a, b in edges:
            star_ids.add(a)
            star_ids.add(b)

    observer_location = GLOBAL_EPH['earth'] + wgs84.latlon(lat, lon, elevation_m=elevation)
    positions = _star_positions(star_ids, observer_location, GLOBAL_TS.from_datetime(dt_utc))

    constellations = []
    for full_name, edges in selected:
        ids = sorted({hip for edge in edges for hip in edge})
        stars = []
        for hip_id in ids:
            pos = positions.get(hip_id)
            if pos is None:
                logger.debug("HIP %s not available in Hipparcos data", hip_id)
                continue
            altitude, azimuth, magnitude = pos
            stars.append({
                'hip_id': hip_id,
                'altitude': altitude,
                'azimuth': azimuth,
                'magnitude': magnitude,
                'visible': altitude > -10,
            })
        constellations.append({
            'name': full_name,
            'name_de': CONSTELLATION_TRANSLATIONS.get(full_name, full_name),
            'stars': stars,
            'lines': [[a, b] for (a, b) in edges],
            'boundary_ra': [0, 0],
            'boundary_dec': [0, 0],
        })

    return {
        'constellations': constellations,
        'location': location,
        'time': dt_utc.isoformat(),
        'count': len(constellations),
    }


@router.get("/zodiac")
async def get_zodiac_constellations(
    lat: float = Query(..., description="Latitude in degrees"),
    lon: float = Query(..., description="Longitude in degrees"), 
    elevation: float = Query(0, description="Elevation in meters"),
    time: str | None = Query(None, description="ISO time string (optional)"),
):
    """Get zodiac constellation data with calculated star positions"""
    
    try:
        dt_utc = parse_time_param(time)
        
        result = await asyncio.to_thread(compute_constellations, lat, lon, elevation, dt_utc)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in zodiac endpoint")
        raise HTTPException(status_code=500, detail="Internal server error") from e
