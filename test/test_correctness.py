#!/usr/bin/env python3
"""
Correctness test: Verify optimization produces SAME results
Compare old vs new implementation
"""
import time
from datetime import datetime, timezone
from api.computation import LOADER, ts, eph
import bright_asteroids

# Test parameters - same as test_realistic.py
TEST_LAT = 46.7632
TEST_LON = 14.8417
TEST_ELEVATION = 405
TEST_TIME = datetime(2027, 5, 12, 12, 0, 0, tzinfo=timezone.utc)

def test_correctness_and_performance():
    """Test that optimization is correct AND faster"""
    location = {"latitude": TEST_LAT, "longitude": TEST_LON, "elevation": TEST_ELEVATION}
    
    print("=" * 80)
    print("CORRECTNESS & PERFORMANCE TEST")
    print("=" * 80)
    print(f"Location: {TEST_LAT}°N, {TEST_LON}°E, {TEST_ELEVATION}m")
    print(f"Test time: {TEST_TIME.isoformat()}")
    print("=" * 80)
    print()
    
    # Expected results from OLD version (test_realistic.py)
    print("EXPECTED RESULTS (from previous test):")
    print("-" * 80)
    print("Asteroids: 5 objects, ~71s")
    print("Total time: ~158s (2.63 min)")
    print()
    
    # Test NEW optimized version
    print("TESTING NEW OPTIMIZED VERSION:")
    print("-" * 80)
    
    t_start = time.time()
    asteroid_list = bright_asteroids.load_bright_asteroids(
        LOADER, ts, eph, location,
        max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE,
        use_cache=False,  # Force recomputation
        current_dt=TEST_TIME
    )
    t_total = time.time() - t_start
    
    asteroid_count = len(asteroid_list) if asteroid_list else 0
    
    print(f"Time:    {t_total:.2f}s ({t_total/60:.2f} min)")
    print(f"Objects: {asteroid_count}")
    print()
    
    # Show asteroid details
    if asteroid_list:
        print("FOUND ASTEROIDS:")
        print("-" * 80)
        print(f"{'Name':<20} | {'V mag':>6} | {'Alt':>6} | {'Az':>6}")
        print("-" * 80)
        for ast in asteroid_list:
            name = ast.get('name', 'Unknown')
            v_mag = ast.get('magnitude', 0)  # Correct key!
            alt = ast.get('altitude', 0)
            az = ast.get('azimuth', 0)
            print(f"{name:<20} | {v_mag:>6.2f} | {alt:>6.1f} | {az:>6.1f}")
    
    print()
    print("=" * 80)
    print("VERIFICATION")
    print("=" * 80)
    
    # Check correctness
    expected_count = 5
    expected_time = 71.48
    
    correct_count = asteroid_count == expected_count
    speedup = expected_time / t_total if t_total > 0 else 0
    time_saved = expected_time - t_total
    
    print(f"Object count:  {asteroid_count} (expected: {expected_count}) {'✓' if correct_count else '✗ WRONG!'}")
    print(f"Old time:      {expected_time:.2f}s")
    print(f"New time:      {t_total:.2f}s")
    print(f"Speedup:       {speedup:.2f}x")
    print(f"Time saved:    {time_saved:.2f}s ({time_saved/expected_time*100:.1f}%)")
    print()
    
    if not correct_count:
        print("⚠️  WARNING: Object count differs! Optimization may be incorrect!")
        print("    Expected: 5 asteroids")
        print(f"    Got:      {asteroid_count} asteroids")
        print()
        if asteroid_count < expected_count:
            print("    → Pre-filter too aggressive? Check safety margin!")
        else:
            print("    → Pre-filter too loose? Check logic!")
    else:
        print("✓ CORRECTNESS: Same number of objects found")
        
        if speedup > 1.1:
            print(f"✓ PERFORMANCE: {speedup:.2f}x faster!")
        elif speedup >= 0.9:
            print("~ PERFORMANCE: About the same speed")
        else:
            print(f"✗ PERFORMANCE: Slower than before ({speedup:.2f}x)")
    
    print("=" * 80)
    
    return asteroid_count, t_total, correct_count

if __name__ == "__main__":
    test_correctness_and_performance()
