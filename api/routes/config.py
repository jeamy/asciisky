"""
Configuration endpoint to expose magnitude limits to frontend
"""
from fastapi import APIRouter

import bright_asteroids
import comets

router = APIRouter()

@router.get("/config")
async def get_config():
    """
    Returns configuration values including magnitude limits
    """
    return {
        "magnitude_limits": {
            "asteroids": {
                "max_apparent": bright_asteroids.MAX_APPARENT_MAGNITUDE,
                "max_absolute": bright_asteroids.MAX_ABSOLUTE_MAGNITUDE
            },
            "comets": {
                "max_apparent": comets.MAX_APPARENT_MAGNITUDE,
                "max_absolute": comets.MAX_ABSOLUTE_MAGNITUDE
            }
        },
        "CONSTELLATIONS": {
            "ENABLE_CONSTELLATION_LAYER": True,
            "DEFAULT_VISIBLE": False,
            "STROKE_WIDTH": 1.5,
            "STROKE_COLOR": "#4a90e2",
            "STROKE_OPACITY": 0.7,
            "LABEL_COLOR": "#4a90e2",
            "LABEL_OPACITY": 0.8,
            "LABEL_FONT_SIZE": "12px"
        }
    }
