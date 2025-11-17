"""
Feature Flags and Configuration for Smart Interpolation
======================================================

Central configuration management for the smart interpolation system
with feature flags, environment variables, and runtime configuration.

Features:
- Feature flag management for gradual rollout
- Environment variable configuration
- Runtime configuration updates
- Validation and defaults
- Configuration monitoring and logging
"""

import os
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class InterpolationStrategy(Enum):
    """Available interpolation strategies"""
    NEAREST_BUCKET = "nearest_bucket"          # Original fallback strategy
    SMART_INTERPOLATION = "smart_interpolation"  # New adaptive strategy
    ON_DEMAND_ONLY = "on_demand_only"          # Compute everything fresh
    HYBRID = "hybrid"                          # Mix of strategies


class CorrectionLevel(Enum):
    """Levels of astronomical corrections"""
    NONE = "none"              # No corrections
    BASIC = "basic"            # Basic smoothing only
    STANDARD = "standard"      # Standard corrections
    ADVANCED = "advanced"      # All corrections including validation


@dataclass
class SmartInterpolationConfig:
    """Configuration for smart interpolation system"""
    
    # Feature flags
    enable_smart_interpolation: bool = field(default_factory=lambda: 
        os.getenv('ENABLE_SMART_INTERPOLATION', 'false').lower() == 'true')
    
    enable_on_demand_computation: bool = field(default_factory=lambda:
        os.getenv('ENABLE_ON_DEMAND_COMPUTATION', 'true').lower() == 'true')
    
    enable_astronomical_corrections: bool = field(default_factory=lambda:
        os.getenv('ENABLE_ASTRONOMICAL_CORRECTIONS', 'true').lower() == 'true')
    
    enable_background_tasks: bool = field(default_factory=lambda:
        os.getenv('ENABLE_INTERPOLATION_BACKGROUND_TASKS', 'true').lower() == 'true')
    
    # Strategy selection
    interpolation_strategy: InterpolationStrategy = field(default_factory=lambda:
        InterpolationStrategy(os.getenv('INTERPOLATION_STRATEGY', 'nearest_bucket')))
    
    correction_level: CorrectionLevel = field(default_factory=lambda:
        CorrectionLevel(os.getenv('ASTRONOMICAL_CORRECTION_LEVEL', 'basic')))
    
    # Performance settings
    max_computation_time: float = field(default_factory=lambda:
        float(os.getenv('INTERPOLATION_MAX_COMPUTATION_TIME', '30.0')))
    
    cache_ttl_seconds: int = field(default_factory=lambda:
        int(os.getenv('INTERPOLATION_CACHE_TTL', '86400')))  # 24 hours
    
    max_future_hours: float = field(default_factory=lambda:
        float(os.getenv('INTERPOLATION_MAX_FUTURE_HOURS', '2.0')))
    
    # Quality settings
    min_quality_threshold: float = field(default_factory=lambda:
        float(os.getenv('INTERPOLATION_MIN_QUALITY_THRESHOLD', '0.5')))
    
    max_interpolation_error: float = field(default_factory=lambda:
        float(os.getenv('INTERPOLATION_MAX_ERROR_DEGREES', '2.0')))
    
    # Computation limits
    max_comets: int = field(default_factory=lambda:
        int(os.getenv('INTERPOLATION_MAX_COMETS', '1000')))
    
    # Retry and error handling
    enable_retry: bool = field(default_factory=lambda:
        os.getenv('INTERPOLATION_ENABLE_RETRY', 'true').lower() == 'true')
    
    max_retries: int = field(default_factory=lambda:
        int(os.getenv('INTERPOLATION_MAX_RETRIES', '2')))
    
    retry_delay_seconds: float = field(default_factory=lambda:
        float(os.getenv('INTERPOLATION_RETRY_DELAY', '1.0')))
    
    # Monitoring and debugging
    enable_metrics: bool = field(default_factory=lambda:
        os.getenv('INTERPOLATION_ENABLE_METRICS', 'true').lower() == 'true')
    
    enable_debug_logging: bool = field(default_factory=lambda:
        os.getenv('INTERPOLATION_DEBUG_LOGGING', 'false').lower() == 'true')
    
    log_performance_warnings: bool = field(default_factory=lambda:
        os.getenv('INTERPOLATION_LOG_PERFORMANCE_WARNINGS', 'true').lower() == 'true')
    
    # User-specific settings (for gradual rollout)
    enabled_user_ids: List[str] = field(default_factory=lambda:
        os.getenv('INTERPOLATION_ENABLED_USER_IDS', '').split(',') if os.getenv('INTERPOLATION_ENABLED_USER_IDS') else [])
    
    enabled_percentage: float = field(default_factory=lambda:
        float(os.getenv('INTERPOLATION_ENABLED_PERCENTAGE', '0.0')))  # 0-100% of users
    
    def __post_init__(self):
        """Validate configuration after initialization"""
        self._validate_config()
        self._log_config()
    
    def _validate_config(self):
        """Validate configuration values"""
        if self.max_future_hours < 0 or self.max_future_hours > 24:
            logger.warning(f"Invalid max_future_hours: {self.max_future_hours}, using default 2.0")
            self.max_future_hours = 2.0
        
        if self.cache_ttl_seconds < 0:
            logger.warning(f"Invalid cache_ttl_seconds: {self.cache_ttl_seconds}, using default 86400")
            self.cache_ttl_seconds = 86400
        
        if self.min_quality_threshold < 0 or self.min_quality_threshold > 1:
            logger.warning(f"Invalid min_quality_threshold: {self.min_quality_threshold}, using default 0.5")
            self.min_quality_threshold = 0.5
        
        if self.enabled_percentage < 0 or self.enabled_percentage > 100:
            logger.warning(f"Invalid enabled_percentage: {self.enabled_percentage}, using default 0.0")
            self.enabled_percentage = 0.0
    
    def _log_config(self):
        """Log current configuration"""
        logger.info(f"Smart Interpolation Configuration:")
        logger.info(f"  - Enabled: {self.enable_smart_interpolation}")
        logger.info(f"  - Strategy: {self.interpolation_strategy.value}")
        logger.info(f"  - On-Demand: {self.enable_on_demand_computation}")
        logger.info(f"  - Corrections: {self.enable_astronomical_corrections} ({self.correction_level.value})")
        logger.info(f"  - Max Computation Time: {self.max_computation_time}s")
        logger.info(f"  - Cache TTL: {self.cache_ttl_seconds}s")
        logger.info(f"  - Max Future Hours: {self.max_future_hours}")
        logger.info(f"  - Enabled Users: {len(self.enabled_user_ids)}")
        logger.info(f"  - Enabled Percentage: {self.enabled_percentage}%")
    
    def is_enabled_for_user(self, user_id: str) -> bool:
        """
        Check if smart interpolation is enabled for a specific user.
        Used for gradual rollout.
        """
        if not self.enable_smart_interpolation:
            return False
        
        # If user is explicitly enabled
        if user_id in self.enabled_user_ids:
            return True
        
        # If percentage-based rollout
        if self.enabled_percentage > 0:
            # Simple hash-based user selection for consistent rollout
            user_hash = hash(user_id) % 100
            return user_hash < self.enabled_percentage
        
        return False
    
    def should_use_smart_interpolation(self, user_id: str = 'anonymous') -> bool:
        """
        Determine if smart interpolation should be used for this request.
        """
        return self.is_enabled_for_user(user_id)
    
    def get_strategy_for_user(self, user_id: str = 'anonymous') -> InterpolationStrategy:
        """
        Get interpolation strategy for a specific user.
        """
        if not self.should_use_smart_interpolation(user_id):
            return InterpolationStrategy.NEAREST_BUCKET
        
        return self.interpolation_strategy
    
    def update_from_dict(self, config_dict: Dict[str, Any]) -> None:
        """
        Update configuration from dictionary.
        """
        for key, value in config_dict.items():
            if hasattr(self, key):
                setattr(self, key, value)
                logger.info(f"Updated config: {key} = {value}")
        
        self._validate_config()
        self._log_config()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.
        """
        result = {}
        for field_name, field_def in self.__dataclass_fields__.items():
            value = getattr(self, field_name)
            if isinstance(value, Enum):
                result[field_name] = value.value
            elif isinstance(value, list):
                result[field_name] = value.copy()
            else:
                result[field_name] = value
        return result


class InterpolationConfigManager:
    """
    Manages interpolation configuration with runtime updates and monitoring.
    """
    
    def __init__(self):
        self._config = SmartInterpolationConfig()
        self._config_timestamp = 0
        self._update_callbacks = []
        
        logger.info("Interpolation Config Manager initialized")
    
    def get_config(self) -> SmartInterpolationConfig:
        """Get current configuration"""
        return self._config
    
    def reload_config(self) -> None:
        """Reload configuration from environment variables"""
        old_config = self._config.to_dict()
        self._config = SmartInterpolationConfig()
        self._config_timestamp = os.times()[4]  # Current time
        
        # Notify callbacks if configuration changed
        if old_config != self._config.to_dict():
            logger.info("Interpolation configuration changed")
            for callback in self._update_callbacks:
                try:
                    callback(self._config)
                except Exception as e:
                    logger.error(f"Error in config update callback: {e}")
    
    def update_config(self, config_dict: Dict[str, Any]) -> None:
        """Update configuration from dictionary"""
        self._config.update_from_dict(config_dict)
        self._config_timestamp = os.times()[4]
        
        # Notify callbacks
        for callback in self._update_callbacks:
            try:
                callback(self._config)
            except Exception as e:
                logger.error(f"Error in config update callback: {e}")
    
    def add_update_callback(self, callback) -> None:
        """Add callback for configuration updates"""
        self._update_callbacks.append(callback)
    
    def remove_update_callback(self, callback) -> None:
        """Remove callback for configuration updates"""
        if callback in self._update_callbacks:
            self._update_callbacks.remove(callback)
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get configuration summary for monitoring"""
        return {
            'enabled': self._config.enable_smart_interpolation,
            'strategy': self._config.interpolation_strategy.value,
            'on_demand_enabled': self._config.enable_on_demand_computation,
            'corrections_enabled': self._config.enable_astronomical_corrections,
            'correction_level': self._config.correction_level.value,
            'enabled_users': len(self._config.enabled_user_ids),
            'enabled_percentage': self._config.enabled_percentage,
            'last_updated': self._config_timestamp
        }
    
    def enable_for_user(self, user_id: str) -> None:
        """Enable smart interpolation for specific user"""
        if user_id not in self._config.enabled_user_ids:
            self._config.enabled_user_ids.append(user_id)
            logger.info(f"Enabled smart interpolation for user: {user_id}")
    
    def disable_for_user(self, user_id: str) -> None:
        """Disable smart interpolation for specific user"""
        if user_id in self._config.enabled_user_ids:
            self._config.enabled_user_ids.remove(user_id)
            logger.info(f"Disabled smart interpolation for user: {user_id}")
    
    def set_enabled_percentage(self, percentage: float) -> None:
        """Set percentage of users enabled (0-100)"""
        if 0 <= percentage <= 100:
            self._config.enabled_percentage = percentage
            logger.info(f"Set enabled percentage to: {percentage}%")
        else:
            logger.error(f"Invalid percentage: {percentage}, must be 0-100")
    
    def enable_feature(self, feature: str) -> None:
        """Enable a specific feature"""
        if feature == 'smart_interpolation':
            self._config.enable_smart_interpolation = True
        elif feature == 'on_demand':
            self._config.enable_on_demand_computation = True
        elif feature == 'corrections':
            self._config.enable_astronomical_corrections = True
        elif feature == 'background_tasks':
            self._config.enable_background_tasks = True
        else:
            logger.warning(f"Unknown feature: {feature}")
    
    def disable_feature(self, feature: str) -> None:
        """Disable a specific feature"""
        if feature == 'smart_interpolation':
            self._config.enable_smart_interpolation = False
        elif feature == 'on_demand':
            self._config.enable_on_demand_computation = False
        elif feature == 'corrections':
            self._config.enable_astronomical_corrections = False
        elif feature == 'background_tasks':
            self._config.enable_background_tasks = False
        else:
            logger.warning(f"Unknown feature: {feature}")


# Global configuration manager instance
_config_manager = None


def get_config_manager() -> InterpolationConfigManager:
    """Get global configuration manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = InterpolationConfigManager()
    return _config_manager


def get_interpolation_config() -> SmartInterpolationConfig:
    """Get current interpolation configuration"""
    return get_config_manager().get_config()


def is_smart_interpolation_enabled(user_id: str = 'anonymous') -> bool:
    """Check if smart interpolation is enabled for user"""
    config = get_interpolation_config()
    return config.should_use_smart_interpolation(user_id)


def get_interpolation_strategy(user_id: str = 'anonymous') -> InterpolationStrategy:
    """Get interpolation strategy for user"""
    config = get_interpolation_config()
    return config.get_strategy_for_user(user_id)


# Convenience functions for common operations
def enable_smart_interpolation_for_all():
    """Enable smart interpolation for all users"""
    manager = get_config_manager()
    manager.update_config({'enable_smart_interpolation': True, 'enabled_percentage': 100.0})


def disable_smart_interpolation():
    """Disable smart interpolation completely"""
    manager = get_config_manager()
    manager.update_config({'enable_smart_interpolation': False})


def enable_for_percentage(percentage: float):
    """Enable smart interpolation for percentage of users"""
    manager = get_config_manager()
    manager.set_enabled_percentage(percentage)


def reload_interpolation_config():
    """Reload configuration from environment"""
    manager = get_config_manager()
    manager.reload_config()
