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
        
        # Clear pickle cache directories
        cache_dirs = ['cache/asteroids', 'cache/comets']
        for cache_dir in cache_dirs:
            if os.path.exists(cache_dir):
                print(f"Invalidating cache directory: {cache_dir}")
                shutil.rmtree(cache_dir)
                os.makedirs(cache_dir, exist_ok=True)
                print(f"Cache directory cleared: {cache_dir}")
        
        # Clear SQLite cache tables (positions AND dataframes)
        try:
            from db_utils import get_db_connection
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Delete all asteroid positions
            cursor.execute("DELETE FROM asteroid_positions")
            deleted_asteroid_positions = cursor.rowcount
            
            # Delete all comet positions
            cursor.execute("DELETE FROM comet_positions")
            deleted_comet_positions = cursor.rowcount
            
            # Delete asteroid dataframes (force reload with new magnitude limit)
            cursor.execute("DELETE FROM asteroids")
            deleted_asteroid_df = cursor.rowcount
            
            # Delete comet dataframes (force reload with new magnitude limit)
            cursor.execute("DELETE FROM comets")
            deleted_comet_df = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            print(f"Cleared SQLite cache:")
            print(f"  - Asteroid positions: {deleted_asteroid_positions}")
            print(f"  - Comet positions: {deleted_comet_positions}")
            print(f"  - Asteroid dataframes: {deleted_asteroid_df}")
            print(f"  - Comet dataframes: {deleted_comet_df}")
        except Exception as e:
            print(f"Error clearing SQLite cache: {e}")
            
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
        # Get old filters to check if they changed
        old_filters = settings.get_magnitude_filters()
        
        # Update filters
        updated_filters = settings.set_magnitude_filters(
            asteroid_max=filters.asteroidMaxMagnitude,
            comet_max=filters.cometMaxMagnitude
        )
        
        # Check if filters actually changed
        filters_changed = (
            (filters.asteroidMaxMagnitude is not None and 
             old_filters.get("asteroidMaxMagnitude") != filters.asteroidMaxMagnitude) or
            (filters.cometMaxMagnitude is not None and 
             old_filters.get("cometMaxMagnitude") != filters.cometMaxMagnitude)
        )
        
        # Invalidate cache if filters changed
        if filters_changed:
            print(f"Filters changed from {old_filters} to {updated_filters}, invalidating cache...")
            invalidate_cache()
        
        return {
            "success": True,
            "filters": updated_filters,
            "cache_invalidated": filters_changed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
