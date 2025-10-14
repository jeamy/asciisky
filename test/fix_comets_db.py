#!/usr/bin/env python3
"""
Fix comets database: Clear and reload with correct column mapping
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_utils import get_db_connection, get_database_stats
import comets

print("=" * 80)
print("KOMETEN-DB REPARIEREN")
print("=" * 80)
print()

# Check current state
stats = get_database_stats()
print(f"Aktuell in DB: {stats['comets_count']} Kometen")
print()

# Clear comets table
print("Lösche alte Kometen aus DB...")
from db_utils import db_transaction
with db_transaction() as conn:
    conn.execute("DELETE FROM comets")
print("✓ Kometen gelöscht")
print()

# Load fresh dataframe
print("Lade Kometen-DataFrame...")
df = comets.load_comet_dataframe(use_cache=False)
print(f"✓ {len(df)} Kometen geladen")
print()

# Store in DB with correct column names
print("Speichere Kometen in DB (mit korrekten Spaltennamen)...")
from db_utils import store_comet_dataframe
stored_count = store_comet_dataframe(df)
print(f"✓ {stored_count} Kometen gespeichert")
print()

# Check final state
stats_after = get_database_stats()
print(f"Nach der Reparatur: {stats_after['comets_count']} Kometen in DB")
print()

if stats_after['comets_count'] > 100:
    print(f"✓ ERFOLG! DB enthält jetzt {stats_after['comets_count']} Kometen")
else:
    print(f"⚠️  Problem: Nur {stats_after['comets_count']} Kometen in DB")

print("=" * 80)
