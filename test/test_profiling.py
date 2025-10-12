#!/usr/bin/env python3
"""
Detailed profiling of asteroid/comet computation to find bottlenecks
"""
import time
import cProfile
import pstats
import io
from datetime import datetime, timezone
from api.computation import LOADER, ts, eph
import bright_asteroids
import comets

# Test parameters
TEST_LAT = 46.7632
TEST_LON = 14.8417
TEST_ELEVATION = 405
TEST_TIME = datetime(2026, 6, 15, 14, 30, 0, tzinfo=timezone.utc)

def profile_asteroids():
    """Profile asteroid computation with detailed timing"""
    location = {"latitude": TEST_LAT, "longitude": TEST_LON, "elevation": TEST_ELEVATION}
    
    print("=" * 80)
    print("PROFILING ASTEROID COMPUTATION")
    print("=" * 80)
    
    # Create profiler
    profiler = cProfile.Profile()
    
    # Profile the computation
    profiler.enable()
    t_start = time.time()
    
    result = bright_asteroids.load_bright_asteroids(
        LOADER, ts, eph, location,
        max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE,
        use_cache=True,
        current_dt=TEST_TIME
    )
    
    t_total = time.time() - t_start
    profiler.disable()
    
    # Get statistics
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s)
    ps.sort_stats('cumulative')
    ps.print_stats(30)  # Top 30 functions
    
    print(f"\nTotal time: {t_total:.2f}s")
    print(f"Objects found: {len(result) if result else 0}")
    print("\nTop 30 functions by cumulative time:")
    print("-" * 80)
    print(s.getvalue())

def profile_comets():
    """Profile comet computation with detailed timing"""
    location = {"latitude": TEST_LAT, "longitude": TEST_LON, "elevation": TEST_ELEVATION}
    
    print("\n\n")
    print("=" * 80)
    print("PROFILING COMET COMPUTATION")
    print("=" * 80)
    
    # Create profiler
    profiler = cProfile.Profile()
    
    # Profile the computation
    profiler.enable()
    t_start = time.time()
    
    result = comets.load_comets(
        ts, eph, location,
        use_cache=True,
        current_dt=TEST_TIME
    )
    
    t_total = time.time() - t_start
    profiler.disable()
    
    # Get statistics
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s)
    ps.sort_stats('cumulative')
    ps.print_stats(30)  # Top 30 functions
    
    print(f"\nTotal time: {t_total:.2f}s")
    print(f"Objects found: {len(result) if result else 0}")
    print("\nTop 30 functions by cumulative time:")
    print("-" * 80)
    print(s.getvalue())

def manual_timing_asteroids():
    """Manual timing of major steps in asteroid computation"""
    from cache_utils import normalize_location, location_key, time_bucket_utc
    from db_utils import get_asteroids_by_magnitude, get_asteroid_orbit_data
    
    location = {"latitude": TEST_LAT, "longitude": TEST_LON, "elevation": TEST_ELEVATION}
    lat, lon, elevation = TEST_LAT, TEST_LON, TEST_ELEVATION
    
    print("\n\n")
    print("=" * 80)
    print("MANUAL TIMING - ASTEROIDS (Step by Step)")
    print("=" * 80)
    
    timings = {}
    
    # Step 1: Load asteroid dataframe
    t = time.time()
    from db_utils import get_asteroids_by_magnitude
    asteroid_rows = get_asteroids_by_magnitude(
        max_magnitude=bright_asteroids.MAX_ABSOLUTE_MAGNITUDE,
        limit=bright_asteroids.MAX_ASTEROID_COUNT
    )
    timings['1_load_dataframe'] = time.time() - t
    print(f"1. Load asteroid list from DB: {timings['1_load_dataframe']:.2f}s ({len(asteroid_rows)} asteroids)")
    
    # Step 2: Filter by rough magnitude
    t = time.time()
    # This happens in process_asteroids_from_sqlite
    timings['2_filter_rough'] = time.time() - t
    print(f"2. Filter by rough magnitude: {timings['2_filter_rough']:.2f}s")
    
    # Step 3: Compute positions for ALL asteroids
    t = time.time()
    from skyfield.api import wgs84
    topos = wgs84.latlon(lat, lon, elevation_m=elevation)
    observer = eph['earth'] + topos
    t_skyfield = ts.from_datetime(TEST_TIME)
    
    computed = 0
    for row in asteroid_rows[:100]:  # Sample first 100 to estimate
        orbit_data = get_asteroid_orbit_data(row['id'])
        if orbit_data:
            asteroid_obj = eph['sun'] + orbit_data
            astrometric = observer.at(t_skyfield).observe(asteroid_obj)
            computed += 1
    
    time_per_asteroid = (time.time() - t) / computed
    estimated_total = time_per_asteroid * len(asteroid_rows)
    timings['3_compute_positions'] = estimated_total
    print(f"3. Compute positions (estimated): {estimated_total:.2f}s")
    print(f"   - Time per asteroid: {time_per_asteroid:.3f}s")
    print(f"   - Total asteroids: {len(asteroid_rows)}")
    
    # Step 4: Rise/set/transit calculations
    t = time.time()
    # Sample 10 asteroids for rise/set
    from skyfield import almanac
    sample_count = 10
    for row in asteroid_rows[:sample_count]:
        orbit_data = get_asteroid_orbit_data(row['id'])
        if orbit_data:
            asteroid_obj = eph['sun'] + orbit_data
            t0 = ts.from_datetime(TEST_TIME.replace(hour=0, minute=0, second=0))
            t1 = ts.from_datetime(TEST_TIME.replace(hour=23, minute=59, second=59))
            f = almanac.risings_and_settings(eph, asteroid_obj, topos)
            times, events = almanac.find_discrete(t0, t1, f)
    
    time_per_rise_set = (time.time() - t) / sample_count
    estimated_rise_set = time_per_rise_set * len(asteroid_rows)
    timings['4_rise_set_transit'] = estimated_rise_set
    print(f"4. Rise/set/transit (estimated): {estimated_rise_set:.2f}s")
    print(f"   - Time per asteroid: {time_per_rise_set:.3f}s")
    
    # Step 5: Store to DB
    timings['5_store_db'] = 0.5  # Usually very fast
    print(f"5. Store to DB: {timings['5_store_db']:.2f}s")
    
    print()
    print("BREAKDOWN:")
    print("-" * 80)
    total = sum(timings.values())
    for key, value in sorted(timings.items(), key=lambda x: x[1], reverse=True):
        percentage = (value / total * 100) if total > 0 else 0
        print(f"{key:30s}: {value:7.2f}s ({percentage:5.1f}%)")
    print("-" * 80)
    print(f"{'ESTIMATED TOTAL':30s}: {total:7.2f}s")

if __name__ == "__main__":
    # Run profiling
    profile_asteroids()
    profile_comets()
    manual_timing_asteroids()
