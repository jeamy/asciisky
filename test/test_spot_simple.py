#!/usr/bin/env python3
"""
Simple performance test: Measure computation time for single hour
Uses a future date to ensure no cache exists
"""
import time
from datetime import datetime, timezone
from api.computation import LOADER, ts, eph
import bright_asteroids
import comets

# Test parameters - future date with no cache
TEST_LAT = 46.7632
TEST_LON = 14.8417
TEST_ELEVATION = 405
TEST_TIME = datetime(2026, 6, 15, 14, 30, 0, tzinfo=timezone.utc)

def test_single_hour():
    """Test computation time for a single hour"""
    location = {"latitude": TEST_LAT, "longitude": TEST_LON, "elevation": TEST_ELEVATION}
    
    print("=" * 80)
    print("SINGLE HOUR COMPUTATION TEST")
    print("=" * 80)
    print(f"Location: {TEST_LAT}°N, {TEST_LON}°E, {TEST_ELEVATION}m")
    print(f"Test time: {TEST_TIME.isoformat()}")
    print("=" * 80)
    print()
    
    # First run - should compute from scratch
    print("FIRST RUN (no cache):")
    print("-" * 80)
    
    t_start_total = time.time()
    
    # Asteroids
    t_start = time.time()
    asteroid_list = bright_asteroids.load_bright_asteroids(
        LOADER, ts, eph, location,
        max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE,
        use_cache=True,
        current_dt=TEST_TIME
    )
    t_asteroids = time.time() - t_start
    asteroid_count = len(asteroid_list) if asteroid_list else 0
    
    # Comets
    t_start = time.time()
    comet_list = comets.load_comets(
        ts, eph, location,
        use_cache=True,
        current_dt=TEST_TIME
    )
    t_comets = time.time() - t_start
    comet_count = len(comet_list) if comet_list else 0
    
    t_total_first = time.time() - t_start_total
    
    print(f"Asteroids: {t_asteroids:7.2f}s ({asteroid_count} objects)")
    print(f"Comets:    {t_comets:7.2f}s ({comet_count} objects)")
    print(f"TOTAL:     {t_total_first:7.2f}s ({t_total_first/60:.2f} minutes)")
    print()
    
    # Second run - should use cache
    print("SECOND RUN (with cache):")
    print("-" * 80)
    
    t_start_total = time.time()
    
    # Asteroids
    t_start = time.time()
    asteroid_list = bright_asteroids.load_bright_asteroids(
        LOADER, ts, eph, location,
        max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE,
        use_cache=True,
        current_dt=TEST_TIME
    )
    t_asteroids = time.time() - t_start
    
    # Comets
    t_start = time.time()
    comet_list = comets.load_comets(
        ts, eph, location,
        use_cache=True,
        current_dt=TEST_TIME
    )
    t_comets = time.time() - t_start
    
    t_total_second = time.time() - t_start_total
    
    print(f"Asteroids: {t_asteroids:7.3f}s")
    print(f"Comets:    {t_comets:7.3f}s")
    print(f"TOTAL:     {t_total_second:7.3f}s")
    print()
    
    # Summary
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"First computation:  {t_total_first:7.2f}s ({t_total_first/60:5.2f} min)")
    print(f"Second computation: {t_total_second:7.3f}s")
    print(f"Speedup:            {t_total_first/t_total_second:7.0f}x")
    print()
    print("INTERPRETATION:")
    print(f"  - User selecting new date: waits ~{t_total_first/60:.1f} minutes")
    print(f"  - User polling same date:   waits ~{t_total_second:.2f} seconds")
    print()
    print("CURRENT SPOT STRATEGY:")
    print(f"  - Computes single hour first: {t_total_first/60:.1f} min")
    print(f"  - Then expands ±12h (23 more hours): ~{(t_total_first * 23)/60:.0f} min")
    print(f"  - Total for ±12h window: ~{(t_total_first * 24)/60:.0f} min")
    print("=" * 80)

if __name__ == "__main__":
    test_single_hour()
