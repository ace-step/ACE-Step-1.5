"""
LoRA Utilities for ACE-Step

Provides utilities for injecting LoRA adapters into the DiT decoder model.
Uses PEFT (Parameter-Efficient Fine-Tuning) library for LoRA implementation.
"""

import os
from typing import Optional, List, Dict, Any, Tuple
from loguru import logger

import torch
import torch.nn as nn

try:
    from peft import (
        get_peft_model,
        LoraConfig,
        TaskType,
        PeftModel,
        PeftConfig,
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
    
    # Get the decoder (DiT model)
    decoder = model.decoder
    
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
        lora_path: Path to saved LoRA weights (adapter or .pt file)
        lora_config: LoRA configuration (required if loading from .pt file)
        
    Returns:
        Model with LoRA weights loaded
    """
    if not os.path.exists(lora_path):
        raise FileNotFoundError(f"LoRA weights not found: {lora_path}")
    
    # Check if it's a PEFT adapter directory
    if os.path.isdir(lora_path):
        if not PEFT_AVAILABLE:
            raise ImportError("PEFT library is required to load adapter. Install with: pip install peft")
        
        # Load PEFT adapter
        peft_config = PeftConfig.from_pretrained(lora_path)
        model.decoder = PeftModel.from_pretrained(model.decoder, lora_path)
        logger.info(f"LoRA adapter loaded from {lora_path}")
    
    elif lora_path.endswith('.pt'):
        # Load from PyTorch state dict
        if lora_config is None:
            raise ValueError("lora_config is required when loading from .pt file")
        
        # First inject LoRA structure
        model, _ = inject_lora_into_dit(model, lora_config)
        
        # Load weights
        lora_state_dict = torch.load(lora_path, map_location='cpu', weights_only=True)
        
        # Load into model
        model_state = model.state_dict()
        for name, param in lora_state_dict.items():
            if name in model_state:
                model_state[name].copy_(param)
            else:
                logger.warning(f"Unexpected key in LoRA state dict: {name}")
        
        logger.info(f"LoRA weights loaded from {lora_path}")
    
    else:
        raise ValueError(f"Unsupported LoRA weight format: {lora_path}")
    
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

    # Find adapter path
    adapter_path = os.path.join(checkpoint_dir, "adapter")
    if os.path.exists(adapter_path):
        result["adapter_path"] = adapter_path
    elif os.path.exists(checkpoint_dir):
        result["adapter_path"] = checkpoint_dir

    # Load training state
    state_path = os.path.join(checkpoint_dir, "training_state.pt")
    if os.path.exists(state_path):
        map_location = device if device else "cpu"
        training_state = torch.load(state_path, map_location=map_location, weights_only=True)

        result["epoch"] = training_state.get("epoch", 0)
        result["global_step"] = training_state.get("global_step", 0)

        # Load optimizer state if provided
        if optimizer is not None and "optimizer_state_dict" in training_state:
            try:
                optimizer.load_state_dict(training_state["optimizer_state_dict"])
                result["loaded_optimizer"] = True
                logger.info("Optimizer state loaded from checkpoint")
            except Exception as e:
                logger.warning(f"Failed to load optimizer state: {e}")

        # Load scheduler state if provided
        if scheduler is not None and "scheduler_state_dict" in training_state:
            try:
                scheduler.load_state_dict(training_state["scheduler_state_dict"])
                result["loaded_scheduler"] = True
                logger.info("Scheduler state loaded from checkpoint")
            except Exception as e:
                logger.warning(f"Failed to load scheduler state: {e}")

        logger.info(f"Loaded checkpoint from epoch {result['epoch']}, step {result['global_step']}")
    else:
        # Fallback: extract epoch from path
        import re
        match = re.search(r'epoch_(\d+)', checkpoint_dir)
        if match:
            result["epoch"] = int(match.group(1))
            logger.info(f"No training_state.pt found, extracted epoch {result['epoch']} from path")

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
