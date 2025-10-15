"""
Settings-Modul für AsciiSky
Speichert Benutzereinstellungen wie Magnitude-Filter persistent
"""
import os
import json
from datetime import datetime

# Pfad zur Einstellungsdatei
SETTINGS_FILE = "user_settings.json"

# Default-Einstellungen aus ENV-Variablen
def get_default_magnitude_filters():
    """Liest die Default-Magnitude-Werte aus den ENV-Variablen"""
    return {
        "asteroidMaxMagnitude": float(os.getenv("ASCII_SKY_ASTEROID_MAX_APPARENT_MAG", "10.0")),
        "cometMaxMagnitude": float(os.getenv("ASCII_SKY_COMET_MAX_APPARENT_MAG", "14.0"))
    }

# Default-Einstellungen
DEFAULT_SETTINGS = {
    "location": {
        "latitude": 48.2082,  # Wien
        "longitude": 16.3738,
        "elevation": 171.0,
        "name": "Wien"
    },
    "filters": get_default_magnitude_filters(),
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
                # Stelle sicher, dass filters existiert
                if "filters" not in settings:
                    settings["filters"] = get_default_magnitude_filters()
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

def get_magnitude_filters():
    """Gibt die gespeicherten Magnitude-Filter zurück"""
    global settings
    
    if settings is None:
        load_settings()
    
    # Fallback auf Default-Werte aus ENV
    default_filters = get_default_magnitude_filters()
    return settings.get("filters", default_filters)

def set_magnitude_filters(asteroid_max=None, comet_max=None):
    """Speichert die Magnitude-Filter"""
    global settings
    
    if settings is None:
        load_settings()
    
    if "filters" not in settings:
        settings["filters"] = get_default_magnitude_filters()
    
    if asteroid_max is not None:
        settings["filters"]["asteroidMaxMagnitude"] = float(asteroid_max)
    
    if comet_max is not None:
        settings["filters"]["cometMaxMagnitude"] = float(comet_max)
    
    save_settings()
    return settings["filters"]

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
