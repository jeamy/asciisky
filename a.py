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

# Beobachtungszeitpunkt
t = ts.now()

print("=" * 80)
print("HELLE HIMMELSOBJEKTE SICHTBAR VON BERLIN")
print("=" * 80)

# ========================================
# KLEINPLANETEN (ASTEROIDEN)
# ========================================
print("\n🪨 KLEINPLANETEN (Helligkeit < 8.0 mag)")
print("-" * 60)

try:
    # MPCORB laden + Header überspringen
    with open('cache/MPCORB.DAT', 'rb') as f:
        for _ in range(43):  # Korrekte Anzahl Header-Zeilen
            next(f)
        asteroids_df = mpc.load_mpcorb_dataframe(f)

    # Numerische Spalten konvertieren
    numeric_cols = [
        'magnitude_H', 'magnitude_G', 'mean_anomaly_degrees',
        'argument_of_perihelion_degrees', 'longitude_of_ascending_node_degrees',
        'inclination_degrees', 'eccentricity', 'mean_daily_motion_degrees',
        'semimajor_axis_au'
    ]
    for col in numeric_cols:
        asteroids_df[col] = pd.to_numeric(asteroids_df[col], errors='coerce')

    bright_asteroids = []
    
    for idx, row in asteroids_df.head(2000).iterrows():
        try:
            # Nur Objekte mit gültigen H-Werten prüfen
            if pd.isna(row['magnitude_H']):
                continue
            
            # Orbit erzeugen (um Sonne)
            asteroid_orbit = mpc.mpcorb_orbit(row, ts, GM_SUN)
            
            # In baryzentrisches Objekt umwandeln
            asteroid_bary = sun + asteroid_orbit
            
            # Beobachtung von Berlin
            astrometric = berlin.at(t).observe(asteroid_bary).apparent()
            ra, dec, distance = astrometric.radec()
            
            # Distanzen
            delta = distance.au  # Erde–Asteroid
            r = sun.at(t).observe(asteroid_bary).distance().au  # Sonne–Asteroid
            
            # Helligkeit berechnen
            H = row['magnitude_H']
            G = row['magnitude_G'] if not pd.isna(row['magnitude_G']) else 0.15  # Standard G-Wert
            
            # Phasenwinkel (vereinfacht)
            phase_angle = np.arccos(np.clip((r**2 + delta**2 - 1) / (2*r*delta), -1, 1))
            phase_angle_deg = np.degrees(phase_angle)
            
            # HG-System Helligkeit
            if phase_angle_deg < 120:
                phi1 = np.exp(-3.33 * (np.tan(phase_angle/2)**0.63))
                phi2 = np.exp(-1.87 * (np.tan(phase_angle/2)**1.22))
                m = H + 5*np.log10(r*delta) - 2.5*np.log10((1-G)*phi1 + G*phi2)
            else:
                m = H + 5*np.log10(r*delta)  # Vereinfacht für große Phasenwinkel
            
            if m < 8.0:
                # Höhe über Horizont
                alt, az, _ = astrometric.altaz()
                
                bright_asteroids.append({
                    'name': row['designation'],
                    'magnitude': m,
                    'ra': ra.hours,
                    'dec': dec.degrees,
                    'altitude': alt.degrees,
                    'distance_au': delta,
                    'sun_distance_au': r
                })
                
        except Exception as e:
            # Stille Fehler für ungültige Orbits
            continue
    
    # Sortieren nach Helligkeit
    bright_asteroids.sort(key=lambda x: x['magnitude'])
    
    for asteroid in bright_asteroids:
        visible = "✓" if asteroid['altitude'] > 0 else "✗"
        print(f"{asteroid['name'][:25]:<25} m={asteroid['magnitude']:.1f} "
              f"RA={asteroid['ra']:.2f}h Dec={asteroid['dec']:.1f}° "
              f"Alt={asteroid['altitude']:.1f}° {visible} "
              f"δ={asteroid['distance_au']:.2f}AU")

except FileNotFoundError:
    print("MPCORB.DAT nicht gefunden. Lade von MPC...")
    # Alternative: Online laden
    with load.open('https://www.minorplanetcenter.net/iau/MPCORB/MPCORB.DAT') as f:
        # Erste 43 Zeilen überspringen
        lines = f.readlines()[43:]
        # Hier müsste man die Daten manuell parsen...
        print("Online-Laden implementierung fehlt noch")

print(f"\nGefunden: {len(bright_asteroids)} Kleinplaneten heller als 8.0 mag")