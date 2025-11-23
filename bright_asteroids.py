"""
Module for calculating positions of bright minor planets (asteroids)
"""
from pathlib import Path

from skyfield.api import Topos, Loader
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2
import pandas as pd
from skyfield import almanac
import numpy as np
import os
import time
from datetime import datetime, timedelta, timezone
import gzip
import urllib.request
from skyfield.data import mpc
import math
from types import SimpleNamespace
from typing import Optional
import pickle
from cache_utils import normalize_location, location_key, time_bucket_utc
from db_utils import get_asteroid_dataframe
from timezone_utils import get_tzinfo
from db_utils import (
    store_asteroid_dataframe, store_asteroid_positions,
    get_asteroid_positions
)
from data_paths import DATA_DIR, DE421_PATH, MPCORB_PATH

# Konstanten
MPCORB_FILE = Path(MPCORB_PATH)
MPCORB_URL = 'https://www.minorplanetcenter.net/iau/MPCORB/MPCORB.DAT.gz'
MAX_ASTEROIDS = 5000
# Magnitude thresholds (restored defaults)
# H-limit for prefiltering by absolute magnitude (smaller = brighter)
MAX_ABSOLUTE_MAGNITUDE = float(os.environ.get('ASCII_SKY_ASTEROID_MAX_ABSOLUTE_MAG', '12.0'))
# V-limit for final apparent magnitude filtering
MAX_APPARENT_MAGNITUDE = float(os.environ.get('ASCII_SKY_ASTEROID_MAX_APPARENT_MAG', '10.0'))
# Gravitationskonstante der Sonne für Skyfield
GM_SUN = 1.32712440041e20

# Cache-Gültigkeitsdauer in Stunden
CACHE_VALIDITY_HOURS = 12

# Module-specific cache granularity for per-location/time asteroid list
# Use a 1-hour time bucket; TTL must cover the 30-day precompute window
# so that snapshots created up to 30 days earlier remain valid.
ASTEROID_CACHE_BUCKET_HOURS = 1
ASTEROID_CACHE_TTL_SECONDS = 31 * 24 * 3600  # 31 days
# Cache kind for consistency with celestial/comets naming
ASTEROID_CACHE_KIND = 'asteroids'

# Limit number of event computations (rise/set/transit) per request to reduce CPU peaks
ASTEROIDS_EVENTS_MAX = int(os.environ.get('ASCII_SKY_ASTEROIDS_EVENTS_MAX', '50'))

# In-memory cache for asteroid DataFrame
_asteroid_df_cache = None
_asteroid_df_timestamp = None
ASTEROID_DF_CACHE_TTL_SECONDS = 49 * 3600  # 49 hours (matches positions cache TTL)

def clear_in_memory_cache():
    """Clear in-memory DataFrame cache - called when filters change"""
    global _asteroid_df_cache, _asteroid_df_timestamp
    _asteroid_df_cache = None
    _asteroid_df_timestamp = None
    print("Cleared asteroid in-memory DataFrame cache")


def load_asteroid_dataframe(use_cache: bool = True) -> pd.DataFrame:
    """Return cached asteroid DataFrame from filesystem (pickle).

    Mirrors comets.load_comet_dataframe so workers can pre-load data reliably.
    """
    global _asteroid_df_cache, _asteroid_df_timestamp

    if use_cache and _asteroid_df_cache is not None and _asteroid_df_timestamp is not None:
        age_seconds = (datetime.now(timezone.utc) - _asteroid_df_timestamp).total_seconds()
        if age_seconds < ASTEROID_DF_CACHE_TTL_SECONDS:
            return _asteroid_df_cache

    df_pickle = get_asteroid_dataframe()
    if not df_pickle:
        raise RuntimeError("Asteroid DataFrame cache missing. Run nightly_data_updater first.")

    df = pickle.loads(df_pickle)
    if not isinstance(df, pd.DataFrame):
        raise ValueError("Asteroid DataFrame pickle did not contain a pandas DataFrame")

    _asteroid_df_cache = df
    _asteroid_df_timestamp = datetime.now(timezone.utc)
    return df

def format_time(dt, tz=None):
    """
    Formatiert ein datetime-Objekt als lokale Zeit im Format 'HH:MM'.
    Gibt None zurück, wenn dt None ist.
    Wenn tz übergeben wird, wird in diese Zeitzone konvertiert. Naive dt
    wird als UTC interpretiert.
    """
    if dt is None:
        return None
    # Stelle sicher, dass dt tz-aware ist (interpretiere naive als UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if tz is None:
        local_time = dt.astimezone()
    else:
        local_time = dt.astimezone(tz)
    return f"{local_time.hour:02d}:{local_time.minute:02d}"

# IAU H-G asteroid magnitude system
def asteroid_apparent_magnitude(H, G, r, delta, phase_angle_deg):
    """
    Compute apparent V magnitude using the IAU H-G phase function.
    V = H + 5 log10(r * delta) - 2.5 log10((1 - G) * Phi1 + G * Phi2)
    with Phi1 = exp(-3.33 * tan(alpha/2)^0.63) and Phi2 = exp(-1.87 * tan(alpha/2)^1.22)
    """
    try:
        alpha = math.radians(phase_angle_deg)
        tan_half = math.tan(alpha / 2.0)
        # Phase functions
        phi1 = math.exp(-3.33 * (tan_half ** 0.63))
        phi2 = math.exp(-1.87 * (tan_half ** 1.22))
        # Avoid log of zero
        flux_term = max((1.0 - float(G)) * phi1 + float(G) * phi2, 1e-12)
        value = float(H) + 5.0 * math.log10(max(r * delta, 1e-12)) - 2.5 * math.log10(flux_term)
        return value
    except Exception:
        # Conservative fallback if anything goes wrong
        return float(H) + 5.0 * math.log10(max(r * delta, 1e-12))

def vectorized_asteroid_apparent_magnitude(H, G, r, delta, phase_angle_deg):
    """
    Compute apparent V magnitude using the IAU H-G phase function (vectorized).
    V = H + 5 log10(r * delta) - 2.5 log10((1 - G) * Phi1 + G * Phi2)
    
    Args:
        H: Absolute magnitude (array)
        G: Slope parameter (array)
        r: Heliocentric distance in AU (array)
        delta: Geocentric distance in AU (array)
        phase_angle_deg: Phase angle in degrees (array)
    
    Returns:
        Apparent magnitude (array)
    """
    alpha = np.radians(phase_angle_deg)
    tan_half = np.tan(alpha / 2.0)
    
    # Phase functions (ensure base is non-negative)
    tan_half_safe = np.maximum(tan_half, 0)
    phi1 = np.exp(-3.33 * (tan_half_safe ** 0.63))
    phi2 = np.exp(-1.87 * (tan_half_safe ** 1.22))
    
    # Flux term
    flux_term = (1.0 - G) * phi1 + G * phi2
    
    # Avoid log of zero
    flux_term = np.maximum(flux_term, 1e-12)
    distance_term = np.maximum(r * delta, 1e-12)
    
    value = H + 5.0 * np.log10(distance_term) - 2.5 * np.log10(flux_term)
    return value

def download_mpcorb_file():
    """
    Lädt die MPCORB.DAT.gz-Datei von der Minor Planet Center-Website herunter
    """
    try:
        print(f"Downloading MPCORB.DAT.gz from {MPCORB_URL}...")
        # Stelle sicher, dass das Verzeichnis existiert
        MPCORB_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Datei herunterladen mit Fortschrittsanzeige
        print("Starting download...")
        with urllib.request.urlopen(MPCORB_URL, timeout=300) as response, MPCORB_FILE.open('wb') as out_file:
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
        if MPCORB_FILE.exists() and MPCORB_FILE.stat().st_size > 0:
            print(f"File size: {MPCORB_FILE.stat().st_size / (1024*1024):.1f} MB")
            return True
        else:
            print("Download failed: File is empty or does not exist")
            return False
    except Exception as e:
        print(f"Error downloading MPCORB.DAT.gz: {e}")
        return False
    return True

def should_update_mpcorb_file():
    """
    Überprüft ob MPCORB-Datei aktualisiert werden sollte (täglich)
    
    NOTE: Daily updates are now handled by nightly_data_updater.py at 2:00 AM.
    This function is kept for manual/utility purposes only.
    """
    if not MPCORB_FILE.exists():
        return True
    
    # Prüfe Alter der Datei
    file_age = time.time() - MPCORB_FILE.stat().st_mtime
    # Aktualisiere täglich (24 Stunden = 86400 Sekunden)
    return file_age > 86400

def load_bright_asteroids(loader, ts, eph, observer_location, max_magnitude=MAX_APPARENT_MAGNITUDE, use_cache=True, current_dt: Optional[datetime] = None, dataframe=None):
    """
    Load and calculate positions, magnitudes, and rise/set times of the brightest minor planets
    """
    if isinstance(observer_location, dict):
        lat, lon, elevation = observer_location.get('latitude', 0.0), observer_location.get('longitude', 0.0), observer_location.get('elevation', 0.0)
    else:
        try:
            lat, lon, elevation = observer_location.latitude.degrees, observer_location.longitude.degrees, observer_location.elevation.m
        except AttributeError:
            print("Warning: Could not extract location data from observer_location")
            lat, lon, elevation = 0.0, 0.0, 0.0

    print(f"Getting asteroids with magnitude <= {max_magnitude} at lat={lat}, lon={lon}, elevation={elevation}.")
    # Determine observer timezone from coordinates
    tz = get_tzinfo(lat, lon)

    # Check PostgreSQL cache
    if use_cache:
        # PostgreSQL backend: check for cached positions
        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        time_bucket = time_bucket_utc(current_dt, ASTEROID_CACHE_BUCKET_HOURS)
        
    # --- PostgreSQL Loading (ONLY source) ---
    import pickle
    
    try:
        # Use provided dataframe if available (Worker Optimization)
        if dataframe is not None:
            df = dataframe
            # print(f"Using pre-loaded dataframe with {len(df)} asteroids")
        else:
            df_pickle = get_asteroid_dataframe()
            if not df_pickle:
                print("ERROR: No asteroids in PostgreSQL database! Run data_updater first.")
                return []
            
            df = pickle.loads(df_pickle)
            print(f"Loaded {len(df)} asteroids from PostgreSQL database")
        
        # Step 1: Filter by absolute magnitude
        df_filtered = df[df['magnitude_H'] <= MAX_ABSOLUTE_MAGNITUDE].copy()
        df_filtered = df_filtered.sort_values('magnitude_H')
        print(f"Step 1: Filtered to {len(df_filtered)} asteroids with H <= {MAX_ABSOLUTE_MAGNITUDE}")
        
        # Step 2: NumPy Pre-Filter - Rough apparent magnitude estimation
        # Typical distances: r=2.5 AU (heliocentric), delta=1.5 AU (geocentric)
        H_array = df_filtered['magnitude_H'].values
        r_typical = 2.5  # AU
        delta_typical = 1.5  # AU
        rough_apparent_mag = H_array + 5 * np.log10(r_typical * delta_typical)
        
        # Keep only objects that could be brighter than max_magnitude + 3.0 margin
        # (margin accounts for variation in actual distances)
        bright_enough = rough_apparent_mag <= (max_magnitude + 3.0)
        df_filtered = df_filtered[bright_enough].copy()
        print(f"Step 2: NumPy pre-filter kept {len(df_filtered)} candidates (rough mag <= {max_magnitude + 3.0})")
        
        # Step 3: Limit to reasonable number for processing
        df_filtered = df_filtered.head(MAX_ASTEROIDS * 2)
        print(f"Step 3: Limited to {len(df_filtered)} asteroids for processing")
        
    except Exception as e:
        print(f"ERROR: Cannot connect to PostgreSQL database: {e}")
        print("Make sure POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD are set correctly.")
        return []

    # Process asteroids from DataFrame
    if df_filtered is not None and not df_filtered.empty:
        # Process DataFrame directly (same logic as before)
        from skyfield.data import mpc
        from skyfield.toposlib import Topos
        from skyfield import almanac

        # Use passed parameters (don't create new ones!)
        return _compute_asteroids_vectorized(
            df_filtered=df_filtered,
            ts=ts,
            eph=eph,
            lat=lat,
            lon=lon,
            elevation=elevation,
            max_magnitude=max_magnitude,
            use_cache=use_cache,
            current_dt=current_dt,
            tz=tz,
        )
    else:
        # No data available
        return []

    # --- Calculations ---
    # Use simulated time if provided; else current UTC
    dt_utc = current_dt or datetime.now(timezone.utc)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    t = ts.from_datetime(dt_utc)
    topos = Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=elevation)
    observer = eph['earth'] + topos
    sun = eph['sun']
    
    try:
        df.dropna(subset=['magnitude_H'], inplace=True)
        candidates_df = df[df['magnitude_H'] < MAX_ABSOLUTE_MAGNITUDE].copy()
        print(f"Found {len(candidates_df)} candidates with H < {MAX_ABSOLUTE_MAGNITUDE}")

        apparent_magnitudes = []
        for index, row in candidates_df.iterrows():
            try:
                orbit = mpc.mpcorb_orbit(row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)
                # Build barycentric target (explicit center check)
                center_code = int(getattr(orbit, 'center', 10))
                target = (sun + orbit) if center_code != 0 else orbit

                astrometric = observer.at(t).observe(target)
                # Distances
                delta = astrometric.distance().au
                sun_vec = sun.at(t).observe(target)
                r = sun_vec.distance().au
                phase_angle = astrometric.phase_angle(sun).degrees
                # Compute apparent magnitude using IAU H-G model
                apparent_mag = asteroid_apparent_magnitude(
                    H=row['magnitude_H'], G=row['magnitude_G'], r=r, delta=delta, phase_angle_deg=phase_angle
                )
                apparent_magnitudes.append(apparent_mag)
            except Exception as e:
                print(f"  - Error processing {row.get('designation', 'N/A')}: {e}")
                apparent_magnitudes.append(float('inf'))
        
        candidates_df['apparent_magnitude'] = apparent_magnitudes
        # Cache with mag 20.0 to include all asteroids, filtering happens in API route
        bright_df = candidates_df[candidates_df['apparent_magnitude'] <= 20.0].sort_values('apparent_magnitude')
        top_df = bright_df.head(MAX_ASTEROIDS)
        print(f"Found {len(top_df)} asteroids with apparent mag <= 20.0 (user filter: {max_magnitude})")

        asteroid_list = []
        events_computed = 0
        for index, row in top_df.iterrows():
            try:
                orbit = mpc.mpcorb_orbit(row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)
                # Build barycentric target (explicit center check)
                center_code = int(getattr(orbit, 'center', 10))
                target = (sun + orbit) if center_code != 0 else orbit
                astrometric = observer.at(t).observe(target)
                apparent = astrometric.apparent()
                ra, dec, distance = apparent.radec()
                alt, az, _ = apparent.altaz()

                # Event times limited to reduce CPU
                rise_time, set_time, transit_time = None, None, None
                if events_computed < ASTEROIDS_EVENTS_MAX:
                    # Start/end window anchored at simulated day's UTC midnight
                    start_time = ts.utc(t.utc_datetime().replace(hour=0, minute=0, second=0, microsecond=0))
                    end_time = ts.utc(start_time.utc_datetime() + timedelta(days=2))
                    rise_set_func = almanac.risings_and_settings(eph, target, topos)
                    times, events = almanac.find_discrete(start_time, end_time, rise_set_func)
                    
                    for ti, event in zip(times, events):
                        if event == 1 and rise_time is None: rise_time = ti.utc_datetime()
                        elif event == 0 and set_time is None: set_time = ti.utc_datetime()
                    # Bestimme die nächste Nacht (Rise->Set) nach dt_utc als Fenster für die obere Kulmination
                    night_start_utc, night_end_utc = None, None
                    last_rise_utc = None
                    for ti_rs, ev_rs in zip(times, events):
                        ev_dt_utc = ti_rs.utc_datetime().replace(tzinfo=timezone.utc)
                        if ev_rs == 1:  # rise
                            last_rise_utc = ev_dt_utc
                        elif ev_rs == 0 and last_rise_utc is not None:  # set paired with last rise
                            # wähle das erste Rise->Set Paar, dessen Set in der Zukunft liegt
                            if ev_dt_utc >= (dt_utc if dt_utc.tzinfo else dt_utc.replace(tzinfo=timezone.utc)):
                                night_start_utc, night_end_utc = last_rise_utc, ev_dt_utc
                                break
                    if night_start_utc is None or night_end_utc is None:
                        # Fallback: benutze die zuerst gefundenen rise/set Zeiten, wenn vorhanden
                        night_start_utc, night_end_utc = rise_time, set_time
                    
                    f = almanac.meridian_transits(eph, target, topos)
                    t_times, t_events = almanac.find_discrete(start_time, end_time, f)
                    # Wähle die nächste obere Kulmination innerhalb des Nachtfensters (UTC-basiert)
                    chosen_time_utc = None
                    if len(t_times):
                        now_utc = dt_utc if dt_utc.tzinfo is not None else dt_utc.replace(tzinfo=timezone.utc)
                        candidates = []
                        for ti, ev in zip(t_times, t_events):
                            utc_dt = ti.utc_datetime().replace(tzinfo=timezone.utc)
                            # Altitude am Transit-Zeitpunkt bestimmen (höher = obere Kulmination)
                            try:
                                alt_deg = observer.at(ti).observe(target).apparent().altaz()[0].degrees
                            except Exception:
                                alt_deg = float('-inf')
                            candidates.append((utc_dt, alt_deg, int(ev)))
                        # Filtere auf das Nachtfenster (falls vorhanden)
                        if night_start_utc is not None and night_end_utc is not None:
                            pool = [c for c in candidates if c[0] >= night_start_utc and c[0] <= night_end_utc]
                        else:
                            # Bevorzuge zukünftige Ereignisse
                            pool = [c for c in candidates if c[0] >= now_utc]
                            if not pool:
                                pool = candidates
                        if pool:
                            pool.sort(key=lambda x: (-x[1], x[0]))
                            chosen_time_utc = pool[0][0]
                    transit_time = chosen_time_utc
                    events_computed += 1

                asteroid_list.append({
                    "name": row['designation'], "number": str(row.name),
                    "magnitude": round(float(row['apparent_magnitude']), 1),
                    "ra": ra.hours * 15.0, "dec": dec.degrees,
                    "altitude": alt.degrees, "azimuth": az.degrees,
                    "distance": round(distance.au, 3), "rise_time": format_time(rise_time, tz),
                    "set_time": format_time(set_time, tz), "transit_time": format_time(transit_time, tz),
                    "type": "asteroid", "symbol": "⚸"  # Unicode U+26B8 (Asteroid)
                })
            except Exception as e:
                print(f"Error in final processing for {row['designation']}: {e}")
                continue
        
        return asteroid_list

    except Exception as e:
        print(f"An unexpected error occurred during asteroid calculation: {e}")
        return []


def _timescale_from_datetimes(ts, times_dt):
    if hasattr(ts, "from_datetimes"):
        return ts.from_datetimes(times_dt)
    years = [dt.year for dt in times_dt]
    months = [dt.month for dt in times_dt]
    days = [dt.day for dt in times_dt]
    hours = [dt.hour for dt in times_dt]
    minutes = [dt.minute for dt in times_dt]
    seconds = [dt.second + dt.microsecond / 1e6 for dt in times_dt]
    return ts.utc(years, months, days, hours, minutes, seconds)


def _compute_asteroids_vectorized(
    df_filtered,
    ts,
    eph,
    lat,
    lon,
    elevation,
    max_magnitude,
    use_cache,
    current_dt,
    tz,
):
    """Vectorized magnitude computation and final asteroid processing.

    This helper mirrors the logic of the existing final processing loop but uses
    vectorized_asteroid_apparent_magnitude to compute apparent magnitudes for
    all candidates in one step. The cache always stores objects up to a
    brightness of min(max_magnitude, 20.0); API routes may apply a stricter
    user filter on top of that.
    """

    # Use simulated time if provided; else current UTC
    dt_utc = current_dt or datetime.now(timezone.utc)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    t = ts.from_datetime(dt_utc)

    topos = Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=elevation)
    observer = eph['earth'] + topos
    sun = eph['sun']

    # Build orbits and initial observations, skipping rows that fail
    orbits = []
    targets = []
    observations = []
    index_map = {}

    for idx, row in df_filtered.iterrows():
        try:
            orbit = mpc.mpcorb_orbit(row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)
            center_code = int(getattr(orbit, "center", 10))
            target = (sun + orbit) if center_code != 0 else orbit
            astrometric = observer.at(t).observe(target)

            index_map[idx] = len(orbits)
            orbits.append(orbit)
            targets.append(target)
            observations.append(astrometric)
        except Exception:
            # Skip objects that fail during orbit or observation creation
            continue

    if not orbits:
        return []

    # Restrict DataFrame to successfully processed rows and keep order stable
    valid_indices = list(index_map.keys())
    candidates_df = df_filtered.loc[valid_indices].copy()

    # Extract distances and phase angles into NumPy arrays
    deltas = np.array([obs.distance().au for obs in observations])
    sun_observations = [sun.at(t).observe(target) for target in targets]
    rs = np.array([obs.distance().au for obs in sun_observations])
    phase_angles = np.array([obs.phase_angle(sun).degrees for obs in observations])

    # Prepare H and G arrays
    H_values = candidates_df["magnitude_H"].to_numpy()
    if "magnitude_G" in candidates_df.columns:
        G_values = candidates_df["magnitude_G"].fillna(0.15).to_numpy()
    else:
        G_values = np.full_like(H_values, 0.15, dtype=float)

    # Vectorized magnitude calculation (IAU H-G model)
    apparent_magnitudes = vectorized_asteroid_apparent_magnitude(
        H=H_values,
        G=G_values,
        r=rs,
        delta=deltas,
        phase_angle_deg=phase_angles,
    )

    candidates_df["apparent_magnitude"] = apparent_magnitudes

    # Cache limit: never exceed mag 20.0, but respect caller's max_magnitude if lower
    if max_magnitude is None:
        cache_limit = min(MAX_APPARENT_MAGNITUDE, 20.0)
    else:
        try:
            cache_limit = min(float(max_magnitude), 20.0)
        except Exception:
            cache_limit = 20.0

    bright_df = candidates_df[candidates_df["apparent_magnitude"] <= cache_limit].sort_values(
        "apparent_magnitude"
    )
    top_df = bright_df.head(MAX_ASTEROIDS)
    print(
        f"Found {len(top_df)} asteroids with apparent mag <= {cache_limit} (user filter: {max_magnitude})"
    )

    asteroid_list = []
    events_computed = 0

    # --- Vectorized Event Finding (Grid Search) ---
    # Create a time grid for the next 48 hours (5 minute steps)
    # This replaces the slow iterative find_discrete for each asteroid
    
    # Start/end window anchored at simulated day's UTC midnight
    start_time_ts = ts.utc(t.utc_datetime().replace(hour=0, minute=0, second=0, microsecond=0))
    end_time_ts = ts.utc(start_time_ts.utc_datetime() + timedelta(days=2))
    
    start_dt = start_time_ts.utc_datetime()
    end_dt = end_time_ts.utc_datetime()
    
    minutes_step = 5
    total_minutes = int((end_dt - start_dt).total_seconds() / 60)
    steps = total_minutes // minutes_step
    
    # Create time array
    times_dt = [start_dt + timedelta(minutes=i*minutes_step) for i in range(steps + 1)]
    t_grid = _timescale_from_datetimes(ts, times_dt)
    
    # Compute positions for all top asteroids at all times
    # We need to compute observer.at(t_grid).observe(target) for each target
    # Since we have N targets and M times, we loop over targets but vector over time
    # This is still much faster than find_discrete which iterates internally
    
    asteroid_list = []
    
    # Pre-calculate horizon for rise/set (standard refraction -0.5667 deg)
    horizon = -0.5667
    
    for idx, row in top_df.iterrows():
        try:
            pos = index_map.get(idx)
            if pos is None:
                continue

            target = targets[pos]
            
            # 1. Current position (single time point)
            astrometric = observer.at(t).observe(target)
            apparent = astrometric.apparent()
            ra, dec, distance = apparent.radec()
            alt, az, _ = apparent.altaz()
            
            # 2. Event finding (Vectorized over time)
            # Compute altitude over the grid
            # Note: observer.at(t_grid) is efficient
            grid_obs = observer.at(t_grid).observe(target)
            grid_alt, grid_az, _ = grid_obs.apparent().altaz()
            alt_deg = grid_alt.degrees
            
            # Find rise/set (zero crossings of alt - horizon)
            alt_shifted = alt_deg - horizon
            sign_change = (alt_shifted[:-1] * alt_shifted[1:]) < 0
            indices = np.where(sign_change)[0]
            
            rise_time = None
            set_time = None
            
            # Process crossings to find first rise and set
            for i in indices:
                # Linear interpolation
                y0 = alt_shifted[i]
                y1 = alt_shifted[i+1]
                fraction = -y0 / (y1 - y0)
                event_dt = times_dt[i] + timedelta(minutes=minutes_step * fraction)
                
                # Rise: y0 < 0 (below horizon) -> y1 > 0 (above)
                if y0 < 0 and rise_time is None:
                    rise_time = event_dt
                # Set: y0 > 0 (above) -> y1 < 0 (below)
                elif y0 > 0 and set_time is None:
                    set_time = event_dt
                    
                if rise_time and set_time:
                    break
            
            # Transit (Max altitude)
            # Find index of max altitude
            # We want the max altitude that occurs *at night* ideally, but for now just global max in window
            # Or better: max altitude near the middle of the window?
            # Let's stick to finding the highest point in the grid
            max_idx = np.argmax(alt_deg)
            transit_time = times_dt[max_idx]
            
            # Refine transit time? 5 min resolution is probably enough for display
            
            asteroid_list.append(
                {
                    "name": row["designation"],
                    "number": str(row.name),
                    "magnitude": round(float(row["apparent_magnitude"]), 1),
                    "ra": ra.hours * 15.0,
                    "dec": dec.degrees,
                    "altitude": alt.degrees,
                    "azimuth": az.degrees,
                    "distance": round(distance.au, 3),
                    "rise_time": format_time(rise_time, tz),
                    "set_time": format_time(set_time, tz),
                    "transit_time": format_time(transit_time, tz),
                    "type": "asteroid",
                    "symbol": "⚸",  # Unicode U+26B8 (Asteroid)
                }
            )
        except Exception as e:
            print(f"Error in final processing for {row.get('designation', 'N/A')}: {e}")
            continue

    # Cache the results for future requests (same semantics as before)
    if use_cache:
        try:
            lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
            loc_key = location_key(lat_norm, lon_norm, elev_norm)
            time_bucket = time_bucket_utc(current_dt, ASTEROID_CACHE_BUCKET_HOURS)

            # Use 0 as representative ID (all asteroids share same location/time)
            representative_id = 0
            store_asteroid_positions(
                representative_id,
                loc_key,
                time_bucket,
                lat,
                lon,
                elevation,
                asteroid_list,
            )
        except Exception as e:
            print(f"Failed to cache asteroid positions: {e}")

    return asteroid_list
