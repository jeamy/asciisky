"""
API routes for magnitude filter settings
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import settings
import os
import shutil
from pathlib import Path

router = APIRouter()

class MagnitudeFilters(BaseModel):
    asteroidMaxMagnitude: Optional[float] = None
    cometMaxMagnitude: Optional[float] = None

def invalidate_cache():
    """Invalidate asteroid and comet caches when filters change"""
    try:
        # Clear in-memory DataFrame caches first
        try:
            import comets
            import bright_asteroids
            comets.clear_in_memory_cache()
            bright_asteroids.clear_in_memory_cache()
            print("Cleared in-memory DataFrame caches")
        except Exception as e:
            print(f"Error clearing in-memory caches: {e}")
        
        # Clear PostgreSQL cache tables (positions AND dataframes)
        try:
            from db_utils import get_db_connection
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                
                # NOTE: We do NOT delete ANY PostgreSQL caches!
                # All caches contain unfiltered data:
                # - asteroid_positions/comet_positions: All computed positions (unfiltered)
                # - asteroids/comets: All objects up to Mag 20.0 (unfiltered)
                # Filtering happens in API routes based on user_settings.json.
                # All caches are reusable for any filter setting!
                
                conn.commit()
                
                print(f"Cache invalidation:")
                print(f"  - In-memory caches: Cleared")
                print(f"  - PostgreSQL caches: NOT deleted (all unfiltered, reusable)")
                print(f"  - Filtering: Happens in API routes based on user_settings.json")
            finally:
                conn.close()
        except Exception as e:
            print(f"Error clearing PostgreSQL cache: {e}")
            
    except Exception as e:
        print(f"Error invalidating cache: {e}")

@router.get("/filters")
async def get_filters():
    """Get current magnitude filter settings"""
    try:
        filters = settings.get_magnitude_filters()
        return {
            "success": True,
            "filters": filters
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/filters")
async def set_filters(filters: MagnitudeFilters):
    """Set magnitude filter settings and invalidate cache"""
    try:
        # Get old filters BEFORE updating to check if they changed
        old_filters = settings.get_magnitude_filters()
        old_asteroid = old_filters.get("asteroidMaxMagnitude")
        old_comet = old_filters.get("cometMaxMagnitude")
        
        # Update filters
        updated_filters = settings.set_magnitude_filters(
            asteroid_max=filters.asteroidMaxMagnitude,
            comet_max=filters.cometMaxMagnitude
        )
        
        # Check if filters actually changed (compare with OLD values, not current)
        filters_changed = (
            (filters.asteroidMaxMagnitude is not None and 
             old_asteroid != filters.asteroidMaxMagnitude) or
            (filters.cometMaxMagnitude is not None and 
             old_comet != filters.cometMaxMagnitude)
        )
        
        # NOTE: Cache invalidation is NOT needed anymore!
        # Reason: Workers cache with max_magnitude=20.0 (all objects)
        # Filtering happens at API level based on user_settings.json
        # Only invalidate if user DECREASES filter (to remove objects from view)
        # But even then, no recalculation needed - just filter differently
        
        if filters_changed:
            print(f"Filters changed from {old_filters} to {updated_filters}")
            print(f"No cache invalidation needed - filtering happens at API level")
        
        return {
            "success": True,
            "filters": updated_filters,
            "cache_invalidated": False  # No cache invalidation needed - filtering at API level
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
