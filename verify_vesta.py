import datetime
from skyfield.api import wgs84
import main as webapp
import bright_asteroids
from skyfield.data import mpc
import math
import pandas as pd

def verify_vesta_magnitude():
    # --- Setup ---
    # Time and location for verification
    dt_utc = datetime.datetime(2025, 9, 8, 0, 45, 0, tzinfo=datetime.timezone.utc)
    location = wgs84.latlon(48.2082, 16.3738, elevation_m=171)

    # Skyfield objects from the main app
    ts = webapp.ts
    eph = webapp.eph
    observer = eph['earth'] + location
    sun = eph['sun']
    t = ts.from_datetime(dt_utc)

    # --- Find Vesta's data ---
    # Load the asteroid dataframe
    df = bright_asteroids.load_bright_asteroids(webapp.LOADER, ts, eph, {"latitude": 48.2082, "longitude": 16.3738, "elevation": 171.0}, use_cache=False, current_dt=dt_utc)

    vesta_data = None
    for asteroid in df:
        if asteroid['name'] == '4 Vesta':
            vesta_data = asteroid
            break

    if vesta_data:
        print(f"Vesta data from script: {vesta_data}")
        # The magnitude is already calculated in the returned data
        print(f"Apparent magnitude for Vesta from script: {vesta_data['magnitude']}")
    else:
        print("Could not find Vesta in the returned data.")
        # Manual calculation if not found in the top bright asteroids
        print("Performing manual calculation for Vesta...")
        import gzip
        with gzip.open(bright_asteroids.MPCORB_FILE, 'rb') as f:
            df_all = mpc.load_mpcorb_dataframe(f)

        # Convert columns to numeric, like in bright_asteroids.py
        numeric_cols = [
            'magnitude_H', 'magnitude_G', 'mean_anomaly_degrees', 'argument_of_perihelion_degrees',
            'longitude_of_ascending_node_degrees', 'inclination_degrees', 'eccentricity',
            'mean_daily_motion_degrees', 'semimajor_axis_au'
        ]
        for col in numeric_cols:
            if col in df_all.columns:
                df_all[col] = pd.to_numeric(df_all[col], errors='coerce')

        # Let's find Vesta by searching the 'designation' column
        print("DataFrame columns:", df_all.columns)

        # The designation for Vesta in MPCORB.DAT might just be 'Vesta' or '4 Vesta'.
        # Or, we can find it by its number. Let's find the row where the 'number' column is '00004'.
        # The 'number' column is the index of the original dataframe, which is now a column.
        # Let's check the first few rows of the 'designation' column to see the format.
        print("Designation column head:")
        print(df_all['designation'].head())

        vesta_row = df_all[df_all['designation'].str.contains('Vesta', na=False)].iloc[0]

        if vesta_row.empty:
            print("Could not find Vesta in the DataFrame.")
            return

        print("Found Vesta row:")
        print(vesta_row)



        from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2
        orbit = mpc.mpcorb_orbit(vesta_row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)
        target = sun + orbit

        astrometric = observer.at(t).observe(target)

        # Distances
        delta = astrometric.distance().au # Geocentric distance
        r = sun.at(t).observe(target).distance().au # Heliocentric distance

        # Phase angle
        phase_angle = astrometric.phase_angle(sun).degrees

        # H and G values for Vesta
        H = vesta_row['magnitude_H']
        # Use the more accurate G value from JPL Horizons
        G = 0.32

        print(f"Using H={H}, G={G} (from JPL)")

        # Calculate apparent magnitude
        mag = bright_asteroids.asteroid_apparent_magnitude(H, G, r, delta, phase_angle)

        print(f"Calculated Apparent Magnitude for Vesta: {mag}")

if __name__ == "__main__":
    verify_vesta_magnitude()
