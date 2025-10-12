#!/usr/bin/env python3
"""
Correctness test for comet optimization
"""
import time
from datetime import datetime, timezone
from api.computation import ts, eph
import comets

# Test parameters - same as before
TEST_LAT = 46.7632
TEST_LON = 14.8417
TEST_ELEVATION = 405
TEST_TIME = datetime(2027, 5, 12, 12, 0, 0, tzinfo=timezone.utc)

def test_comets():
    """Test comet computation after optimization"""
    location = {"latitude": TEST_LAT, "longitude": TEST_LON, "elevation": TEST_ELEVATION}
    
    print("=" * 80)
    print("COMET OPTIMIZATION TEST")
    print("=" * 80)
    print(f"Location: {TEST_LAT}°N, {TEST_LON}°E, {TEST_ELEVATION}m")
    print(f"Test time: {TEST_TIME.isoformat()}")
    print("=" * 80)
    print()
    
    # Expected results from OLD version
    print("EXPECTED RESULTS (from previous test):")
    print("-" * 80)
    print("Comets: 0 objects, ~86.47s")
    print()
    
    # Test NEW optimized version
    print("TESTING NEW OPTIMIZED VERSION:")
    print("-" * 80)
    
    t_start = time.time()
    comet_list = comets.load_comets(
        ts, eph, location,
        use_cache=False,  # Force recomputation
        current_dt=TEST_TIME
    )
    t_total = time.time() - t_start
    
    comet_count = len(comet_list) if comet_list else 0
    
    print(f"Time:    {t_total:.2f}s ({t_total/60:.2f} min)")
    print(f"Objects: {comet_count}")
    print()
    
    # Show comet details
    if comet_list:
        print("FOUND COMETS:")
        print("-" * 80)
        print(f"{'Name':<30} | {'V mag':>6} | {'Alt':>6} | {'Az':>6}")
        print("-" * 80)
        for c in comet_list:
            name = c.get('name', 'Unknown')
            v_mag = c.get('magnitude', 0)
            alt = c.get('altitude', 0)
            az = c.get('azimuth', 0)
            print(f"{name:<30} | {v_mag:>6.2f} | {alt:>6.1f} | {az:>6.1f}")
    else:
        print("(No comets found - expected for this date/location)")
    
    print()
    print("=" * 80)
    print("VERIFICATION")
    print("=" * 80)
    
    # Check correctness
    expected_count = 0
    expected_time = 86.47
    
    correct_count = comet_count == expected_count
    speedup = expected_time / t_total if t_total > 0 else 0
    time_saved = expected_time - t_total
    
    print(f"Object count:  {comet_count} (expected: {expected_count}) {'✓' if correct_count else '✗ WRONG!'}")
    print(f"Old time:      {expected_time:.2f}s")
    print(f"New time:      {t_total:.2f}s")
    print(f"Speedup:       {speedup:.2f}x")
    print(f"Time saved:    {time_saved:.2f}s ({time_saved/expected_time*100:.1f}%)")
    print()
    
    if not correct_count:
        print("⚠️  WARNING: Object count differs!")
        print(f"    Expected: {expected_count} comets")
        print(f"    Got:      {comet_count} comets")
        if comet_count < expected_count:
            print("    → Pre-filter too aggressive?")
        else:
            print("    → Pre-filter too loose?")
    else:
        print("✓ CORRECTNESS: Same number of objects found")
        
        if speedup > 1.1:
            print(f"✓ PERFORMANCE: {speedup:.2f}x faster!")
        elif speedup >= 0.9:
            print("~ PERFORMANCE: About the same speed")
        else:
            print(f"✗ PERFORMANCE: Slower than before ({speedup:.2f}x)")
    
    print("=" * 80)
    
    # Combined summary
    print()
    print("COMBINED ASTEROID + COMET SUMMARY:")
    print("-" * 80)
    asteroid_old = 71.48
    asteroid_new = 6.76
    comet_old = expected_time
    comet_new = t_total
    
    total_old = asteroid_old + comet_old
    total_new = asteroid_new + comet_new
    
    print(f"Asteroids: {asteroid_old:.2f}s → {asteroid_new:.2f}s")
    print(f"Comets:    {comet_old:.2f}s → {comet_new:.2f}s")
    print(f"TOTAL:     {total_old:.2f}s → {total_new:.2f}s")
    print(f"Overall speedup: {total_old/total_new:.2f}x")
    print(f"Time saved: {total_old - total_new:.2f}s")
    print()
    print(f"USER EXPERIENCE:")
    print(f"  Before: ~{total_old/60:.1f} minutes per hour")
    print(f"  After:  ~{total_new/60:.1f} minutes per hour")
    print(f"  For ±12h (24 hours): ~{(total_new*24)/60:.0f} minutes (was {(total_old*24)/60:.0f} min)")
    print("=" * 80)

if __name__ == "__main__":
    test_comets()
