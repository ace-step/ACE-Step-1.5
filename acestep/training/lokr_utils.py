"""
LoKr utilities for ACE-Step training and inference.

This module integrates LyCORIS LoKr adapters with the ACE-Step decoder.
"""

import json
import os
from typing import Any, Dict, Optional, Tuple

import torch
from loguru import logger

from acestep.training.configs import LoKRConfig
from acestep.training.path_safety import safe_path

try:
    from lycoris import LycorisNetwork, create_lycoris

    LYCORIS_AVAILABLE = True
except ImportError:
    LYCORIS_AVAILABLE = False
    LycorisNetwork = Any  # type: ignore[assignment,misc]
    logger.warning(
        "LyCORIS library not installed. LoKr training/inference unavailable. "
        "Install with: pip install lycoris-lora"
    )


def check_lycoris_available() -> bool:
    """Check if LyCORIS is importable."""
    return LYCORIS_AVAILABLE


def _matches_target_module_name(module_name: str, target_modules) -> bool:
    """Return True if a LyCORIS module name maps to one of target module suffixes."""
    if not module_name:
        return False
    name = module_name.lower()
    for target in target_modules or []:
        t = str(target).strip().lower()
        if not t:
            continue
        if name.endswith(t) or f"_{t}" in name or f".{t}" in name:
            return True
    return False


def inject_lokr_into_dit(
    model,
    lokr_config: LoKRConfig,
    multiplier: float = 1.0,
) -> Tuple[Any, "LycorisNetwork", Dict[str, Any]]:
    """
    Inject LoKr adapters into the decoder.

    Returns:
        Tuple: (model, lycoris_network, info_dict)
    """
    if not LYCORIS_AVAILABLE:
        raise ImportError(
            "LyCORIS library is required for LoKr training. "
            "Install with: pip install lycoris-lora"
        )

    decoder = model.decoder

    # Freeze all existing params before creating adapter params.
    for _, param in model.named_parameters():
        param.requires_grad = False

    LycorisNetwork.apply_preset(
        {
            "unet_target_name": lokr_config.target_modules,
            "target_name": lokr_config.target_modules,
        }
    )

    lycoris_net = create_lycoris(
        decoder,
        multiplier,
        linear_dim=lokr_config.linear_dim,
        linear_alpha=lokr_config.linear_alpha,
        algo="lokr",
        factor=lokr_config.factor,
        decompose_both=lokr_config.decompose_both,
        use_tucker=lokr_config.use_tucker,
        use_scalar=lokr_config.use_scalar,
        full_matrix=lokr_config.full_matrix,
        bypass_mode=lokr_config.bypass_mode,
        rs_lora=lokr_config.rs_lora,
        unbalanced_factorization=lokr_config.unbalanced_factorization,
    )

    if lokr_config.weight_decompose:
        try:
            lycoris_net = create_lycoris(
                decoder,
                multiplier,
                linear_dim=lokr_config.linear_dim,
                linear_alpha=lokr_config.linear_alpha,
                algo="lokr",
                factor=lokr_config.factor,
                decompose_both=lokr_config.decompose_both,
                use_tucker=lokr_config.use_tucker,
                use_scalar=lokr_config.use_scalar,
                full_matrix=lokr_config.full_matrix,
                bypass_mode=lokr_config.bypass_mode,
                rs_lora=lokr_config.rs_lora,
                unbalanced_factorization=lokr_config.unbalanced_factorization,
                dora_wd=True,
            )
        except Exception as exc:
            logger.warning(f"DoRA mode not supported in current LyCORIS build: {exc}")

    lycoris_net.apply_to()

    # Keep a reference on decoder so it stays discoverable after wrappers.
    # Always refresh this reference to avoid stale nets from earlier runs.
    decoder._lycoris_net = lycoris_net

    lokr_param_list = []
    enabled_module_count = 0
    disabled_module_count = 0
    disabled_examples = []

    for idx, module in enumerate(getattr(lycoris_net, "loras", []) or []):
        module_name = (
            getattr(module, "lora_name", None)
            or getattr(module, "name", None)
            or f"{module.__class__.__name__}#{idx}"
        )
        enabled = _matches_target_module_name(module_name, lokr_config.target_modules)

        if enabled:
            enabled_module_count += 1
        else:
            disabled_module_count += 1
            if len(disabled_examples) < 8:
                disabled_examples.append(module_name)

        for param in module.parameters():
            param.requires_grad = enabled
            if enabled:
                lokr_param_list.append(param)

    logger.info(
        f"LoKr target filter: enabled {enabled_module_count} LyCORIS modules "
        f"(disabled {disabled_module_count}) for targets={lokr_config.target_modules}"
    )
    if disabled_examples:
        logger.info("LoKr disabled non-target modules (sample): " + ", ".join(disabled_examples))

    if not lokr_param_list:
        for param in lycoris_net.parameters():
            param.requires_grad = True
            lokr_param_list.append(param)

    # De-duplicate possible shared params.
    unique_params = {id(p): p for p in lokr_param_list}
    total_params = sum(p.numel() for p in model.parameters())
    lokr_params = sum(p.numel() for p in unique_params.values())
    trainable_params = sum(p.numel() for p in unique_params.values() if p.requires_grad)

    info = {
        "total_params": total_params,
        "lokr_params": lokr_params,
        "trainable_params": trainable_params,
        "trainable_ratio": trainable_params / total_params if total_params > 0 else 0.0,
        "linear_dim": lokr_config.linear_dim,
        "linear_alpha": lokr_config.linear_alpha,
        "factor": lokr_config.factor,
        "algo": "lokr",
        "target_modules": lokr_config.target_modules,
    }

    logger.info("LoKr injected into decoder")
    logger.info(
        f"LoKr trainable params: {trainable_params:,}/{total_params:,} "
        f"({info['trainable_ratio']:.2%})"
    )
    return model, lycoris_net, info


def save_lokr_weights(
    lycoris_net: "LycorisNetwork",
    output_dir: str,
    dtype: Optional[torch.dtype] = None,
    metadata: Optional[Dict[str, str]] = None,
) -> str:
    """Save LoKr weights to safetensors."""
    output_dir = safe_path(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    weights_path = os.path.join(output_dir, "lokr_weights.safetensors")

    save_metadata: Dict[str, str] = {"algo": "lokr", "format": "lycoris"}
    if metadata:
        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, str):
                save_metadata[key] = value
            else:
                save_metadata[key] = json.dumps(value, ensure_ascii=True)

    lycoris_net.save_weights(weights_path, dtype=dtype, metadata=save_metadata)
    logger.info(f"LoKr weights saved to {weights_path}")
    return weights_path


def load_lokr_weights(lycoris_net: "LycorisNetwork", weights_path: str) -> Dict[str, Any]:
    """Load LoKr weights into an injected LyCORIS network."""
    weights_path = safe_path(weights_path)
    if not os.path.exists(weights_path):
        raise FileNotFoundError(f"LoKr weights not found: {weights_path}")
    result = lycoris_net.load_weights(weights_path)
    logger.info(f"LoKr weights loaded from {weights_path}")
    return result


def save_lokr_training_checkpoint(
    lycoris_net: "LycorisNetwork",
    optimizer,
    scheduler,
    epoch: int,
    global_step: int,
    output_dir: str,
    lokr_config: Optional[LoKRConfig] = None,
    run_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Save LoKr weights plus optimizer/scheduler state."""
    output_dir = safe_path(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    metadata: Dict[str, Any] = {}
    if lokr_config is not None:
        metadata["lokr_config"] = lokr_config.to_dict()
    if run_metadata is not None:
        metadata["run_metadata"] = run_metadata
    metadata = metadata or None
    save_lokr_weights(lycoris_net, output_dir, metadata=metadata)

    state = {
        "epoch": epoch,
        "global_step": global_step,
        "optimizer_state_dict": optimizer.state_dict(),
        "scheduler_state_dict": scheduler.state_dict(),
    }
    if lokr_config is not None:
        state["lokr_config"] = lokr_config.to_dict()
    if run_metadata is not None:
        state["run_metadata"] = run_metadata

    state_path = os.path.join(output_dir, "training_state.pt")
    torch.save(state, state_path)
    logger.info(f"LoKr checkpoint saved to {output_dir} (epoch={epoch}, step={global_step})")
    return output_dir
