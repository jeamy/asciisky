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
        }
    }
