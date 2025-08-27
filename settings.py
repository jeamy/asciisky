"""
Settings-Modul für AsciiSky
Speichert Benutzereinstellungen wie Magnitude-Filter persistent
"""
import os
import json
from datetime import datetime

# Pfad zur Einstellungsdatei
SETTINGS_FILE = "user_settings.json"

# Default-Einstellungen
DEFAULT_SETTINGS = {
    "asteroid_max_magnitude": 8.0,
    "comet_max_magnitude": 12.0,
    "location": {
        "latitude": 48.2082,  # Wien
        "longitude": 16.3738,
        "elevation": 171.0,
        "name": "Wien"
    },
    "last_updated": datetime.now().isoformat()
}

# Globale Einstellungen
settings = None

def load_settings():
    """Lädt die Benutzereinstellungen aus der Datei"""
    global settings
    
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                print(f"Settings loaded: {settings}")
        else:
            settings = DEFAULT_SETTINGS.copy()
            save_settings()
            print(f"Default settings created: {settings}")
    except Exception as e:
        print(f"Error loading settings: {str(e)}")
        settings = DEFAULT_SETTINGS.copy()
    
    return settings

def save_settings():
    """Speichert die Benutzereinstellungen in der Datei"""
    global settings
    
    if settings is None:
        settings = DEFAULT_SETTINGS.copy()
    
    try:
        settings["last_updated"] = datetime.now().isoformat()
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
        print(f"Settings saved: {settings}")
    except Exception as e:
        print(f"Error saving settings: {str(e)}")

def get_asteroid_magnitude():
    """Gibt die maximale Magnitude für Asteroiden zurück"""
    global settings
    
    if settings is None:
        load_settings()
    
    return settings.get("asteroid_max_magnitude", DEFAULT_SETTINGS["asteroid_max_magnitude"])

def get_comet_magnitude():
    """Gibt die maximale Magnitude für Kometen zurück"""
    global settings
    
    if settings is None:
        load_settings()
    
    return settings.get("comet_max_magnitude", DEFAULT_SETTINGS["comet_max_magnitude"])

def set_asteroid_magnitude(magnitude):
    """Setzt die maximale Magnitude für Asteroiden"""
    global settings
    
    if settings is None:
        load_settings()
    
    settings["asteroid_max_magnitude"] = float(magnitude)
    save_settings()
    return settings["asteroid_max_magnitude"]

def set_comet_magnitude(magnitude):
    """Setzt die maximale Magnitude für Kometen"""
    global settings
    
    if settings is None:
        load_settings()
    
    settings["comet_max_magnitude"] = float(magnitude)
    save_settings()
    return settings["comet_max_magnitude"]

def set_magnitude_filters(asteroid_mag, comet_mag):
    """Setzt beide Magnitude-Filter gleichzeitig"""
    global settings
    
    if settings is None:
        load_settings()
    
    settings["asteroid_max_magnitude"] = float(asteroid_mag)
    settings["comet_max_magnitude"] = float(comet_mag)
    save_settings()
    return settings

def get_location():
    """Gibt die gespeicherten Standortdaten zurück"""
    global settings
    
    if settings is None:
        load_settings()
    
    return settings.get("location", DEFAULT_SETTINGS["location"])

def set_location(latitude, longitude, elevation, name=None):
    """Speichert die Standortdaten"""
    global settings
    
    if settings is None:
        load_settings()
    
    settings["location"] = {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "elevation": float(elevation)
    }
    
    # Speichere den Ortsnamen, wenn er übergeben wurde
    if name:
        settings["location"]["name"] = name
    
    save_settings()
    return settings["location"]
