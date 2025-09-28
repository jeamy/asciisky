"""Utilities for resolving data file locations used by ASCII Sky."""
from __future__ import annotations

import os
from pathlib import Path

# Determine project root (directory containing this file)
_PROJECT_ROOT = Path(__file__).resolve().parent

# Default data directory lives under project root unless overridden
_DEFAULT_DATA_DIR = _PROJECT_ROOT / "data"
DATA_DIR = Path(os.environ.get("ASCII_SKY_DATA_DIR", _DEFAULT_DATA_DIR)).resolve()

# Subdirectory holding long-lived MPC data downloads
DATA_CACHE_DIR = DATA_DIR / "cache"

# Commonly accessed data files
DE421_PATH = DATA_DIR / "de421.bsp"
HIPPARCOS_MAIN_PATH = DATA_DIR / "hip_main.dat"
CONSTELLATIONSHIP_PATH = DATA_DIR / "constellationship.fab"
COMET_ELEMENTS_PATH = DATA_CACHE_DIR / "COMET_ELEMENTS.txt"
MPCORB_PATH = DATA_CACHE_DIR / "MPCORB.DAT.gz"


def ensure_data_dirs() -> None:
    """Create data directories if they do not already exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)


# Make sure the directories exist at import time
ensure_data_dirs()
