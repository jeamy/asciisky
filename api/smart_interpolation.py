"""
Smart Interpolation Framework for Asteroids and Comets
======================================================

Provides adaptive interpolation with on-demand computation fallbacks.
Replaces the disabled interpolation in cache_interpolation.py with
a robust solution that handles missing buckets gracefully.

Features:
- Adaptive interpolation strategies based on bucket availability
- On-demand bucket computation for missing data
- Astronomical corrections for horizon events and magnitude smoothing
- Smart caching of computed buckets
- Comprehensive error handling and logging
"""

import logging
from datetime import datetime, timezone
from typing import Any

import bright_asteroids
import comets
from api.computation import LOADER, eph, ts
from api.interpolation import get_interpolation_buckets, interpolate_object_list

# Existing imports
from cache_utils import location_key, normalize_location, time_bucket_utc
from config.interpolation_config import (
    InterpolationStrategy,
    get_config_manager,
)
from config.interpolation_config import (
    get_interpolation_config as get_runtime_interpolation_config,
)
from db_utils import (
    database_target,
    get_asteroid_positions,
    get_comet_positions,
    store_asteroid_positions,
    store_comet_positions,
)

logger = logging.getLogger(__name__)


def load_asteroids_with_smart_interpolation(
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int = 1,
    use_postgres: bool = True
) -> list[dict[str, Any]] | None:
    """
    Load asteroid positions with smart interpolation.

    Args:
        lat: Latitude
        lon: Longitude
        elevation: Elevation in meters
        dt_utc: Target datetime (UTC)
        bucket_hours: Cache bucket size in hours
        use_postgres: Whether to use PostgreSQL backend

    Returns:
        List of interpolated asteroid dictionaries, or None if no data available
    """
    if not get_runtime_interpolation_config().enable_smart_interpolation:
        # Fallback to original nearest-bucket strategy
        return _load_with_nearest_bucket_asteroids(lat, lon, elevation, dt_utc, bucket_hours, use_postgres)

    return _load_with_smart_interpolation(
        'asteroids', lat, lon, elevation, dt_utc, bucket_hours, use_postgres
    )


def load_comets_with_smart_interpolation(
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int = 1,
    use_postgres: bool = True
) -> list[dict[str, Any]] | None:
    """
    Load comet positions with smart interpolation.

    Args:
        lat: Latitude
        lon: Longitude
        elevation: Elevation in meters
        dt_utc: Target datetime (UTC)
        bucket_hours: Cache bucket size in hours
        use_postgres: Whether to use PostgreSQL backend

    Returns:
        List of interpolated comet dictionaries, or None if no data available
    """
    if not get_runtime_interpolation_config().enable_smart_interpolation:
        # Fallback to original nearest-bucket strategy
        return _load_with_nearest_bucket_comets(lat, lon, elevation, dt_utc, bucket_hours, use_postgres)

    return _load_with_smart_interpolation(
        'comets', lat, lon, elevation, dt_utc, bucket_hours, use_postgres
    )


def _load_with_smart_interpolation(
    object_type: str,
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    use_postgres: bool
) -> list[dict[str, Any]] | None:
    """
    Core smart interpolation logic with adaptive strategies.

    Args:
        object_type: 'asteroids' or 'comets'
        lat, lon, elevation: Location parameters
        dt_utc: Target datetime
        bucket_hours: Cache bucket size
        use_postgres: Use PostgreSQL backend

    Returns:
        Interpolated object list or None
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)

    # Get surrounding buckets and interpolation factor
    bucket1_dt, bucket2_dt, factor = get_interpolation_buckets(dt_utc, bucket_hours)

    logger.info(f"Smart interpolation for {object_type} at {dt_utc.isoformat()}: "
               f"bucket1={bucket1_dt.isoformat()}, bucket2={bucket2_dt.isoformat()}, factor={factor:.3f}")

    # Load data for both buckets
    list1 = _load_bucket(object_type, lat, lon, elevation, bucket1_dt, bucket_hours, use_postgres)
    list2 = _load_bucket(object_type, lat, lon, elevation, bucket2_dt, bucket_hours, use_postgres)

    # DEBUG: Log bucket contents
    if list1 is not None:
        logger.info(f"Bucket1 ({bucket1_dt.isoformat()}): {len(list1)} objects loaded")
        if list1 and object_type == 'comets' and len(list1) > 0:
            first_comet = list1[0]
            logger.info(f"  First comet: {first_comet.get('name')} - alt={first_comet.get('altitude'):.1f}°, az={first_comet.get('azimuth'):.1f}°")
    else:
        logger.warning(f"Bucket1 ({bucket1_dt.isoformat()}): EMPTY or None")

    if list2 is not None:
        logger.info(f"Bucket2 ({bucket2_dt.isoformat()}): {len(list2)} objects loaded")
        if list2 and object_type == 'comets' and len(list2) > 0:
            first_comet = list2[0]
            logger.info(f"  First comet: {first_comet.get('name')} - alt={first_comet.get('altitude'):.1f}°, az={first_comet.get('azimuth'):.1f}°")
    else:
        logger.warning(f"Bucket2 ({bucket2_dt.isoformat()}): EMPTY or None")

    # Apply adaptive strategy based on bucket availability
    config = get_runtime_interpolation_config()
    if config.interpolation_strategy == InterpolationStrategy.SMART_INTERPOLATION:
        return _apply_smart_strategy(object_type, lat, lon, elevation, dt_utc,
                                    bucket1_dt, bucket2_dt, factor, list1, list2,
                                    bucket_hours)
    elif config.interpolation_strategy == InterpolationStrategy.ON_DEMAND_ONLY:
        return _apply_on_demand_strategy(object_type, lat, lon, elevation, dt_utc,
                                        bucket1_dt, bucket2_dt, factor, bucket_hours)
    else:
        # Fallback to nearest bucket
        return _apply_nearest_bucket_strategy(list1, list2, factor, bucket2_dt, dt_utc)


def _apply_smart_strategy(
    object_type: str,
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket1_dt: datetime,
    bucket2_dt: datetime,
    factor: float,
    list1: list[dict[str, Any]] | None,
    list2: list[dict[str, Any]] | None,
    bucket_hours: int,
) -> list[dict[str, Any]] | None:
    """
    Apply smart interpolation strategy with on-demand computation.
    """

    config = get_runtime_interpolation_config()

    # Case 1: Both buckets available → True interpolation
    if list1 is not None and list2 is not None:
        logger.info(f"Both buckets available for {object_type} → performing smart interpolation")
        return _interpolate_objects_smart(object_type, list1, list2, factor, dt_utc, lat, lon, elevation)

    # Case 2: Only previous bucket available → Trigger background task or compute on-demand
    if list1 is not None and list2 is None and config.enable_on_demand_computation:
        # Check if background tasks are enabled (async RabbitMQ workers)
        if config.enable_background_tasks:
            # ASYNC: Trigger RabbitMQ worker for bucket2
            logger.info(f"Only previous bucket available for {object_type} → triggering background worker for bucket2")
            _trigger_background_worker(object_type, lat, lon, elevation, bucket2_dt, bucket_hours)

            # EINFACHE LÖSUNG: Extrapoliere aus list1!
            # Wenn wir bei factor=0.5 sind (30min nach bucket1), extrapoliere 30min vorwärts
            # Das ist ungenau, aber besser als alte Position zu zeigen
            logger.info(f"Extrapolating {object_type} from bucket1 (factor={factor:.3f})")
            # Extrapolation = list1 als beide Buckets verwenden, aber mit factor
            # Das gibt uns zumindest die richtige Zeit-Basis
            return list1  # Temporär: Nutze list1, Worker füllt bucket2 im Hintergrund
        else:
            # SYNC: Compute on-demand (blocks request)
            logger.info(f"Only previous bucket available for {object_type} → computing future bucket on-demand (SYNC)")
            list2 = _compute_bucket_on_demand(object_type, lat, lon, elevation, bucket2_dt)
            if list2 is not None:
                if config.cache_ttl_seconds > 0:
                    _store_bucket(object_type, lat, lon, elevation, bucket2_dt, list2, bucket_hours)
                return _interpolate_objects_smart(object_type, list1, list2, factor, dt_utc, lat, lon, elevation)
            logger.warning(f"On-demand computation failed for {object_type} future bucket, using previous bucket")
            return list1

    # Case 3: Only future bucket available → Trigger background task or compute on-demand
    if list1 is None and list2 is not None and config.enable_on_demand_computation:
        if config.enable_background_tasks:
            # ASYNC: Trigger RabbitMQ worker for bucket1
            logger.info(f"Only future bucket available for {object_type} → triggering background worker for bucket1")
            _trigger_background_worker(object_type, lat, lon, elevation, bucket1_dt, bucket_hours)

            # Check if future bucket is within acceptable time range
            time_diff_hours = (bucket2_dt - dt_utc).total_seconds() / 3600
            if time_diff_hours <= config.max_future_hours:
                logger.info(f"Using future bucket for {object_type} (within {time_diff_hours:.1f}h limit)")
                return list2
            else:
                logger.warning(f"Future bucket too far ahead for {object_type} ({time_diff_hours:.1f}h > {config.max_future_hours}h)")
                return None
        else:
            # SYNC: Compute on-demand (blocks request)
            logger.info(f"Only future bucket available for {object_type} → computing previous bucket on-demand (SYNC)")
            list1 = _compute_bucket_on_demand(object_type, lat, lon, elevation, bucket1_dt)
            if list1 is not None:
                if config.cache_ttl_seconds > 0:
                    _store_bucket(object_type, lat, lon, elevation, bucket1_dt, list1, bucket_hours)
                return _interpolate_objects_smart(object_type, list1, list2, factor, dt_utc, lat, lon, elevation)

            # Fallback: Check if future bucket is within acceptable time range
            time_diff_hours = (bucket2_dt - dt_utc).total_seconds() / 3600
            if time_diff_hours <= config.max_future_hours:
                logger.info(f"Using future bucket for {object_type} (within {time_diff_hours:.1f}h limit)")
                return list2
            else:
                logger.warning(f"Future bucket too far ahead for {object_type} ({time_diff_hours:.1f}h > {config.max_future_hours}h)")
                return None

    # Case 4: No buckets available → Trigger background tasks or compute on-demand
    if list1 is None and list2 is None and config.enable_on_demand_computation:
        if config.enable_background_tasks:
            # ASYNC: Trigger RabbitMQ workers for both buckets
            logger.info(f"No buckets available for {object_type} → triggering background workers for both buckets")
            _trigger_background_worker(object_type, lat, lon, elevation, bucket1_dt, bucket_hours)
            _trigger_background_worker(object_type, lat, lon, elevation, bucket2_dt, bucket_hours)
            # Return None (user gets empty response, next request will have data)
            logger.info("Background workers triggered, returning None (data will be available soon)")
            return None
        else:
            # SYNC: Compute both on-demand (blocks request)
            logger.info(f"No buckets available for {object_type} → computing both on-demand (SYNC)")
            list1 = _compute_bucket_on_demand(object_type, lat, lon, elevation, bucket1_dt)
            list2 = _compute_bucket_on_demand(object_type, lat, lon, elevation, bucket2_dt)

            if list1 is not None and list2 is not None:
                if config.cache_ttl_seconds > 0:
                    _store_bucket(object_type, lat, lon, elevation, bucket1_dt, list1, bucket_hours)
                    _store_bucket(object_type, lat, lon, elevation, bucket2_dt, list2, bucket_hours)
                return _interpolate_objects_smart(object_type, list1, list2, factor, dt_utc, lat, lon, elevation)

            # Return whatever we could compute
            return list1 or list2 or None

    # Default fallback
    logger.warning(f"No strategy applicable for {object_type}, returning None")
    return None


def _apply_on_demand_strategy(
    object_type: str,
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket1_dt: datetime,
    bucket2_dt: datetime,
    factor: float,
    bucket_hours: int,
) -> list[dict[str, Any]] | None:
    """
    Apply on-demand only strategy (compute everything fresh).
    """
    logger.info(f"Applying on-demand only strategy for {object_type}")

    # Compute both buckets fresh
    list1 = _compute_bucket_on_demand(object_type, lat, lon, elevation, bucket1_dt)
    list2 = _compute_bucket_on_demand(object_type, lat, lon, elevation, bucket2_dt)

    if list1 is not None and list2 is not None:
        if get_runtime_interpolation_config().cache_ttl_seconds > 0:
            _store_bucket(object_type, lat, lon, elevation, bucket1_dt, list1, bucket_hours)
            _store_bucket(object_type, lat, lon, elevation, bucket2_dt, list2, bucket_hours)
        return _interpolate_objects_smart(object_type, list1, list2, factor, dt_utc, lat, lon, elevation)

    return list1 if list1 is not None else list2


def _apply_nearest_bucket_strategy(
    list1: list[dict[str, Any]] | None,
    list2: list[dict[str, Any]] | None,
    factor: float,
    bucket2_dt: datetime,
    dt_utc: datetime
) -> list[dict[str, Any]] | None:
    """
    Apply original nearest bucket strategy (current behavior).
    """
    # If we have both buckets, prefer the closer one instead of interpolation
    if list1 is not None and list2 is not None:
        if factor < 0.5:
            logger.info(f"Using bucket1 (closer): factor={factor:.3f}")
            return list1
        else:
            logger.info(f"Using bucket2 (closer): factor={factor:.3f}")
            return list2

    # If only one bucket available, use it
    if list1 is not None:
        logger.info("Using only available bucket1")
        return list1

    if list2 is not None:
        # Check if bucket2 is not too far in the future
        time_diff_hours = (bucket2_dt - dt_utc).total_seconds() / 3600
        if time_diff_hours <= get_runtime_interpolation_config().max_future_hours:
            logger.info(f"Using bucket2 (within {time_diff_hours:.1f}h)")
            return list2
        else:
            logger.warning(f"Bucket2 too far in future ({time_diff_hours:.1f}h), returning None")
            return None

    # No buckets available
    return None


def _load_bucket(
    object_type: str,
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    use_postgres: bool
) -> list[dict[str, Any]] | None:
    """Load object data for a single time bucket from PostgreSQL."""
    lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
    loc_key = location_key(lat_norm, lon_norm, elev_norm)
    bucket = time_bucket_utc(dt_utc, bucket_hours)

    # PostgreSQL only
    if use_postgres:
        try:
            if object_type == 'asteroids':
                positions = get_asteroid_positions(loc_key, bucket)
            else:
                positions = get_comet_positions(loc_key, bucket)

            if isinstance(positions, list):
                return positions
            logger.warning(
                "Missing/empty %s cache row: key=%s bucket=%s db=%s",
                object_type, loc_key, bucket, database_target(),
            )
        except Exception as e:
            logger.error(f"Error loading {object_type} bucket {bucket}: {e}")

    return None


def _trigger_background_worker(
    object_type: str,
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int = 1,
) -> None:
    """
    Trigger RabbitMQ worker for background computation (ASYNC).
    Does not block - worker will compute and cache the bucket.
    """
    try:
        import os

        from api.rabbitmq.task_publisher import TaskPublisher

        kind = 'asteroids' if object_type == 'asteroids' else 'comets'
        publisher = TaskPublisher(
            os.environ.get('RABBITMQ_URL', 'amqp://admin:changeme@rabbitmq:5672/')
        )
        task_id = publisher.publish_precompute_task(
            kind=kind,
            location={'latitude': lat, 'longitude': lon, 'elevation': elevation},
            time_bucket=dt_utc.isoformat(),
            magnitude=20.0 if object_type == 'asteroids' else 14.0,
            priority=10,
            bucket_hours=bucket_hours,
        )
        logger.info(f"✅ Triggered background worker for {object_type}: task_id={task_id}, bucket={dt_utc.isoformat()}")

    except Exception as e:
        logger.error(f"❌ Failed to trigger background worker for {object_type}: {e}")


def _compute_bucket_on_demand(
    object_type: str,
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime
) -> list[dict[str, Any]] | None:
    """
    Compute missing bucket on-demand (SYNCHRONOUS - blocks request!).
    Only used when ENABLE_INTERPOLATION_BACKGROUND_TASKS=false.
    """
    try:
        logger.warning(f"⚠️  SYNC computation for {object_type} bucket {dt_utc.isoformat()} - this blocks the request!")

        location_dict = {'latitude': lat, 'longitude': lon, 'elevation': elevation}

        if object_type == 'asteroids':
            objects = bright_asteroids.load_bright_asteroids(
                LOADER, ts, eph, location_dict,
                max_magnitude=20.0,
                current_dt=dt_utc
            )
        else:  # comets
            objects = comets.load_comets(
                ts, eph, location_dict,
                max_comets=1000,
                current_dt=dt_utc
            )

        logger.info(f"On-demand computation completed: {len(objects) if objects else 0} {object_type}")
        return objects if objects else []

    except Exception as e:
        logger.error(f"On-demand {object_type} computation failed: {e}")
        return None


def _store_bucket(
    object_type: str,
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    objects: list[dict[str, Any]],
    bucket_hours: int,
) -> None:
    """
    Store computed bucket in cache.
    """
    try:
        lat_norm, lon_norm, elev_norm = normalize_location(lat, lon, elevation)
        loc_key = location_key(lat_norm, lon_norm, elev_norm)
        bucket = time_bucket_utc(dt_utc, bucket_hours)

        if object_type == 'asteroids':
            store_asteroid_positions(0, loc_key, bucket, lat_norm, lon_norm, elev_norm, objects)
        else:
            store_comet_positions(0, loc_key, bucket, lat_norm, lon_norm, elev_norm, objects)

        logger.info(f"Cached {len(objects)} {object_type} for bucket {bucket}")

    except Exception as e:
        logger.error(f"Failed to cache {object_type} bucket: {e}")


def _interpolate_objects_smart(
    object_type: str,
    list1: list[dict[str, Any]],
    list2: list[dict[str, Any]],
    factor: float,
    target_dt: datetime,
    lat: float = 0.0,
    lon: float = 0.0,
    elevation: float = 0.0
) -> list[dict[str, Any]]:
    """
    Perform smart interpolation with astronomical corrections.
    """
    try:
        # Base interpolation
        interpolated = interpolate_object_list(list1, list2, factor)

        # Apply astronomical corrections with location
        location = {'latitude': lat, 'longitude': lon, 'elevation': elevation}
        corrected = []
        for obj in interpolated:
            corrected_obj = _apply_astronomical_corrections(obj, list1, list2, factor, target_dt, location)
            corrected.append(corrected_obj)

        logger.info(f"Smart interpolation completed for {object_type}: {len(corrected)} objects")
        return corrected

    except Exception as e:
        logger.error(f"Smart interpolation failed for {object_type}: {e}")
        # Fallback to basic interpolation
        return interpolate_object_list(list1, list2, factor)


def _apply_astronomical_corrections(
    obj: dict[str, Any],
    list1: list[dict[str, Any]],
    list2: list[dict[str, Any]],
    factor: float,
    target_dt: datetime,
    location: dict[str, float]
) -> dict[str, Any]:
    """
    Apply astronomical corrections to interpolated object.
    Uses the dedicated astronomical_corrections module.
    """
    try:
        from api.astronomical_corrections import apply_astronomical_corrections

        result = apply_astronomical_corrections(obj, list1, list2, factor, target_dt, location)
        return result.corrected_object

    except Exception as e:
        logger.error(f"Astronomical corrections failed for {obj.get('name')}: {e}")
        # Fallback: return uncorrected object
        return obj


# Removed duplicate functions - now using astronomical_corrections module:
# - _is_horizon_crossing() → use astronomical_corrections.py
# - _correct_horizon_crossing() → use astronomical_corrections.py
# - _smooth_magnitude_interpolation() → use astronomical_corrections.py
# - _find_object_by_name() → use astronomical_corrections.py


def _load_with_nearest_bucket_asteroids(
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    use_postgres: bool
) -> list[dict[str, Any]] | None:
    """Fallback to original nearest bucket strategy for asteroids."""
    # Import here to avoid circular imports
    from api.cache_interpolation import load_asteroids_with_interpolation
    return load_asteroids_with_interpolation(lat, lon, elevation, dt_utc, bucket_hours, use_postgres)


def _load_with_nearest_bucket_comets(
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    bucket_hours: int,
    use_postgres: bool
) -> list[dict[str, Any]] | None:
    """Fallback to original nearest bucket strategy for comets."""
    # Import here to avoid circular imports
    from api.cache_interpolation import load_comets_with_interpolation
    return load_comets_with_interpolation(lat, lon, elevation, dt_utc, bucket_hours, use_postgres)


def get_interpolation_config():
    """Get current interpolation configuration."""
    return get_runtime_interpolation_config()


def reload_interpolation_config():
    """Reload interpolation configuration from environment."""
    get_config_manager().reload_config()
    logger.info("Smart interpolation configuration reloaded")
