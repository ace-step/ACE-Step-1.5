"""
GPU Configuration Module
Centralized GPU memory detection and adaptive configuration management

Debug Mode:
    Set environment variable MAX_CUDA_VRAM to simulate different GPU memory sizes.
    Example: MAX_CUDA_VRAM=8 python acestep  # Simulates 8GB GPU
    
    This is useful for testing GPU tier configurations on high-end hardware.
"""

import os
import sys
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from loguru import logger


# Environment variable for debugging/testing different GPU memory configurations
DEBUG_MAX_CUDA_VRAM_ENV = "MAX_CUDA_VRAM"


@dataclass
class GPUConfig:
    """GPU configuration based on available memory"""
    tier: str  # "tier1", "tier2", etc. or "unlimited"
    gpu_memory_gb: float
    
    # Duration limits (in seconds)
    max_duration_with_lm: int  # When LM is initialized
    max_duration_without_lm: int  # When LM is not initialized
    
    # Batch size limits
    max_batch_size_with_lm: int
    max_batch_size_without_lm: int
    
    # LM configuration
    init_lm_default: bool  # Whether to initialize LM by default
    available_lm_models: List[str]  # Available LM models for this tier
    
    # LM memory allocation (GB) for each model size
    lm_memory_gb: Dict[str, float]  # e.g., {"0.6B": 3, "1.7B": 8, "4B": 12}


# GPU tier configurations
GPU_TIER_CONFIGS = {
    "tier1": {  # <= 4GB
        "max_duration_with_lm": 180,  # 3 minutes
        "max_duration_without_lm": 180,  # 3 minutes
        "max_batch_size_with_lm": 1,
        "max_batch_size_without_lm": 1,
        "init_lm_default": False,
        "available_lm_models": [],
        "lm_memory_gb": {},
    },
    "tier2": {  # 4-6GB
        "max_duration_with_lm": 360,  # 6 minutes
        "max_duration_without_lm": 360,  # 6 minutes
        "max_batch_size_with_lm": 1,
        "max_batch_size_without_lm": 1,
        "init_lm_default": False,
        "available_lm_models": [],
        "lm_memory_gb": {},
    },
    "tier3": {  # 6-8GB
        "max_duration_with_lm": 240,  # 4 minutes with LM
        "max_duration_without_lm": 360,  # 6 minutes without LM
        "max_batch_size_with_lm": 2,
        "max_batch_size_without_lm": 2,
        "init_lm_default": False,  # Don't init by default due to limited memory
        "available_lm_models": ["acestep-5Hz-lm-0.6B", "acestep-5Hz-lm-1.7B", "acestep-5Hz-lm-4B"],
        "lm_memory_gb": {"0.6B": 3, "1.7B": 8, "4B": 12},
    },
    "tier4": {  # 8-12GB
        "max_duration_with_lm": 240,  # 4 minutes with LM
        "max_duration_without_lm": 360,  # 6 minutes without LM
        "max_batch_size_with_lm": 2,
        "max_batch_size_without_lm": 4,
        "init_lm_default": False,  # Don't init by default
        "available_lm_models": ["acestep-5Hz-lm-0.6B", "acestep-5Hz-lm-1.7B", "acestep-5Hz-lm-4B"],
        "lm_memory_gb": {"0.6B": 3, "1.7B": 8, "4B": 12},
    },
    "tier5": {  # 12-16GB
        "max_duration_with_lm": 240,  # 4 minutes with LM
        "max_duration_without_lm": 360,  # 6 minutes without LM
        "max_batch_size_with_lm": 2,
        "max_batch_size_without_lm": 4,
        "init_lm_default": True,
        "available_lm_models": ["acestep-5Hz-lm-0.6B", "acestep-5Hz-lm-1.7B", "acestep-5Hz-lm-4B"],
        "lm_memory_gb": {"0.6B": 3, "1.7B": 8, "4B": 12},
    },
    "tier6": {  # 16-24GB
        "max_duration_with_lm": 480,  # 8 minutes
        "max_duration_without_lm": 480,  # 8 minutes
        "max_batch_size_with_lm": 4,
        "max_batch_size_without_lm": 8,
        "init_lm_default": True,
        "available_lm_models": ["acestep-5Hz-lm-0.6B", "acestep-5Hz-lm-1.7B", "acestep-5Hz-lm-4B"],
        "lm_memory_gb": {"0.6B": 3, "1.7B": 8, "4B": 12},
    },
    "unlimited": {  # >= 24GB
        "max_duration_with_lm": 600,  # 10 minutes (max supported)
        "max_duration_without_lm": 600,  # 10 minutes
        "max_batch_size_with_lm": 8,
        "max_batch_size_without_lm": 8,
        "init_lm_default": True,
        "available_lm_models": ["acestep-5Hz-lm-0.6B", "acestep-5Hz-lm-1.7B", "acestep-5Hz-lm-4B"],
        "lm_memory_gb": {"0.6B": 3, "1.7B": 8, "4B": 12},
    },
}


def get_gpu_memory_gb() -> float:
    """
    Get GPU memory in GB. Returns 0 if no GPU is available.
    
    Debug Mode:
        Set environment variable MAX_CUDA_VRAM to override the detected GPU memory.
        Example: MAX_CUDA_VRAM=8 python acestep  # Simulates 8GB GPU
        
        This allows testing different GPU tier configurations on high-end hardware.
    """
    # Check for debug override first
    debug_vram = os.environ.get(DEBUG_MAX_CUDA_VRAM_ENV)
    if debug_vram is not None:
        try:
            simulated_gb = float(debug_vram)
            logger.warning(f"⚠️ DEBUG MODE: Simulating GPU memory as {simulated_gb:.1f}GB (set via {DEBUG_MAX_CUDA_VRAM_ENV} environment variable)")
            return simulated_gb
        except ValueError:
            logger.warning(f"Invalid {DEBUG_MAX_CUDA_VRAM_ENV} value: {debug_vram}, ignoring")
    
    try:
        import torch
        if torch.cuda.is_available():
            # Get total memory of the first GPU in GB
            total_memory = torch.cuda.get_device_properties(0).total_memory
            memory_gb = total_memory / (1024**3)  # Convert bytes to GB
            return memory_gb
        elif hasattr(torch, 'xpu') and torch.xpu.is_available():
            # Get total memory of the first XPU in GB
            total_memory = torch.xpu.get_device_properties(0).total_memory
            memory_gb = total_memory / (1024**3)  # Convert bytes to GB
            return memory_gb
        else:
            return 0
    except Exception as e:
        logger.warning(f"Failed to detect GPU memory: {e}")
        return 0


def get_gpu_tier(gpu_memory_gb: float) -> str:
    """
    Determine GPU tier based on available memory.
    
    Args:
        gpu_memory_gb: GPU memory in GB
        
    Returns:
        Tier string: "tier1", "tier2", "tier3", "tier4", "tier5", "tier6", or "unlimited"
    """
    if gpu_memory_gb <= 0:
        # CPU mode - use tier1 limits
        return "tier1"
    elif gpu_memory_gb <= 4:
        return "tier1"
    elif gpu_memory_gb <= 6:
        return "tier2"
    elif gpu_memory_gb <= 8:
        return "tier3"
    elif gpu_memory_gb <= 12:
        return "tier4"
    elif gpu_memory_gb <= 16:
        return "tier5"
    elif gpu_memory_gb <= 24:
        return "tier6"
    else:
        return "unlimited"


def get_gpu_config(gpu_memory_gb: Optional[float] = None) -> GPUConfig:
    """
    Get GPU configuration based on detected or provided GPU memory.
    
    Args:
        gpu_memory_gb: GPU memory in GB. If None, will be auto-detected.
        
    Returns:
        GPUConfig object with all configuration parameters
    """
    if gpu_memory_gb is None:
        gpu_memory_gb = get_gpu_memory_gb()
    
    tier = get_gpu_tier(gpu_memory_gb)
    config = GPU_TIER_CONFIGS[tier]
    
    return GPUConfig(
        tier=tier,
        gpu_memory_gb=gpu_memory_gb,
        max_duration_with_lm=config["max_duration_with_lm"],
        max_duration_without_lm=config["max_duration_without_lm"],
        max_batch_size_with_lm=config["max_batch_size_with_lm"],
        max_batch_size_without_lm=config["max_batch_size_without_lm"],
        init_lm_default=config["init_lm_default"],
        available_lm_models=config["available_lm_models"],
        lm_memory_gb=config["lm_memory_gb"],
    )


def get_lm_model_size(model_path: str) -> str:
    """
    Extract LM model size from model path.
    
    Args:
        model_path: Model path string (e.g., "acestep-5Hz-lm-0.6B")
        
    Returns:
        Model size string: "0.6B", "1.7B", or "4B"
    """
    if "0.6B" in model_path:
        return "0.6B"
    elif "1.7B" in model_path:
        return "1.7B"
    elif "4B" in model_path:
        return "4B"
    else:
        # Default to smallest model assumption
        return "0.6B"


def get_lm_gpu_memory_ratio(model_path: str, total_gpu_memory_gb: float) -> Tuple[float, float]:
    """
    Calculate GPU memory utilization ratio for LM model.
    
    Args:
        model_path: LM model path (e.g., "acestep-5Hz-lm-0.6B")
        total_gpu_memory_gb: Total GPU memory in GB
        
    Returns:
        Tuple of (gpu_memory_utilization_ratio, target_memory_gb)
    """
    model_size = get_lm_model_size(model_path)
    
    # Target memory allocation for each model size
    target_memory = {
        "0.6B": 3.0,
        "1.7B": 8.0,
        "4B": 12.0,
    }
    
    target_gb = target_memory.get(model_size, 3.0)
    
    # For large GPUs (>=24GB), don't restrict memory too much
    if total_gpu_memory_gb >= 24:
        # Use a reasonable ratio that allows the model to run efficiently
        ratio = min(0.9, max(0.2, target_gb / total_gpu_memory_gb))
    else:
        # For smaller GPUs, strictly limit memory usage
        ratio = min(0.9, max(0.1, target_gb / total_gpu_memory_gb))
    
    return ratio, target_gb


def check_duration_limit(
    duration: float,
    gpu_config: GPUConfig,
    lm_initialized: bool
) -> Tuple[bool, str]:
    """
    Check if requested duration is within limits for current GPU configuration.
    
    Args:
        duration: Requested duration in seconds
        gpu_config: Current GPU configuration
        lm_initialized: Whether LM is initialized
        
    Returns:
        Tuple of (is_valid, warning_message)
    """
    max_duration = gpu_config.max_duration_with_lm if lm_initialized else gpu_config.max_duration_without_lm
    
    if duration > max_duration:
        warning_msg = (
            f"⚠️ Requested duration ({duration:.0f}s) exceeds the limit for your GPU "
            f"({gpu_config.gpu_memory_gb:.1f}GB). Maximum allowed: {max_duration}s "
            f"({'with' if lm_initialized else 'without'} LM). "
            f"Duration will be clamped to {max_duration}s."
        )
        return False, warning_msg
    
    return True, ""


def check_batch_size_limit(
    batch_size: int,
    gpu_config: GPUConfig,
    lm_initialized: bool
) -> Tuple[bool, str]:
    """
    Check if requested batch size is within limits for current GPU configuration.
    
    Args:
        batch_size: Requested batch size
        gpu_config: Current GPU configuration
        lm_initialized: Whether LM is initialized
        
    Returns:
        Tuple of (is_valid, warning_message)
    """
    max_batch_size = gpu_config.max_batch_size_with_lm if lm_initialized else gpu_config.max_batch_size_without_lm
    
    if batch_size > max_batch_size:
        warning_msg = (
            f"⚠️ Requested batch size ({batch_size}) exceeds the limit for your GPU "
            f"({gpu_config.gpu_memory_gb:.1f}GB). Maximum allowed: {max_batch_size} "
            f"({'with' if lm_initialized else 'without'} LM). "
            f"Batch size will be clamped to {max_batch_size}."
        )
        return False, warning_msg
    
    return True, ""


def is_lm_model_supported(model_path: str, gpu_config: GPUConfig) -> Tuple[bool, str]:
    """
    Check if the specified LM model is supported for current GPU configuration.
    
    Args:
        model_path: LM model path
        gpu_config: Current GPU configuration
        
    Returns:
        Tuple of (is_supported, warning_message)
    """
    if not gpu_config.available_lm_models:
        return False, (
            f"⚠️ Your GPU ({gpu_config.gpu_memory_gb:.1f}GB) does not have enough memory "
            f"to run any LM model. Please disable LM initialization."
        )
    
    model_size = get_lm_model_size(model_path)
    
    # Check if model size is in available models
    for available_model in gpu_config.available_lm_models:
        if model_size in available_model:
            return True, ""
    
    return False, (
        f"⚠️ LM model {model_path} ({model_size}) is not supported for your GPU "
        f"({gpu_config.gpu_memory_gb:.1f}GB). Available models: {', '.join(gpu_config.available_lm_models)}"
    )


def get_recommended_lm_model(gpu_config: GPUConfig) -> Optional[str]:
    """
    Get recommended LM model for current GPU configuration.
    
    Args:
        gpu_config: Current GPU configuration
        
    Returns:
        Recommended LM model path, or None if LM is not supported
    """
    if not gpu_config.available_lm_models:
        return None
    
    # Return the largest available model (last in the list)
    return gpu_config.available_lm_models[-1]


def print_gpu_config_info(gpu_config: GPUConfig):
    """Print GPU configuration information for debugging."""
    logger.info(f"GPU Configuration:")
    logger.info(f"  - GPU Memory: {gpu_config.gpu_memory_gb:.1f} GB")
    logger.info(f"  - Tier: {gpu_config.tier}")
    logger.info(f"  - Max Duration (with LM): {gpu_config.max_duration_with_lm}s ({gpu_config.max_duration_with_lm // 60} min)")
    logger.info(f"  - Max Duration (without LM): {gpu_config.max_duration_without_lm}s ({gpu_config.max_duration_without_lm // 60} min)")
    logger.info(f"  - Max Batch Size (with LM): {gpu_config.max_batch_size_with_lm}")
    logger.info(f"  - Max Batch Size (without LM): {gpu_config.max_batch_size_without_lm}")
    logger.info(f"  - Init LM by Default: {gpu_config.init_lm_default}")
    logger.info(f"  - Available LM Models: {gpu_config.available_lm_models or 'None'}")


# Global GPU config instance (initialized lazily)
_global_gpu_config: Optional[GPUConfig] = None


def get_global_gpu_config() -> GPUConfig:
    """Get the global GPU configuration, initializing if necessary."""
    global _global_gpu_config
    if _global_gpu_config is None:
        _global_gpu_config = get_gpu_config()
    return _global_gpu_config


def set_global_gpu_config(config: GPUConfig):
    """Set the global GPU configuration."""
    global _global_gpu_config
    _global_gpu_config = config
