import pandas as pd
from skyfield.api import Loader, Topos
from skyfield.data import mpc
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2 as GM_SUN
import numpy as np

# Setup
load = Loader('~/skyfield-data')
ts = load.timescale()
eph = load('de421.bsp')
earth = eph['earth']
sun = eph['sun']
berlin = earth + Topos('52.52 N', '13.40 E')

# MPCORB laden + Header überspringen
with open('cache/MPCORB.DAT', 'rb') as f:
    for _ in range(22):  # Header-Zeilen überspringen
        next(f)
    df = mpc.load_mpcorb_dataframe(f)

print(df.columns)
print(df.head(25))

# Spalten in float umwandeln
numeric_cols = [
    'magnitude_H', 'magnitude_G', 'mean_anomaly_degrees',
    'argument_of_perihelion_degrees', 'longitude_of_ascending_node_degrees',
    'inclination_degrees', 'eccentricity', 'mean_daily_motion_degrees',
    'semimajor_axis_au'
]
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce')


# --- Ceres auswählen ---
ceres_row = df[df['designation'].str.contains('Ceres', na=False)].iloc[0]

# --- Orbit erzeugen (um Sonne) ---
ceres_orbit = mpc.mpcorb_orbit(ceres_row, ts, GM_SUN)

# --- In baryzentrisches Objekt umwandeln (wichtig!) ---
ceres_bary = sun + ceres_orbit

# --- Beobachtungszeitpunkt ---
t = ts.utc(2025, 22, 29, 22, 0, 0)

# --- Beobachtung von Berlin ---
astrometric = berlin.at(t).observe(ceres_bary).apparent()
ra, dec, distance = astrometric.radec()

# --- Distanzen ---
delta = berlin.at(t).observe(ceres_bary).distance().au   # Erde–Ceres
r     = sun.at(t).observe(ceres_bary).distance().au      # Sonne–Ceres

# --- Helligkeit ---
H = ceres_row['magnitude_H']
m = H + 5 * np.log10(r * delta)

print(f"Ceres am {t.utc_iso()}")
print(f"RA = {ra}, Dec = {dec}")
print(f"Distanz Erde–Ceres = {delta:.3f} au, Sonne–Ceres = {r:.3f} au")
print(f"Absolute Helligkeit H = {H:.2f}, scheinbare V ≈ {m:.2f}")

