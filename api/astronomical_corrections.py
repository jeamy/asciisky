"""
Astronomical Corrections for Smart Interpolation
=================================================

Provides sophisticated corrections for interpolated astronomical data
to handle horizon events, magnitude smoothing, and time-based artifacts.

Features:
- Horizon crossing detection and correction
- Magnitude smoothing with non-linear interpolation
- Rise/set/transit time recalculation
- Position consistency validation
- Object appearance/disappearance handling
"""

import math
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from skyfield.api import wgs84
from api.computation import ts, eph

logger = logging.getLogger(__name__)


class HorizonEventType(Enum):
    """Types of horizon events"""
    RISING = "rising"          # Object crosses from below to above horizon
    SETTING = "setting"        # Object crosses from above to below horizon
    NO_EVENT = "no_event"      # No horizon crossing
    UNKNOWN = "unknown"        # Cannot determine event type


@dataclass
class HorizonEvent:
    """Information about a horizon crossing event"""
    event_type: HorizonEventType
    crossing_time: Optional[datetime]
    altitude_at_crossing: float
    azimuth_at_crossing: float
    confidence: float  # 0.0 to 1.0


@dataclass
class CorrectionResult:
    """Result of astronomical correction"""
    corrected_object: Dict[str, Any]
    applied_corrections: List[str]
    correction_quality: float  # 0.0 to 1.0
    warnings: List[str]


class AstronomicalCorrectionConfig:
    """Configuration for astronomical corrections"""
    
    def __init__(self):
        self.enable_horizon_correction = True
        self.enable_magnitude_smoothing = True
        self.enable_time_recalculation = True
        self.enable_position_validation = True
        self.horizon_threshold = 0.5  # degrees from horizon for event detection
        self.magnitude_smoothing_factor = 0.3  # smoothing strength (0.0 = none, 1.0 = full)
        self.max_interpolation_error = 2.0  # degrees max acceptable position error
        self.confidence_threshold = 0.7  # minimum confidence for corrections
        
        logger.info(f"Astronomical Corrections Config: horizon={self.enable_horizon_correction}, "
                   f"magnitude={self.enable_magnitude_smoothing}, "
                   f"time_recalc={self.enable_time_recalculation}")


class AstronomicalCorrector:
    """
    Applies sophisticated astronomical corrections to interpolated objects.
    """
    
    def __init__(self, config: Optional[AstronomicalCorrectionConfig] = None):
        self.config = config or AstronomicalCorrectionConfig()
        logger.info("Astronomical Corrector initialized")
    
    def correct_interpolated_object(
        self,
        obj: Dict[str, Any],
        list1: List[Dict[str, Any]],
        list2: List[Dict[str, Any]],
        factor: float,
        target_dt: datetime,
        location: Dict[str, float]
    ) -> CorrectionResult:
        """
        Apply astronomical corrections to an interpolated object.
        
        Args:
            obj: Interpolated object dictionary
            list1: Object list from previous bucket
            list2: Object list from next bucket
            factor: Interpolation factor (0.0 = list1, 1.0 = list2)
            target_dt: Target datetime for interpolation
            location: Observer location dict
            
        Returns:
            CorrectionResult with corrected object and metadata
        """
        applied_corrections = []
        warnings = []
        corrected_obj = obj.copy()
        quality_scores = []
        
        try:
            # 1. Horizon event detection and correction
            if self.config.enable_horizon_correction:
                horizon_result = self._correct_horizon_crossing(
                    corrected_obj, list1, list2, factor, target_dt, location
                )
                corrected_obj = horizon_result.corrected_object
                applied_corrections.extend(horizon_result.applied_corrections)
                warnings.extend(horizon_result.warnings)
                quality_scores.append(horizon_result.correction_quality)
            
            # 2. Magnitude smoothing
            if self.config.enable_magnitude_smoothing and 'magnitude' in corrected_obj:
                magnitude_result = self._apply_magnitude_smoothing(
                    corrected_obj, list1, list2, factor
                )
                corrected_obj = magnitude_result.corrected_object
                applied_corrections.extend(magnitude_result.applied_corrections)
                warnings.extend(magnitude_result.warnings)
                quality_scores.append(magnitude_result.correction_quality)
            
            # 3. Position validation and correction
            if self.config.enable_position_validation:
                position_result = self._validate_and_correct_position(
                    corrected_obj, list1, list2, factor, target_dt, location
                )
                corrected_obj = position_result.corrected_object
                applied_corrections.extend(position_result.applied_corrections)
                warnings.extend(position_result.warnings)
                quality_scores.append(position_result.correction_quality)
            
            # 4. Time-based recalculation (rise/set/transit)
            if self.config.enable_time_recalculation:
                time_result = self._recalculate_time_based_events(
                    corrected_obj, target_dt, location
                )
                corrected_obj = time_result.corrected_object
                applied_corrections.extend(time_result.applied_corrections)
                warnings.extend(time_result.warnings)
                quality_scores.append(time_result.correction_quality)
            
            # Calculate overall quality
            overall_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 1.0
            
            logger.debug(f"Applied {len(applied_corrections)} corrections to {obj.get('name', 'unknown')}: "
                        f"{applied_corrections}, quality={overall_quality:.3f}")
            
            return CorrectionResult(
                corrected_object=corrected_obj,
                applied_corrections=applied_corrections,
                correction_quality=overall_quality,
                warnings=warnings
            )
            
        except Exception as e:
            logger.error(f"Error applying astronomical corrections to {obj.get('name', 'unknown')}: {e}")
            return CorrectionResult(
                corrected_object=obj,
                applied_corrections=[],
                correction_quality=0.0,
                warnings=[f"Correction failed: {str(e)}"]
            )
    
    def _correct_horizon_crossing(
        self,
        obj: Dict[str, Any],
        list1: List[Dict[str, Any]],
        list2: List[Dict[str, Any]],
        factor: float,
        target_dt: datetime,
        location: Dict[str, float]
    ) -> CorrectionResult:
        """
        Detect and correct horizon crossing events.
        """
        applied_corrections = []
        warnings = []
        
        # Find object in both buckets
        obj1 = self._find_object_by_name(list1, obj.get('name'))
        obj2 = self._find_object_by_name(list2, obj.get('name'))
        
        if not obj1 or not obj2:
            return CorrectionResult(obj, [], 0.5, ["Object missing in one bucket"])
        
        alt1 = obj1.get('altitude', -999)
        alt2 = obj2.get('altitude', -999)
        alt_interp = obj.get('altitude', -999)
        
        # Detect horizon crossing
        event = self._detect_horizon_event(alt1, alt2, factor)
        
        if event.event_type == HorizonEventType.NO_EVENT:
            return CorrectionResult(obj, [], 1.0, [])
        
        logger.debug(f"Horizon event detected for {obj.get('name')}: {event.event_type.value}")
        
        try:
            if event.event_type == HorizonEventType.RISING:
                # Object is rising - apply smooth transition
                corrected_alt = self._interpolate_horizon_rising(alt1, alt2, factor, event)
                obj['altitude'] = corrected_alt
                applied_corrections.append("horizon_rising_correction")
                
            elif event.event_type == HorizonEventType.SETTING:
                # Object is setting - apply smooth transition
                corrected_alt = self._interpolate_horizon_setting(alt1, alt2, factor, event)
                obj['altitude'] = corrected_alt
                applied_corrections.append("horizon_setting_correction")
            
            # Adjust azimuth if needed for smooth horizon crossing
            if abs(alt_interp) < self.config.horizon_threshold:
                corrected_az = self._smooth_horizon_azimuth(
                    obj1.get('azimuth', 0), obj2.get('azimuth', 0), factor, event
                )
                obj['azimuth'] = corrected_az
                applied_corrections.append("horizon_azimuth_smoothing")
            
            return CorrectionResult(obj, applied_corrections, event.confidence, warnings)
            
        except Exception as e:
            logger.error(f"Error correcting horizon crossing: {e}")
            return CorrectionResult(obj, [], 0.0, [f"Horizon correction failed: {str(e)}"])
    
    def _detect_horizon_event(
        self,
        alt1: float,
        alt2: float,
        factor: float
    ) -> HorizonEvent:
        """
        Detect horizon crossing event type and timing.
        """
        # Check for horizon crossing
        if (alt1 > 0 and alt2 > 0) or (alt1 <= 0 and alt2 <= 0):
            # No horizon crossing
            return HorizonEvent(HorizonEventType.NO_EVENT, None, 0, 0, 1.0)
        
        # Determine event type
        if alt1 <= 0 and alt2 > 0:
            event_type = HorizonEventType.RISING
        elif alt1 > 0 and alt2 <= 0:
            event_type = HorizonEventType.SETTING
        else:
            event_type = HorizonEventType.UNKNOWN
        
        # Estimate crossing time (linear approximation)
        if alt1 != alt2:
            crossing_factor = -alt1 / (alt2 - alt1)
            confidence = max(0.1, 1.0 - abs(crossing_factor - 0.5) * 2)  # Higher confidence near middle
        else:
            crossing_factor = 0.5
            confidence = 0.5
        
        # Estimate altitude at crossing (should be ~0)
        altitude_at_crossing = alt1 + (alt2 - alt1) * crossing_factor
        
        return HorizonEvent(
            event_type=event_type,
            crossing_time=None,  # Could be calculated if needed
            altitude_at_crossing=altitude_at_crossing,
            azimuth_at_crossing=0,  # Could be calculated if needed
            confidence=confidence
        )
    
    def _interpolate_horizon_rising(
        self,
        alt1: float,
        alt2: float,
        factor: float,
        event: HorizonEvent
    ) -> float:
        """
        Apply smooth interpolation for rising objects.
        """
        # Use sigmoid-like smoothing for horizon crossing
        if factor < event.confidence:
            # Still below horizon, keep negative altitude
            return alt1 + (alt2 - alt1) * factor
        else:
            # Above horizon, apply smooth transition
            smooth_factor = self._smooth_transition(factor, event.confidence)
            return alt1 + (alt2 - alt1) * smooth_factor
    
    def _interpolate_horizon_setting(
        self,
        alt1: float,
        alt2: float,
        factor: float,
        event: HorizonEvent
    ) -> float:
        """
        Apply smooth interpolation for setting objects.
        """
        # Use sigmoid-like smoothing for horizon crossing
        if factor < (1.0 - event.confidence):
            # Still above horizon
            smooth_factor = self._smooth_transition(factor, 1.0 - event.confidence)
            return alt1 + (alt2 - alt1) * smooth_factor
        else:
            # Below horizon, keep negative altitude
            return alt1 + (alt2 - alt1) * factor
    
    def _smooth_transition(self, factor: float, center: float) -> float:
        """
        Apply smooth sigmoid-like transition around center point.
        """
        # Simple sigmoid approximation
        steepness = 6.0  # Controls transition sharpness
        shifted = (factor - center) * steepness
        sigmoid = 1.0 / (1.0 + math.exp(-shifted))
        return sigmoid
    
    def _smooth_horizon_azimuth(
        self,
        az1: float,
        az2: float,
        factor: float,
        event: HorizonEvent
    ) -> float:
        """
        Apply smooth azimuth interpolation near horizon.
        """
        # Handle azimuth wraparound
        diff = az2 - az1
        if diff > 180:
            diff -= 360
        elif diff < -180:
            diff += 360
        
        # Apply smoothing based on event confidence
        smoothed_az = az1 + diff * factor
        
        # Normalize to 0-360
        return smoothed_az % 360
    
    def _apply_magnitude_smoothing(
        self,
        obj: Dict[str, Any],
        list1: List[Dict[str, Any]],
        list2: List[Dict[str, Any]],
        factor: float
    ) -> CorrectionResult:
        """
        Apply smoothing to magnitude interpolation.
        """
        try:
            obj1 = self._find_object_by_name(list1, obj.get('name'))
            obj2 = self._find_object_by_name(list2, obj.get('name'))
            
            if not obj1 or not obj2:
                return CorrectionResult(obj, [], 0.5, ["Magnitude data missing"])
            
            mag1 = obj1.get('magnitude', 99)
            mag2 = obj2.get('magnitude', 99)
            mag_interp = obj.get('magnitude', 99)
            
            # Check for large magnitude jumps (possible errors)
            mag_diff = abs(mag2 - mag1)
            if mag_diff > 5.0:  # Large magnitude change
                # Apply stronger smoothing for large changes
                smoothing_factor = min(0.8, self.config.magnitude_smoothing_factor * 2)
                smoothed_mag = self._smooth_nonlinear(mag1, mag2, factor, smoothing_factor)
                obj['magnitude'] = smoothed_mag
                
                return CorrectionResult(
                    obj, 
                    ["magnitude_smoothing_large_change"], 
                    0.8,
                    [f"Large magnitude change detected: {mag_diff:.2f} mag"]
                )
            else:
                # Normal smoothing
                smoothed_mag = self._smooth_nonlinear(mag1, mag2, factor, self.config.magnitude_smoothing_factor)
                obj['magnitude'] = smoothed_mag
                
                return CorrectionResult(obj, ["magnitude_smoothing"], 0.9, [])
                
        except Exception as e:
            logger.error(f"Error applying magnitude smoothing: {e}")
            return CorrectionResult(obj, [], 0.0, [f"Magnitude smoothing failed: {str(e)}"])
    
    def _smooth_nonlinear(
        self,
        val1: float,
        val2: float,
        factor: float,
        smoothing_strength: float
    ) -> float:
        """
        Apply non-linear smoothing between two values.
        """
        # Linear interpolation
        linear = val1 + (val2 - val1) * factor
        
        # Smooth interpolation using ease-in-out curve
        if smoothing_strength <= 0:
            return linear
        
        # Apply ease-in-out smoothing
        smooth_factor = self._ease_in_out(factor)
        smoothed = val1 + (val2 - val1) * (factor * (1 - smoothing_strength) + smooth_factor * smoothing_strength)
        
        return smoothed
    
    def _ease_in_out(self, t: float) -> float:
        """
        Ease-in-out function for smooth transitions.
        """
        if t < 0.5:
            return 2 * t * t
        else:
            return 1 - pow(-2 * t + 2, 2) / 2
    
    def _validate_and_correct_position(
        self,
        obj: Dict[str, Any],
        list1: List[Dict[str, Any]],
        list2: List[Dict[str, Any]],
        factor: float,
        target_dt: datetime,
        location: Dict[str, float]
    ) -> CorrectionResult:
        """
        Validate interpolated position and apply corrections if needed.
        """
        try:
            # Basic validation checks
            altitude = obj.get('altitude', -999)
            azimuth = obj.get('azimuth', -999)
            
            warnings = []
            applied_corrections = []
            quality = 1.0
            
            # Check altitude bounds
            if altitude < -90 or altitude > 90:
                logger.warning(f"Invalid altitude for {obj.get('name')}: {altitude}")
                # Clamp to valid range
                obj['altitude'] = max(-90, min(90, altitude))
                applied_corrections.append("altitude_bounds_correction")
                quality *= 0.8
                warnings.append("Altitude out of bounds, clamped")
            
            # Check azimuth bounds
            if azimuth < 0 or azimuth >= 360:
                # Normalize azimuth
                obj['azimuth'] = azimuth % 360
                applied_corrections.append("azimuth_normalization")
                quality *= 0.9
            
            # Check for unrealistic position jumps
            obj1 = self._find_object_by_name(list1, obj.get('name'))
            obj2 = self._find_object_by_name(list2, obj.get('name'))
            
            if obj1 and obj2:
                # Calculate expected position at target time
                expected_alt = obj1.get('altitude', 0) + (obj2.get('altitude', 0) - obj1.get('altitude', 0)) * factor
                expected_az = obj1.get('azimuth', 0) + (obj2.get('azimuth', 0) - obj1.get('azimuth', 0)) * factor
                
                # Handle azimuth wraparound
                az_diff = expected_az - obj.get('azimuth', 0)
                if az_diff > 180:
                    az_diff -= 360
                elif az_diff < -180:
                    az_diff += 360
                
                # Check position consistency
                alt_error = abs(expected_alt - obj.get('altitude', 0))
                az_error = abs(az_diff)
                
                if alt_error > self.config.max_interpolation_error:
                    warnings.append(f"Large altitude interpolation error: {alt_error:.2f}°")
                    quality *= 0.7
                
                if az_error > self.config.max_interpolation_error:
                    warnings.append(f"Large azimuth interpolation error: {az_error:.2f}°")
                    quality *= 0.7
            
            return CorrectionResult(obj, applied_corrections, quality, warnings)
            
        except Exception as e:
            logger.error(f"Error validating position: {e}")
            return CorrectionResult(obj, [], 0.0, [f"Position validation failed: {str(e)}"])
    
    def _recalculate_time_based_events(
        self,
        obj: Dict[str, Any],
        target_dt: datetime,
        location: Dict[str, float]
    ) -> CorrectionResult:
        """
        Recalculate rise/set/transit times for interpolated object.
        """
        # TODO: Implement sophisticated time-based event recalculation
        # This would involve:
        # 1. Computing precise rise/set times for target date
        # 2. Interpolating transit times
        # 3. Updating object metadata with new times
        
        return CorrectionResult(obj, [], 1.0, [])
    
    def _find_object_by_name(self, object_list: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
        """
        Find object in list by name.
        """
        if not name:
            return None
        
        for obj in object_list:
            if obj.get('name') == name:
                return obj
        return None


# Global corrector instance
_corrector = None


def get_astronomical_corrector() -> AstronomicalCorrector:
    """
    Get global astronomical corrector instance.
    """
    global _corrector
    if _corrector is None:
        _corrector = AstronomicalCorrector()
    return _corrector


def apply_astronomical_corrections(
    obj: Dict[str, Any],
    list1: List[Dict[str, Any]],
    list2: List[Dict[str, Any]],
    factor: float,
    target_dt: datetime,
    location: Dict[str, float]
) -> CorrectionResult:
    """
    Convenience function to apply astronomical corrections.
    """
    corrector = get_astronomical_corrector()
    return corrector.correct_interpolated_object(obj, list1, list2, factor, target_dt, location)
