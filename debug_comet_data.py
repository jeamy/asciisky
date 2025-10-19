#!/usr/bin/env python3
import pickle
from db_utils import get_comet_positions

# Lade Daten aus DB
loc_key = "lat+46.7632_lon+14.8417_el+0410"
time_bucket = "20251020T10"

data = get_comet_positions(loc_key, time_bucket, max_age_seconds=31*24*3600)

if data:
    print(f"Found {len(data)} comets\n")
    
    # Zeige Kometen mit und ohne Rise/Set
    for comet in data:
        name = comet.get('name', 'Unknown')
        rise = comet.get('rise_time')
        set_time = comet.get('set_time')
        transit = comet.get('transit_time')
        altitude = comet.get('altitude', 0)
        
        if name in ['210P/Christensen', 'C/2025 A6 (Lemmon)', 'C/2025 R2 (SWAN)', 'C/2024 E1 (Wierzchos)', '24P/Schaumasse']:
            status = "✅" if rise or set_time else "❌"
            print(f"{status} {name}: alt={altitude:.1f}°, rise={rise}, set={set_time}, transit={transit}")
else:
    print("No data found")
