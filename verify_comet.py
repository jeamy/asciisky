import datetime
from skyfield.api import wgs84, Topos
import main as webapp
import comets
import pandas as pd
from skyfield.data import mpc
import math

def verify_comet_magnitude():
    # --- Setup ---
    # Time and location for verification
    dt_utc = datetime.datetime(2025, 9, 8, 0, 45, 0, tzinfo=datetime.timezone.utc)

    # Skyfield objects
    ts = webapp.ts
    eph = webapp.eph
    t = ts.from_datetime(dt_utc)
    topos = Topos(latitude_degrees=48.2082, longitude_degrees=16.3738, elevation_m=171.0)
    observer = eph['earth'] + topos
    sun = eph['sun']

    # --- Manual Calculation ---
    df = comets.load_comet_dataframe()
    if df is None or df.empty:
        print("Could not load comet data.")
        return

    df_reset = df.reset_index()
    hartley_row = df_reset[df_reset['designation'].str.contains('103P/Hartley', na=False)].iloc[0]

    if hartley_row.empty:
        print("Could not find 103P/Hartley in the DataFrame.")
        return

    print("Found 103P/Hartley row:")
    print(hartley_row)

    # Re-implement the magnitude calculation from comets.py
    try:
        from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2
        orbit = mpc.comet_orbit(hartley_row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)
        target = sun + orbit

        astrometric = observer.at(t).observe(target)

        r = sun.at(t).observe(target).distance().au # Heliocentric distance
        delta = astrometric.distance().au # Geocentric distance

        M1 = hartley_row['M1']
        n = hartley_row.get('k1', 4.0) # Default to 4.0 if k1 is not present

        apparent_magnitude = (
            float(M1)
            + 5.0 * math.log10(max(delta, 1e-12))
            + 2.5 * float(n) * math.log10(max(r, 1e-12))
        )

        print(f"\nCalculated Apparent Magnitude for 103P/Hartley: {apparent_magnitude}")

    except Exception as e:
        print(f"An error occurred during calculation: {e}")

if __name__ == "__main__":
    verify_comet_magnitude()
