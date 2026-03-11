"""
LoRA Utilities for ACE-Step

Provides utilities for inspecting and merging LoRA adapters.
Uses PEFT (Parameter-Efficient Fine-Tuning) library for LoRA implementation.
"""

from typing import Dict, Any
from loguru import logger

try:
    from peft import PeftModel

    PEFT_AVAILABLE = True
except ImportError:
    PEFT_AVAILABLE = False
    logger.warning("PEFT library not installed. LoRA training will not be available.")


def check_peft_available() -> bool:
    """Check if PEFT library is available."""
    return PEFT_AVAILABLE


def merge_lora_weights(model) -> Any:
    """Merge LoRA weights into the base model.

    This permanently integrates the LoRA adaptations into the model weights.
    After merging, the model can be used without PEFT.

    Args:
        model: Model with LoRA adapters

    Returns:
        Model with merged weights
    """
    if hasattr(model, "decoder") and hasattr(model.decoder, "merge_and_unload"):
        model.decoder = model.decoder.merge_and_unload()
        logger.info("LoRA weights merged into base model")
    else:
        logger.warning("Model does not support LoRA merging")

    return model


def get_lora_info(model) -> Dict[str, Any]:
    """Get information about LoRA adapters in the model.

    Args:
        model: Model to inspect

    Returns:
        Dictionary with LoRA information
    """
    info = {
        "has_lora": False,
        "lora_params": 0,
        "total_params": 0,
        "modules_with_lora": [],
    }

    total_params = 0
    lora_params = 0
    lora_modules = []

    for name, param in model.named_parameters():
        total_params += param.numel()
        if "lora_" in name:
            lora_params += param.numel()
            module_name = name.rsplit(".lora_", 1)[0]
            if module_name not in lora_modules:
                lora_modules.append(module_name)

    info["total_params"] = total_params
    info["lora_params"] = lora_params
    info["has_lora"] = lora_params > 0
    info["modules_with_lora"] = lora_modules

    if total_params > 0:
        info["lora_ratio"] = lora_params / total_params

    return info
