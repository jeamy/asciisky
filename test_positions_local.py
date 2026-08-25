#!/usr/bin/env python3
"""
Standalone local test + benchmark for asteroid and comet position calculations.
No PostgreSQL, no FastAPI - uses local pickle/data files directly.

Run with:
    .venv/bin/python test_positions_local.py
"""
import pickle
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from skyfield.api import Loader, wgs84
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2
from skyfield.data import mpc

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DE421_PATH = DATA_DIR / "de421.bsp"
ASTEROID_PKL = DATA_DIR / "asteroid_dataframe.pkl"
COMET_PKL = DATA_DIR / "comet_dataframe.pkl"

# Observer location: Vienna (AT)
LAT, LON, ELEV = 48.2, 16.37, 170.0

MAX_ABSOLUTE_MAG_ASTEROID = 12.0
MAX_APPARENT_MAG_ASTEROID = 10.0
MAX_ABSOLUTE_MAG_COMET = 18.0
MAX_COMETS = 20
TEST_TIME_UTC = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
VALIDATION_SAMPLE_SIZE = 64

# ---------------------------------------------------------------------------
# Shared magnitude helpers (copied verbatim from modules)
# ---------------------------------------------------------------------------

def vectorized_asteroid_apparent_magnitude(H, G, r, delta, phase_angle_deg):
    alpha = np.radians(phase_angle_deg)
    tan_half = np.tan(alpha / 2.0)
    tan_half_safe = np.maximum(tan_half, 0)
    phi1 = np.exp(-3.33 * (tan_half_safe ** 0.63))
    phi2 = np.exp(-1.87 * (tan_half_safe ** 1.22))
    flux_term = np.maximum((1.0 - G) * phi1 + G * phi2, 1e-12)
    distance_term = np.maximum(r * delta, 1e-12)
    return H + 5.0 * np.log10(distance_term) - 2.5 * np.log10(flux_term)


def vectorized_comet_apparent_magnitude(M1, n, delta, r):
    delta_safe = np.maximum(delta, 1e-12)
    r_safe = np.maximum(r, 1e-12)
    return M1 + 5.0 * np.log10(delta_safe) + 2.5 * n * np.log10(r_safe)


# ---------------------------------------------------------------------------
# Rise/set/transit helper (simplified from astronomy_utils)
# ---------------------------------------------------------------------------
DEFAULT_HORIZON_DEG = -0.5667

def build_time_grid(ts, t, days=2, minutes_step=5):
    from datetime import timedelta
    start_dt = t.utc_datetime().replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(days=days)
    total_minutes = int((end_dt - start_dt).total_seconds() / 60)
    steps = total_minutes // minutes_step
    times_dt = [start_dt + timedelta(minutes=i * minutes_step) for i in range(steps + 1)]
    t_grid = ts.from_datetimes(times_dt)
    return t_grid, times_dt, minutes_step


def compute_rise_set_transit(alt_deg, times_dt, minutes_step, horizon=DEFAULT_HORIZON_DEG):
    from datetime import timedelta
    rise_time = set_time = transit_time = None
    if alt_deg is None or len(alt_deg) == 0:
        return rise_time, set_time, transit_time
    alt_shifted = alt_deg - horizon
    sign_change = (alt_shifted[:-1] * alt_shifted[1:]) < 0
    indices = np.where(sign_change)[0]
    for i in indices:
        y0, y1 = alt_shifted[i], alt_shifted[i + 1]
        denom = y1 - y0
        if abs(denom) < 1e-15:
            continue
        fraction = -y0 / denom
        event_dt = times_dt[i] + timedelta(minutes=minutes_step * fraction)
        if y0 < 0 and rise_time is None:
            rise_time = event_dt
        elif y0 > 0 and set_time is None:
            set_time = event_dt
        if rise_time is not None and set_time is not None:
            break
    try:
        transit_time = times_dt[int(np.argmax(alt_deg))]
    except Exception:
        pass
    return rise_time, set_time, transit_time


# ---------------------------------------------------------------------------
# Setup Skyfield
# ---------------------------------------------------------------------------

def setup_skyfield():
    print(f"Loading ephemeris from {DE421_PATH} ...")
    loader = Loader(str(DATA_DIR))
    ts = loader.timescale()
    eph = loader('de421.bsp')
    return ts, eph


# ---------------------------------------------------------------------------
# ASTEROID TEST
# ---------------------------------------------------------------------------

def run_asteroid_test(ts, eph):
    print("\n" + "=" * 60)
    print("  ASTEROID POSITION TEST")
    print("=" * 60)

    if not ASTEROID_PKL.exists():
        print(f"  ERROR: {ASTEROID_PKL} not found")
        return None

    t0 = time.perf_counter()
    with ASTEROID_PKL.open("rb") as f:
        df = pickle.load(f)
    print(f"  Loaded {len(df)} asteroids from pickle in {time.perf_counter()-t0:.2f}s")

    # Filter by absolute magnitude
    df_filtered = df[df['magnitude_H'] <= MAX_ABSOLUTE_MAG_ASTEROID].copy()
    print(f"  After H<={MAX_ABSOLUTE_MAG_ASTEROID} filter: {len(df_filtered)} asteroids")

    # NumPy rough apparent magnitude pre-filter
    H_array = df_filtered['magnitude_H'].values
    rough_mag = H_array + 5 * np.log10(2.5 * 1.5)
    df_filtered = df_filtered[rough_mag <= (MAX_APPARENT_MAG_ASTEROID + 1.5)].copy()
    df_filtered = df_filtered.sort_values('magnitude_H').head(10000)
    print(f"  After rough mag pre-filter: {len(df_filtered)} candidates")

    dt_utc = TEST_TIME_UTC
    t = ts.from_datetime(dt_utc)
    location = wgs84.latlon(LAT, LON, elevation_m=ELEV)
    observer = eph['earth'] + location
    sun = eph['sun']

    # Barycentric reference positions
    sun_xyz = sun.at(t).position.au
    observer_at_t = observer.at(t)
    observer_xyz = observer_at_t.position.au

    # --- Serial orbit building (GIL prevents thread speedup) ---
    t1 = time.perf_counter()
    orbits, targets, index_map = [], [], {}
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
    t_orbit = time.perf_counter() - t1
    print(f"  Built {len(orbits)} orbits in {t_orbit:.2f}s")

    if not orbits:
        print("  ERROR: No orbits built")
        return None

    valid_indices = list(index_map.keys())
    candidates_df = df_filtered.loc[valid_indices].copy()

    # --- Batch Kepler propagation + vectorized geometry ---
    t2 = time.perf_counter()
    a = candidates_df["semimajor_axis_au"].to_numpy(dtype=float)
    e = candidates_df["eccentricity"].to_numpy(dtype=float)
    mean_anomaly = np.radians(candidates_df["mean_anomaly_degrees"].to_numpy(dtype=float))
    epochs_tt = np.array([orbit.epoch.tt for orbit in orbits], dtype=float)
    mean_anomaly = (
        mean_anomaly + np.sqrt(orbits[0].mu_au3_d2 / a**3) * (t.tt - epochs_tt) + np.pi
    ) % (2 * np.pi) - np.pi
    eccentric_anomaly = mean_anomaly + 0.85 * e * np.sign(np.sin(mean_anomaly))
    for _ in range(12):
        correction = (eccentric_anomaly - e * np.sin(eccentric_anomaly) - mean_anomaly) / (
            1 - e * np.cos(eccentric_anomaly)
        )
        eccentric_anomaly -= correction
    assert np.max(np.abs(correction)) < 1e-12
    x_orbit = a * (np.cos(eccentric_anomaly) - e)
    y_orbit = a * np.sqrt(1 - e * e) * np.sin(eccentric_anomaly)
    inclination = np.radians(candidates_df["inclination_degrees"].to_numpy(dtype=float))
    node = np.radians(candidates_df["longitude_of_ascending_node_degrees"].to_numpy(dtype=float))
    periapsis = np.radians(candidates_df["argument_of_perihelion_degrees"].to_numpy(dtype=float))
    co, so = np.cos(node), np.sin(node)
    cw, sw = np.cos(periapsis), np.sin(periapsis)
    ci, si = np.cos(inclination), np.sin(inclination)
    ecliptic_xyz = np.array([
        (co*cw - so*sw*ci)*x_orbit + (-co*sw - so*cw*ci)*y_orbit,
        (so*cw + co*sw*ci)*x_orbit + (-so*sw + co*cw*ci)*y_orbit,
        sw*si*x_orbit + cw*si*y_orbit,
    ])
    tgt_xyz = orbits[0]._rotation @ ecliptic_xyz + sun_xyz[:, None]
    diff_sun = tgt_xyz - sun_xyz[:, None]
    diff_observer = tgt_xyz - observer_xyz[:, None]
    rs = np.sqrt(np.sum(diff_sun ** 2, axis=0))
    deltas = np.sqrt(np.sum(diff_observer ** 2, axis=0))
    cos_phase = np.sum(diff_sun * diff_observer, axis=0) / (rs * deltas)
    phase_angles = np.degrees(np.arccos(np.clip(cos_phase, -1.0, 1.0)))
    t_dist = time.perf_counter() - t2
    print(f"  Computed distances/phase angles in {t_dist:.2f}s  (vectorized)")

    # Compare a bounded sample against Skyfield's slower, light-time-corrected path.
    sample_n = min(VALIDATION_SAMPLE_SIZE, len(targets))
    reference_obs = [observer_at_t.observe(target) for target in targets[:sample_n]]
    reference_xyz = np.array([target.at(t).position.au for target in targets[:sample_n]]).T
    reference_delta = np.array([obs.distance().au for obs in reference_obs])
    reference_phase = np.array([obs.phase_angle(sun).degrees for obs in reference_obs])
    delta_error = float(np.max(np.abs(deltas[:sample_n] - reference_delta)))
    phase_error = float(np.max(np.abs(phase_angles[:sample_n] - reference_phase)))
    position_error = float(np.max(np.abs(tgt_xyz[:, :sample_n] - reference_xyz)))
    print(f"  Validation ({sample_n}): max position error={position_error:.3e} AU, "
          f"delta error={delta_error:.6f} AU, phase error={phase_error:.6f} deg")
    assert position_error < 1e-10, f"Asteroid batch position error too large: {position_error} AU"
    assert delta_error < 0.0011, f"Asteroid distance error too large: {delta_error} AU"
    assert phase_error < 0.003, f"Asteroid phase-angle error too large: {phase_error} deg"

    H_values = candidates_df["magnitude_H"].to_numpy()
    G_values = candidates_df["magnitude_G"].fillna(0.15).to_numpy() if "magnitude_G" in candidates_df.columns else np.full_like(H_values, 0.15)

    apparent_magnitudes = vectorized_asteroid_apparent_magnitude(H_values, G_values, rs, deltas, phase_angles)
    candidates_df["apparent_magnitude"] = apparent_magnitudes

    bright_df = candidates_df[candidates_df["apparent_magnitude"] <= MAX_APPARENT_MAG_ASTEROID].sort_values("apparent_magnitude")
    print(f"  Bright asteroids (mag <= {MAX_APPARENT_MAG_ASTEROID}): {len(bright_df)}")

    if bright_df.empty:
        print("  No bright enough asteroids found - showing top 5 by apparent mag:")
        top5 = candidates_df.sort_values("apparent_magnitude").head(5)
        for _, r in top5.iterrows():
            print(f"    {r.get('designation','?'):30s}  H={r['magnitude_H']:.1f}  app={r['apparent_magnitude']:.2f}")
        return {"count": 0, "orbit_time": t_orbit, "dist_time": t_dist}

    # Rise/set/transit for top entries
    top_df = bright_df.head(20)
    t_grid, times_dt, minutes_step = build_time_grid(ts, t)
    observer_at_grid = observer.at(t_grid)

    t3 = time.perf_counter()
    results = []
    for idx, row in top_df.iterrows():
        pos = index_map.get(idx)
        if pos is None:
            continue
        target = targets[pos]
        try:
            apparent = observer_at_t.observe(target).apparent()
            ra, dec, distance = apparent.radec()
            alt, az, _ = apparent.altaz()
            grid_alt, _, _ = observer_at_grid.observe(target).apparent().altaz()
            rise, setv, transit = compute_rise_set_transit(grid_alt.degrees, times_dt, minutes_step)
            results.append({
                "name": row["designation"],
                "magnitude": round(float(row["apparent_magnitude"]), 1),
                "ra_deg": ra.hours * 15.0,
                "dec_deg": dec.degrees,
                "alt_deg": alt.degrees,
                "az_deg": az.degrees,
                "dist_au": round(distance.au, 3),
            })
        except Exception as e:
            print(f"    WARN: {row.get('designation','?')}: {e}")
    t_risefall = time.perf_counter() - t3

    print(f"  Rise/set/transit for {len(results)} asteroids in {t_risefall:.2f}s")
    print(f"\n  {'Name':<30} {'Mag':>5}  {'Alt':>7}  {'Az':>7}  {'Dist(AU)':>9}")
    print(f"  {'-'*30} {'-'*5}  {'-'*7}  {'-'*7}  {'-'*9}")
    for r in results[:10]:
        print(f"  {r['name']:<30} {r['magnitude']:>5.1f}  {r['alt_deg']:>7.2f}°  {r['az_deg']:>7.2f}°  {r['dist_au']:>9.3f}")

    total = time.perf_counter() - t0
    print(f"\n  TOTAL asteroid test time: {total:.2f}s  (orbits={t_orbit:.2f}s, dists={t_dist:.2f}s, rise/set={t_risefall:.2f}s)")
    return {"count": len(results), "orbit_time": t_orbit, "dist_time": t_dist, "riseset_time": t_risefall, "total": total}


# ---------------------------------------------------------------------------
# COMET TEST
# ---------------------------------------------------------------------------

class _RowProxy:
    def __init__(self, data):
        self._d = data
    def __getitem__(self, key):
        return self._d[key]
    def get(self, key, default=None):
        return self._d.get(key, default)
    def __getattr__(self, key):
        try:
            return self._d[key]
        except KeyError:
            raise AttributeError(key) from None


def _make_comet_row_data(designation, row):
    """Build full data dict with all MPC aliases needed by skyfield.mpc.comet_orbit."""
    e = float(row['e'])
    q = float(row['q'])
    i = float(row['i'])
    om = float(row['om'])
    w = float(row['w'])
    epoch_tt = float(row['epoch_tt']) if pd.notna(row.get('epoch_tt')) else None
    tp = float(row['Tp']) if pd.notna(row.get('Tp')) else None
    return {
        'designation': designation,
        'e': e, 'q': q, 'i': i, 'incl': i, 'om': om, 'node': om, 'w': w, 'peri': w,
        'epoch_tt': epoch_tt, 'Tp': tp,
        # MPC raw names expected by skyfield.mpc.comet_orbit via attribute access
        'eccentricity': e,
        'perihelion_distance_au': q,
        'inclination_degrees': i,
        'longitude_of_ascending_node_degrees': om,
        'argument_of_perihelion_degrees': w,
        'perihelion_year': _float_or_none(row.get('perihelion_year')),
        'perihelion_month': _float_or_none(row.get('perihelion_month')),
        'perihelion_day': _float_or_none(row.get('perihelion_day')),
        'M1': None, 'k1': None, 'M2': None, 'k2': None,
    }


def _float_or_none(val):
    try:
        return float(val) if val is not None and not pd.isna(val) else None
    except Exception:
        return None


def _standardize_comet_df(df):
    """Simplified version of comets._standardize_comet_df."""
    df = df.copy()
    # Reset index if designation is there
    try:
        if 'designation' in list(df.index.names):
            df = df.reset_index()
    except Exception:
        pass
    # Ensure essential columns exist
    for col in ['e', 'q', 'incl', 'i', 'om', 'w', 'node', 'peri', 'epoch_tt', 'Tp', 'M1', 'k1']:
        if col not in df.columns:
            df[col] = np.nan
    numeric_cols = ['e', 'q', 'incl', 'i', 'om', 'node', 'w', 'peri', 'epoch_tt', 'Tp', 'M1', 'k1',
                    'perihelion_year', 'perihelion_month', 'perihelion_day']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'om' in df.columns:
        df['node'] = df['node'].fillna(df['om'])
    if 'w' in df.columns:
        df['peri'] = df['peri'].fillna(df['w'])
    essentials = [c for c in ['e', 'q'] if c in df.columns]
    if essentials:
        df = df.dropna(subset=essentials)
    if 'designation' in df.columns:
        df = df.set_index('designation', drop=True)
    return df


def run_comet_test(ts, eph):
    print("\n" + "=" * 60)
    print("  COMET POSITION TEST")
    print("=" * 60)

    if not COMET_PKL.exists():
        print(f"  ERROR: {COMET_PKL} not found")
        return None

    t0 = time.perf_counter()
    with COMET_PKL.open("rb") as f:
        df_raw = pickle.load(f)
    print(f"  Loaded {len(df_raw)} comets from pickle in {time.perf_counter()-t0:.2f}s")

    df = _standardize_comet_df(df_raw)
    print(f"  After standardization: {len(df)} comets")

    # Prefilter by M1
    df_pref = df[(df['M1'].notna()) & (df['M1'] <= MAX_ABSOLUTE_MAG_COMET)].copy()
    if 'M1' in df_pref.columns:
        df_pref = df_pref.sort_values('M1')
    print(f"  After M1<={MAX_ABSOLUTE_MAG_COMET} filter: {len(df_pref)} candidates")

    dt_utc = TEST_TIME_UTC
    t = ts.from_datetime(dt_utc)
    location = wgs84.latlon(LAT, LON, elevation_m=ELEV)
    observer = eph['earth'] + location
    sun = eph['sun']
    observer_at_t = observer.at(t)
    sun_xyz = sun.at(t).position.au
    observer_xyz = observer_at_t.position.au

    # --- Serial orbit building + geometric distance calculation ---
    def _prepare_comet(args):
        designation, row = args
        try:
            row2 = row.copy()
            row2['designation'] = designation
            for src, dst in [('om', 'node'), ('node', 'om'), ('w', 'peri'),
                              ('peri', 'w'), ('incl', 'i'), ('i', 'incl')]:
                if pd.isna(row2.get(dst)) and pd.notna(row2.get(src)):
                    row2[dst] = row2[src]
            if any(pd.isna(row2.get(c)) for c in ['e', 'q', 'i', 'om', 'w']):
                return None
            tp_v = float(row2['Tp']) if pd.notna(row2.get('Tp')) else None
            epoch_tt_v = float(row2['epoch_tt']) if pd.notna(row2.get('epoch_tt')) else None
            if tp_v is None:
                y = _float_or_none(row2.get('perihelion_year'))
                m_p = _float_or_none(row2.get('perihelion_month'))
                d_p = _float_or_none(row2.get('perihelion_day'))
                if y is not None and m_p is not None and d_p is not None:
                    tp_v = float(ts.tt(int(y), int(m_p), d_p).tt)
                    row2['Tp'] = tp_v
            data = _make_comet_row_data(designation, row2)
            data['Tp'] = tp_v
            data['epoch_tt'] = epoch_tt_v
            orbit = mpc.comet_orbit(_RowProxy(data), ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)
            center_code = int(getattr(orbit, 'center', 10))
            target = (sun + orbit) if center_code != 0 else orbit
            M1_val = row2.get('M1')
            if M1_val is None or pd.isna(M1_val):
                return None
            n_raw = row2.get('k1')
            n = float(n_raw) if (n_raw is not None and pd.notna(n_raw)) else 4.0
            return designation, row2, target, orbit, float(M1_val), n
        except Exception:
            return None

    t1 = time.perf_counter()
    comet_rows_list = list(df_pref.iterrows())
    raw_c = [_prepare_comet(item) for item in comet_rows_list]

    processed_rows = []
    orbits = []
    M1_list, n_list = [], []
    for res in raw_c:
        if res is None:
            continue
        designation, row2, target, orbit, M1, n = res
        processed_rows.append((designation, row2, target))
        orbits.append(orbit)
        M1_list.append(M1)
        n_list.append(n)

    t_orbit = time.perf_counter() - t1
    print(f"  Built {len(processed_rows)} comet orbits in {t_orbit:.2f}s")

    if not processed_rows:
        print("  ERROR: No comet orbits built")
        return None

    eccentricity = np.array([row.e for _, row, _ in processed_rows], dtype=float)
    perihelion = np.array([row.q for _, row, _ in processed_rows], dtype=float)
    periapsis_tt = np.array([orbit.epoch.tt for orbit in orbits], dtype=float)
    mu = orbits[0].mu_au3_d2
    x_orbit = np.empty(len(orbits))
    y_orbit = np.empty(len(orbits))
    elliptic = eccentricity < 1
    e = eccentricity[elliptic]
    a = perihelion[elliptic] / (1 - e)
    mean_anomaly = np.sqrt(mu / a**3) * (t.tt - periapsis_tt[elliptic])
    mean_anomaly = (mean_anomaly + np.pi) % (2*np.pi) - np.pi
    anomaly = mean_anomaly + 0.85*e*np.sign(np.sin(mean_anomaly))
    for _ in range(50):
        anomaly -= (anomaly - e*np.sin(anomaly) - mean_anomaly) / (1 - e*np.cos(anomaly))
    x_orbit[elliptic] = a*(np.cos(anomaly) - e)
    y_orbit[elliptic] = a*np.sqrt(1 - e*e)*np.sin(anomaly)
    hyperbolic = eccentricity > 1
    e = eccentricity[hyperbolic]
    a = perihelion[hyperbolic] / (e - 1)
    mean_anomaly = np.sqrt(mu / a**3) * (t.tt - periapsis_tt[hyperbolic])
    anomaly = np.arcsinh(mean_anomaly/e)
    for _ in range(50):
        anomaly -= (e*np.sinh(anomaly) - anomaly - mean_anomaly) / (e*np.cosh(anomaly) - 1)
    x_orbit[hyperbolic] = a*(e - np.cosh(anomaly))
    y_orbit[hyperbolic] = a*np.sqrt(e*e - 1)*np.sinh(anomaly)
    parabolic = eccentricity == 1
    q = perihelion[parabolic]
    barker_time = (t.tt - periapsis_tt[parabolic]) / np.sqrt(2*q**3/mu)
    anomaly = 2*np.sinh(np.arcsinh(1.5*barker_time)/3)
    x_orbit[parabolic] = q*(1 - anomaly*anomaly)
    y_orbit[parabolic] = 2*q*anomaly
    inclination = np.radians([row.i for _, row, _ in processed_rows])
    node = np.radians([row.om for _, row, _ in processed_rows])
    argument = np.radians([row.w for _, row, _ in processed_rows])
    co, so = np.cos(node), np.sin(node)
    cw, sw = np.cos(argument), np.sin(argument)
    ci, si = np.cos(inclination), np.sin(inclination)
    ecliptic_xyz = np.array([
        (co*cw-so*sw*ci)*x_orbit + (-co*sw-so*cw*ci)*y_orbit,
        (so*cw+co*sw*ci)*x_orbit + (-so*sw+co*cw*ci)*y_orbit,
        sw*si*x_orbit + cw*si*y_orbit,
    ])
    target_xyz = orbits[0]._rotation @ ecliptic_xyz + sun_xyz[:, None]
    r_list = np.linalg.norm(target_xyz - sun_xyz[:, None], axis=0)
    delta_list = np.linalg.norm(target_xyz - observer_xyz[:, None], axis=0)

    sample_n = min(VALIDATION_SAMPLE_SIZE, len(processed_rows))
    reference_delta = np.array([
        observer_at_t.observe(processed_rows[i][2]).distance().au
        for i in range(sample_n)
    ])
    reference_xyz = np.array([
        processed_rows[i][2].at(t).position.au for i in range(sample_n)
    ]).T
    delta_error = float(np.max(np.abs(np.asarray(delta_list[:sample_n]) - reference_delta)))
    position_error = float(np.max(np.abs(target_xyz[:, :sample_n] - reference_xyz)))
    print(f"  Validation ({sample_n}): max position error={position_error:.3e} AU, "
          f"delta error={delta_error:.6f} AU")
    assert position_error < 1e-8, f"Comet batch position error too large: {position_error} AU"
    assert delta_error < 0.005, f"Comet distance error too large: {delta_error} AU"

    # Vectorized magnitude computation
    M1_arr = np.array(M1_list, dtype=float)
    n_arr = np.array(n_list, dtype=float)
    delta_arr = np.array(delta_list, dtype=float)
    r_arr = np.array(r_list, dtype=float)
    apparent_magnitudes = vectorized_comet_apparent_magnitude(M1_arr, n_arr, delta_arr, r_arr)

    bright_mask = apparent_magnitudes <= 20.0
    bright_idx = np.where(bright_mask)[0]
    if len(bright_idx) == 0:
        print("  No comets with mag <= 20.0")
        return {"count": 0, "orbit_time": t_orbit}

    order = np.argsort(apparent_magnitudes[bright_idx])
    selected_idx = bright_idx[order][:MAX_COMETS]
    print(f"  Comets with mag<=20: {len(bright_idx)}, processing top {len(selected_idx)}")

    # Rise/set/transit
    t_grid, times_dt, minutes_step = build_time_grid(ts, t)
    observer_at_grid = observer.at(t_grid)

    t3 = time.perf_counter()
    results = []
    for pos in selected_idx:
        try:
            designation, row2, target = processed_rows[pos]
            apparent_mag = float(apparent_magnitudes[pos])
            apparent = observer_at_t.observe(target).apparent()
            ra, dec, distance = apparent.radec()
            alt, az, _ = apparent.altaz()
            grid_alt, _, _ = observer_at_grid.observe(target).apparent().altaz()
            rise, setv, transit = compute_rise_set_transit(grid_alt.degrees, times_dt, minutes_step)
            name = str(row2.get('name', designation)) if pd.notna(row2.get('name', None)) else designation
            results.append({
                "name": name,
                "designation": designation,
                "magnitude": round(apparent_mag, 1),
                "alt_deg": float(alt.degrees),
                "az_deg": float(az.degrees),
                "dist_au": round(float(distance.au), 3),
            })
        except Exception as e:
            print(f"    WARN: {designation}: {e}")
    t_risefall = time.perf_counter() - t3

    print(f"  Rise/set/transit for {len(results)} comets in {t_risefall:.2f}s")
    print(f"\n  {'Name/Designation':<40} {'Mag':>5}  {'Alt':>7}  {'Dist(AU)':>9}")
    print(f"  {'-'*40} {'-'*5}  {'-'*7}  {'-'*9}")
    for r in results[:10]:
        print(f"  {r['name']:<40} {r['magnitude']:>5.1f}  {r['alt_deg']:>7.2f}°  {r['dist_au']:>9.3f}")

    total = time.perf_counter() - t0
    print(f"\n  TOTAL comet test time: {total:.2f}s  (orbits={t_orbit:.2f}s, rise/set={t_risefall:.2f}s)")
    return {"count": len(results), "orbit_time": t_orbit, "riseset_time": t_risefall, "total": total}


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Focused unit tests for refactored comets.py helpers
# ---------------------------------------------------------------------------

def test_comets_standardize_prefers_valid_eq_rows():
    import comets
    df = pd.DataFrame({
        'designation': ['A', 'A', 'B'],
        'reference': ['20240101', '20240201', '20240115'],
        'e': [np.nan, 0.5, 0.7],
        'q': [np.nan, 1.5, 2.0],
        'Tp': [2459000.0, 2459100.0, 2459200.0],
    })
    result = comets._standardize_comet_df(df)
    assert len(result) == 2
    assert 'A' in result.index
    assert 'B' in result.index
    assert result.loc['A', 'e'] == 0.5
    assert result.loc['A', 'q'] == 1.5
    assert result.loc['A', 'reference'] == '20240201'


def test_comets_standardize_filters_time_reference():
    import comets
    df = pd.DataFrame({
        'designation': ['A', 'B', 'C'],
        'e': [0.5, 0.6, 0.7],
        'q': [1.5, 1.6, 1.7],
        'epoch_tt': [2459000.0, np.nan, np.nan],
        'Tp': [np.nan, 2459100.0, np.nan],
    })
    result = comets._standardize_comet_df(df)
    assert len(result) == 2
    assert 'A' in result.index
    assert 'B' in result.index
    assert 'C' not in result.index


def test_comets_standardize_maps_mpc_aliases():
    import comets
    df = pd.DataFrame({
        'designation': ['A'],
        'eccentricity': ['0.5'],
        'perihelion_distance_au': ['1.5'],
        'inclination_degrees': ['10.0'],
        'longitude_of_ascending_node_degrees': ['20.0'],
        'argument_of_perihelion_degrees': ['30.0'],
        'magnitude_g': ['8.5'],
        'magnitude_k': ['4.0'],
        'Tp': [2459000.0],
    })
    result = comets._standardize_comet_df(df)
    assert len(result) == 1
    assert result.loc['A', 'e'] == 0.5
    assert result.loc['A', 'q'] == 1.5
    assert result.loc['A', 'i'] == 10.0
    assert result.loc['A', 'node'] == 20.0
    assert result.loc['A', 'peri'] == 30.0
    assert result.loc['A', 'M1'] == 8.5
    assert result.loc['A', 'k1'] == 4.0


def test_comets_select_visible_comets():
    import comets
    mags = np.array([21.0, 18.5, 20.0, 19.0])
    bright_idx, selected_idx = comets._select_visible_comets(mags, max_comets=2)
    assert len(bright_idx) == 3
    assert len(selected_idx) == 2
    np.testing.assert_array_equal(selected_idx, np.array([1, 3]))


def test_comets_select_visible_comets_empty():
    import comets
    mags = np.array([21.0, 22.0])
    bright_idx, selected_idx = comets._select_visible_comets(mags, max_comets=5)
    assert len(bright_idx) == 0
    assert len(selected_idx) == 0


def test_comets_compute_distances():
    import comets
    tgt_xyz = np.array([[3.0, 4.0, 0.0], [6.0, 8.0, 0.0]]).T
    sun_xyz = np.array([0.0, 0.0, 0.0])
    observer_xyz = np.array([6.0, 8.0, 0.0])
    r_arr, delta_arr = comets._compute_comet_distances(tgt_xyz, sun_xyz, observer_xyz)
    np.testing.assert_allclose(r_arr, np.array([5.0, 10.0]))
    np.testing.assert_allclose(delta_arr, np.array([5.0, 0.0]))


def test_comets_normalize_row_builds_dates():
    import comets
    ts = Loader(str(DATA_DIR)).timescale()
    row = pd.Series({
        'e': 0.5,
        'q': 1.5,
        'i': 10.0,
        'om': 20.0,
        'w': 30.0,
        'M1': 8.0,
        'k1': 4.0,
        'perihelion_year': 2026.0,
        'perihelion_month': 6.0,
        'perihelion_day': 15.0,
        'epoch_year': 2024.0,
        'epoch_month': 1.0,
        'epoch_day': 1.0,
    })
    result = comets._normalize_comet_row(('C/2026 A', row, ts))
    assert result is not None
    designation, row2, orbit_key, M1, n = result
    assert designation == 'C/2026 A'
    assert M1 == 8.0
    assert n == 4.0
    assert row2['Tp'] == pytest.approx(float(ts.tt(2026, 6, 15).tt))
    assert row2['epoch_tt'] == pytest.approx(float(ts.tt(2024, 1, 1).tt))


def test_comets_normalize_row_rejects_missing_m1():
    import comets
    ts = Loader(str(DATA_DIR)).timescale()
    row = pd.Series({
        'e': 0.5,
        'q': 1.5,
        'i': 10.0,
        'om': 20.0,
        'w': 30.0,
        'Tp': 2459000.0,
    })
    result = comets._normalize_comet_row(('C/2026 A', row, ts))
    assert result is None


if __name__ == "__main__":
    print("=" * 60)
    print("  ASCIISKY - LOCAL POSITION CALCULATION TEST")
    print(f"  Python {sys.version.split()[0]}  |  numpy {np.__version__}  |  pandas {pd.__version__}")
    print(f"  Observer: lat={LAT}, lon={LON}, elev={ELEV}m")
    print("=" * 60)

    ts, eph = setup_skyfield()

    ast_result = run_asteroid_test(ts, eph)
    comet_result = run_comet_test(ts, eph)

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    if ast_result:
        print(f"  Asteroids: {ast_result.get('count', 0)} results  total={ast_result.get('total', 0):.2f}s")
    if comet_result:
        print(f"  Comets:    {comet_result.get('count', 0)} results  total={comet_result.get('total', 0):.2f}s")
    print()
