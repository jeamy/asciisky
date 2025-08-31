import pandas as pd
import numpy as np
from skyfield.api import Loader, Topos
from skyfield.data import mpc
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2 as GM_SUN

# Setup
load = Loader('~/skyfield-data')
ts = load.timescale()
eph = load('de421.bsp')
earth = eph['earth']
sun = eph['sun']
berlin = earth + Topos('52.52 N', '13.40 E')

# MPC Kometenliste laden
with load.open('https://www.minorplanetcenter.net/iau/MPCORB/CometEls.txt') as f:
    df = mpc.load_comets_dataframe(f)

# Numerische Spalten konvertieren
numeric_cols = ['perihelion_year', 'perihelion_month', 'perihelion_day',
                'perihelion_distance_au', 'eccentricity',
                'argument_of_perihelion_degrees',
                'longitude_of_ascending_node_degrees',
                'inclination_degrees', 'magnitude_g', 'magnitude_k']
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce')

# Beobachtungszeitpunkt
t = ts.now()

# Nur Kometen, die potentiell heller als m=16 sind
bright_limit = 14.5 

print("Helle Kometen sichtbar von Berlin:")
print("-" * 50)

for idx, row in df.iterrows():
    try:
        # Prüfe ob alle notwendigen Daten vorhanden sind
        if pd.isna(row['magnitude_g']) or pd.isna(row['perihelion_distance_au']):
            continue
            
        # Kometen-Orbit relativ zum Solar System Barycenter
        comet_bary = mpc.comet_orbit(row, ts, gm_km3_s2=GM_SUN)
        
        # Sicherstellen, dass das Zentrum das Barycenter ist
        if comet_bary.center != 0:  # 0 = Solar System Barycenter
            # Orbit zum Barycenter verschieben
            comet_bary = eph['sun'] + comet_bary
        
        # Position des Kometen relativ zur Sonne (für Helligkeitsberechnung)
        comet_sun_vector = sun.at(t).observe(comet_bary)
        r = comet_sun_vector.distance().au  # Sonne–Komet Distanz
        
        # Beobachtung von Berlin (Erde ist bereits im gleichen Bezugssystem)
        astrometric = berlin.at(t).observe(comet_bary).apparent()
        
        # RA/Dec
        ra, dec, distance = astrometric.radec()
        delta = distance.au  # Erde–Komet Distanz
        
        # Visuelle Helligkeit approximieren
        # Formel: m = H + 5*log10(r*delta) + 2.5*n*log10(r)
        # Vereinfacht: m = H + 5*log10(r*delta) (n=0 Annahme)
        H = row['magnitude_g']
        m = H + 5 * np.log10(r * delta)
        
        if m < bright_limit:
            # Höhe über Horizont berechnen
            alt, az, distance = astrometric.altaz()
            
            print(f"{row['designation'][:25]:<25} m={m:.1f} "
                  f"RA={ra.hours:.2f}h Dec={dec.degrees:.1f}° "
                  f"Alt={alt.degrees:.1f}° r={r:.2f}AU δ={delta:.2f}AU")
                  
    except Exception as e:
        # Nur unerwartete Fehler ausgeben, fehlende Daten sind normal
        if "magnitude_g" not in str(e) and "perihelion_distance" not in str(e):
            print(f"Fehler bei {row['designation']}: {e}")
        continue

print("-" * 50)
print(f"Berechnet für: {t.utc_datetime()} UTC")
print(f"Beobachtungsort: Berlin (52.52°N, 13.40°E)")
print(f"Helligkeitslimit: {bright_limit} mag")