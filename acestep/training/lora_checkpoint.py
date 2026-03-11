"""
LoRA Checkpoint Utilities for ACE-Step

Provides functions for saving and loading LoRA checkpoints.
"""

import os
from typing import Optional, Dict, Any
from loguru import logger

import torch
from torch.nn import Module

from acestep.training.path_safety import safe_path
from acestep.training.configs import LoRAConfig

try:
    from peft import PeftModel

    PEFT_AVAILABLE = True
except ImportError:
    PEFT_AVAILABLE = False


def save_lora_weights(
    model: Module,
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
    output_dir = safe_path(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    if hasattr(model, "decoder") and hasattr(model.decoder, "save_pretrained"):
        adapter_path = os.path.join(output_dir, "adapter")
        model.decoder.save_pretrained(adapter_path)
        logger.info(f"LoRA adapter saved to {adapter_path}")
        return adapter_path
    elif save_full_model:
        model_path = os.path.join(output_dir, "model.pt")
        torch.save(model.state_dict(), model_path)
        logger.info(f"Full model state dict saved to {model_path}")
        return model_path
    else:
        lora_state_dict = {}
        for name, param in model.named_parameters():
            if "lora_" in name:
                lora_state_dict[name] = param.data.clone()

        if not lora_state_dict:
            logger.warning("No LoRA parameters found to save!")
            return ""

        lora_path = os.path.join(output_dir, "lora_weights.pt")
        torch.save(lora_state_dict, lora_path)
        logger.info(f"LoRA weights saved to {lora_path}")
        return lora_path


def load_lora_weights(
    model: Module,
    lora_path: str,
    _lora_config: Optional[LoRAConfig] = None,
) -> Module:
    """Load LoRA adapter weights into the model.

    Args:
        model: The base model (without LoRA)
        lora_path: Path to saved LoRA adapter directory
        lora_config: Unused; retained for API compatibility

    Returns:
        Model with LoRA weights loaded
    """
    validated = safe_path(lora_path)
    if not os.path.exists(validated):
        raise FileNotFoundError(f"LoRA weights not found: {validated}")

    if os.path.isdir(validated):
        if not PEFT_AVAILABLE:
            raise ImportError(
                "PEFT library is required to load adapter. Install with: pip install peft"
            )

        model.decoder = PeftModel.from_pretrained(model.decoder, validated)
        logger.info(f"LoRA adapter loaded from {validated}")

    elif validated.endswith(".pt"):
        raise ValueError(
            "Loading LoRA weights from .pt files is disabled for security. "
            "Use a PEFT adapter directory instead."
        )

    else:
        raise ValueError(f"Unsupported LoRA weight format: {validated}")

    return model


def save_training_checkpoint(
    model: Module,
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
    output_dir = safe_path(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    save_lora_weights(model, output_dir)

    training_state = {
        "epoch": epoch,
        "global_step": global_step,
        "optimizer_state_dict": optimizer.state_dict(),
        "scheduler_state_dict": scheduler.state_dict(),
    }

    state_path = os.path.join(output_dir, "training_state.pt")
    torch.save(training_state, state_path)

    logger.info(
        f"Training checkpoint saved to {output_dir} (epoch {epoch}, step {global_step})"
    )
    return output_dir


def load_training_checkpoint(
    checkpoint_dir: str,
    optimizer=None,
    scheduler=None,
    device: torch.device = None,
) -> Dict[str, Any]:
    """Load training checkpoint.

    Args:
        checkpoint_dir: Directory containing checkpoint files
        optimizer: Optimizer instance to load state into (optional).
            When provided, loads optimizer_state_dict from the checkpoint.
        scheduler: Scheduler instance to load state into (optional).
            When provided, loads scheduler_state_dict from the checkpoint.
        device: Device to load tensors to

    Returns:
        Dictionary with checkpoint info:
        - epoch: Saved epoch number
        - global_step: Saved global step
        - adapter_path: Path to adapter weights
        - loaded_optimizer: Whether optimizer state was loaded (True when optimizer param provided and state loaded)
        - loaded_scheduler: Whether scheduler state was loaded (True when scheduler param provided and state loaded)
    """
    result = {
        "epoch": 0,
        "global_step": 0,
        "adapter_path": None,
        "loaded_optimizer": False,
        "loaded_scheduler": False,
    }

    try:
        safe_dir = safe_path(checkpoint_dir)
    except ValueError:
        logger.warning(f"Rejected unsafe checkpoint directory: {checkpoint_dir!r}")
        return result

    adapter_path = os.path.join(safe_dir, "adapter")
    if os.path.isdir(adapter_path):
        result["adapter_path"] = adapter_path
    elif os.path.isdir(safe_dir):
        result["adapter_path"] = safe_dir

    state_path = os.path.join(safe_dir, "training_state.pt")
    if os.path.isfile(state_path):
        try:
            training_state = torch.load(
                state_path, map_location=device, weights_only=True
            )

            if "epoch" in training_state:
                try:
                    result["epoch"] = int(training_state["epoch"])
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"Failed to parse 'epoch' from training_state.pt: {e}, using default 0"
                    )
            if "global_step" in training_state:
                try:
                    result["global_step"] = int(training_state["global_step"])
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"Failed to parse 'global_step' from training_state.pt: {e}, using default 0"
                    )

            if optimizer is not None and "optimizer_state_dict" in training_state:
                try:
                    optimizer_state = training_state["optimizer_state_dict"]
                    if device is not None:
                        for state in optimizer_state.get("state", {}).values():
                            for k, v in state.items():
                                if isinstance(v, torch.Tensor):
                                    state[k] = v.to(device)
                    optimizer.load_state_dict(optimizer_state)
                    result["loaded_optimizer"] = True
                    logger.info("Loaded optimizer state from checkpoint")
                except (RuntimeError, ValueError, KeyError) as e:
                    logger.warning(f"Failed to load optimizer state: {e}")

            if scheduler is not None and "scheduler_state_dict" in training_state:
                try:
                    scheduler.load_state_dict(training_state["scheduler_state_dict"])
                    result["loaded_scheduler"] = True
                    logger.info("Loaded scheduler state from checkpoint")
                except (RuntimeError, ValueError, KeyError) as e:
                    logger.warning(f"Failed to load scheduler state: {e}")

            logger.info(
                f"Loaded checkpoint metadata from epoch {result['epoch']}, step {result['global_step']}"
            )
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning(f"Failed to load training_state.pt: {e}")
    else:
        import re

        match = re.search(r"epoch_(\d+)", safe_dir)
        if match:
            result["epoch"] = int(match.group(1))
            logger.info(
                f"No training_state.pt found, extracted epoch {result['epoch']} from path"
            )

    return result
