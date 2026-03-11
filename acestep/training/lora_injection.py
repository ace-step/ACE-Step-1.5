"""
LoRA Injection Utilities for ACE-Step

Provides functions for injecting LoRA adapters into the DiT decoder model.
"""

from typing import List, Tuple, Any, Dict
from loguru import logger
import types

import torch.nn as nn

from acestep.training.configs import LoRAConfig


def _safe_enable_input_require_grads(self):
    """Safely call enable_input_require_grads on the decoder.

    This helper wraps the original enable_input_require_grads method,
    handling NotImplementedError gracefully and tracking whether the hook
    was successfully enabled.

    Args:
        self: The decoder module to call enable_input_require_grads on.
    """
    orig_enable_input_require_grads = getattr(
        self, "_acestep_orig_enable_input_require_grads", None
    )

    try:
        if orig_enable_input_require_grads is not None:
            result = orig_enable_input_require_grads()
        else:
            result = None
        try:
            self._acestep_input_grads_hook_enabled = True
        except Exception:
            logger.debug(
                "Failed to set _acestep_input_grads_hook_enabled", exc_info=True
            )
        return result
    except NotImplementedError:
        try:
            self._acestep_input_grads_hook_enabled = False
        except Exception:
            logger.debug(
                "Failed to set _acestep_input_grads_hook_enabled", exc_info=True
            )
        if not getattr(self, "_acestep_input_grads_warning_emitted", False):
            logger.info(
                "Skipping enable_input_require_grads for decoder: "
                "get_input_embeddings is not implemented (expected for DiT)"
            )
            try:
                self._acestep_input_grads_warning_emitted = True
            except Exception:
                logger.debug(
                    "Failed to set _acestep_input_grads_warning_emitted", exc_info=True
                )
        return None


try:
    from peft import (
        get_peft_model,
        LoraConfig,
        TaskType,
        PeftModel,
    )

    PEFT_AVAILABLE = True
except ImportError:
    PEFT_AVAILABLE = False
    logger.warning("PEFT library not installed. LoRA training will not be available.")


def _unwrap_decoder(module: nn.Module) -> nn.Module:
    """Unwrap PEFT/Fabric wrappers from a model/decoder to retrieve the base DiT module.

    This internal helper walks the wrapper chain and returns the underlying
    ``nn.Module`` that can be passed to PEFT for adapter injection.

    Args:
        module: A model or decoder that may have PEFT/Fabric wrappers.

    Returns:
        The unwrapped base DiT decoder module.
    """
    decoder = module
    seen_ids = {id(decoder)}
    while True:
        next_decoder = getattr(decoder, "_forward_module", None)
        if next_decoder is None:
            break
        next_id = id(next_decoder)
        if next_id in seen_ids:
            break
        seen_ids.add(next_id)
        decoder = next_decoder

    base_model = getattr(decoder, "base_model", None)
    if base_model is not None:
        inner_model = getattr(base_model, "model", None)
        if inner_model is not None and isinstance(inner_model, nn.Module):
            decoder = inner_model
        else:
            decoder = base_model

    final_model = getattr(decoder, "model", None)
    if final_model is not None and isinstance(final_model, nn.Module):
        decoder = final_model

    return decoder


def get_dit_target_modules(model) -> List[str]:
    """Get the list of module names in the DiT decoder that can have LoRA applied.

    Args:
        model: The AceStepConditionGenerationModel

    Returns:
        List of module names suitable for LoRA
    """
    target_modules = []

    if hasattr(model, "decoder"):
        for name, module in model.decoder.named_modules():
            if any(proj in name for proj in ["q_proj", "k_proj", "v_proj", "o_proj"]):
                if isinstance(module, nn.Linear):
                    target_modules.append(name)

    return target_modules


def freeze_non_lora_parameters(model, freeze_encoder: bool = True) -> None:
    """Freeze all non-LoRA parameters in the model.

    Args:
        model: The model to freeze parameters for
        freeze_encoder: Whether to freeze the encoder (condition encoder)
    """
    encoder_prefixes = ("encoder", "text_encoder", "vision_encoder", "model.encoder")

    for name, param in model.named_parameters():
        is_lora = "lora_" in name
        is_encoder = name.startswith(encoder_prefixes) or any(
            name.startswith(f"{prefix}.") for prefix in encoder_prefixes
        )

        if is_lora:
            param.requires_grad = True
        elif freeze_encoder or not is_encoder:
            param.requires_grad = False

    total_params = 0
    trainable_params = 0

    for _, param in model.named_parameters():
        total_params += param.numel()
        if param.requires_grad:
            trainable_params += param.numel()

    logger.info(f"Frozen parameters: {total_params - trainable_params:,}")
    logger.info(f"Trainable parameters: {trainable_params:,}")


def inject_lora_into_dit(
    model,
    lora_config: LoRAConfig,
) -> Tuple[Any, Dict[str, Any]]:
    """Inject LoRA adapters into the DiT decoder of the model.

    Args:
        model: The AceStepConditionGenerationModel
        lora_config: LoRA configuration

    Returns:
        Tuple of (peft_model, info_dict)
    """
    if not PEFT_AVAILABLE:
        raise ImportError(
            "PEFT library is required for LoRA training. Install with: pip install peft"
        )

    decoder = _unwrap_decoder(model.decoder)
    model.decoder = decoder

    if hasattr(decoder, "enable_input_require_grads"):
        orig = decoder.enable_input_require_grads
        decoder._acestep_orig_enable_input_require_grads = orig
        decoder.enable_input_require_grads = types.MethodType(
            _safe_enable_input_require_grads, decoder
        )

    if hasattr(decoder, "is_gradient_checkpointing"):
        try:
            decoder.is_gradient_checkpointing = False
        except Exception:
            pass

    peft_lora_config = LoraConfig(
        r=lora_config.r,
        lora_alpha=lora_config.alpha,
        lora_dropout=lora_config.dropout,
        target_modules=lora_config.target_modules,
        bias=lora_config.bias,
        task_type=TaskType.FEATURE_EXTRACTION,
    )

    peft_decoder = get_peft_model(decoder, peft_lora_config)
    model.decoder = peft_decoder

    for name, param in model.named_parameters():
        if "lora_" not in name:
            param.requires_grad = False

    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

    info = {
        "total_params": total_params,
        "trainable_params": trainable_params,
        "trainable_ratio": trainable_params / total_params if total_params > 0 else 0,
        "lora_r": lora_config.r,
        "lora_alpha": lora_config.alpha,
        "target_modules": lora_config.target_modules,
    }

    logger.info("LoRA injected into DiT decoder:")
    logger.info(f"  Total parameters: {total_params:,}")
    logger.info(
        f"  Trainable parameters: {trainable_params:,} ({info['trainable_ratio']:.2%})"
    )
    logger.info(f"  LoRA rank: {lora_config.r}, alpha: {lora_config.alpha}")

    return model, info
