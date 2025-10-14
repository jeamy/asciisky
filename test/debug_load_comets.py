#!/usr/bin/env python3
"""
Debug: Warum werden keine Kometen von load_comets() gefunden?
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from api.computation import ts, eph
import comets
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG, format='%(message)s')

TEST_LAT = 46.7632
TEST_LON = 14.8417
TEST_ELEVATION = 405
TEST_TIME = datetime(2025, 10, 14, 20, 0, 0, tzinfo=timezone.utc)

location = {"latitude": TEST_LAT, "longitude": TEST_LON, "elevation": TEST_ELEVATION}

print("=" * 80)
print("DEBUG: load_comets() Step-by-Step")
print("=" * 80)
print()

result = comets.load_comets(
    ts, eph, location,
    use_cache=False,
    current_dt=TEST_TIME
)

print()
print("=" * 80)
print(f"RESULT: {len(result) if result else 0} comets found")
print("=" * 80)

if result:
    for i, c in enumerate(result[:5], 1):
        print(f"{i}. {c.get('name', 'N/A')}: V={c.get('magnitude', '?')}")
else:
    print("NO COMETS FOUND")
    print()
    print("Possible reasons:")
    print("1. Prefilter too aggressive (M1 threshold)")
    print("2. Apparent magnitude filter too strict")
    print("3. Orbit calculation failing")
    print("4. Time/position calculation error")
