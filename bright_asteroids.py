"""
Module for calculating positions of bright minor planets (asteroids).

Data flow: MPCORB DataFrame (loaded once from PostgreSQL via nightly_data_updater)
-> prefilter by absolute magnitude H -> vectorized apparent-magnitude calc using
the IAU H-G phase function -> rise/set/transit on a 5-min grid.
"""
import logging
import os
import pickle
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from skyfield.api import wgs84
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2
from skyfield.data import mpc

from astronomy_utils import (
    build_event_time_grid,
    compute_rise_set_transit_from_altitudes,
    format_time,
)
from cache_utils import normalize_location, location_key, time_bucket_utc
from data_paths import MPCORB_PATH
from db_utils import get_asteroid_dataframe, store_asteroid_positions
from timezone_utils import get_tzinfo

logger = logging.getLogger(__name__)

# Konstanten
MPCORB_FILE = Path(MPCORB_PATH)
MPCORB_URL = 'https://www.minorplanetcenter.net/iau/MPCORB/MPCORB.DAT.gz'
MAX_ASTEROIDS = 5000
# H-limit for prefiltering by absolute magnitude (smaller = brighter)
MAX_ABSOLUTE_MAGNITUDE = float(os.environ.get('ASCII_SKY_ASTEROID_MAX_ABSOLUTE_MAG', '12.0'))
# V-limit for final apparent magnitude filtering
MAX_APPARENT_MAGNITUDE = float(os.environ.get('ASCII_SKY_ASTEROID_MAX_APPARENT_MAG', '10.0'))

# Module-specific cache granularity for per-location/time asteroid list.
# Use a 1-hour time bucket; TTL must cover the 30-day precompute window
# so that snapshots created up to 30 days earlier remain valid.
ASTEROID_CACHE_BUCKET_HOURS = int(os.environ.get('ASTEROID_CACHE_BUCKET_HOURS', '1'))
ASTEROID_CACHE_TTL_SECONDS = int(os.environ.get('ASTEROID_CACHE_TTL_SECONDS', str(31 * 24 * 3600)))

# IAU H-G asteroid magnitude system
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
    """Laedt die MPCORB.DAT.gz-Datei von der Minor Planet Center-Website herunter.

    Called by ``nightly_data_updater.py`` as a HTTP fallback when FTP is disabled.
    """
    try:
        logger.info("Downloading MPCORB.DAT.gz from %s", MPCORB_URL)
        MPCORB_FILE.parent.mkdir(parents=True, exist_ok=True)

        with urllib.request.urlopen(MPCORB_URL, timeout=300) as response, MPCORB_FILE.open('wb') as out_file:
            file_size = int(response.info().get('Content-Length', 0))
            if file_size:
                logger.info("File size: %.1f MB", file_size / (1024 * 1024))

            downloaded = 0
            block_size = 8192
            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                downloaded += len(buffer)
                out_file.write(buffer)
                # Log progress every ~1MB
                if file_size and downloaded % (1024 * 1024) < block_size:
                    logger.info(
                        "Downloaded: %.1f MB (%.1f%%)",
                        downloaded / (1024 * 1024),
                        downloaded * 100 / file_size,
                    )

        logger.info("Download complete. File saved to %s", MPCORB_FILE)

        if MPCORB_FILE.exists() and MPCORB_FILE.stat().st_size > 0:
            return True
        logger.error("Download failed: File is empty or does not exist")
        return False
    except Exception as e:
        logger.error("Error downloading MPCORB.DAT.gz: %s", e)
        return False


def load_bright_asteroids(loader, ts, eph, observer_location, max_magnitude=MAX_APPARENT_MAGNITUDE,
                          use_cache=True, current_dt: Optional[datetime] = None, dataframe=None):
    """
    Load and calculate positions, magnitudes, and rise/set times of the brightest minor planets
    """
    if isinstance(observer_location, dict):
        lat = float(observer_location.get('latitude', 0.0))
        lon = float(observer_location.get('longitude', 0.0))
        elevation = float(observer_location.get('elevation', 0.0))
    else:
        try:
            lat = float(observer_location.latitude.degrees)
            lon = float(observer_location.longitude.degrees)
            elevation = float(observer_location.elevation.m)
        except AttributeError:
            logger.warning("Could not extract location data from observer_location")
            lat, lon, elevation = 0.0, 0.0, 0.0

    logger.info("Getting asteroids with magnitude <= %s at lat=%s, lon=%s, elevation=%s",
                max_magnitude, lat, lon, elevation)
    tz = get_tzinfo(lat, lon)

    # --- DataFrame loading (PostgreSQL ONLY) ---
    try:
        if dataframe is not None:
            df = dataframe
        else:
            df_pickle = get_asteroid_dataframe()
            if not df_pickle:
                logger.error("No asteroids in PostgreSQL database! Run data_updater first.")
                return []
            df = pickle.loads(df_pickle)
            logger.info("Loaded %d asteroids from PostgreSQL database", len(df))

        # Step 1: Filter by absolute magnitude
        df_filtered = df[df['magnitude_H'] <= MAX_ABSOLUTE_MAGNITUDE].copy()
        logger.debug("Step 1: Filtered to %d asteroids with H <= %s",
                     len(df_filtered), MAX_ABSOLUTE_MAGNITUDE)

        # Step 2: NumPy Pre-Filter - Rough apparent magnitude estimation
        # Typical distances: r=2.5 AU (heliocentric), delta=1.5 AU (geocentric)
        H_array = df_filtered['magnitude_H'].values
        r_typical = 2.5  # AU
        delta_typical = 1.5  # AU
        rough_apparent_mag = H_array + 5 * np.log10(r_typical * delta_typical)
        # A 1.5-mag margin retained every result in the local reference dataset
        # while substantially reducing the expensive orbit-propagation workload.
        bright_enough = rough_apparent_mag <= (max_magnitude + 1.5)
        df_filtered = df_filtered[bright_enough].copy()
        logger.debug("Step 2: NumPy pre-filter kept %d candidates (rough mag <= %s)",
                     len(df_filtered), max_magnitude + 1.5)

        # Step 3: Sort by H and limit to a reasonable processing budget
        df_filtered = df_filtered.sort_values('magnitude_H').head(MAX_ASTEROIDS * 2)
        logger.debug("Step 3: Limited to %d asteroids for processing", len(df_filtered))
    except Exception as e:
        logger.error("Cannot load asteroid dataframe: %s", e)
        return []

    if df_filtered is None or df_filtered.empty:
        return []

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

    # Modern Skyfield API (Topos is deprecated).
    location = wgs84.latlon(lat, lon, elevation_m=elevation)
    observer = eph['earth'] + location
    sun = eph['sun']

    # Barycentric reference positions (computed once, reused for all targets).
    sun_xyz = sun.at(t).position.au  # (3,)
    observer_at_t = observer.at(t)
    observer_xyz = observer_at_t.position.au  # (3,)

    # --- Build orbits (serial — GIL prevents thread speedup here) ---
    orbits = []
    targets = []
    index_map = {}

    for idx, row in df_filtered.iterrows():
        try:
            orbit = mpc.mpcorb_orbit(row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)
            center_code = int(getattr(orbit, "center", 10))
            target = (sun + orbit) if center_code != 0 else orbit
            index_map[idx] = len(orbits)
            orbits.append(orbit)
            targets.append(target)
        except Exception:
            continue

    if not orbits:
        return []

    # Restrict DataFrame to successfully processed rows.
    valid_indices = list(index_map.keys())
    candidates_df = df_filtered.loc[valid_indices].copy()

    # Propagate all elliptical MPCORB elements in one NumPy batch. This follows
    # the same two-body equations as Skyfield's per-object Kepler propagator,
    # but avoids thousands of Python calls. Fall back for unexpected elements.
    try:
        a = candidates_df["semimajor_axis_au"].to_numpy(dtype=float)
        e = candidates_df["eccentricity"].to_numpy(dtype=float)
        if not (np.all(np.isfinite(a)) and np.all((e >= 0.0) & (e < 1.0))):
            raise ValueError("batch propagation requires finite elliptical elements")

        mean_anomaly = np.radians(candidates_df["mean_anomaly_degrees"].to_numpy(dtype=float))
        epochs_tt = np.array([orbit.epoch.tt for orbit in orbits], dtype=float)
        mean_motion = np.sqrt(orbits[0].mu_au3_d2 / (a ** 3))
        mean_anomaly = (mean_anomaly + mean_motion * (t.tt - epochs_tt) + np.pi) % (2.0 * np.pi) - np.pi

        # Robust vectorized Newton solve of M = E - e*sin(E).
        eccentric_anomaly = mean_anomaly + 0.85 * e * np.sign(np.sin(mean_anomaly))
        for _ in range(12):
            correction = (
                eccentric_anomaly - e * np.sin(eccentric_anomaly) - mean_anomaly
            ) / (1.0 - e * np.cos(eccentric_anomaly))
            eccentric_anomaly -= correction
        if np.max(np.abs(correction)) > 1e-12:
            raise ValueError("batch Kepler solver did not converge")

        x_orbit = a * (np.cos(eccentric_anomaly) - e)
        y_orbit = a * np.sqrt(1.0 - e * e) * np.sin(eccentric_anomaly)
        inclination = np.radians(candidates_df["inclination_degrees"].to_numpy(dtype=float))
        node = np.radians(candidates_df["longitude_of_ascending_node_degrees"].to_numpy(dtype=float))
        periapsis = np.radians(candidates_df["argument_of_perihelion_degrees"].to_numpy(dtype=float))

        cos_node, sin_node = np.cos(node), np.sin(node)
        cos_peri, sin_peri = np.cos(periapsis), np.sin(periapsis)
        cos_inc, sin_inc = np.cos(inclination), np.sin(inclination)
        ecliptic_xyz = np.array([
            (cos_node * cos_peri - sin_node * sin_peri * cos_inc) * x_orbit
            + (-cos_node * sin_peri - sin_node * cos_peri * cos_inc) * y_orbit,
            (sin_node * cos_peri + cos_node * sin_peri * cos_inc) * x_orbit
            + (-sin_node * sin_peri + cos_node * cos_peri * cos_inc) * y_orbit,
            sin_peri * sin_inc * x_orbit + cos_peri * sin_inc * y_orbit,
        ])
        tgt_xyz = orbits[0]._rotation @ ecliptic_xyz + sun_xyz[:, None]
    except Exception as exc:
        logger.debug("Falling back to per-object asteroid propagation: %s", exc)
        tgt_xyz = np.array([target.at(t).position.au for target in targets]).T

    diff_sun = tgt_xyz - sun_xyz[:, None]    # (3, N) heliocentric vectors
    diff_observer = tgt_xyz - observer_xyz[:, None]  # (3, N) topocentric vectors

    rs = np.sqrt(np.sum(diff_sun ** 2, axis=0))      # heliocentric distances (AU)
    deltas = np.sqrt(np.sum(diff_observer ** 2, axis=0))  # topocentric distances (AU)

    # Phase angle: angle at the asteroid between the sun-direction and the observer-direction.
    # IAU definition: angle between vectors (target->sun) and (target->observer).
    # target->sun = -diff_sun; target->observer = -diff_observer.
    cos_phase = np.sum(diff_sun * diff_observer, axis=0) / (rs * deltas)
    phase_angles = np.degrees(np.arccos(np.clip(cos_phase, -1.0, 1.0)))

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
    logger.info("Found %d asteroids with apparent mag <= %s (user filter: %s)",
                len(top_df), cache_limit, max_magnitude)

    # --- Vectorized Event Finding (Grid Search) ---
    # 48h window with 5-min resolution anchored at simulated day's UTC midnight.
    t_grid, times_dt, minutes_step = build_event_time_grid(ts, t, days=2, minutes_step=5)

    # Cache observer.at(t_grid) once; reused for every asteroid.
    observer_at_grid = observer.at(t_grid)

    asteroid_list = []
    for idx, row in top_df.iterrows():
        try:
            pos = index_map.get(idx)
            if pos is None:
                continue

            target = targets[pos]

            # 1. Current position (single time point) - reuses cached observer_at_t
            apparent = observer_at_t.observe(target).apparent()
            ra, dec, distance = apparent.radec()
            alt, az, _ = apparent.altaz()

            # 2. Grid-based rise/set/transit (linear interpolation of alt - horizon)
            grid_alt, _grid_az, _ = observer_at_grid.observe(target).apparent().altaz()
            rise_time, set_time, transit_time = compute_rise_set_transit_from_altitudes(
                grid_alt.degrees, times_dt, minutes_step
            )

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
            logger.debug("Error in final processing for %s: %s", row.get('designation', 'N/A'), e)
            continue

    # Cache the results for future requests (same semantics as before)
    if use_cache:
        try:
            lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
            loc_key = location_key(lat_norm, lon_norm, elev_norm)
            time_bucket = time_bucket_utc(dt_utc, ASTEROID_CACHE_BUCKET_HOURS)

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
            logger.debug("Failed to cache asteroid positions: %s", e)

    return asteroid_list
