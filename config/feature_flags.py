"""
Feature Flags System für RabbitMQ-Migration
Ermöglicht schrittweises Rollout ohne Code-Änderungen
"""
import os
import hashlib
import random
from enum import Enum
from typing import Optional


class FeatureFlag(Enum):
    """Feature Flags für schrittweise Migration"""
    USE_RABBITMQ = "USE_RABBITMQ"
    USE_RABBITMQ_ASTEROIDS = "USE_RABBITMQ_ASTEROIDS"
    USE_RABBITMQ_COMETS = "USE_RABBITMQ_COMETS"
    USE_RABBITMQ_CELESTIAL = "USE_RABBITMQ_CELESTIAL"
    USE_RABBITMQ_CONSTELLATIONS = "USE_RABBITMQ_CONSTELLATIONS"
    RABBITMQ_PERCENTAGE = "RABBITMQ_PERCENTAGE"  # 0-100


class FeatureFlags:
    """Zentrale Feature Flag Verwaltung"""
    
    @staticmethod
    def is_enabled(flag: FeatureFlag) -> bool:
        """
        Prüft ob Feature Flag aktiviert ist
        
        Args:
            flag: Feature Flag Enum
            
        Returns:
            True wenn aktiviert, sonst False
        """
        env_value = os.environ.get(flag.value, "false").lower()
        return env_value in ("true", "1", "yes", "on")
    
    @staticmethod
    def get_percentage(flag: FeatureFlag) -> int:
        """
        Gibt Prozentsatz für graduelle Rollouts zurück
        
        Args:
            flag: Feature Flag Enum
            
        Returns:
            Prozentsatz (0-100)
        """
        try:
            value = int(os.environ.get(flag.value, "0"))
            return max(0, min(100, value))  # Clamp zwischen 0 und 100
        except ValueError:
            return 0
    
    @staticmethod
    def should_use_rabbitmq(user_id: Optional[str] = None) -> bool:
        """
        Entscheidet ob RabbitMQ verwendet werden soll.
        Unterstützt graduelles Rollout basierend auf User-ID Hash.
        
        Args:
            user_id: Optional User-ID für konsistentes Routing
            
        Returns:
            True wenn RabbitMQ verwendet werden soll
        """
        # Globaler Flag
        if not FeatureFlags.is_enabled(FeatureFlag.USE_RABBITMQ):
            return False
        
        # Prozentbasiertes Rollout
        percentage = FeatureFlags.get_percentage(FeatureFlag.RABBITMQ_PERCENTAGE)
        if percentage == 0:
            return False
        if percentage >= 100:
            return True
        
        # Hash-basierte Verteilung (konsistent pro User)
        if user_id:
            hash_value = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
            return (hash_value % 100) < percentage
        
        # Fallback: Random (nicht konsistent, aber funktioniert)
        return random.randint(0, 99) < percentage
    
    @staticmethod
    def should_use_rabbitmq_for_type(data_type: str, user_id: Optional[str] = None) -> bool:
        """
        Entscheidet ob RabbitMQ für einen bestimmten Datentyp verwendet werden soll
        
        Args:
            data_type: 'asteroids', 'comets', 'celestial', 'constellations'
            user_id: Optional User-ID
            
        Returns:
            True wenn RabbitMQ für diesen Typ verwendet werden soll
        """
        # Erst globalen RabbitMQ-Flag prüfen
        if not FeatureFlags.should_use_rabbitmq(user_id):
            return False
        
        # Dann typ-spezifischen Flag prüfen
        flag_map = {
            'asteroids': FeatureFlag.USE_RABBITMQ_ASTEROIDS,
            'comets': FeatureFlag.USE_RABBITMQ_COMETS,
            'celestial': FeatureFlag.USE_RABBITMQ_CELESTIAL,
            'constellations': FeatureFlag.USE_RABBITMQ_CONSTELLATIONS,
        }
        
        flag = flag_map.get(data_type.lower())
        if flag is None:
            return False
        
        return FeatureFlags.is_enabled(flag)


# Globale Instanz für einfachen Zugriff
feature_flags = FeatureFlags()


# Convenience Functions
def use_rabbitmq(user_id: Optional[str] = None) -> bool:
    """Shortcut für should_use_rabbitmq"""
    return feature_flags.should_use_rabbitmq(user_id)


def use_rabbitmq_for(data_type: str, user_id: Optional[str] = None) -> bool:
    """Shortcut für should_use_rabbitmq_for_type"""
    return feature_flags.should_use_rabbitmq_for_type(data_type, user_id)
