"""
LoRA Utilities for ACE-Step

Provides utilities for injecting LoRA adapters into the DiT decoder model.
Uses PEFT (Parameter-Efficient Fine-Tuning) library for LoRA implementation.
"""

import os
from typing import Optional, List, Dict, Any, Tuple
from loguru import logger
import types

import torch
import torch.nn as nn
from safetensors.torch import load_file

# Restrict checkpoint-related filesystem access to a safe root.
# This mirrors SAFE_TRAINING_ROOT in training_handlers.py.
SAFE_CHECKPOINT_ROOT = os.path.abspath(os.getcwd())

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

from acestep.training.configs import LoRAConfig


def check_peft_available() -> bool:
    """Check if PEFT library is available."""
    return PEFT_AVAILABLE


def get_dit_target_modules(model) -> List[str]:
    """Get the list of module names in the DiT decoder that can have LoRA applied.
    
    Args:
        model: The AceStepConditionGenerationModel
        
    Returns:
        List of module names suitable for LoRA
    """
    target_modules = []
    
    # Focus on the decoder (DiT) attention layers
    if hasattr(model, 'decoder'):
        for name, module in model.decoder.named_modules():
            # Target attention projection layers
            if any(proj in name for proj in ['q_proj', 'k_proj', 'v_proj', 'o_proj']):
                if isinstance(module, nn.Linear):
                    target_modules.append(name)
    
    return target_modules


def freeze_non_lora_parameters(model, freeze_encoder: bool = True) -> None:
    """Freeze all non-LoRA parameters in the model.
    
    Args:
        model: The model to freeze parameters for
        freeze_encoder: Whether to freeze the encoder (condition encoder)
    """
    # Freeze all parameters first
    for param in model.parameters():
        param.requires_grad = False
    
    # Count frozen and trainable parameters
    total_params = 0
    trainable_params = 0
    
    for name, param in model.named_parameters():
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
        raise ImportError("PEFT library is required for LoRA training. Install with: pip install peft")
    
    # Get the decoder (DiT model). Previous failed training runs may leave
    # Fabric/PEFT wrappers attached; unwrap to a clean base module first.
    decoder = model.decoder
    while hasattr(decoder, "_forward_module"):
        decoder = decoder._forward_module
    if hasattr(decoder, "base_model"):
        base_model = decoder.base_model
        if hasattr(base_model, "model"):
            decoder = base_model.model
        else:
            decoder = base_model
    if hasattr(decoder, "model") and isinstance(decoder.model, nn.Module):
        decoder = decoder.model
    model.decoder = decoder

    # PEFT may call enable_input_require_grads() when is_gradient_checkpointing
    # is true. AceStepDiTModel doesn't implement get_input_embeddings, so the
    # default implementation raises NotImplementedError. Guard this path.
    if hasattr(decoder, "enable_input_require_grads"):
        orig_enable_input_require_grads = decoder.enable_input_require_grads

        def _safe_enable_input_require_grads(self):
            try:
                result = orig_enable_input_require_grads()
                try:
                    self._acestep_input_grads_hook_enabled = True
                except Exception:
                    pass
                return result
            except NotImplementedError:
                try:
                    self._acestep_input_grads_hook_enabled = False
                except Exception:
                    pass
                if not getattr(self, "_acestep_input_grads_warning_emitted", False):
                    logger.info(
                        "Skipping enable_input_require_grads for decoder: "
                        "get_input_embeddings is not implemented (expected for DiT)"
                    )
                    try:
                        self._acestep_input_grads_warning_emitted = True
                    except Exception:
                        pass
                return None

        decoder.enable_input_require_grads = types.MethodType(
            _safe_enable_input_require_grads, decoder
        )

    # Avoid PEFT auto-prep path on non-embedding diffusion decoder.
    if hasattr(decoder, "is_gradient_checkpointing"):
        try:
            decoder.is_gradient_checkpointing = False
        except Exception:
            pass
    
    # Create PEFT LoRA config
    peft_lora_config = LoraConfig(
        r=lora_config.r,
        lora_alpha=lora_config.alpha,
        lora_dropout=lora_config.dropout,
        target_modules=lora_config.target_modules,
        bias=lora_config.bias,
        task_type=TaskType.FEATURE_EXTRACTION,  # For diffusion models
    )
    
    # Apply LoRA to the decoder
    peft_decoder = get_peft_model(decoder, peft_lora_config)
    
    # Replace the decoder in the original model
    model.decoder = peft_decoder
    
    # Freeze all non-LoRA parameters
    # Freeze encoder, tokenizer, detokenizer
    for name, param in model.named_parameters():
        # Only keep LoRA parameters trainable
        if 'lora_' not in name:
            param.requires_grad = False
    
    # Count parameters
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
    
    logger.info(f"LoRA injected into DiT decoder:")
    logger.info(f"  Total parameters: {total_params:,}")
    logger.info(f"  Trainable parameters: {trainable_params:,} ({info['trainable_ratio']:.2%})")
    logger.info(f"  LoRA rank: {lora_config.r}, alpha: {lora_config.alpha}")
    
    return model, info


def save_lora_weights(
    model,
    output_dir: str,
    save_full_model: bool = False,
) -> str:
    """Save LoRA adapter weights.
    
    Args:
        model: Model with LoRA adapters
        output_dir: Directory to save weights
        save_full_model: Whether to save the full model state dict
        
    Returns:
        Path to saved weights
    """
    os.makedirs(output_dir, exist_ok=True)
    
    if hasattr(model, 'decoder') and hasattr(model.decoder, 'save_pretrained'):
        # Save PEFT adapter
        adapter_path = os.path.join(output_dir, "adapter")
        model.decoder.save_pretrained(adapter_path)
        logger.info(f"LoRA adapter saved to {adapter_path}")
        return adapter_path
    elif save_full_model:
        # Save full model state dict (larger file)
        model_path = os.path.join(output_dir, "model.pt")
        torch.save(model.state_dict(), model_path)
        logger.info(f"Full model state dict saved to {model_path}")
        return model_path
    else:
        # Extract only LoRA parameters
        lora_state_dict = {}
        for name, param in model.named_parameters():
            if 'lora_' in name:
                lora_state_dict[name] = param.data.clone()
        
        if not lora_state_dict:
            logger.warning("No LoRA parameters found to save!")
            return ""
        
        lora_path = os.path.join(output_dir, "lora_weights.pt")
        torch.save(lora_state_dict, lora_path)
        logger.info(f"LoRA weights saved to {lora_path}")
        return lora_path


def load_lora_weights(
    model,
    lora_path: str,
    lora_config: Optional[LoRAConfig] = None,
) -> Any:
    """Load LoRA adapter weights into the model.
    
    Args:
        model: The base model (without LoRA)
        lora_path: Path to saved LoRA adapter directory
        lora_config: Unused; retained for API compatibility
        
    Returns:
        Model with LoRA weights loaded
    """
    safe_lora_path = _safe_checkpoint_dir(lora_path)
    if safe_lora_path is None:
        raise ValueError(f"Rejected unsafe LoRA path: {lora_path!r}")
    if not os.path.exists(safe_lora_path):
        raise FileNotFoundError(f"LoRA weights not found: {safe_lora_path}")
    
    # Check if it's a PEFT adapter directory
    if os.path.isdir(safe_lora_path):
        if not PEFT_AVAILABLE:
            raise ImportError("PEFT library is required to load adapter. Install with: pip install peft")
        
        # Load PEFT adapter
        model.decoder = PeftModel.from_pretrained(model.decoder, safe_lora_path)
        logger.info(f"LoRA adapter loaded from {safe_lora_path}")
    
    elif safe_lora_path.endswith('.pt'):
        raise ValueError(
            "Loading LoRA weights from .pt files is disabled for security. "
            "Use a PEFT adapter directory instead."
        )
    
    else:
        raise ValueError(f"Unsupported LoRA weight format: {safe_lora_path}")
    
    return model


def save_training_checkpoint(
    model,
    optimizer,
    scheduler,
    epoch: int,
    global_step: int,
    output_dir: str,
) -> str:
    """Save a training checkpoint including LoRA weights and training state.

    Args:
        model: Model with LoRA adapters
        optimizer: Optimizer state
        scheduler: Scheduler state
        epoch: Current epoch number
        global_step: Current global step
        output_dir: Directory to save checkpoint

    Returns:
        Path to saved checkpoint directory
    """
    os.makedirs(output_dir, exist_ok=True)

    # Save LoRA adapter weights
    adapter_path = save_lora_weights(model, output_dir)

    # Save training state (optimizer, scheduler, epoch, step)
    training_state = {
        "epoch": epoch,
        "global_step": global_step,
        "optimizer_state_dict": optimizer.state_dict(),
        "scheduler_state_dict": scheduler.state_dict(),
    }

    state_path = os.path.join(output_dir, "training_state.pt")
    torch.save(training_state, state_path)

    logger.info(f"Training checkpoint saved to {output_dir} (epoch {epoch}, step {global_step})")
    return output_dir


def _safe_checkpoint_dir(user_dir: str) -> Optional[str]:
    """Safely resolve a user-provided path within SAFE_CHECKPOINT_ROOT."""
    if not user_dir:
        return None
    candidate = user_dir.strip()
    if not candidate:
        return None
    safe_root = os.path.realpath(os.path.abspath(SAFE_CHECKPOINT_ROOT))
    if os.path.isabs(candidate):
        # Reject absolute paths to prevent escaping SAFE_CHECKPOINT_ROOT
        return None
    normalized = os.path.realpath(os.path.join(safe_root, candidate))
    try:
        common = os.path.commonpath([safe_root, normalized])
    except ValueError:
        return None
    if common != safe_root:
        return None
    return normalized


def load_training_checkpoint(
    checkpoint_dir: str,
    optimizer=None,
    scheduler=None,
    device: torch.device = None,
) -> Dict[str, Any]:
    """Load training checkpoint.

    Args:
        checkpoint_dir: Directory containing checkpoint files
        optimizer: Optimizer instance to load state into (optional)
        scheduler: Scheduler instance to load state into (optional)
        device: Device to load tensors to

    Returns:
        Dictionary with checkpoint info:
        - epoch: Saved epoch number
        - global_step: Saved global step
        - adapter_path: Path to adapter weights
        - loaded_optimizer: Whether optimizer state was loaded
        - loaded_scheduler: Whether scheduler state was loaded
    """
    result = {
        "epoch": 0,
        "global_step": 0,
        "adapter_path": None,
        "loaded_optimizer": False,
        "loaded_scheduler": False,
    }

    # Normalize and validate checkpoint directory to stay within SAFE_CHECKPOINT_ROOT
    safe_dir = _safe_checkpoint_dir(checkpoint_dir)
    if safe_dir is None:
        logger.warning(f"Rejected unsafe checkpoint directory: {checkpoint_dir!r}")
        return result

    # Find adapter path (safe_dir is already validated)
    adapter_path = os.path.join(safe_dir, "adapter")
    if os.path.isdir(adapter_path):
        result["adapter_path"] = adapter_path
    elif os.path.isdir(safe_dir):
        result["adapter_path"] = safe_dir

    # Load training state (use safetensors; avoid unsafe pickle-based torch.load)
    # safe_dir is already validated, so we can join directly
    state_path = os.path.join(safe_dir, "training_state.safetensors")
    if os.path.isfile(state_path):
        # safetensors is a safe, non-executable tensor serialization format
        try:
            # Convert device to string format expected by load_file
            # PyTorch device objects have proper __str__ that produces "cpu", "cuda:0", etc.
            device_str = str(device) if device is not None else "cpu"
            training_state_tensors = load_file(state_path, device=device_str)

            # Expect scalar tensors for epoch/global_step if present
            if "epoch" in training_state_tensors:
                try:
                    result["epoch"] = int(training_state_tensors["epoch"].item())
                except (ValueError, TypeError, RuntimeError) as e:
                    logger.warning(f"Failed to parse 'epoch' from training_state.safetensors: {e}, using default 0")
            if "global_step" in training_state_tensors:
                try:
                    result["global_step"] = int(training_state_tensors["global_step"].item())
                except (ValueError, TypeError, RuntimeError) as e:
                    logger.warning(f"Failed to parse 'global_step' from training_state.safetensors: {e}, using default 0")

            # For security, do not attempt to deserialize optimizer/scheduler state
            # from arbitrary objects. If tensor-only states are added in the future,
            # they can be wired here in a controlled way.
            logger.info(f"Loaded checkpoint metadata from epoch {result['epoch']}, step {result['global_step']}")
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning(f"Failed to load training_state.safetensors: {e}")
    else:
        # Fallback: extract epoch from path
        import re
        match = re.search(r'epoch_(\d+)', safe_dir)
        if match:
            result["epoch"] = int(match.group(1))
            logger.info(f"No training_state.safetensors found, extracted epoch {result['epoch']} from path")

    return result


def merge_lora_weights(model) -> Any:
    """Merge LoRA weights into the base model.

    This permanently integrates the LoRA adaptations into the model weights.
    After merging, the model can be used without PEFT.
    
    Args:
        model: Model with LoRA adapters
        
    Returns:
        Model with merged weights
    """
    if hasattr(model, 'decoder') and hasattr(model.decoder, 'merge_and_unload'):
        # PEFT model - merge and unload
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
        if 'lora_' in name:
            lora_params += param.numel()
            # Extract module name
            module_name = name.rsplit('.lora_', 1)[0]
            if module_name not in lora_modules:
                lora_modules.append(module_name)
    
    info["total_params"] = total_params
    info["lora_params"] = lora_params
    info["has_lora"] = lora_params > 0
    info["modules_with_lora"] = lora_modules
    
    if total_params > 0:
        info["lora_ratio"] = lora_params / total_params
    
    return info
