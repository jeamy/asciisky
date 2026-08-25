#!/usr/bin/env python3
"""
Test script for magnitude filter functionality
Tests cache invalidation and filter changes
"""

import time

import requests

BASE_URL = "http://localhost:8000"

def print_section(title):
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def get_current_filters():
    """Get current filter settings"""
    response = requests.get(f"{BASE_URL}/api/filters")
    if response.status_code == 200:
        data = response.json()
        return data.get('filters', {})
    return None

def set_filters(asteroid_mag, comet_mag):
    """Set new filter values"""
    payload = {
        "asteroidMaxMagnitude": asteroid_mag,
        "cometMaxMagnitude": comet_mag
    }
    response = requests.post(f"{BASE_URL}/api/filters", json=payload)
    if response.status_code == 200:
        data = response.json()
        return data
    return None

def get_asteroids(lat=46.7632, lon=14.8417, elevation=410):
    """Get asteroid list"""
    response = requests.get(
        f"{BASE_URL}/api/asteroids",
        params={"lat": lat, "lon": lon, "elevation": elevation}
    )
    if response.status_code == 200:
        data = response.json()
        # API returns dict with 'bodies' key
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
        # API returns dict with 'bodies' key
        if isinstance(data, dict) and 'bodies' in data:
            return list(data['bodies'].values())
        return data
    return None

def analyze_objects(objects, object_type="objects"):
    """Analyze magnitude distribution"""
    if not objects:
        print(f"  No {object_type} returned")
        return False
    
    magnitudes = []
    for obj in objects:
        mag = obj.get('magnitude') or obj.get('apparent_magnitude')
        if mag is not None:
            magnitudes.append(mag)
    
    if magnitudes:
        print(f"  Total {object_type}: {len(objects)}")
        print(f"  Magnitude range: {min(magnitudes):.1f} to {max(magnitudes):.1f}")
        print(f"  Average magnitude: {sum(magnitudes)/len(magnitudes):.1f}")
        
        # Count by magnitude bins
        bins = {
            "< 10": len([m for m in magnitudes if m < 10]),
            "10-12": len([m for m in magnitudes if 10 <= m < 12]),
            "12-14": len([m for m in magnitudes if 12 <= m < 14]),
            "14-16": len([m for m in magnitudes if 14 <= m < 16]),
            "16-18": len([m for m in magnitudes if 16 <= m < 18]),
            "> 18": len([m for m in magnitudes if m >= 18])
        }
        print("  Distribution:")
        for bin_name, count in bins.items():
            if count > 0:
                print(f"    {bin_name}: {count}")
    else:
        print(f"  {len(objects)} {object_type} (no magnitude data)")

def main():
    print_section("MAGNITUDE FILTER TEST")
    
    # Step 1: Get current filters
    print_section("Step 1: Current Filter Settings")
    current = get_current_filters()
    if current:
        print(f"  Asteroid max magnitude: {current.get('asteroidMaxMagnitude')}")
        print(f"  Comet max magnitude: {current.get('cometMaxMagnitude')}")
    else:
        print("  ERROR: Could not get current filters")
        return False
    
    # Step 2: Get objects with current filters
    print_section("Step 2: Objects with Current Filters")
    print("\n  Asteroids:")
    asteroids = get_asteroids()
    analyze_objects(asteroids, "asteroids")
    
    print("\n  Comets:")
    comets = get_comets()
    analyze_objects(comets, "comets")
    
    # Step 3: First set to low values to ensure we have a baseline
    print_section("Step 3a: Setting Low Baseline Filters")
    baseline_asteroid_mag = 10.0
    baseline_comet_mag = 14.0
    print(f"  Setting asteroid filter to {baseline_asteroid_mag}")
    print(f"  Setting comet filter to {baseline_comet_mag}")
    
    result = set_filters(baseline_asteroid_mag, baseline_comet_mag)
    if result:
        print(f"  Success: {result.get('success')}")
        print(f"  Cache invalidated: {result.get('cache_invalidated')}")
    
    print("  Waiting 5 seconds...")
    time.sleep(5)
    
    # Step 3b: Change filters to MUCH higher values than baseline
    print_section("Step 3b: Changing to Higher Filters")
    new_asteroid_mag = 18.0  # Higher than baseline (16.0)
    new_comet_mag = 19.5     # Higher than baseline (18.0)
    print(f"  Setting asteroid filter to {new_asteroid_mag}")
    print(f"  Setting comet filter to {new_comet_mag}")
    
    result = set_filters(new_asteroid_mag, new_comet_mag)
    if result:
        print(f"  Success: {result.get('success')}")
        print(f"  Cache invalidated: {result.get('cache_invalidated')}")
        print(f"  New filters: {result.get('filters')}")
    else:
        print("  ERROR: Could not set filters")
        return
    
    # Step 4: Wait for recalculation
    print_section("Step 4: Waiting for Recalculation")
    print("  Waiting 30 seconds for cache to be rebuilt...")
    for i in range(30, 0, -1):
        print(f"  {i}...", end="\r")
        time.sleep(1)
    print("  Done!              ")
    
    # Step 5: Get objects with new filters
    print_section("Step 5: Objects with New Filters")
    print("\n  Asteroids:")
    asteroids_new = get_asteroids()
    analyze_objects(asteroids_new, "asteroids")
    
    print("\n  Comets:")
    comets_new = get_comets()
    analyze_objects(comets_new, "comets")
    
    # Step 6: Compare results
    print_section("Step 6: Comparison")
    
    old_asteroid_count = len(asteroids) if asteroids else 0
    new_asteroid_count = len(asteroids_new) if asteroids_new else 0
    print(f"  Asteroids: {old_asteroid_count} → {new_asteroid_count} (Δ {new_asteroid_count - old_asteroid_count:+d})")
    
    old_comet_count = len(comets) if comets else 0
    new_comet_count = len(comets_new) if comets_new else 0
    print(f"  Comets: {old_comet_count} → {new_comet_count} (Δ {new_comet_count - old_comet_count:+d})")
    
    # Step 7: Verify new objects are within new magnitude range
    print_section("Step 7: Verification")
    
    if asteroids_new:
        mags = [obj.get('magnitude') or obj.get('apparent_magnitude') 
                for obj in asteroids_new 
                if obj.get('magnitude') or obj.get('apparent_magnitude')]
        if mags:
            max_mag = max(mags)
            print(f"  Asteroid max magnitude: {max_mag:.1f}")
            if max_mag <= new_asteroid_mag:
                print(f"  ✓ All asteroids within filter limit ({new_asteroid_mag})")
            else:
                print(f"  ✗ Some asteroids exceed filter limit ({new_asteroid_mag})")
    
    if comets_new:
        mags = [obj.get('magnitude') or obj.get('apparent_magnitude') 
                for obj in comets_new 
                if obj.get('magnitude') or obj.get('apparent_magnitude')]
        if mags:
            max_mag = max(mags)
            print(f"  Comet max magnitude: {max_mag:.1f}")
            if max_mag <= new_comet_mag:
                print(f"  ✓ All comets within filter limit ({new_comet_mag})")
            else:
                print(f"  ✗ Some comets exceed filter limit ({new_comet_mag})")
    
    # Step 8: Check if we got more objects
    print_section("Step 8: Test Result")
    
    success = True
    if new_asteroid_count <= old_asteroid_count:
        print(f"  ⚠ WARNING: Asteroid count did not increase ({old_asteroid_count} → {new_asteroid_count})")
        print("    Expected more asteroids with higher magnitude limit")
        success = False
    else:
        print(f"  ✓ Asteroid count increased ({old_asteroid_count} → {new_asteroid_count})")
    
    if new_comet_count <= old_comet_count:
        print(f"  ⚠ WARNING: Comet count did not increase ({old_comet_count} → {new_comet_count})")
        print("    Expected more comets with higher magnitude limit")
        success = False
    else:
        print(f"  ✓ Comet count increased ({old_comet_count} → {new_comet_count})")
    
    if success:
        print("\n  ✓✓✓ TEST PASSED ✓✓✓")
    else:
        print("\n  ✗✗✗ TEST FAILED ✗✗✗")
        print("\n  Possible issues:")
        print("    - Cache not invalidated properly")
        print("    - Worker not using max_magnitude=20.0")
        print("    - Old cache still being used")
        print("    - Need to wait longer for recalculation")
    
    print()
    return success

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
