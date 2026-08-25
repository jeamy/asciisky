#!/usr/bin/env python3
"""
Performance test for magnitude filter recalculation
Measures how long it takes to recalculate cache after filter change
"""

import time

import requests

BASE_URL = "http://localhost:8000"

def set_filters(asteroid_mag, comet_mag):
    """Set new filter values"""
    payload = {
        "asteroidMaxMagnitude": asteroid_mag,
        "cometMaxMagnitude": comet_mag
    }
    response = requests.post(f"{BASE_URL}/api/filters", json=payload)
    if response.status_code == 200:
        return response.json()
    return None

def get_asteroids(lat=46.7632, lon=14.8417, elevation=410):
    """Get asteroid list"""
    response = requests.get(
        f"{BASE_URL}/api/asteroids",
        params={"lat": lat, "lon": lon, "elevation": elevation}
    )
    if response.status_code == 200:
        data = response.json()
        if isinstance(data, dict) and 'bodies' in data:
            return list(data['bodies'].values())
        return data
    return None

def get_comets(lat=46.7632, lon=14.8417, elevation=410):
    """Get comet list"""
    response = requests.get(
        f"{BASE_URL}/api/comets",
        params={"lat": lat, "lon": lon, "elevation": elevation}
    )
    if response.status_code == 200:
        data = response.json()
        if isinstance(data, dict) and 'bodies' in data:
            return list(data['bodies'].values())
        return data
    return None

def main():
    print("="*60)
    print("  PERFORMANCE TEST: Cache Recalculation Time")
    print("="*60)
    
    # Test parameters
    asteroid_mag = 11.0
    comet_mag = 15.0
    lat = 46.7632
    lon = 14.8417
    elevation = 410
    
    print("\nTest parameters:")
    print(f"  Asteroid magnitude: {asteroid_mag}")
    print(f"  Comet magnitude: {comet_mag}")
    print(f"  Location: {lat}, {lon}, {elevation}m")
    
    # Step 1: Set filters and invalidate cache
    print("\n" + "="*60)
    print("  Step 1: Setting filters and invalidating cache")
    print("="*60)
    
    start_time = time.time()
    result = set_filters(asteroid_mag, comet_mag)
    
    if result:
        print(f"  Success: {result.get('success')}")
        print(f"  Cache invalidated: {result.get('cache_invalidated')}")
        print(f"  Filters: {result.get('filters')}")
    else:
        print("  ERROR: Could not set filters")
        return False
    
    filter_time = time.time() - start_time
    print(f"  Time to set filters: {filter_time:.2f}s")
    
    # Step 2: Request asteroids (triggers recalculation)
    print("\n" + "="*60)
    print("  Step 2: Requesting asteroids (triggers recalculation)")
    print("="*60)
    
    asteroid_start = time.time()
    asteroids = get_asteroids(lat, lon, elevation)
    asteroid_time = time.time() - asteroid_start
    
    if asteroids:
        print(f"  Asteroids received: {len(asteroids)}")
        mags = [a.get('magnitude', 0) for a in asteroids if 'magnitude' in a]
        if mags:
            print(f"  Magnitude range: {min(mags):.1f} to {max(mags):.1f}")
    else:
        print("  No asteroids received")
    
    print(f"  Time to get asteroids: {asteroid_time:.2f}s")
    
    # Step 3: Request comets (may use cached data or trigger recalculation)
    print("\n" + "="*60)
    print("  Step 3: Requesting comets")
    print("="*60)
    
    comet_start = time.time()
    comets = get_comets(lat, lon, elevation)
    comet_time = time.time() - comet_start
    
    if comets:
        print(f"  Comets received: {len(comets)}")
        mags = [c.get('magnitude', 0) for c in comets if 'magnitude' in c]
        if mags:
            print(f"  Magnitude range: {min(mags):.1f} to {max(mags):.1f}")
    else:
        print("  No comets received")
    
    print(f"  Time to get comets: {comet_time:.2f}s")
    
    # Summary
    print("\n" + "="*60)
    print("  SUMMARY")
    print("="*60)
    
    total_time = time.time() - start_time
    
    print(f"\n  Filter setting:        {filter_time:.2f}s")
    print(f"  Asteroid calculation:  {asteroid_time:.2f}s")
    print(f"  Comet calculation:     {comet_time:.2f}s")
    print("  " + "-"*40)
    print(f"  Total time:            {total_time:.2f}s")
    print(f"  Total time (minutes):  {total_time/60:.2f}min")
    
    # Performance assessment
    print("\n  Performance assessment:")
    if total_time < 10:
        print("  ✓ EXCELLENT: Very fast recalculation")
    elif total_time < 30:
        print("  ✓ GOOD: Acceptable recalculation time")
    elif total_time < 60:
        print("  ⚠ MODERATE: Recalculation takes some time")
    elif total_time < 180:
        print("  ⚠ SLOW: Recalculation takes several minutes")
    else:
        print("  ✗ VERY SLOW: Recalculation takes too long")
    
    print()
    return True

if __name__ == "__main__":
    try:
        raise SystemExit(0 if main() else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
        raise SystemExit(1)
