#!/usr/bin/env python3
"""
Debug: Why are KStars comets not being processed?
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_utils import load_comets_dataframe_from_db
import comets

print("=" * 80)
print("DEBUG: Sind KStars-Kometen im DataFrame?")
print("=" * 80)
print()

# Load from DB
df = load_comets_dataframe_from_db(20.0)
print(f"Loaded {len(df)} comets from DB")
print()

# Check KStars comets
kstars_names = [
    'C/2025 K1 (ATLAS)',
    'C/2025 R2 (SWAN)',
    'C/2025 A6 (Lemmon)',
    'C/2024 E1 (Wierzchos)',
    '141P-E/Machholz',
    '141P-G/Machholz'
]

print("Checking KStars comets in DataFrame:")
print("-" * 80)

for name in kstars_names:
    if name in df.index:
        row = df.loc[name]
        M1 = row.get('M1', 'N/A')
        k1 = row.get('k1', 'N/A')
        print(f"✓ {name:<30}: M1={M1}, k1={k1}")
    else:
        # Try partial match
        matches = [idx for idx in df.index if name.split()[0] in idx]
        if matches:
            print(f"~ {name:<30}: Found as {matches[0]}")
        else:
            print(f"✗ {name:<30}: NOT FOUND")

print()
print("=" * 80)

# Check prefilter
MAX_ABSOLUTE_MAG = comets.MAX_ABSOLUTE_MAGNITUDE
print(f"Prefilter: M1 <= {MAX_ABSOLUTE_MAG}")
print()

df_pref = df[(df['M1'].notna()) & (df['M1'] <= MAX_ABSOLUTE_MAG)]
print(f"After prefilter: {len(df_pref)} comets")
print()

# Check if KStars comets survive prefilter
print("KStars comets after prefilter:")
print("-" * 80)
for name in kstars_names:
    if name in df_pref.index:
        print(f"✓ {name}")
    else:
        if name in df.index:
            M1 = df.loc[name].get('M1', 'N/A')
            print(f"✗ {name} (filtered out, M1={M1} > {MAX_ABSOLUTE_MAG})")
        else:
            print(f"✗ {name} (not in original DF)")

