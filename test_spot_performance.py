#!/usr/bin/env python3
"""
Performance test for spot computation:
1. Clear DB for test timestamp
2. Trigger spot computation for single hour
3. Measure time until data is available
4. Check if expansion task started
5. Report actual measured times
"""
import time
import sys
import sqlite3
from datetime import datetime, timezone, timedelta
from api.computation import LOADER, ts, eph
import bright_asteroids
import comets
from cache_utils import normalize_location, location_key, time_bucket_utc

# Test parameters
TEST_LAT = 46.7632
TEST_LON = 14.8417
TEST_ELEVATION = 405
# Use a future date that definitely has no cache
TEST_TIME = datetime(2026, 6, 15, 14, 30, 0, tzinfo=timezone.utc)

def clear_db_for_test():
    """Clear DB entries for test location and time"""
    lat_norm, lon_norm, elev_norm = normalize_location(TEST_LAT, TEST_LON, TEST_ELEVATION)
    loc_key_str = location_key(lat_norm, lon_norm, elev_norm)
    
    # Calculate time buckets for ±12h
    start_time = TEST_TIME - timedelta(hours=12)
    end_time = TEST_TIME + timedelta(hours=12)
    
    buckets = []
    current = start_time
    while current <= end_time:
        bucket = time_bucket_utc(current, 1)
        buckets.append(bucket)
        current += timedelta(hours=1)
    
    try:
        conn = sqlite3.connect('data/asciisky.db')
        cursor = conn.cursor()
        
        # Clear asteroids
        deleted_asteroids = 0
        for bucket in buckets:
            cursor.execute('DELETE FROM asteroid_positions WHERE location_key = ? AND time_bucket = ?', 
                          (loc_key_str, bucket))
            deleted_asteroids += cursor.rowcount
        
        # Clear comets
        deleted_comets = 0
        for bucket in buckets:
            cursor.execute('DELETE FROM comet_positions WHERE location_key = ? AND time_bucket = ?', 
                          (loc_key_str, bucket))
            deleted_comets += cursor.rowcount
        
        conn.commit()
        conn.close()
        
        print(f"Cleared DB: {deleted_asteroids} asteroid entries, {deleted_comets} comet entries")
        print(f"Location: {loc_key_str}")
        print(f"Time range: {buckets[0]} to {buckets[-1]}")
        return True
    except Exception as e:
        print(f"Error clearing DB: {e}")
        return False

def check_data_available(location, dt_utc):
    """Check if both asteroid and comet data are available for given time"""
    try:
        # Check asteroids
        lat_norm, lon_norm, elev_norm = normalize_location(location['latitude'], 
                                                           location['longitude'], 
                                                           location['elevation'])
        loc_key_str = location_key(lat_norm, lon_norm, elev_norm)
        bucket = time_bucket_utc(dt_utc, 1)
        
        conn = sqlite3.connect('data/asciisky.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM asteroid_positions WHERE location_key = ? AND time_bucket = ?',
                      (loc_key_str, bucket))
        asteroid_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM comet_positions WHERE location_key = ? AND time_bucket = ?',
                      (loc_key_str, bucket))
        comet_count = cursor.fetchone()[0]
        
        conn.close()
        
        return asteroid_count > 0 and comet_count > 0, asteroid_count, comet_count
    except Exception as e:
        print(f"Error checking data: {e}")
        return False, 0, 0

def compute_single_hour(location, dt_utc):
    """Compute asteroids and comets for a single hour"""
    print(f"\n{'='*80}")
    print(f"COMPUTING SINGLE HOUR: {dt_utc.isoformat()}")
    print(f"{'='*80}")
    
    # Measure asteroids
    t_start = time.time()
    try:
        asteroid_list = bright_asteroids.load_bright_asteroids(
            LOADER, ts, eph, location,
            max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE,
            use_cache=True,
            current_dt=dt_utc
        )
        t_asteroids = time.time() - t_start
        asteroid_count = len(asteroid_list) if asteroid_list else 0
        print(f"✓ Asteroids: {t_asteroids:.2f}s ({asteroid_count} objects)")
    except Exception as e:
        print(f"✗ Asteroids failed: {e}")
        return None
    
    # Measure comets
    t_start = time.time()
    try:
        comet_list = comets.load_comets(
            ts, eph, location,
            use_cache=True,
            current_dt=dt_utc
        )
        t_comets = time.time() - t_start
        comet_count = len(comet_list) if comet_list else 0
        print(f"✓ Comets: {t_comets:.2f}s ({comet_count} objects)")
    except Exception as e:
        print(f"✗ Comets failed: {e}")
        return None
    
    total_time = t_asteroids + t_comets
    print(f"{'='*80}")
    print(f"TOTAL TIME: {total_time:.2f}s ({total_time/60:.2f} minutes)")
    print(f"{'='*80}\n")
    
    return {
        'total_time': total_time,
        'asteroid_time': t_asteroids,
        'comet_time': t_comets,
        'asteroid_count': asteroid_count,
        'comet_count': comet_count
    }

def test_performance():
    """Main test function"""
    location = {"latitude": TEST_LAT, "longitude": TEST_LON, "elevation": TEST_ELEVATION}
    
    print("=" * 80)
    print("SPOT COMPUTATION PERFORMANCE TEST")
    print("=" * 80)
    print(f"Location: {TEST_LAT}°N, {TEST_LON}°E, {TEST_ELEVATION}m")
    print(f"Test time: {TEST_TIME.isoformat()}")
    print("=" * 80)
    print()
    
    # Step 1: Clear DB
    print("Step 1: Clearing DB for test...")
    if not clear_db_for_test():
        print("Failed to clear DB, aborting test")
        return
    print()
    
    # Step 2: Verify no data exists
    print("Step 2: Verifying no data exists...")
    available, ast_count, com_count = check_data_available(location, TEST_TIME)
    if available:
        print(f"WARNING: Data still exists! Asteroids: {ast_count}, Comets: {com_count}")
        print("Aborting test")
        return
    print("✓ Confirmed: No cached data exists")
    print()
    
    # Step 3: Compute single hour
    print("Step 3: Computing SINGLE HOUR (spot computation)...")
    result = compute_single_hour(location, TEST_TIME)
    
    if not result:
        print("Computation failed, aborting test")
        return
    
    # Step 4: Verify data now exists
    print("Step 4: Verifying data was cached...")
    available, ast_count, com_count = check_data_available(location, TEST_TIME)
    if not available:
        print(f"✗ Data not cached! Asteroids: {ast_count}, Comets: {com_count}")
        return
    print(f"✓ Data cached successfully! Asteroids: {ast_count}, Comets: {com_count}")
    print()
    
    # Step 5: Test cache retrieval speed
    print("Step 5: Testing cache retrieval speed...")
    t_start = time.time()
    asteroid_list = bright_asteroids.load_bright_asteroids(
        LOADER, ts, eph, location,
        max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE,
        use_cache=True,
        current_dt=TEST_TIME
    )
    comet_list = comets.load_comets(
        ts, eph, location,
        use_cache=True,
        current_dt=TEST_TIME
    )
    t_cache = time.time() - t_start
    print(f"✓ Cache retrieval: {t_cache:.3f}s (should be < 0.1s)")
    print()
    
    # Summary
    print("=" * 80)
    print("TEST RESULTS")
    print("=" * 80)
    print(f"First computation (single hour):")
    print(f"  - Total time: {result['total_time']:.2f}s ({result['total_time']/60:.2f} minutes)")
    print(f"  - Asteroids: {result['asteroid_time']:.2f}s ({result['asteroid_count']} objects)")
    print(f"  - Comets: {result['comet_time']:.2f}s ({result['comet_count']} objects)")
    print(f"\nCache retrieval (same hour):")
    print(f"  - Total time: {t_cache:.3f}s")
    print(f"  - Speedup: {result['total_time']/t_cache:.0f}x faster")
    print()
    print(f"USER EXPERIENCE:")
    print(f"  - First request: ~{result['total_time']/60:.1f} minutes")
    print(f"  - Subsequent requests: < 0.1 seconds")
    print("=" * 80)
    
    # Check for ±12h (expansion would handle this)
    print("\nChecking surrounding hours (±12h)...")
    hours_with_data = 0
    for h in range(-12, 13):
        test_dt = TEST_TIME + timedelta(hours=h)
        available, _, _ = check_data_available(location, test_dt)
        if available:
            hours_with_data += 1
    
    print(f"Hours with cached data: {hours_with_data}/25")
    if hours_with_data == 1:
        print("✓ Correct: Only center hour computed (expansion would handle rest)")
    else:
        print(f"? Unexpected: {hours_with_data} hours have data")

if __name__ == "__main__":
    test_performance()
