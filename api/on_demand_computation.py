"""
On-Demand Computation Service for Smart Interpolation
=====================================================

Provides immediate computation of missing asteroid/comet buckets
with intelligent caching and background task triggering.

Features:
- Synchronous computation for immediate response
- Background task triggering for future caching
- Smart caching with TTL management
- Error handling and retry logic
- Performance monitoring and metrics
"""

import logging
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

# AsciiSky imports
import bright_asteroids
import comets
from api.computation import LOADER, eph, ts
from api.rabbitmq.task_publisher import get_task_publisher
from cache_utils import location_key, normalize_location, time_bucket_utc
from db_utils import store_asteroid_positions, store_comet_positions

logger = logging.getLogger(__name__)


class ComputationStatus(Enum):
    """Status of on-demand computation"""
    SUCCESS = "success"
    FAILED = "failed"
    CACHED = "cached"
    BACKGROUND_TRIGGERED = "background_triggered"


@dataclass
class ComputationResult:
    """Result of on-demand computation"""
    status: ComputationStatus
    objects: list[dict[str, Any]] | None
    computation_time: float
    cache_hit: bool
    error_message: str | None = None
    task_id: str | None = None


@dataclass
class ComputationMetrics:
    """Metrics for on-demand computation performance"""
    total_computations: int = 0
    successful_computations: int = 0
    cache_hits: int = 0
    background_tasks_triggered: int = 0
    average_computation_time: float = 0.0
    total_computation_time: float = 0.0


class OnDemandComputationConfig:
    """Configuration for on-demand computation"""
    
    def __init__(self):
        self.enabled = os.getenv('ON_DEMAND_COMPUTATION_ENABLED', 'true').lower() == 'true'
        self.cache_ttl = int(os.getenv('ON_DEMAND_CACHE_TTL', '86400'))  # 24 hours
        self.max_computation_time = float(os.getenv('ON_DEMAND_MAX_COMPUTATION_TIME', '30.0'))  # seconds
        self.trigger_background_tasks = os.getenv('ON_DEMAND_TRIGGER_BACKGROUND', 'true').lower() == 'true'
        self.max_magnitude_asteroids = float(os.getenv('ON_DEMAND_MAX_MAGNITUDE_ASTEROIDS', '20.0'))
        self.max_comets = int(os.getenv('ON_DEMAND_MAX_COMETS', '1000'))
        self.retry_failed_computations = os.getenv('ON_DEMAND_RETRY_FAILED', 'true').lower() == 'true'
        self.max_retries = int(os.getenv('ON_DEMAND_MAX_RETRIES', '2'))
        
        logger.info(f"On-Demand Computation Config: enabled={self.enabled}, "
                   f"cache_ttl={self.cache_ttl}s, "
                   f"max_computation_time={self.max_computation_time}s")


class OnDemandComputationService:
    """
    Service for on-demand computation of asteroid and comet buckets.
    """
    
    def __init__(self, config: OnDemandComputationConfig | None = None):
        self.config = config or OnDemandComputationConfig()
        self.metrics = ComputationMetrics()
        self._computation_cache = {}  # Simple in-memory cache for very recent computations
        self._cache_timestamps = {}
        
        logger.info(f"On-Demand Computation Service initialized: {self.config.enabled}")
    
    def compute_asteroid_bucket(
        self,
        lat: float,
        lon: float,
        elevation: float,
        dt_utc: datetime,
        force_recompute: bool = False
    ) -> ComputationResult:
        """
        Compute asteroid bucket on-demand.
        
        Args:
            lat, lon, elevation: Location parameters
            dt_utc: Target datetime for computation
            force_recompute: Force fresh computation even if cached
            
        Returns:
            ComputationResult with computed asteroids or error information
        """
        return self._compute_bucket(
            object_type='asteroids',
            lat=lat,
            lon=lon,
            elevation=elevation,
            dt_utc=dt_utc,
            force_recompute=force_recompute,
            computation_func=self._compute_asteroids_sync
        )
    
    def compute_comet_bucket(
        self,
        lat: float,
        lon: float,
        elevation: float,
        dt_utc: datetime,
        force_recompute: bool = False
    ) -> ComputationResult:
        """
        Compute comet bucket on-demand.
        
        Args:
            lat, lon, elevation: Location parameters
            dt_utc: Target datetime for computation
            force_recompute: Force fresh computation even if cached
            
        Returns:
            ComputationResult with computed comets or error information
        """
        return self._compute_bucket(
            object_type='comets',
            lat=lat,
            lon=lon,
            elevation=elevation,
            dt_utc=dt_utc,
            force_recompute=force_recompute,
            computation_func=self._compute_comets_sync
        )
    
    def _compute_bucket(
        self,
        object_type: str,
        lat: float,
        lon: float,
        elevation: float,
        dt_utc: datetime,
        force_recompute: bool,
        computation_func: Callable
    ) -> ComputationResult:
        """
        Core computation logic with caching and error handling.
        """
        start_time = time.time()
        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        bucket = time_bucket_utc(dt_utc, 1)
        cache_key = f"{object_type}:{loc_key}:{bucket}"
        
        try:
            # Check in-memory cache first
            if not force_recompute and self._is_cached(cache_key):
                cached_objects = self._computation_cache[cache_key]
                self.metrics.cache_hits += 1
                
                computation_time = time.time() - start_time
                logger.info(f"Cache hit for {object_type} bucket: {len(cached_objects)} objects in {computation_time:.3f}s")
                
                return ComputationResult(
                    status=ComputationStatus.CACHED,
                    objects=cached_objects,
                    computation_time=computation_time,
                    cache_hit=True
                )
            
            # Perform computation
            logger.info(f"Computing {object_type} bucket on-demand for {dt_utc.isoformat()}")
            objects = computation_func(lat, lon, elevation, dt_utc)
            
            if objects is None:
                objects = []
            
            computation_time = time.time() - start_time
            
            # Check computation time limit
            if computation_time > self.config.max_computation_time:
                logger.warning(f"{object_type} computation exceeded time limit: {computation_time:.2f}s > {self.config.max_computation_time}s")
            
            # Cache the result
            self._cache_result(cache_key, objects)
            
            # Store in persistent cache
            if self.config.cache_ttl > 0:
                self._store_bucket_persistent(object_type, loc_key, bucket, lat_norm, lon_norm, elev_norm, objects)
            
            # Trigger background task for future caching
            if self.config.trigger_background_tasks:
                self._trigger_background_computation(object_type, lat, lon, elevation, dt_utc)
            
            # Update metrics
            self.metrics.total_computations += 1
            self.metrics.successful_computations += 1
            self.metrics.total_computation_time += computation_time
            self.metrics.average_computation_time = self.metrics.total_computation_time / self.metrics.total_computations
            
            logger.info(f"Successfully computed {object_type} bucket: {len(objects)} objects in {computation_time:.3f}s")
            
            return ComputationResult(
                status=ComputationStatus.SUCCESS,
                objects=objects,
                computation_time=computation_time,
                cache_hit=False
            )
            
        except Exception as e:
            computation_time = time.time() - start_time
            error_msg = f"On-demand {object_type} computation failed: {e!s}"
            logger.error(error_msg)
            
            # Update metrics
            self.metrics.total_computations += 1
            
            # Retry logic
            if self.config.retry_failed_computations and not force_recompute:
                logger.info(f"Retrying failed {object_type} computation")
                return self._compute_bucket(
                    object_type, lat, lon, elevation, dt_utc, 
                    force_recompute=True, computation_func=computation_func
                )
            
            return ComputationResult(
                status=ComputationStatus.FAILED,
                objects=None,
                computation_time=computation_time,
                cache_hit=False,
                error_message=error_msg
            )
    
    def _compute_asteroids_sync(
        self,
        lat: float,
        lon: float,
        elevation: float,
        dt_utc: datetime
    ) -> list[dict[str, Any]] | None:
        """
        Synchronous asteroid computation.
        """
        location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        
        asteroids = bright_asteroids.load_bright_asteroids(
            LOADER, ts, eph, location_dict,
            max_magnitude=self.config.max_magnitude_asteroids,
            current_dt=dt_utc
        )
        
        return asteroids if asteroids else []
    
    def _compute_comets_sync(
        self,
        lat: float,
        lon: float,
        elevation: float,
        dt_utc: datetime
    ) -> list[dict[str, Any]] | None:
        """
        Synchronous comet computation.
        """
        location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        
        comets_data = comets.load_comets(
            ts, eph, location_dict,
            max_comets=self.config.max_comets,
            current_dt=dt_utc
        )
        
        return comets_data if comets_data else []
    
    
    def _is_cached(self, cache_key: str) -> bool:
        """
        Check if result is cached and not expired.
        """
        if cache_key not in self._computation_cache:
            return False
        
        if cache_key not in self._cache_timestamps:
            return False
        
        cache_age = time.time() - self._cache_timestamps[cache_key]
        return cache_age < min(self.config.cache_ttl, 300)  # Max 5 minutes in-memory cache
    
    def _cache_result(self, cache_key: str, objects: list[dict[str, Any]]) -> None:
        """
        Cache computation result in memory.
        """
        self._computation_cache[cache_key] = objects
        self._cache_timestamps[cache_key] = time.time()
        
        # Clean old cache entries periodically
        if len(self._computation_cache) > 100:  # Simple cleanup threshold
            self._cleanup_old_cache()
    
    def _cleanup_old_cache(self) -> None:
        """
        Remove expired entries from in-memory cache.
        """
        current_time = time.time()
        expired_keys = []
        
        for cache_key, timestamp in self._cache_timestamps.items():
            if current_time - timestamp > 300:  # 5 minutes
                expired_keys.append(cache_key)
        
        for key in expired_keys:
            self._computation_cache.pop(key, None)
            self._cache_timestamps.pop(key, None)
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    def _store_bucket_persistent(
        self,
        object_type: str,
        loc_key: str,
        bucket: str,
        lat_norm: float,
        lon_norm: float,
        elev_norm: float,
        objects: list[dict[str, Any]]
    ) -> None:
        """
        Store computed bucket in persistent cache.
        """
        try:
            if object_type == 'asteroids':
                store_asteroid_positions(0, loc_key, bucket, lat_norm, lon_norm, elev_norm, objects)
            else:
                store_comet_positions(0, loc_key, bucket, lat_norm, lon_norm, elev_norm, objects)
            
            logger.debug(f"Stored {len(objects)} {object_type} in persistent cache for bucket {bucket}")
            
        except Exception as e:
            logger.error(f"Failed to store {object_type} bucket in persistent cache: {e}")
    
    def _trigger_background_computation(
        self,
        object_type: str,
        lat: float,
        lon: float,
        elevation: float,
        dt_utc: datetime
    ) -> None:
        """
        Trigger background computation for related buckets.
        """
        try:
            # Create task for background processing
            task_id = f"{object_type}_ondemand_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            
            # Trigger via RabbitMQ if available
            task_publisher = get_task_publisher()
            if task_publisher:
                task_data = {
                    'task_id': task_id,
                    'type': 'on_demand',
                    'object_type': object_type,
                    'location': {'latitude': lat, 'longitude': lon, 'elevation': elevation},
                    'time_bucket': dt_utc.isoformat(),
                    'magnitude': self.config.max_magnitude_asteroids if object_type == 'asteroids' else 14.0,
                    'priority': 5  # Medium priority for on-demand triggered tasks
                }
                
                task_publisher.publish_on_demand_task(task_data)
                
                self.metrics.background_tasks_triggered += 1
                logger.info(f"Triggered background computation for {object_type}: task_id={task_id}")
            else:
                # Fallback: trigger via existing API mechanisms
                logger.debug(f"No task publisher available for {object_type} background computation")
                
        except Exception as e:
            logger.error(f"Failed to trigger background {object_type} computation: {e}")
    
    def get_metrics(self) -> ComputationMetrics:
        """
        Get current computation metrics.
        """
        return self.metrics
    
    def reset_metrics(self) -> None:
        """
        Reset computation metrics.
        """
        self.metrics = ComputationMetrics()
        logger.info("On-demand computation metrics reset")
    
    def clear_cache(self) -> None:
        """
        Clear all caches.
        """
        self._computation_cache.clear()
        self._cache_timestamps.clear()
        logger.info("On-demand computation cache cleared")


# Global service instance
_service = None


def get_on_demand_service() -> OnDemandComputationService:
    """
    Get global on-demand computation service instance.
    """
    global _service
    if _service is None:
        _service = OnDemandComputationService()
    return _service
