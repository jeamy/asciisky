#!/usr/bin/env python3
"""
Realistic end-to-end test: Call the ACTUAL functions that get called
Measure where time is spent in a real computation
"""
import time
from datetime import datetime, timezone
from api.computation import LOADER, ts, eph
import bright_asteroids
import comets

# Use unique timestamp to avoid cache
TEST_LAT = 46.7632
TEST_LON = 14.8417
TEST_ELEVATION = 405
TEST_TIME = datetime(2027, 5, int(time.time() % 28) + 1, 12, 0, 0, tzinfo=timezone.utc)

def test_real_computation():
    """Test actual asteroid/comet computation as it happens in production"""
    location = {"latitude": TEST_LAT, "longitude": TEST_LON, "elevation": TEST_ELEVATION}
    
    print("=" * 80)
    print("REALISTIC END-TO-END TEST")
    print("=" * 80)
    print(f"Location: {TEST_LAT}°N, {TEST_LON}°E, {TEST_ELEVATION}m")
    print(f"Test time: {TEST_TIME.isoformat()} (unique)")
    print("=" * 80)
    print()
    
    # Test 1: Asteroids
    print("ASTEROID COMPUTATION:")
    print("-" * 80)
    t_start = time.time()
    
    asteroid_list = bright_asteroids.load_bright_asteroids(
        LOADER, ts, eph, location,
        max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE,
        use_cache=False,  # Force recomputation
        current_dt=TEST_TIME
    )
    
    t_asteroids = time.time() - t_start
    print(f"Time: {t_asteroids:.2f}s ({t_asteroids/60:.2f} min)")
    print(f"Objects: {len(asteroid_list) if asteroid_list else 0}")
    print()
    
    # Test 2: Comets
    print("COMET COMPUTATION:")
    print("-" * 80)
    t_start = time.time()
    
    comet_list = comets.load_comets(
        ts, eph, location,
        use_cache=False,  # Force recomputation
        current_dt=TEST_TIME
    )
    
    t_comets = time.time() - t_start
    print(f"Time: {t_comets:.2f}s ({t_comets/60:.2f} min)")
    print(f"Objects: {len(comet_list) if comet_list else 0}")
    print()
    
    # Summary
    total = t_asteroids + t_comets
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Asteroids: {t_asteroids:7.2f}s ({t_asteroids/total*100:5.1f}%)")
    print(f"Comets:    {t_comets:7.2f}s ({t_comets/total*100:5.1f}%)")
    print(f"TOTAL:     {total:7.2f}s ({total/60:.2f} min)")
    print("=" * 80)
    print()
    print(f"USER WAITING TIME: ~{total/60:.1f} minutes")

if __name__ == "__main__":
    test_real_computation()
