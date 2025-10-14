#!/usr/bin/env python3
"""
Test the specific comets from KStars screenshot
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from api.computation import ts, eph
from db_utils import get_db_connection
from skyfield.data import mpc
from skyfield.toposlib import Topos
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2 as GM_SUN
import math
import pandas as pd
import pickle

TEST_LAT = 46.7632
TEST_LON = 14.8417
TEST_ELEVATION = 405
TEST_TIME = datetime(2025, 10, 14, 20, 0, 0, tzinfo=timezone.utc)

print("=" * 80)
print("KSTARS KOMETEN-VERGLEICH")
print("=" * 80)
print(f"Datum: 14. Oktober 2025, 20:00 UTC (22:00 MESZ)")
print(f"KStars Filter: 14,00 mag")
print("=" * 80)
print()

# Setup Skyfield
sun = eph['sun']
t = ts.from_datetime(TEST_TIME)
topos = Topos(latitude_degrees=TEST_LAT, longitude_degrees=TEST_LON, elevation_m=TEST_ELEVATION)
observer = eph['earth'] + topos

# KStars comets
kstars_comets = [
    'C/2025 K1 (ATLAS)',
    'C/2025 R2 (SWAN)',
    'C/2025 A6 (Lemmon)',
    'C/2024 E1 (Wierzchos)',
    '141P-E/Machholz',
    '141P-G/Machholz',
    '141P-P/Machholz'
]

print(f"{'Komet':<30} | {'M1':>5} | {'k1':>5} | {'r (AU)':>8} | {'Δ (AU)':>8} | {'V mag':>7} | {'Alt':>6} | {'Status'}")
print("-" * 95)

conn = get_db_connection()
found_count = 0

for comet_name in kstars_comets:
    cursor = conn.execute("SELECT designation, orbit_data FROM comets WHERE designation LIKE ?", (f'%{comet_name}%',))
    row = cursor.fetchone()
    
    if not row:
        # Try variations
        base_name = comet_name.replace('-E/', '/').replace('-G/', '/').replace('-P/', '/')
        cursor = conn.execute("SELECT designation, orbit_data FROM comets WHERE designation LIKE ?", (f'%{base_name}%',))
        row = cursor.fetchone()
    
    if not row:
        print(f"{comet_name:<30} | {'?':>5} | {'?':>5} | {'?':>8} | {'?':>8} | {'?':>7} | {'?':>6} | NOT IN DB")
        continue
    
    try:
        designation = row['designation']
        orbit_row = pickle.loads(row['orbit_data'])
        
        # Add designation to the row
        orbit_row['designation'] = designation
        
        # Create orbit
        orbit = mpc.comet_orbit(orbit_row, ts, gm_km3_s2=GM_SUN)
        
        # Determine target
        try:
            center_code = int(getattr(orbit, 'center', 10))
        except:
            center_code = 10
        target = (sun + orbit) if center_code != 0 else orbit
        
        # Calculate position
        astrometric = observer.at(t).observe(target)
        comet_helio = target.at(t)
        r = comet_helio.distance().au
        delta = astrometric.distance().au
        
        # Altitude
        alt, az, _ = astrometric.apparent().altaz()
        
        # Calculate magnitude
        M1 = float(orbit_row.get('M1'))
        n_raw = orbit_row.get('k1')
        n = float(n_raw) if (n_raw is not None and pd.notna(n_raw)) else 4.0
        
        apparent_mag = (
            float(M1)
            + 5.0 * math.log10(max(delta, 1e-12))
            + 2.5 * float(n) * math.log10(max(r, 1e-12))
        )
        
        status = "✓" if apparent_mag <= 16.0 else "Faint"
        if apparent_mag <= 16.0:
            found_count += 1
        
        print(f"{designation[:30]:<30} | {M1:>5.1f} | {n:>5.1f} | {r:>8.3f} | {delta:>8.3f} | {apparent_mag:>7.2f} | {alt.degrees:>6.1f}° | {status}")
        
    except Exception as e:
        print(f"{comet_name:<30} | {'?':>5} | {'?':>5} | {'?':>8} | {'?':>8} | {'?':>7} | {'?':>6} | ERROR: {str(e)[:20]}")

print("-" * 95)
print(f"\nKStars zeigt: 7 Kometen")
print(f"Wir finden:   {found_count} Kometen (V <= 16.0)")
print()

if found_count < 7:
    print("⚠️  PROBLEM: Wir finden weniger Kometen als KStars!")
    print()
    print("Mögliche Ursachen:")
    print("1. KStars verwendet anderen Magnitudenfilter (M1 statt V?)")
    print("2. KStars zeigt Kometen 'über die Nacht verteilt' (nicht alle gleichzeitig)")
    print("3. Unsere Magnitude-Berechnung ist anders als KStars")
    print("4. Verschiedene Orbit-Daten (verschiedene Epochen)")
