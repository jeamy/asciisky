#!/usr/bin/env python3
"""
Test script to measure computation time for asteroids/comets for a specific time ±12h
"""
import time
from datetime import datetime, timezone, timedelta
from api.computation import LOADER, ts, eph
import bright_asteroids
import comets

# Test parameters
TEST_LAT = 46.7632
TEST_LON = 14.8417
TEST_ELEVATION = 405
TEST_TIME = datetime(2025, 11, 30, 11, 0, 0, tzinfo=timezone.utc)  # 30. November 2025, 11:00 UTC
HOURS_RADIUS = 12

def test_computation():
    """Test computation time for ±12h window"""
    location = {"latitude": TEST_LAT, "longitude": TEST_LON, "elevation": TEST_ELEVATION}
    
    # Calculate time range
    start_time = TEST_TIME - timedelta(hours=HOURS_RADIUS)
    end_time = TEST_TIME + timedelta(hours=HOURS_RADIUS)
    total_hours = (end_time - start_time).total_seconds() / 3600
    
    print("=" * 80)
    print(f"SPOT COMPUTATION TEST")
    print("=" * 80)
    print(f"Location: {TEST_LAT}°N, {TEST_LON}°E, {TEST_ELEVATION}m")
    print(f"Center time: {TEST_TIME.isoformat()}")
    print(f"Time range: {start_time.isoformat()} to {end_time.isoformat()}")
    print(f"Total hours: {int(total_hours)} hours ({int(total_hours)} time buckets)")
    print("=" * 80)
    print()
    
    # Test asteroids
    print("Testing ASTEROIDS computation...")
    print("-" * 80)
    
    asteroid_times = []
    current_time = start_time
    
    while current_time <= end_time:
        t_start = time.time()
        
        try:
            asteroid_list = bright_asteroids.load_bright_asteroids(
                LOADER, ts, eph, location,
                max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE,
                use_cache=True,
                current_dt=current_time
            )
            
            t_end = time.time()
            duration = t_end - t_start
            asteroid_times.append(duration)
            
            count = len(asteroid_list) if asteroid_list else 0
            status = "cached" if duration < 0.1 else "computed"
            print(f"  {current_time.strftime('%Y-%m-%d %H:%M')}: {duration:6.2f}s ({count:2d} objects) [{status}]")
            
        except Exception as e:
            print(f"  {current_time.strftime('%Y-%m-%d %H:%M')}: ERROR - {e}")
            asteroid_times.append(0)
        
        current_time += timedelta(hours=1)
    
    print()
    print(f"Asteroids - Total time: {sum(asteroid_times):.2f}s")
    print(f"Asteroids - Average per hour: {sum(asteroid_times)/len(asteroid_times):.2f}s")
    print(f"Asteroids - Min: {min(asteroid_times):.2f}s, Max: {max(asteroid_times):.2f}s")
    print()
    
    # Test comets
    print("Testing COMETS computation...")
    print("-" * 80)
    
    comet_times = []
    current_time = start_time
    
    while current_time <= end_time:
        t_start = time.time()
        
        try:
            comet_list = comets.load_comets(
                ts, eph, location,
                use_cache=True,
                current_dt=current_time
            )
            
            t_end = time.time()
            duration = t_end - t_start
            comet_times.append(duration)
            
            count = len(comet_list) if comet_list else 0
            status = "cached" if duration < 0.1 else "computed"
            print(f"  {current_time.strftime('%Y-%m-%d %H:%M')}: {duration:6.2f}s ({count:2d} objects) [{status}]")
            
        except Exception as e:
            print(f"  {current_time.strftime('%Y-%m-%d %H:%M')}: ERROR - {e}")
            comet_times.append(0)
        
        current_time += timedelta(hours=1)
    
    print()
    print(f"Comets - Total time: {sum(comet_times):.2f}s")
    print(f"Comets - Average per hour: {sum(comet_times)/len(comet_times):.2f}s")
    print(f"Comets - Min: {min(comet_times):.2f}s, Max: {max(comet_times):.2f}s")
    print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    total_time = sum(asteroid_times) + sum(comet_times)
    print(f"Total computation time: {total_time:.2f}s ({total_time/60:.2f} minutes)")
    print(f"Time per hour bucket: {total_time/int(total_hours):.2f}s")
    print(f"Asteroids: {sum(asteroid_times):.2f}s ({sum(asteroid_times)/total_time*100:.1f}%)")
    print(f"Comets: {sum(comet_times):.2f}s ({sum(comet_times)/total_time*100:.1f}%)")
    print("=" * 80)

if __name__ == "__main__":
    test_computation()
