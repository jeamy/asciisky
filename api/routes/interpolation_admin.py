"""
Interpolation Administration API Routes
======================================

Administrative endpoints for managing smart interpolation features,
including configuration updates, monitoring, and gradual rollout controls.

Features:
- Feature flag management
- User-specific enablement
- Configuration updates
- Performance monitoring
- Rollback capabilities
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.on_demand_computation import get_on_demand_service
from api.routes.admin_users import _require_admin
from config.interpolation_config import (
    CorrectionLevel,
    InterpolationStrategy,
    get_config_manager,
    get_interpolation_config,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/admin/interpolation",
    tags=["interpolation-admin"],
    dependencies=[Depends(_require_admin)],
)


class ConfigUpdateRequest(BaseModel):
    """Request model for configuration updates"""
    enable_smart_interpolation: bool | None = None
    interpolation_strategy: str | None = None
    enable_on_demand_computation: bool | None = None
    enable_astronomical_corrections: bool | None = None
    correction_level: str | None = None
    max_computation_time: float | None = None
    cache_ttl_seconds: int | None = None
    max_future_hours: float | None = None
    enabled_percentage: float | None = Field(None, ge=0, le=100)


class UserEnablementRequest(BaseModel):
    """Request model for user-specific enablement"""
    user_ids: list[str] = Field(..., description="List of user IDs to enable/disable")
    enable: bool = Field(True, description="Whether to enable or disable for users")


class InterpolationStatusResponse(BaseModel):
    """Response model for interpolation status"""
    enabled: bool
    strategy: str
    on_demand_enabled: bool
    corrections_enabled: bool
    correction_level: str
    enabled_users: int
    enabled_percentage: float
    last_updated: float


class MetricsResponse(BaseModel):
    """Response model for performance metrics"""
    total_computations: int
    successful_computations: int
    cache_hits: int
    background_tasks_triggered: int
    average_computation_time: float
    cache_hit_rate: float


@router.get("/status", response_model=InterpolationStatusResponse)
async def get_interpolation_status():
    """
    Get current interpolation configuration status.
    """
    try:
        manager = get_config_manager()
        summary = manager.get_config_summary()
        
        return InterpolationStatusResponse(**summary)
    except Exception as e:
        logger.error(f"Error getting interpolation status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_interpolation_config(config_update: ConfigUpdateRequest):
    """
    Update interpolation configuration.
    """
    try:
        manager = get_config_manager()
        
        # Build update dictionary from request
        update_dict = {}
        if config_update.enable_smart_interpolation is not None:
            update_dict['enable_smart_interpolation'] = config_update.enable_smart_interpolation
        
        if config_update.interpolation_strategy is not None:
            try:
                strategy = InterpolationStrategy(config_update.interpolation_strategy)
                update_dict['interpolation_strategy'] = strategy
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid strategy: {config_update.interpolation_strategy}")
        
        if config_update.enable_on_demand_computation is not None:
            update_dict['enable_on_demand_computation'] = config_update.enable_on_demand_computation
        
        if config_update.enable_astronomical_corrections is not None:
            update_dict['enable_astronomical_corrections'] = config_update.enable_astronomical_corrections
        
        if config_update.correction_level is not None:
            try:
                level = CorrectionLevel(config_update.correction_level)
                update_dict['correction_level'] = level
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid correction level: {config_update.correction_level}")
        
        if config_update.max_computation_time is not None:
            update_dict['max_computation_time'] = config_update.max_computation_time
        
        if config_update.cache_ttl_seconds is not None:
            update_dict['cache_ttl_seconds'] = config_update.cache_ttl_seconds
        
        if config_update.max_future_hours is not None:
            update_dict['max_future_hours'] = config_update.max_future_hours
        
        if config_update.enabled_percentage is not None:
            update_dict['enabled_percentage'] = config_update.enabled_percentage
        
        # Apply updates
        if update_dict:
            manager.update_config(update_dict)
            logger.info(f"Updated interpolation config: {update_dict}")
            return {"message": "Configuration updated successfully", "updates": update_dict}
        else:
            return {"message": "No updates provided"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating interpolation config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload")
async def reload_interpolation_config():
    """
    Reload interpolation configuration from environment variables.
    """
    try:
        manager = get_config_manager()
        manager.reload_config()
        logger.info("Interpolation configuration reloaded from environment")
        return {"message": "Configuration reloaded successfully"}
    except Exception as e:
        logger.error(f"Error reloading interpolation config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/enable")
async def enable_users_for_interpolation(request: UserEnablementRequest):
    """
    Enable or disable smart interpolation for specific users.
    """
    try:
        manager = get_config_manager()
        
        if request.enable:
            for user_id in request.user_ids:
                manager.enable_for_user(user_id)
            logger.info(f"Enabled smart interpolation for {len(request.user_ids)} users")
            return {"message": f"Enabled for {len(request.user_ids)} users"}
        else:
            for user_id in request.user_ids:
                manager.disable_for_user(user_id)
            logger.info(f"Disabled smart interpolation for {len(request.user_ids)} users")
            return {"message": f"Disabled for {len(request.user_ids)} users"}
            
    except Exception as e:
        logger.error(f"Error updating user enablement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/percentage")
async def set_enabled_percentage(percentage: float = Query(..., ge=0, le=100)):
    """
    Set percentage of users enabled for smart interpolation.
    """
    try:
        manager = get_config_manager()
        manager.set_enabled_percentage(percentage)
        logger.info(f"Set enabled percentage to {percentage}%")
        return {"message": f"Enabled percentage set to {percentage}%"}
    except Exception as e:
        logger.error(f"Error setting enabled percentage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics", response_model=MetricsResponse)
async def get_interpolation_metrics():
    """
    Get performance metrics for on-demand computation.
    """
    try:
        service = get_on_demand_service()
        metrics = service.get_metrics()
        
        # Calculate cache hit rate
        cache_hit_rate = 0.0
        if metrics.total_computations > 0:
            cache_hit_rate = metrics.cache_hits / metrics.total_computations
        
        return MetricsResponse(
            total_computations=metrics.total_computations,
            successful_computations=metrics.successful_computations,
            cache_hits=metrics.cache_hits,
            background_tasks_triggered=metrics.background_tasks_triggered,
            average_computation_time=metrics.average_computation_time,
            cache_hit_rate=cache_hit_rate
        )
    except Exception as e:
        logger.error(f"Error getting interpolation metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/metrics/reset")
async def reset_interpolation_metrics():
    """
    Reset performance metrics.
    """
    try:
        service = get_on_demand_service()
        service.reset_metrics()
        logger.info("Interpolation metrics reset")
        return {"message": "Metrics reset successfully"}
    except Exception as e:
        logger.error(f"Error resetting metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/clear")
async def clear_interpolation_cache():
    """
    Clear all interpolation caches.
    """
    try:
        service = get_on_demand_service()
        service.clear_cache()
        logger.info("Interpolation cache cleared")
        return {"message": "Cache cleared successfully"}
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies")
async def get_available_strategies():
    """
    Get list of available interpolation strategies.
    """
    try:
        strategies = [strategy.value for strategy in InterpolationStrategy]
        return {"strategies": strategies}
    except Exception as e:
        logger.error(f"Error getting strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/correction-levels")
async def get_available_correction_levels():
    """
    Get list of available correction levels.
    """
    try:
        levels = [level.value for level in CorrectionLevel]
        return {"correction_levels": levels}
    except Exception as e:
        logger.error(f"Error getting correction levels: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/features/{feature}/enable")
async def enable_feature(feature: str):
    """
    Enable a specific interpolation feature.
    """
    try:
        manager = get_config_manager()
        manager.enable_feature(feature)
        logger.info(f"Enabled feature: {feature}")
        return {"message": f"Feature '{feature}' enabled"}
    except Exception as e:
        logger.error(f"Error enabling feature {feature}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/features/{feature}/disable")
async def disable_feature(feature: str):
    """
    Disable a specific interpolation feature.
    """
    try:
        manager = get_config_manager()
        manager.disable_feature(feature)
        logger.info(f"Disabled feature: {feature}")
        return {"message": f"Feature '{feature}' disabled"}
    except Exception as e:
        logger.error(f"Error disabling feature {feature}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/full")
async def get_full_config():
    """
    Get full configuration dictionary (for debugging).
    """
    try:
        config = get_interpolation_config()
        return config.to_dict()
    except Exception as e:
        logger.error(f"Error getting full config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rollback")
async def rollback_to_defaults():
    """
    Rollback configuration to defaults (disable smart interpolation).
    """
    try:
        manager = get_config_manager()
        
        # Reset to safe defaults
        default_config = {
            'enable_smart_interpolation': False,
            'interpolation_strategy': 'nearest_bucket',
            'enable_on_demand_computation': False,
            'enable_astronomical_corrections': False,
            'correction_level': 'none',
            'enabled_percentage': 0.0,
            'enabled_user_ids': []
        }
        
        manager.update_config(default_config)
        logger.info("Rolled back interpolation configuration to defaults")
        return {"message": "Configuration rolled back to defaults", "config": default_config}
        
    except Exception as e:
        logger.error(f"Error rolling back config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Health check endpoint
@router.get("/health")
async def interpolation_health_check():
    """
    Health check for interpolation system.
    """
    try:
        service = get_on_demand_service()
        metrics = service.get_metrics()
        
        health_status = {
            "status": "healthy",
            "config_loaded": True,
            "service_initialized": True,
            "total_computations": metrics.total_computations,
            "success_rate": metrics.successful_computations / max(metrics.total_computations, 1)
        }
        
        # Check for potential issues
        if metrics.total_computations > 0:
            success_rate = metrics.successful_computations / metrics.total_computations
            if success_rate < 0.8:  # Less than 80% success rate
                health_status["status"] = "degraded"
                health_status["warning"] = f"Low success rate: {success_rate:.2%}"
        
        return health_status
        
    except Exception as e:
        logger.error(f"Interpolation health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }
