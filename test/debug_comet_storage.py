#!/usr/bin/env python3
"""
Debug: Why are comets not being stored in DB?
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import comets
import pickle
import sqlite3
from db_utils import db_transaction
import pandas as pd

print("=" * 80)
print("DEBUG: Kometen-Speicherung")
print("=" * 80)
print()

# Load dataframe
df = comets.load_comet_dataframe(use_cache=False)
print(f"Loaded {len(df)} comets")
print()

# Check columns
print("DataFrame Columns:")
print(df.columns.tolist())
print()

# Try to store first 5 comets manually
print("Attempting to store first 5 comets:")
print("-" * 80)

def safe_float(val):
    return float(val) if not pd.isna(val) else None

def safe_str(val):
    return str(val) if not pd.isna(val) else ''

for i, (index, row) in enumerate(df.head(5).iterrows()):
    print(f"\nComet {i+1}: {row.get('designation', 'N/A')}")
    
    # Show key fields
    print(f"  M1: {row.get('M1')}")
    print(f"  k1: {row.get('k1')}")
    print(f"  q (perihelion_distance_au): {row.get('perihelion_distance_au', row.get('q'))}")
    print(f"  e (eccentricity): {row.get('eccentricity', row.get('e'))}")
    
    try:
        orbit_data = pickle.dumps(row)
        
        with db_transaction() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO comets (
                    designation, name, magnitude_h, magnitude_g,
                    epoch_packed, perihelion_distance, eccentricity,
                    argument_perihelion, longitude_node, inclination, orbit_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                safe_str(row.get('designation', '')),
                safe_str(row.get('name', '')),
                safe_float(row.get('M1')),
                safe_float(row.get('k1')),
                safe_str(row.get('epoch_packed', '')),
                safe_float(row.get('perihelion_distance_au', row.get('q'))),
                safe_float(row.get('eccentricity', row.get('e'))),
                safe_float(row.get('argument_of_perihelion_degrees', row.get('w', row.get('peri')))),
                safe_float(row.get('longitude_of_ascending_node_degrees', row.get('om', row.get('node')))),
                safe_float(row.get('inclination_degrees', row.get('i', row.get('incl')))),
                orbit_data
            ))
        print("  ✓ Stored successfully")
        
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        print(f"     Type: {type(e).__name__}")

print()
print("=" * 80)

# Check what's in DB
from db_utils import get_database_stats
stats = get_database_stats()
print(f"Comets in DB after test: {stats['comets_count']}")
