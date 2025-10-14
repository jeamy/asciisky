#!/usr/bin/env python3
"""
Test comet detection for today (14.10.2025)
Compare with KStars which shows 7 visible comets
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from datetime import datetime, timezone
from api.computation import ts, eph
import comets

# Test parameters - heute, 20:00 Uhr
TEST_LAT = 46.7632
TEST_LON = 14.8417
TEST_ELEVATION = 405
TEST_TIME = datetime(2025, 10, 14, 20, 0, 0, tzinfo=timezone.utc)

def test_comets_today():
    """Test comet detection for today"""
    location = {"latitude": TEST_LAT, "longitude": TEST_LON, "elevation": TEST_ELEVATION}
    
    print("=" * 80)
    print("KOMETEN-TEST: 14. OKTOBER 2025")
    print("=" * 80)
    print(f"Datum:    14. Oktober 2025, 20:00 UTC (22:00 MESZ)")
    print(f"Location: {TEST_LAT}°N, {TEST_LON}°E, {TEST_ELEVATION}m")
    print("=" * 80)
    print()
    
    print("ERWARTUNG (KStars):")
    print("  7 Kometen über die Nacht verteilt sichtbar")
    print()
    
    print("BERECHNUNG:")
    print("-" * 80)
    
    t_start = time.time()
    comet_list = comets.load_comets(
        ts, eph, location,
        use_cache=False,  # Force fresh computation
        current_dt=TEST_TIME
    )
    t_total = time.time() - t_start
    
    comet_count = len(comet_list) if comet_list else 0
    
    print(f"Zeit:    {t_total:.2f}s")
    print(f"Gefunden: {comet_count} Kometen")
    print()
    
    if comet_list:
        print("GEFUNDENE KOMETEN:")
        print("=" * 80)
        print(f"{'Name':<35} | {'Mag':>5} | {'Höhe':>7} | {'Azimut':>7} | {'Aufgang':>8} | {'Untergang':>8}")
        print("-" * 80)
        
        # Sort by magnitude (brightest first)
        sorted_comets = sorted(comet_list, key=lambda c: c.get('magnitude', 99))
        
        for c in sorted_comets:
            name = c.get('name', 'Unknown')[:35]
            mag = c.get('magnitude')
            alt = c.get('altitude', 0)
            az = c.get('azimuth', 0)
            rise = c.get('rise_time', '-')
            set_time = c.get('set_time', '-')
            
            # Mark visibility
            alt_val = alt if alt is not None else -90
            if alt_val > 20:
                vis = "⭐ Gut"
            elif alt_val > 0:
                vis = "👁️ Tief"
            else:
                vis = "   Unter"
            
            # Handle None values
            mag_str = f"{mag:5.1f}" if mag is not None else "  N/A"
            alt_str = f"{alt_val:7.1f}°" if alt is not None else "    N/A"
            az_str = f"{az:7.1f}°" if az is not None else "    N/A"
            rise_str = str(rise) if rise and rise != '-' else "       -"
            set_str = str(set_time) if set_time and set_time != '-' else "       -"
            print(f"{name:<35} | {mag_str:>5} | {alt_str:>8} | {az_str:>8} | {rise_str:>8} | {set_str:>8} {vis}")
    else:
        print("KEINE KOMETEN GEFUNDEN")
    
    print()
    print("=" * 80)
    print("VERGLEICH")
    print("=" * 80)
    
    expected_count = 7
    visible_now = sum(1 for c in comet_list if c.get('altitude', -90) > 0) if comet_list else 0
    
    print(f"Erwartet (KStars):      {expected_count} Kometen")
    print(f"Gefunden (ASCII Sky):   {comet_count} Kometen")
    print(f"Aktuell über Horizont:  {visible_now} Kometen")
    
    if comet_count >= expected_count:
        print(f"\n✓ KORREKT: {comet_count} Kometen gefunden (>= {expected_count})")
    elif comet_count >= expected_count - 1:
        print(f"\n~ FAST KORREKT: {comet_count} Kometen gefunden (erwartet: {expected_count})")
    else:
        print(f"\n✗ ZU WENIGE: Nur {comet_count} von {expected_count} gefunden!")
        print(f"   {expected_count - comet_count} Kometen fehlen")
    
    print()
    print("HINWEIS:")
    print("  KStars zeigt Kometen 'über die Nacht verteilt'")
    print("  Nicht alle sind zur gleichen Zeit sichtbar")
    print("  Manche gehen auf, während andere untergehen")
    
    print("=" * 80)
    
    return comet_count, t_total

if __name__ == "__main__":
    count, time_taken = test_comets_today()
    print(f"\nFazit: {count} Kometen in {time_taken:.1f}s")
