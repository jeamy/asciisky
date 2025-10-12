#!/usr/bin/env python3
"""
Test: How much time can we save by pre-filtering asteroids?
Compare computing 2220 vs 500 vs 100 asteroids
"""
import time
from datetime import datetime, timezone
from api.computation import LOADER, ts, eph
from db_utils import get_asteroids_by_magnitude

# Test parameters
TEST_LAT = 46.7632
TEST_LON = 14.8417
TEST_ELEVATION = 405
TEST_TIME = datetime(2027, 6, 15, 14, 30, 0, tzinfo=timezone.utc)

def test_different_limits():
    """Test computation time with different asteroid limits"""
    
    # Load different amounts of asteroids from DB
    limits_to_test = [100, 200, 500, 1000, 2220]
    
    print("=" * 80)
    print("PRE-FILTER OPTIMIZATION TEST")
    print("=" * 80)
    print(f"Question: How much faster if we process fewer asteroids?")
    print(f"Location: {TEST_LAT}°N, {TEST_LON}°E, {TEST_ELEVATION}m")
    print(f"Test time: {TEST_TIME.isoformat()}")
    print("=" * 80)
    print()
    
    from skyfield.data import mpc
    from skyfield.toposlib import Topos
    import pickle
    from bright_asteroids import GM_SUN_Pitjeva_2005_km3_s2, asteroid_apparent_magnitude
    import math
    
    # Setup Skyfield
    sun = eph['sun']
    t = ts.from_datetime(TEST_TIME)
    topos = Topos(latitude_degrees=TEST_LAT, longitude_degrees=TEST_LON, elevation_m=TEST_ELEVATION)
    observer = eph['earth'] + topos
    
    results = []
    
    for limit in limits_to_test:
        print(f"Testing with {limit} asteroids...")
        print("-" * 80)
        
        # Load asteroids from DB
        t_load = time.time()
        asteroid_rows = get_asteroids_by_magnitude(max_h_magnitude=12.0, limit=limit)
        load_time = time.time() - t_load
        
        # Compute positions
        t_compute = time.time()
        visible_count = 0
        
        for row in asteroid_rows:
            try:
                orbit_row = pickle.loads(row['orbit_data'])
                orbit = mpc.mpcorb_orbit(orbit_row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)
                
                # Calculate apparent magnitude
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
                
                # Count visible (V < 10)
                if apparent_mag <= 10.0:
                    visible_count += 1
                    
            except Exception:
                pass
        
        compute_time = time.time() - t_compute
        total_time = load_time + compute_time
        
        results.append({
            'limit': limit,
            'load_time': load_time,
            'compute_time': compute_time,
            'total_time': total_time,
            'visible': visible_count,
            'per_asteroid': compute_time / limit if limit > 0 else 0
        })
        
        print(f"  Load from DB: {load_time:.3f}s")
        print(f"  Compute:      {compute_time:.2f}s")
        print(f"  Total:        {total_time:.2f}s")
        print(f"  Visible:      {visible_count} asteroids (V < 10)")
        print(f"  Per asteroid: {compute_time/limit:.3f}s")
        print()
    
    # Summary
    print("=" * 80)
    print("COMPARISON TABLE")
    print("=" * 80)
    print(f"{'Asteroids':>10} | {'Compute Time':>12} | {'Visible':>8} | {'Speedup':>8}")
    print("-" * 80)
    
    baseline = results[-1]['total_time']  # 2220 asteroids
    
    for r in results:
        speedup = baseline / r['total_time']
        print(f"{r['limit']:>10} | {r['total_time']:>10.2f}s | {r['visible']:>8} | {speedup:>7.1f}x")
    
    print("=" * 80)
    print()
    
    # Find optimal limit
    print("RECOMMENDATION:")
    print("-" * 80)
    
    # Find smallest limit that still finds all visible objects
    max_visible = max(r['visible'] for r in results)
    
    for r in results:
        if r['visible'] == max_visible:
            saving = ((baseline - r['total_time']) / baseline) * 100
            print(f"Process only {r['limit']} asteroids (brightest by H magnitude)")
            print(f"  - Still finds all {max_visible} visible objects")
            print(f"  - Time: {r['total_time']:.2f}s instead of {baseline:.2f}s")
            print(f"  - Saves: {saving:.1f}% of computation time")
            print(f"  - Speedup: {baseline/r['total_time']:.1f}x faster")
            break
    
    print("=" * 80)

if __name__ == "__main__":
    test_different_limits()
