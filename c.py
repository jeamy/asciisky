import pandas as pd
import numpy as np
from skyfield.api import Loader, Topos
from skyfield.data import mpc
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2 as GM_SUN

# Setup
load = Loader('/app/cache')
ts = load.timescale()
eph = load('de421.bsp')
earth = eph['earth']
sun = eph['sun']
berlin = earth + Topos('52.5109 N', '13.3989 E')

# Beobachtungszeitpunkt
t = ts.now()

# ========================================
# KOMETEN
# ========================================
print("\n☄️  KOMETEN (Helligkeit < 14.0 mag)")
print("-" * 60)

try:
    # Kometen laden
    with load.open('https://www.minorplanetcenter.net/iau/MPCORB/CometEls.txt') as f:
        comets_df = mpc.load_comets_dataframe(f)

    # Numerische Spalten konvertieren
    comet_numeric_cols = ['perihelion_year', 'perihelion_month', 'perihelion_day',
                         'perihelion_distance_au', 'eccentricity',
                         'argument_of_perihelion_degrees',
                         'longitude_of_ascending_node_degrees',
                         'inclination_degrees', 'magnitude_g', 'magnitude_k']
    for col in comet_numeric_cols:
        comets_df[col] = pd.to_numeric(comets_df[col], errors='coerce')

    bright_comets = []
    
    for idx, row in comets_df.iterrows():
        try:
            # Nur Kometen mit gültigen Helligkeitsdaten
            if pd.isna(row['magnitude_g']):
                continue
                
            # Kometen-Orbit
            comet = mpc.comet_orbit(row, ts, gm_km3_s2=GM_SUN)
            
            # Sicherstellen, dass das Zentrum das Barycenter ist
            if comet.center != 0:  # 0 = Solar System Barycenter
                # Orbit zum Barycenter verschieben
                comet = eph['sun'] + comet
            
            # Beobachtung von Berlin (immer vom Barycenter aus)
            astrometric = berlin.at(t).observe(comet).apparent()
            ra, dec, distance = astrometric.radec()
            delta = distance.au  # Erde–Komet Distanz
            
            # Position relativ zur Sonne für Helligkeitsberechnung
            comet_sun_vector = sun.at(t).observe(comet)
            r = comet_sun_vector.distance().au  # Sonne–Komet Distanz
            
            # Visuelle Helligkeit - beide Formeln zum Vergleich
            H = row['magnitude_g']
            n = row['magnitude_k'] if not pd.isna(row['magnitude_k']) else 4.0   

            # Alte einfache Formel (Version 3)
            m_simple = H + 5 * np.log10(r * delta)
            
            # Korrekte Kometenformel 
            m_correct = H + 5*np.log10(delta) + 2.5*n*np.log10(r)
            
            # Debug-Ausgabe für helle Objekte
            # if m_simple < 14.0 or m_correct < 14.0:
            #    print(f"DEBUG {row['designation'][:20]}: "
            #          f"H={H:.1f} n={n:.1f} r={r:.2f} δ={delta:.2f} "
            #          f"m_simple={m_simple:.1f} m_correct={m_correct:.1f}")
            
            # Verwende die korrekte Formel
            m = m_correct
            
            if m < 14.0:
                # Höhe über Horizont
                alt, az, _ = astrometric.altaz()
                
                bright_comets.append({
                    'name': row['designation'],
                    'magnitude': m,
                    'ra': ra.hours,
                    'dec': dec.degrees,
                    'altitude': alt.degrees,
                    'distance_au': delta,
                    'sun_distance_au': r
                })
                
        except Exception as e:
            print(f"Fehler beim Verarbeiten von {row['designation'][:20]}: {e}")
            continue
    
    # Sortieren nach Helligkeit
    bright_comets.sort(key=lambda x: x['magnitude'])
    
    for comet in bright_comets:
        visible = "✓" if comet['altitude'] > 0 else "✗"
        print(f"{comet['name'][:25]:<25} m={comet['magnitude']:.1f} "
              f"RA={comet['ra']:.2f}h Dec={comet['dec']:.1f}° "
              f"Alt={comet['altitude']:.1f}° {visible} "
              f"δ={comet['distance_au']:.2f}AU")

    print(f"\nGefunden: {len(bright_comets)} Kometen heller als 14.0 mag")

except Exception as e:
    print(f"Fehler beim Laden der Kometen: {e}")