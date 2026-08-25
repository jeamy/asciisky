"""
Settings-Modul für AsciiSky
Speichert Benutzereinstellungen wie Magnitude-Filter persistent
"""
import copy
import json
import logging
import os
import tempfile
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

# RabbitMQ Settings (für Migration)
RABBITMQ_URL = os.environ.get('RABBITMQ_URL', 'amqp://admin:changeme@127.0.0.1:5672/')
RABBITMQ_ENABLED = os.environ.get('USE_RABBITMQ', 'false').lower() in ('true', '1', 'yes', 'on')
RABBITMQ_TIMEOUT = int(os.environ.get('RABBITMQ_TIMEOUT', '30'))
RABBITMQ_RETRY_ATTEMPTS = int(os.environ.get('RABBITMQ_RETRY_ATTEMPTS', '3'))
FALLBACK_TO_OLD_ON_ERROR = os.environ.get('FALLBACK_TO_OLD_ON_ERROR', 'true').lower() in ('true', '1', 'yes', 'on')

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
_settings_lock = threading.RLock()


def _default_settings():
    return copy.deepcopy(DEFAULT_SETTINGS)

def load_settings():
    """Lädt die Benutzereinstellungen aus der Datei"""
    global settings

    with _settings_lock:
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                settings = loaded if isinstance(loaded, dict) else _default_settings()
                settings.setdefault("filters", get_default_magnitude_filters())
            else:
                settings = _default_settings()
                _save_settings_locked()
        except (OSError, ValueError, json.JSONDecodeError):
            logger.exception("Could not load settings; using defaults")
            settings = _default_settings()
        return copy.deepcopy(settings)


def _save_settings_locked():
    """Persist settings atomically. Caller must hold ``_settings_lock``."""
    global settings
    if settings is None:
        settings = _default_settings()
    settings["last_updated"] = datetime.now().isoformat()
    directory = os.path.dirname(os.path.abspath(SETTINGS_FILE)) or "."
    fd, temporary_path = tempfile.mkstemp(prefix=".user_settings-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary_path, SETTINGS_FILE)
    except OSError:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise

def save_settings():
    """Speichert die Benutzereinstellungen in der Datei"""
    global settings
    
    with _settings_lock:
        try:
            _save_settings_locked()
        except OSError:
            logger.exception("Could not save settings")

def get_magnitude_filters():
    """Gibt die gespeicherten Magnitude-Filter zurück"""
    global settings
    
    with _settings_lock:
        if settings is None:
            load_settings()
        return copy.deepcopy(settings.get("filters", get_default_magnitude_filters()))

def set_magnitude_filters(asteroid_max=None, comet_max=None):
    """Speichert die Magnitude-Filter"""
    global settings
    
    with _settings_lock:
        if settings is None:
            load_settings()
        if "filters" not in settings:
            settings["filters"] = get_default_magnitude_filters()
        if asteroid_max is not None:
            settings["filters"]["asteroidMaxMagnitude"] = float(asteroid_max)
        if comet_max is not None:
            settings["filters"]["cometMaxMagnitude"] = float(comet_max)
        save_settings()
        return copy.deepcopy(settings["filters"])

def get_location():
    """Gibt die gespeicherten Standortdaten zurück"""
    global settings
    
    with _settings_lock:
        if settings is None:
            load_settings()
        return copy.deepcopy(settings.get("location", DEFAULT_SETTINGS["location"]))

def set_location(latitude, longitude, elevation, name=None):
    """Speichert die Standortdaten"""
    global settings
    
    with _settings_lock:
        if settings is None:
            load_settings()
        settings["location"] = {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "elevation": float(elevation)
        }
        if name:
            settings["location"]["name"] = name
        save_settings()
        return copy.deepcopy(settings["location"])
