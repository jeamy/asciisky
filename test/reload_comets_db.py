#!/usr/bin/env python3
"""
Reload comets into database with correct column names
"""
import comets
from db_utils import get_database_stats

print("=" * 80)
print("KOMETEN NEU LADEN")
print("=" * 80)
print()

# Check current state
stats = get_database_stats()
print(f"Vor dem Reload: {stats['comets_count']} Kometen in DB")
print()

# Force reload of comet dataframe
print("Lade Kometen-DataFrame...")
df = comets.load_comet_dataframe(use_cache=False)
print(f"DataFrame geladen: {len(df)} Kometen")
print()

# The load_comets function will store the dataframe when it's called
# We need to trigger it once to fill the DB
print("Triggere DB-Speicherung...")
from api.computation import ts, eph
from datetime import datetime, timezone

# Dummy call to trigger storage
try:
    test_location = {"latitude": 46.76, "longitude": 14.84, "elevation": 405}
    test_time = datetime.now(timezone.utc)
    
    # This will store the dataframe in DB
    result = comets.load_comets(ts, eph, test_location, use_cache=False, current_dt=test_time)
    print(f"✓ Berechnung abgeschlossen, {len(result)} Kometen gefunden")
except Exception as e:
    print(f"⚠️  Fehler bei Berechnung: {e}")

print()

# Check final state
stats_after = get_database_stats()
print(f"Nach dem Reload: {stats_after['comets_count']} Kometen in DB")
print()

if stats_after['comets_count'] > stats['comets_count']:
    diff = stats_after['comets_count'] - stats['comets_count']
    print(f"✓ Erfolg! {diff} neue Kometen gespeichert")
else:
    print(f"⚠️  Keine neuen Kometen gespeichert")

print("=" * 80)
