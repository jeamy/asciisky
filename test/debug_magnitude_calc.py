#!/usr/bin/env python3
"""
Debug: Check if magnitude calculation works for first 10 comets
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from api.computation import ts, eph
from db_utils import load_comets_dataframe_from_db
from skyfield.data import mpc
from skyfield.toposlib import Topos
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2 as GM_SUN
import math
import pandas as pd
import numpy as np

TEST_LAT = 46.7632
TEST_LON = 14.8417
TEST_ELEVATION = 405
TEST_TIME = datetime(2025, 10, 14, 20, 0, 0, tzinfo=timezone.utc)

print("=" * 80)
print("MAGNITUDE CALCULATION TEST")
print("=" * 80)
print()

# Load comets from DB
df = load_comets_dataframe_from_db(18.0)
print(f"Loaded {len(df)} comets from DB")
print()

# Setup Skyfield
sun = eph['sun']
t = ts.from_datetime(TEST_TIME)
topos = Topos(latitude_degrees=TEST_LAT, longitude_degrees=TEST_LON, elevation_m=TEST_ELEVATION)
observer = eph['earth'] + topos

print(f"Testing first 20 comets...")
print("-" * 80)
print(f"{'Designation':<30} | {'M1':>5} | {'k1':>5} | {'r (AU)':>8} | {'Δ (AU)':>8} | {'V mag':>7} | {'Status'}")
print("-" * 80)

success = 0
fail = 0
too_faint = 0

for i, (designation, row) in enumerate(df.head(20).iterrows()):
    try:
        # Prepare row
        row2 = row.copy()
        row2['designation'] = designation
        
        # Create orbit
        orbit = mpc.comet_orbit(row2, ts, gm_km3_s2=GM_SUN)
        
        # Determine target
        try:
            center_code = int(getattr(orbit, 'center', 10))
        except:
            center_code = 10
        target = (sun + orbit) if center_code != 0 else orbit
        
        # Calculate position
        astrometric = observer.at(t).observe(target)
        
        # Calculate distances
        comet_helio = target.at(t)
        r = comet_helio.distance().au
        delta = astrometric.distance().au
        
        # Calculate magnitude
        M1 = float(row2.get('M1'))
        n_raw = row2.get('k1')
        n = float(n_raw) if (n_raw is not None and pd.notna(n_raw)) else 4.0
        
        apparent_mag = (
            float(M1)
            + 5.0 * math.log10(max(delta, 1e-12))
            + 2.5 * float(n) * math.log10(max(r, 1e-12))
        )
        
        status = "✓"
        if apparent_mag <= 14.0:
            status = "✓ BRIGHT"
            success += 1
        else:
            status = f"  Faint"
            too_faint += 1
        
        print(f"{designation[:30]:<30} | {M1:>5.1f} | {n:>5.1f} | {r:>8.3f} | {delta:>8.3f} | {apparent_mag:>7.2f} | {status}")
        
    except Exception as e:
        print(f"{designation[:30]:<30} | {'?':>5} | {'?':>5} | {'?':>8} | {'?':>8} | {'?':>7} | ✗ {str(e)[:20]}")
        fail += 1

print("-" * 80)
print(f"Success: {success} bright, {too_faint} too faint, {fail} failed")
print()

if success == 0 and too_faint > 0:
    print("⚠️  ALL comets are too faint for current date/location!")
    print("   This might be normal - comets vary greatly in brightness")
    print("   They may be too far from the sun/earth right now")
elif fail > 0:
    print(f"⚠️  {fail} orbit calculations failed")
