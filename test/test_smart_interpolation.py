"""
Tests for Smart Interpolation System
====================================

Comprehensive test suite for the smart interpolation framework,
including unit tests, integration tests, and performance tests.

Features:
- Unit tests for core interpolation logic
- Integration tests with API routes
- Performance benchmarks
- Error handling validation
- Configuration testing
"""

import pytest
import time
import logging
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List

# Import modules to test
from api.smart_interpolation import (
    SmartInterpolationConfig,
    load_asteroids_with_smart_interpolation,
    load_comets_with_smart_interpolation,
    get_interpolation_config,
    reload_interpolation_config
)
from api.on_demand_computation import (
    OnDemandComputationService,
    ComputationStatus,
    compute_asteroid_bucket_on_demand,
    compute_comet_bucket_on_demand
)
from api.astronomical_corrections import (
    AstronomicalCorrector,
    CorrectionResult,
    apply_astronomical_corrections
)
from config.interpolation_config import (
    InterpolationConfigManager,
    SmartInterpolationConfig as Config,
    InterpolationStrategy,
    CorrectionLevel
)

logger = logging.getLogger(__name__)


class TestSmartInterpolationConfig:
    """Test configuration management"""
    
    def test_default_config(self):
        """Test default configuration values"""
        config = SmartInterpolationConfig()
        assert isinstance(config.enabled, bool)
        assert isinstance(config.on_demand_enabled, bool)
        assert isinstance(config.max_future_hours, float)
        assert config.max_future_hours >= 0
    
    @patch.dict('os.environ', {
        'ENABLE_SMART_INTERPOLATION': 'true',
        'INTERPOLATION_MAX_FUTURE_HOURS': '5.0',
        'INTERPOLATION_STRATEGY': 'smart_interpolation'
    })
    def test_environment_config(self):
        """Test configuration from environment variables"""
        config = SmartInterpolationConfig()
        assert config.enabled is True
        assert config.max_future_hours == 5.0
        assert config.strategy == InterpolationStrategy.SMART_INTERPOLATION
    
    def test_config_validation(self):
        """Test configuration validation"""
        with patch.dict('os.environ', {'INTERPOLATION_MAX_FUTURE_HOURS': '-1'}):
            config = SmartInterpolationConfig()
            assert config.max_future_hours >= 0  # Should be corrected to valid value


class TestOnDemandComputation:
    """Test on-demand computation service"""
    
    @pytest.fixture
    def computation_service(self):
        """Create computation service for testing"""
        config = Mock()
        config.enabled = True
        config.cache_ttl = 3600
        config.max_computation_time = 30.0
        config.max_magnitude_asteroids = 20.0
        config.max_comets = 1000
        
        service = OnDemandComputationService(config)
        return service
    
    def test_service_initialization(self, computation_service):
        """Test service initialization"""
        assert computation_service.config.enabled is True
        assert computation_service.metrics.total_computations == 0
    
    @patch('api.on_demand_computation.bright_asteroids.load_bright_asteroids')
    def test_asteroid_computation_success(self, mock_load, computation_service):
        """Test successful asteroid computation"""
        # Mock asteroid data
        mock_asteroids = [
            {'name': 'Ceres', 'altitude': 45.0, 'azimuth': 180.0, 'magnitude': 8.5},
            {'name': 'Vesta', 'altitude': 30.0, 'azimuth': 90.0, 'magnitude': 9.2}
        ]
        mock_load.return_value = mock_asteroids
        
        # Test computation
        result = computation_service.compute_asteroid_bucket(
            lat=52.5, lon=13.4, elevation=50, 
            dt_utc=datetime.now(timezone.utc)
        )
        
        assert result.status == ComputationStatus.SUCCESS
        assert len(result.objects) == 2
        assert result.computation_time > 0
        assert result.cache_hit is False
    
    @patch('api.on_demand_computation.comets.load_comets')
    def test_comet_computation_success(self, mock_load, computation_service):
        """Test successful comet computation"""
        # Mock comet data
        mock_comets = [
            {'name': 'Halley', 'altitude': 60.0, 'azimuth': 270.0, 'magnitude': 12.0}
        ]
        mock_load.return_value = mock_comets
        
        # Test computation
        result = computation_service.compute_comet_bucket(
            lat=52.5, lon=13.4, elevation=50,
            dt_utc=datetime.now(timezone.utc)
        )
        
        assert result.status == ComputationStatus.SUCCESS
        assert len(result.objects) == 1
        assert result.objects[0]['name'] == 'Halley'
    
    @patch('api.on_demand_computation.bright_asteroids.load_bright_asteroids')
    def test_computation_failure(self, mock_load, computation_service):
        """Test computation failure handling"""
        mock_load.side_effect = Exception("Computation failed")
        
        result = computation_service.compute_asteroid_bucket(
            lat=52.5, lon=13.4, elevation=50,
            dt_utc=datetime.now(timezone.utc)
        )
        
        assert result.status == ComputationStatus.FAILED
        assert result.objects is None
        assert result.error_message is not None
    
    def test_cache_functionality(self, computation_service):
        """Test caching functionality"""
        dt = datetime.now(timezone.utc)
        
        # First computation should cache result
        with patch.object(computation_service, '_compute_asteroids_sync') as mock_compute:
            mock_compute.return_value = [{'name': 'Test', 'altitude': 45.0}]
            
            result1 = computation_service.compute_asteroid_bucket(52.5, 13.4, 50, dt)
            result2 = computation_service.compute_asteroid_bucket(52.5, 13.4, 50, dt)
            
            # Second call should hit cache
            assert result1.cache_hit is False
            assert result2.cache_hit is True
            # Should only call compute once
            mock_compute.assert_called_once()
    
    def test_metrics_tracking(self, computation_service):
        """Test performance metrics tracking"""
        with patch.object(computation_service, '_compute_asteroids_sync') as mock_compute:
            mock_compute.return_value = [{'name': 'Test', 'altitude': 45.0}]
            
            # Perform multiple computations
            for i in range(3):
                computation_service.compute_asteroid_bucket(
                    52.5 + i, 13.4, 50, 
                    datetime.now(timezone.utc) + timedelta(hours=i)
                )
            
            metrics = computation_service.get_metrics()
            assert metrics.total_computations == 3
            assert metrics.successful_computations == 3
            assert metrics.average_computation_time > 0


class TestAstronomicalCorrections:
    """Test astronomical correction system"""
    
    @pytest.fixture
    def corrector(self):
        """Create astronomical corrector for testing"""
        config = Mock()
        config.enable_horizon_correction = True
        config.enable_magnitude_smoothing = True
        config.enable_time_recalculation = True
        config.enable_position_validation = True
        config.horizon_threshold = 0.5
        config.magnitude_smoothing_factor = 0.3
        config.max_interpolation_error = 2.0
        
        return AstronomicalCorrector(config)
    
    def test_corrector_initialization(self, corrector):
        """Test corrector initialization"""
        assert corrector.config.enable_horizon_correction is True
        assert corrector.config.enable_magnitude_smoothing is True
    
    def test_horizon_crossing_detection(self, corrector):
        """Test horizon crossing detection"""
        # Test rising event
        event = corrector._detect_horizon_event(-5.0, 10.0, 0.5)
        assert event.event_type.value == "rising"
        assert event.confidence > 0
        
        # Test setting event
        event = corrector._detect_horizon_event(10.0, -5.0, 0.5)
        assert event.event_type.value == "setting"
        assert event.confidence > 0
        
        # Test no event
        event = corrector._detect_horizon_event(30.0, 35.0, 0.5)
        assert event.event_type.value == "no_event"
    
    def test_magnitude_smoothing(self, corrector):
        """Test magnitude smoothing"""
        # Test normal smoothing
        smoothed = corrector._smooth_nonlinear(8.0, 9.0, 0.5, 0.3)
        assert 8.0 <= smoothed <= 9.0
        
        # Test large change smoothing
        smoothed = corrector._smooth_nonlinear(8.0, 15.0, 0.5, 0.3)
        assert smoothed != 11.5  # Should be different from linear interpolation
    
    def test_position_validation(self, corrector):
        """Test position validation and correction"""
        obj = {'name': 'Test', 'altitude': 95.0, 'azimuth': 370.0}  # Invalid values
        list1 = [{'name': 'Test', 'altitude': 45.0, 'azimuth': 180.0}]
        list2 = [{'name': 'Test', 'altitude': 50.0, 'azimuth': 190.0}]
        
        result = corrector._validate_and_correct_position(
            obj, list1, list2, 0.5, 
            datetime.now(timezone.utc),
            {'latitude': 52.5, 'longitude': 13.4, 'elevation': 50}
        )
        
        assert result.corrected_object['altitude'] <= 90  # Should be clamped
        assert 0 <= result.corrected_object['azimuth'] < 360  # Should be normalized
        assert 'altitude_bounds_correction' in result.applied_corrections
        assert 'azimuth_normalization' in result.applied_corrections
    
    def test_full_correction_pipeline(self, corrector):
        """Test complete correction pipeline"""
        obj = {'name': 'Test', 'altitude': 45.0, 'azimuth': 180.0, 'magnitude': 8.5}
        list1 = [{'name': 'Test', 'altitude': 40.0, 'azimuth': 175.0, 'magnitude': 8.0}]
        list2 = [{'name': 'Test', 'altitude': 50.0, 'azimuth': 185.0, 'magnitude': 9.0}]
        
        result = corrector.correct_interpolated_object(
            obj, list1, list2, 0.5,
            datetime.now(timezone.utc),
            {'latitude': 52.5, 'longitude': 13.4, 'elevation': 50}
        )
        
        assert isinstance(result, CorrectionResult)
        assert result.correction_quality > 0
        assert len(result.applied_corrections) > 0


class TestInterpolationConfigManager:
    """Test configuration manager"""
    
    @pytest.fixture
    def config_manager(self):
        """Create config manager for testing"""
        return InterpolationConfigManager()
    
    def test_config_manager_initialization(self, config_manager):
        """Test config manager initialization"""
        config = config_manager.get_config()
        assert isinstance(config, Config)
        assert hasattr(config, 'enable_smart_interpolation')
    
    def test_config_update(self, config_manager):
        """Test configuration updates"""
        updates = {
            'enable_smart_interpolation': True,
            'max_future_hours': 3.0,
            'enabled_percentage': 25.0
        }
        
        config_manager.update_config(updates)
        config = config_manager.get_config()
        
        assert config.enable_smart_interpolation is True
        assert config.max_future_hours == 3.0
        assert config.enabled_percentage == 25.0
    
    def test_user_enablement(self, config_manager):
        """Test user-specific enablement"""
        user_id = 'test_user_123'
        
        # Initially disabled
        assert config_manager.get_config().is_enabled_for_user(user_id) is False
        
        # Enable for user
        config_manager.enable_for_user(user_id)
        assert config_manager.get_config().is_enabled_for_user(user_id) is True
        
        # Disable for user
        config_manager.disable_for_user(user_id)
        assert config_manager.get_config().is_enabled_for_user(user_id) is False
    
    def test_percentage_enablement(self, config_manager):
        """Test percentage-based enablement"""
        config_manager.set_enabled_percentage(50.0)
        
        # Test multiple users - should be roughly 50% enabled
        enabled_count = 0
        total_tests = 100
        
        for i in range(total_tests):
            user_id = f'test_user_{i}'
            if config_manager.get_config().is_enabled_for_user(user_id):
                enabled_count += 1
        
        # Should be close to 50% (allow some variance)
        assert 40 <= enabled_count <= 60


class TestIntegration:
    """Integration tests for the complete system"""
    
    @patch('api.smart_interpolation.bright_asteroids.load_bright_asteroids')
    @patch('api.smart_interpolation.comets.load_comets')
    def test_smart_interpolation_integration(self, mock_comets, mock_asteroids):
        """Test complete smart interpolation integration"""
        # Mock data
        mock_asteroids.return_value = [
            {'name': 'Ceres', 'altitude': 45.0, 'azimuth': 180.0, 'magnitude': 8.5}
        ]
        mock_comets.return_value = [
            {'name': 'Halley', 'altitude': 60.0, 'azimuth': 270.0, 'magnitude': 12.0}
        ]
        
        # Enable smart interpolation
        with patch.dict('os.environ', {'ENABLE_SMART_INTERPOLATION': 'true'}):
            reload_interpolation_config()
            
            dt = datetime.now(timezone.utc)
            
            # Test asteroid interpolation
            asteroids = load_asteroids_with_smart_interpolation(
                52.5, 13.4, 50, dt, 1, 86400, True
            )
            assert asteroids is not None
            assert len(asteroids) == 1
            
            # Test comet interpolation
            comets = load_comets_with_smart_interpolation(
                52.5, 13.4, 50, dt, 1, 86400, True
            )
            assert comets is not None
            assert len(comets) == 1
    
    def test_fallback_to_nearest_bucket(self):
        """Test fallback to nearest bucket when smart interpolation disabled"""
        with patch.dict('os.environ', {'ENABLE_SMART_INTERPOLATION': 'false'}):
            reload_interpolation_config()
            
            # Should fallback to original implementation
            with patch('api.cache_interpolation.load_asteroids_with_interpolation') as mock_load:
                mock_load.return_value = [{'name': 'Test', 'altitude': 45.0}]
                
                asteroids = load_asteroids_with_smart_interpolation(
                    52.5, 13.4, 50, datetime.now(timezone.utc), 1, 86400, True
                )
                
                assert asteroids is not None
                mock_load.assert_called_once()


class TestPerformance:
    """Performance tests for the interpolation system"""
    
    def test_computation_performance(self):
        """Test computation performance benchmarks"""
        service = OnDemandComputationService()
        
        # Mock computation with realistic timing
        def mock_compute(*args, **kwargs):
            time.sleep(0.1)  # Simulate 100ms computation
            return [{'name': 'Test', 'altitude': 45.0}]
        
        with patch.object(service, '_compute_asteroids_sync', side_effect=mock_compute):
            start_time = time.time()
            result = service.compute_asteroid_bucket(
                52.5, 13.4, 50, datetime.now(timezone.utc)
            )
            end_time = time.time()
            
            assert result.status == ComputationStatus.SUCCESS
            assert result.computation_time >= 0.1
            assert end_time - start_time >= 0.1
    
    def test_cache_performance(self):
        """Test cache performance under load"""
        service = OnDemandComputationService()
        dt = datetime.now(timezone.utc)
        
        with patch.object(service, '_compute_asteroids_sync') as mock_compute:
            mock_compute.return_value = [{'name': 'Test', 'altitude': 45.0}]
            
            # First call - should compute
            start_time = time.time()
            service.compute_asteroid_bucket(52.5, 13.4, 50, dt)
            first_call_time = time.time() - start_time
            
            # Second call - should hit cache
            start_time = time.time()
            result = service.compute_asteroid_bucket(52.5, 13.4, 50, dt)
            second_call_time = time.time() - start_time
            
            assert result.cache_hit is True
            assert second_call_time < first_call_time  # Cache should be faster


# Test fixtures and utilities
@pytest.fixture
def sample_asteroid_data():
    """Sample asteroid data for testing"""
    return [
        {
            'name': 'Ceres',
            'altitude': 45.0,
            'azimuth': 180.0,
            'magnitude': 8.5,
            'distance': 2.5,
            'ra': 180.0,
            'dec': 10.0,
            'type': 'asteroid',
            'symbol': '⚸'
        },
        {
            'name': 'Vesta',
            'altitude': 30.0,
            'azimuth': 90.0,
            'magnitude': 9.2,
            'distance': 1.8,
            'ra': 120.0,
            'dec': 5.0,
            'type': 'asteroid',
            'symbol': '⚸'
        }
    ]


@pytest.fixture
def sample_comet_data():
    """Sample comet data for testing"""
    return [
        {
            'name': 'Halley',
            'altitude': 60.0,
            'azimuth': 270.0,
            'magnitude': 12.0,
            'distance': 5.2,
            'ra': 240.0,
            'dec': -15.0,
            'type': 'comet',
            'symbol': '☄'
        }
    ]


@pytest.fixture
def sample_location():
    """Sample location for testing"""
    return {
        'latitude': 52.5,
        'longitude': 13.4,
        'elevation': 50
    }


if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v', '--tb=short'])
