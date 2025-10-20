#!/usr/bin/env python3
import pickle
from db_utils import get_asteroid_positions

# Lade Daten aus DB
loc_key = "lat+46.7632_lon+14.8417_el+0410"
time_bucket = "20251019T18"
print(f"Checking bucket: {time_bucket} for location: {loc_key}")

data = get_asteroid_positions(loc_key, time_bucket, max_age_seconds=31*24*3600)

if data:
    print(f"Found {len(data)} asteroids")
    if data:
        first = data[0]
        print(f"\nFirst asteroid keys: {list(first.keys())}")
        print(f"\nFirst asteroid data:")
        for key, value in first.items():
            print(f"  {key}: {value}")
else:
    print("No data found")
