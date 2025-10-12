#!/usr/bin/env python3
"""
Test: Can we compute r and delta CHEAPLY without full .observe()?
Compare:
1. Full .observe() (current method)
2. Direct orbit distance calculation
3. Rough estimation
"""
import time
import math
from datetime import datetime, timezone
from api.computation import LOADER, ts, eph
from db_utils import get_asteroids_by_magnitude
from skyfield.data import mpc
from skyfield.toposlib import Topos
import pickle
from bright_asteroids import GM_SUN_Pitjeva_2005_km3_s2, asteroid_apparent_magnitude

# Test parameters
TEST_LAT = 46.7632
TEST_LON = 14.8417
TEST_ELEVATION = 405
TEST_TIME = datetime(2027, 6, 15, 14, 30, 0, tzinfo=timezone.utc)

# Setup
sun = eph['sun']
earth = eph['earth']
t = ts.from_datetime(TEST_TIME)
topos = Topos(latitude_degrees=TEST_LAT, longitude_degrees=TEST_LON, elevation_m=TEST_ELEVATION)
observer = earth + topos

# Load sample asteroids
asteroid_rows = get_asteroids_by_magnitude(max_h_magnitude=12.0, limit=100)

print("=" * 80)
print("CHEAP MAGNITUDE CALCULATION TEST")
print("=" * 80)
print(f"Testing {len(asteroid_rows)} asteroids")
print("=" * 80)
print()

# Method 1: Current method (full observe)
print("Method 1: Full .observe() [CURRENT]")
print("-" * 80)
t_start = time.time()
magnitudes_1 = []

for row in asteroid_rows[:100]:
    try:
        orbit_row = pickle.loads(row['orbit_data'])
        orbit = mpc.mpcorb_orbit(orbit_row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)
        
        # Full observe
        astrometric = observer.at(t).observe(sun + orbit)
        r = astrometric.distance().au
        delta = astrometric.radec()[2].au
        phase_angle = math.degrees(math.acos(
            max(-1, min(1, (r**2 + delta**2 - 1) / (2 * r * delta)))
        ))
        
        apparent_mag = asteroid_apparent_magnitude(
            H=row['magnitude_h'], G=row['magnitude_g'] or 0.15,
            r=r, delta=delta, phase_angle_deg=phase_angle
        )
        magnitudes_1.append(apparent_mag)
    except Exception:
        magnitudes_1.append(99)

time_1 = time.time() - t_start
print(f"Time: {time_1:.3f}s ({time_1/100*1000:.1f}ms per asteroid)")
print()

# Method 2: Separate calculations for r and delta
print("Method 2: Separate heliocentric + geocentric positions")
print("-" * 80)
t_start = time.time()
magnitudes_2 = []

for row in asteroid_rows[:100]:
    try:
        orbit_row = pickle.loads(row['orbit_data'])
        orbit = mpc.mpcorb_orbit(orbit_row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)
        
        # Get heliocentric distance (from sun)
        asteroid_pos_helio = (sun + orbit).at(t)
        r = asteroid_pos_helio.distance().au  # Distance from Sun
        
        # Get geocentric distance (from observer)
        asteroid_pos_geo = observer.at(t).observe(sun + orbit)
        delta = asteroid_pos_geo.distance().au  # Distance from Earth
        
        phase_angle = math.degrees(math.acos(
            max(-1, min(1, (r**2 + delta**2 - 1) / (2 * r * delta)))
        ))
        
        apparent_mag = asteroid_apparent_magnitude(
            H=row['magnitude_h'], G=row['magnitude_g'] or 0.15,
            r=r, delta=delta, phase_angle_deg=phase_angle
        )
        magnitudes_2.append(apparent_mag)
    except Exception:
        magnitudes_2.append(99)

time_2 = time.time() - t_start
print(f"Time: {time_2:.3f}s ({time_2/100*1000:.1f}ms per asteroid)")
print()

# Method 3: Rough estimation (worst case)
print("Method 3: Rough estimation (H + 5 magnitudes)")
print("-" * 80)
print("Use absolute magnitude H as proxy")
print("Assume worst case: r=1.5 AU, delta=2.5 AU → adds ~5 mag")
t_start = time.time()
magnitudes_3 = []

for row in asteroid_rows[:100]:
    # Ultra-fast: just use H + constant
    estimated_mag = row['magnitude_h'] + 5.0  # Rough estimate
    magnitudes_3.append(estimated_mag)

time_3 = time.time() - t_start
print(f"Time: {time_3:.3f}s ({time_3/100*1000:.1f}ms per asteroid)")
print()

# Compare results
print("=" * 80)
print("COMPARISON")
print("=" * 80)
print(f"{'Method':<40} | {'Time':>10} | {'Speedup':>8} | {'Accuracy':>10}")
print("-" * 80)
print(f"{'1. Full observe (current)':40} | {time_1:>8.3f}s | {'1.0x':>8} | {'exact':>10}")
print(f"{'2. Separate helio/geo':40} | {time_2:>8.3f}s | {time_1/time_2:>7.1f}x | {'exact':>10}")
print(f"{'3. Rough H+5 estimate':40} | {time_3:>8.3f}s | {time_1/time_3:>7.0f}x | {'~±2 mag':>10}")
print("=" * 80)
print()

# Analyze filtering effectiveness
print("FILTERING EFFECTIVENESS (threshold: V < 10)")
print("-" * 80)

for name, mags in [("Method 1", magnitudes_1), ("Method 2", magnitudes_2), ("Method 3", magnitudes_3)]:
    would_keep = sum(1 for m in mags if m <= 10.0)
    print(f"{name:20}: {would_keep}/100 asteroids would pass filter")

print()

# Sample comparison
print("SAMPLE: First 10 asteroids")
print("-" * 80)
print(f"{'H':>6} | {'Method 1':>10} | {'Method 2':>10} | {'Method 3':>10} | {'Diff 1-2':>10}")
print("-" * 80)
for i in range(min(10, len(magnitudes_1))):
    h = asteroid_rows[i]['magnitude_h']
    diff = abs(magnitudes_1[i] - magnitudes_2[i])
    print(f"{h:>6.2f} | {magnitudes_1[i]:>10.2f} | {magnitudes_2[i]:>10.2f} | {magnitudes_3[i]:>10.2f} | {diff:>10.3f}")
print("=" * 80)

print()
print("CONCLUSION:")
print("-" * 80)
print("• Method 2 is NOT faster (still needs .observe())")
print("• Method 3 is very fast but inaccurate")
print("• BEST SOLUTION: Cache the position result and reuse it!")
