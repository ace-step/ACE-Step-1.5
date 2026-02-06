"""
Feature Flag System for ACE-Step

Controls visibility of experimental, WIP, or platform-specific features.
Flags can be controlled via environment variables or configuration file.
"""

import os
from enum import Enum
from typing import Dict, Optional
from loguru import logger


class Feature(Enum):
    """Available feature flags"""
    
    # LoRA Training - Currently broken/WIP
    # Issue: Tensor generation runs 10+ hours with GPU at 30% utilization
    LORA_TRAINING = "lora_training"
    
    # Advanced editing features
    ADVANCED_EDITING = "advanced_editing"
    
    # Batch generation
    BATCH_GENERATION = "batch_generation"
    
    # Experimental features
    EXPERIMENTAL_SCORING = "experimental_scoring"
    
    # API features
    API_TRAINING_ENDPOINTS = "api_training_endpoints"


class FeatureFlags:
    """
    Feature flag manager.
    
    Priority order for flag resolution:
    1. Environment variable (ACESTEP_FEATURE_{NAME})
    2. Runtime override
    3. Default value
    """
    
    # Default feature states
    _DEFAULT_FLAGS: Dict[Feature, bool] = {
        Feature.LORA_TRAINING: False,  # Hidden until working
        Feature.ADVANCED_EDITING: True,
        Feature.BATCH_GENERATION: True,
        Feature.EXPERIMENTAL_SCORING: True,
        Feature.API_TRAINING_ENDPOINTS: False,  # Hidden until LoRA training works
    }
    
    # Runtime overrides (for testing/development)
    _overrides: Dict[Feature, bool] = {}
    
    @classmethod
    def is_enabled(cls, feature: Feature) -> bool:
        """
        Check if a feature is enabled.
        
        Args:
            feature: Feature to check
            
        Returns:
            True if feature is enabled, False otherwise
        """
        # Check for runtime override first
        if feature in cls._overrides:
            return cls._overrides[feature]
        
        # Check environment variable
        env_var = f"ACESTEP_FEATURE_{feature.value.upper()}"
        env_value = os.environ.get(env_var)
        if env_value is not None:
            enabled = env_value.lower() in ("true", "1", "yes", "on")
            logger.debug(f"Feature {feature.value} resolved from env: {enabled}")
            return enabled
        
        # Fall back to default
        default = cls._DEFAULT_FLAGS.get(feature, False)
        logger.debug(f"Feature {feature.value} using default: {default}")
        return default
    
    @classmethod
    def enable(cls, feature: Feature) -> None:
        """
        Enable a feature at runtime.
        
        Args:
            feature: Feature to enable
        """
        cls._overrides[feature] = True
        logger.info(f"Feature {feature.value} enabled at runtime")
    
    @classmethod
    def disable(cls, feature: Feature) -> None:
        """
        Disable a feature at runtime.
        
        Args:
            feature: Feature to disable
        """
        cls._overrides[feature] = False
        logger.info(f"Feature {feature.value} disabled at runtime")
    
    @classmethod
    def clear_overrides(cls) -> None:
        """Clear all runtime overrides."""
        cls._overrides.clear()
        logger.info("All feature flag overrides cleared")
    
    @classmethod
    def get_all_flags(cls) -> Dict[str, bool]:
        """
        Get current state of all feature flags.
        
        Returns:
            Dictionary mapping feature names to their current state
        """
        return {
            feature.value: cls.is_enabled(feature)
            for feature in Feature
        }
    
    @classmethod
    def get_disabled_features_message(cls) -> Optional[str]:
        """
        Generate a user-friendly message about disabled features.
        
        Returns:
            Message string if any features are disabled, None otherwise
        """
        disabled = [
            feature for feature in Feature
            if not cls.is_enabled(feature)
        ]
        
        if not disabled:
            return None
        
        messages = {
            Feature.LORA_TRAINING: (
                "LoRA Training is currently disabled. "
                "This feature is under active development and not yet stable. "
                "Enable with ACESTEP_FEATURE_LORA_TRAINING=true if you want to experiment."
            ),
            Feature.API_TRAINING_ENDPOINTS: (
                "Training API endpoints are disabled. "
                "These will be enabled once LoRA training is stable."
            ),
        }
        
        lines = ["The following features are currently disabled:"]
        for feature in disabled:
            if feature in messages:
                lines.append(f"\n• {feature.value}: {messages[feature]}")
        
        return "\n".join(lines) if len(lines) > 1 else None


def is_feature_enabled(feature: Feature) -> bool:
    """
    Convenience function to check if a feature is enabled.
    
    Args:
        feature: Feature to check
        
    Returns:
        True if feature is enabled, False otherwise
    """
    return FeatureFlags.is_enabled(feature)
