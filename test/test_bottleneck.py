#!/usr/bin/env python3
"""
Find the bottleneck: Measure each major step in computation
Use a timestamp that definitely has NO cache
"""
import time
from datetime import datetime, timezone
from api.computation import LOADER, ts, eph
from db_utils import get_asteroids_by_magnitude, get_asteroid_orbit_data
from skyfield.api import wgs84
from skyfield import almanac
import bright_asteroids

# Test parameters - use a time that changes each run
TEST_LAT = 46.7632
TEST_LON = 14.8417
TEST_ELEVATION = 405
# Use seconds to make it unique
TEST_TIME = datetime(2027, 3, 20, 7, 33, int(time.time() % 60), tzinfo=timezone.utc)

def measure_step(description, func, *args, **kwargs):
    """Measure a single step"""
    t = time.time()
    result = func(*args, **kwargs)
    elapsed = time.time() - t
    print(f"  {description:50s}: {elapsed:7.3f}s")
    return elapsed, result

print("=" * 80)
print("BOTTLENECK ANALYSIS - ASTEROID COMPUTATION")
print("=" * 80)
print(f"Test time: {TEST_TIME.isoformat()} (unique - no cache)")
print("=" * 80)
print()

timings = {}

# Step 1: Load asteroid list from DB
print("Step 1: Load asteroid list from DB")
t, asteroid_rows = measure_step(
    "Query SQLite for asteroids",
    get_asteroids_by_magnitude,
    max_h_magnitude=bright_asteroids.MAX_ABSOLUTE_MAGNITUDE,
    limit=5000
)
timings['1_load_from_db'] = t
print(f"  -> {len(asteroid_rows)} asteroids loaded\n")

# Step 2: Setup observer
print("Step 2: Setup Skyfield observer")
t_start = time.time()
topos = wgs84.latlon(TEST_LAT, TEST_LON, elevation_m=TEST_ELEVATION)
observer = eph['earth'] + topos
t_skyfield = ts.from_datetime(TEST_TIME)
timings['2_setup_observer'] = time.time() - t_start
print(f"  Setup observer: {timings['2_setup_observer']:.3f}s\n")

# Step 3: Compute positions (sample 100 asteroids)
print("Step 3: Compute positions for asteroids")
sample_size = 100
positions_computed = 0
t_start = time.time()

for row in asteroid_rows[:sample_size]:
    try:
        orbit_data = get_asteroid_orbit_data(row['id'])
        if orbit_data is not None:
            asteroid_obj = eph['sun'] + orbit_data
            astrometric = observer.at(t_skyfield).observe(asteroid_obj)
            alt, az, distance = astrometric.apparent().altaz()
            positions_computed += 1
    except Exception as e:
        # Skip this asteroid if there's an error
        pass

time_sample = time.time() - t_start
time_per_position = time_sample / positions_computed if positions_computed > 0 else 0
estimated_total_positions = time_per_position * len(asteroid_rows)
timings['3_compute_positions'] = estimated_total_positions

print(f"  Sample: {sample_size} asteroids in {time_sample:.2f}s")
print(f"  Time per asteroid: {time_per_position:.3f}s")
print(f"  ESTIMATED for {len(asteroid_rows)} asteroids: {estimated_total_positions:.2f}s\n")

# Step 4: Rise/Set/Transit (sample 20 asteroids)
print("Step 4: Compute rise/set/transit times")
sample_size_rst = 20
rst_computed = 0
t_start = time.time()

t0 = ts.from_datetime(TEST_TIME.replace(hour=0, minute=0, second=0))
t1 = ts.from_datetime(TEST_TIME.replace(hour=23, minute=59, second=59))

for row in asteroid_rows[:sample_size_rst]:
    try:
        orbit_data = get_asteroid_orbit_data(row['id'])
        if orbit_data is not None:
            asteroid_obj = eph['sun'] + orbit_data
            f = almanac.risings_and_settings(eph, asteroid_obj, topos)
            times, events = almanac.find_discrete(t0, t1, f)
            
            # Compute transit
            f_transit = almanac.meridian_transits(eph, asteroid_obj, topos)
            transit_times, transit_events = almanac.find_discrete(t0, t1, f_transit)
            rst_computed += 1
    except Exception as e:
        # Skip this asteroid if there's an error
        pass

time_sample_rst = time.time() - t_start
time_per_rst = time_sample_rst / rst_computed if rst_computed > 0 else 0
estimated_total_rst = time_per_rst * len(asteroid_rows)
timings['4_rise_set_transit'] = estimated_total_rst

print(f"  Sample: {sample_size_rst} asteroids in {time_sample_rst:.2f}s")
print(f"  Time per asteroid: {time_per_rst:.3f}s")
print(f"  ESTIMATED for {len(asteroid_rows)} asteroids: {estimated_total_rst:.2f}s\n")

# Step 5: Timezone lookup
print("Step 5: Timezone lookup (for formatting)")
t_start = time.time()
from timezone_utils import get_tzinfo
tz = get_tzinfo(TEST_LAT, TEST_LON)
timings['5_timezone_lookup'] = time.time() - t_start
print(f"  Timezone lookup: {timings['5_timezone_lookup']:.3f}s")
print(f"  -> Timezone: {tz}\n")

# Step 6: Store to DB (estimated)
timings['6_store_db'] = 0.5
print(f"Step 6: Store to DB (estimated): {timings['6_store_db']:.3f}s\n")

# Summary
print("=" * 80)
print("SUMMARY - WHERE THE TIME GOES")
print("=" * 80)

total_estimated = sum(timings.values())
sorted_timings = sorted(timings.items(), key=lambda x: x[1], reverse=True)

for step, duration in sorted_timings:
    percentage = (duration / total_estimated * 100) if total_estimated > 0 else 0
    print(f"{step:30s}: {duration:7.2f}s  ({percentage:5.1f}%)")

print("-" * 80)
print(f"{'TOTAL ESTIMATED':30s}: {total_estimated:7.2f}s  ({total_estimated/60:5.2f} min)")
print("=" * 80)

print("\nBOTTLENECKS (highest time consumers):")
for i, (step, duration) in enumerate(sorted_timings[:3], 1):
    print(f"{i}. {step}: {duration:.2f}s")
