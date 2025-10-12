#!/usr/bin/env python3
"""
Functional test: New Year's Eve 2025 (31.12.2025)
Test complete workflow for a realistic date
"""
import time
from datetime import datetime, timezone
from api.computation import LOADER, ts, eph
import bright_asteroids
import comets

# Test parameters - Silvester 2025, 20:00 Uhr (evening)
TEST_LAT = 46.7632
TEST_LON = 14.8417
TEST_ELEVATION = 405
TEST_TIME = datetime(2025, 12, 31, 20, 0, 0, tzinfo=timezone.utc)

def test_silvester():
    """Complete functional test for New Year's Eve 2025"""
    location = {"latitude": TEST_LAT, "longitude": TEST_LON, "elevation": TEST_ELEVATION}
    
    print("=" * 80)
    print("FUNKTIONSTEST: SILVESTER 2025")
    print("=" * 80)
    print(f"Datum:    31. Dezember 2025, 20:00 UTC (21:00 MEZ)")
    print(f"Location: {TEST_LAT}°N, {TEST_LON}°E, {TEST_ELEVATION}m")
    print(f"          (Kärnten, Österreich)")
    print("=" * 80)
    print()
    
    # Test 1: Asteroiden
    print("SCHRITT 1: ASTEROIDEN BERECHNEN")
    print("-" * 80)
    
    t_start = time.time()
    asteroid_list = bright_asteroids.load_bright_asteroids(
        LOADER, ts, eph, location,
        max_magnitude=bright_asteroids.MAX_APPARENT_MAGNITUDE,
        use_cache=False,  # Force fresh computation
        current_dt=TEST_TIME
    )
    t_asteroids = time.time() - t_start
    
    asteroid_count = len(asteroid_list) if asteroid_list else 0
    print(f"Berechnungszeit: {t_asteroids:.2f}s")
    print(f"Gefundene Asteroiden: {asteroid_count}")
    
    if asteroid_list:
        print()
        print("Helle Asteroiden am Himmel:")
        print(f"{'Name':<20} | {'Mag':>5} | {'Höhe':>6} | {'Azimut':>7} | {'Aufgang':>8} | {'Untergang':>8}")
        print("-" * 80)
        for ast in asteroid_list[:10]:  # Show top 10
            name = ast.get('name', 'Unknown')
            mag = ast.get('magnitude', 0)
            alt = ast.get('altitude', 0)
            az = ast.get('azimuth', 0)
            rise = ast.get('rise_time', '-')
            set_time = ast.get('set_time', '-')
            
            # Mark visible objects (above horizon)
            visibility = "👁️" if alt > 0 else "  "
            print(f"{name:<20} | {mag:>5.1f} | {alt:>6.1f}° | {az:>7.1f}° | {rise:>8} | {set_time:>8} {visibility}")
    
    print()
    
    # Test 2: Kometen
    print("SCHRITT 2: KOMETEN BERECHNEN")
    print("-" * 80)
    
    t_start = time.time()
    comet_list = comets.load_comets(
        ts, eph, location,
        use_cache=False,  # Force fresh computation
        current_dt=TEST_TIME
    )
    t_comets = time.time() - t_start
    
    comet_count = len(comet_list) if comet_list else 0
    print(f"Berechnungszeit: {t_comets:.2f}s")
    print(f"Gefundene Kometen: {comet_count}")
    
    if comet_list:
        print()
        print("Helle Kometen am Himmel:")
        print(f"{'Name':<30} | {'Mag':>5} | {'Höhe':>6} | {'Azimut':>7} | {'Aufgang':>8} | {'Untergang':>8}")
        print("-" * 80)
        for c in comet_list[:10]:  # Show top 10
            name = c.get('name', 'Unknown')
            mag = c.get('magnitude', 0)
            alt = c.get('altitude', 0)
            az = c.get('azimuth', 0)
            rise = c.get('rise_time', '-')
            set_time = c.get('set_time', '-')
            
            visibility = "👁️" if alt > 0 else "  "
            print(f"{name:<30} | {mag:>5.1f} | {alt:>6.1f}° | {az:>7.1f}° | {rise:>8} | {set_time:>8} {visibility}")
    else:
        print("(Keine hellen Kometen sichtbar)")
    
    print()
    
    # Summary
    print("=" * 80)
    print("ZUSAMMENFASSUNG")
    print("=" * 80)
    
    total_time = t_asteroids + t_comets
    visible_asteroids = sum(1 for a in asteroid_list if a.get('altitude', -90) > 0) if asteroid_list else 0
    visible_comets = sum(1 for c in comet_list if c.get('altitude', -90) > 0) if comet_list else 0
    
    print(f"Gesamte Berechnungszeit:  {total_time:.2f}s ({total_time/60:.2f} min)")
    print(f"Asteroiden gefunden:       {asteroid_count} (davon {visible_asteroids} über Horizont)")
    print(f"Kometen gefunden:          {comet_count} (davon {visible_comets} über Horizont)")
    print(f"Gesamt sichtbare Objekte:  {visible_asteroids + visible_comets}")
    print()
    
    # Performance assessment
    print("PERFORMANCE-BEWERTUNG:")
    print("-" * 80)
    if total_time < 30:
        print(f"✓ Exzellent! Berechnung in {total_time:.1f}s")
    elif total_time < 60:
        print(f"✓ Gut. Berechnung in {total_time:.1f}s")
    elif total_time < 120:
        print(f"~ Akzeptabel. Berechnung in {total_time:.1f}s")
    else:
        print(f"✗ Langsam. Berechnung dauert {total_time:.1f}s")
    
    print()
    print("EXTRAPOLATION für ±12h Berechnung:")
    print(f"  24 Stunden × {total_time:.1f}s = {(total_time * 24)/60:.1f} Minuten")
    print()
    
    # Validation
    print("VALIDIERUNG:")
    print("-" * 80)
    
    checks_passed = 0
    checks_total = 4
    
    # Check 1: Computation completed
    if asteroid_list is not None and comet_list is not None:
        print("✓ Berechnung erfolgreich abgeschlossen")
        checks_passed += 1
    else:
        print("✗ Fehler bei der Berechnung")
    
    # Check 2: Some objects found
    if asteroid_count > 0:
        print(f"✓ Asteroiden gefunden ({asteroid_count})")
        checks_passed += 1
    else:
        print("? Keine Asteroiden gefunden (ungewöhnlich)")
    
    # Check 3: Reasonable computation time
    if total_time < 60:
        print(f"✓ Performance akzeptabel (<1 min)")
        checks_passed += 1
    else:
        print(f"✗ Performance problematisch (>{total_time:.0f}s)")
    
    # Check 4: Data structure valid
    if asteroid_list and all('name' in a and 'magnitude' in a for a in asteroid_list[:5]):
        print("✓ Datenstruktur korrekt")
        checks_passed += 1
    else:
        print("✗ Datenstruktur fehlerhaft")
    
    print()
    print(f"Tests bestanden: {checks_passed}/{checks_total}")
    print("=" * 80)
    
    return {
        'success': checks_passed == checks_total,
        'asteroid_count': asteroid_count,
        'comet_count': comet_count,
        'total_time': total_time,
        'visible_objects': visible_asteroids + visible_comets
    }

if __name__ == "__main__":
    result = test_silvester()
    
    if result['success']:
        print("\n🎉 FUNKTIONSTEST ERFOLGREICH!")
    else:
        print("\n⚠️  FUNKTIONSTEST TEILWEISE FEHLGESCHLAGEN")
