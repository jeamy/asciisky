#!/usr/bin/env python3
"""
Debug: Why are no comets found?
Check magnitude calculation step by step
"""
import math
import logging
from datetime import datetime, timezone
from skyfield.api import Loader
from skyfield.data import mpc
from db_utils import get_comets_by_magnitude
from api.computation import ts, eph

# Setup
logging.basicConfig(level=logging.DEBUG)
TEST_LAT = 46.7632
TEST_LON = 14.8417
TEST_ELEVATION = 405
TEST_TIME = datetime(2025, 10, 14, 20, 0, 0, tzinfo=timezone.utc)

print("=" * 80)
print("KOMETEN-DEBUG: Warum werden keine gefunden?")
print("=" * 80)
print()

# Load comets from DB
print("SCHRITT 1: Kometen aus DB laden...")
comet_rows = get_comets_by_magnitude(max_h_magnitude=18.0, limit=50)
print(f"Gefunden: {len(comet_rows)} Kometen in DB")
print()

if len(comet_rows) == 0:
    print("✗ PROBLEM: Keine Kometen in der Datenbank!")
    exit(1)

# Setup Skyfield
print("SCHRITT 2: Skyfield Setup...")
from skyfield.toposlib import Topos
sun = eph['sun']
t = ts.from_datetime(TEST_TIME)
topos = Topos(latitude_degrees=TEST_LAT, longitude_degrees=TEST_LON, elevation_m=TEST_ELEVATION)
observer = eph['earth'] + topos
print("✓ Setup OK")
print()

# Test first 10 comets
print("SCHRITT 3: Magnitude-Berechnung testen (erste 10 Kometen)...")
print("-" * 80)
print(f"{'Name':<30} | {'M1':>6} | {'k1':>5} | {'r (AU)':>8} | {'Δ (AU)':>8} | {'V mag':>7} | {'Status'}")
print("-" * 80)

success_count = 0
fail_count = 0
bright_count = 0

for i, row in enumerate(comet_rows[:10]):
    designation = row.get('designation', 'Unknown')
    
    try:
        # Get orbital elements
        epoch_jd = float(row.get('epoch_jd'))
        e = float(row.get('eccentricity'))
        q = float(row.get('perihelion_distance'))
        tp_jd = float(row.get('perihelion_time_jd'))
        node = float(row.get('ascending_node'))
        arg_peri = float(row.get('arg_perihelion'))
        incl = float(row.get('inclination'))
        epoch_day = epoch_jd - 2451545.0
        
        # Create orbit
        from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2 as GM_SUN
        orbit = mpc.comet_orbit(eph, e, q, tp_jd - 2451545.0, node, arg_peri, incl, epoch_day)
        
        # Determine target
        try:
            center_code = int(getattr(orbit, 'center', 10))
        except Exception:
            center_code = 10
        target = (sun + orbit) if center_code != 0 else orbit
        
        # Calculate magnitude
        astrometric = observer.at(t).observe(target)
        comet_helio = target.at(t)
        r = comet_helio.distance().au
        delta = astrometric.distance().au
        
        M1 = float(row.get('M1'))
        n_raw = row.get('k1')
        n = float(n_raw) if (n_raw is not None and str(n_raw) != 'nan') else 4.0
        
        apparent_mag = (
            float(M1)
            + 5.0 * math.log10(max(delta, 1e-12))
            + 2.5 * float(n) * math.log10(max(r, 1e-12))
        )
        
        status = "✓"
        if apparent_mag <= 14.0:
            status = "✓ HELL"
            bright_count += 1
        
        print(f"{designation[:30]:<30} | {M1:>6.1f} | {n:>5.1f} | {r:>8.3f} | {delta:>8.3f} | {apparent_mag:>7.2f} | {status}")
        success_count += 1
        
    except Exception as e:
        print(f"{designation[:30]:<30} | {'?':>6} | {'?':>5} | {'?':>8} | {'?':>8} | {'?':>7} | ✗ {str(e)[:20]}")
        fail_count += 1

print("-" * 80)
print(f"Erfolgreich: {success_count}")
print(f"Fehlgeschlagen: {fail_count}")
print(f"Hell genug (<14.0 mag): {bright_count}")
print()

print("=" * 80)
print("DIAGNOSE:")
print("=" * 80)

if success_count == 0:
    print("✗ ALLE Berechnungen fehlgeschlagen")
    print("  → Problem: Orbit-Berechnung oder Datenformat")
elif bright_count == 0:
    print("✗ Keine hellen Kometen gefunden")
    print("  → Möglicherweise sind aktuell keine hellen Kometen am Himmel")
    print("  → ODER: M1/k1 Werte in DB sind falsch")
else:
    print(f"✓ {bright_count} helle Kometen gefunden!")
    print("  → Kometen-Code sollte diese finden")

print("=" * 80)
