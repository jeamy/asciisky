"""
API routes for magnitude filter settings
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import settings
import os
import shutil
from pathlib import Path
from datetime import datetime
import json

router = APIRouter()

class MagnitudeFilters(BaseModel):
    asteroidMaxMagnitude: Optional[float] = None
    cometMaxMagnitude: Optional[float] = None

def get_user_filters_from_db(user_id: int) -> Optional[dict]:
    """Load magnitude filters from database for a specific user"""
    try:
        from db_utils import get_db_connection
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT settings FROM user_settings WHERE user_id = %s",
                (user_id,)
            )
            row = cursor.fetchone()
            if row and row['settings']:
                user_settings = row['settings']
                return user_settings.get('filters')
            return None
        finally:
            conn.close()
    except Exception as e:
        print(f"Error loading user filters from DB: {e}")
        return None

def save_user_filters_to_db(user_id: int, filters: dict) -> bool:
    """Save magnitude filters to database for a specific user"""
    try:
        from db_utils import get_db_connection
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Get existing settings or create new
            cursor.execute(
                "SELECT settings FROM user_settings WHERE user_id = %s",
                (user_id,)
            )
            row = cursor.fetchone()
            
            if row:
                # Update existing
                user_settings = row['settings']
                user_settings['filters'] = filters
                user_settings['last_updated'] = datetime.utcnow().isoformat()
                
                cursor.execute(
                    "UPDATE user_settings SET settings = %s, last_updated = %s WHERE user_id = %s",
                    (json.dumps(user_settings), datetime.utcnow(), user_id)
                )
            else:
                # Insert new
                user_settings = {
                    'filters': filters,
                    'last_updated': datetime.utcnow().isoformat()
                }
                cursor.execute(
                    "INSERT INTO user_settings (user_id, settings, last_updated) VALUES (%s, %s, %s)",
                    (user_id, json.dumps(user_settings), datetime.utcnow())
                )
            
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        print(f"Error saving user filters to DB: {e}")
        return False

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
async def get_filters(request: Request):
    """Get current magnitude filter settings"""
    try:
        # Check if user is logged in
        user_id = request.session.get('user_id')
        
        if user_id:
            # Load from database
            filters = get_user_filters_from_db(user_id)
            if filters:
                return {
                    "success": True,
                    "filters": filters,
                    "source": "database"
                }
        
        # Fallback to file-based settings
        filters = settings.get_magnitude_filters()
        return {
            "success": True,
            "filters": filters,
            "source": "file"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/filters")
async def set_filters(filters: MagnitudeFilters, request: Request):
    """Set magnitude filter settings and invalidate cache"""
    try:
        # Check if user is logged in
        user_id = request.session.get('user_id')
        
        if user_id:
            # Get old filters from database
            old_filters = get_user_filters_from_db(user_id) or settings.get_default_magnitude_filters()
        else:
            # Get old filters from file
            old_filters = settings.get_magnitude_filters()
        
        old_asteroid = old_filters.get("asteroidMaxMagnitude")
        old_comet = old_filters.get("cometMaxMagnitude")
        
        # Build updated filters
        updated_filters = old_filters.copy()
        if filters.asteroidMaxMagnitude is not None:
            updated_filters["asteroidMaxMagnitude"] = float(filters.asteroidMaxMagnitude)
        if filters.cometMaxMagnitude is not None:
            updated_filters["cometMaxMagnitude"] = float(filters.cometMaxMagnitude)
        
        # Save to appropriate storage
        if user_id:
            # Save to database
            success = save_user_filters_to_db(user_id, updated_filters)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to save filters to database")
            storage = "database"
        else:
            # Save to file
            settings.set_magnitude_filters(
                asteroid_max=filters.asteroidMaxMagnitude,
                comet_max=filters.cometMaxMagnitude
            )
            storage = "file"
        
        # Check if filters actually changed
        filters_changed = (
            (filters.asteroidMaxMagnitude is not None and 
             old_asteroid != filters.asteroidMaxMagnitude) or
            (filters.cometMaxMagnitude is not None and 
             old_comet != filters.cometMaxMagnitude)
        )
        
        if filters_changed:
            print(f"Filters changed from {old_filters} to {updated_filters} (storage: {storage})")
            print(f"No cache invalidation needed - filtering happens at API level")
        
        return {
            "success": True,
            "filters": updated_filters,
            "cache_invalidated": False,  # No cache invalidation needed - filtering at API level
            "storage": storage
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
