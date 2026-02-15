"""
Shared utilities for wizard flow modules.

Contains the Namespace builder for training flows, which maps the wizard
``answers`` dict to the ``argparse.Namespace`` expected by dispatch.
"""

from __future__ import annotations

import argparse

from acestep.training_v2.ui.prompt_helpers import DEFAULT_NUM_WORKERS


def build_train_namespace(a: dict, mode: str) -> argparse.Namespace:
    """Convert a wizard answers dict into an argparse.Namespace for dispatch.

    Args:
        a: Wizard answers dict populated by step functions.
        mode: Training subcommand ('fixed' or 'vanilla').

    Returns:
        A fully populated ``argparse.Namespace``.
    """
    target_modules = a.get("target_modules_str", "q_proj k_proj v_proj o_proj").split()
    nw = a.get("num_workers", DEFAULT_NUM_WORKERS)
    return argparse.Namespace(
        subcommand=mode,
        plain=False,
        yes=False,
        _from_wizard=True,
        # Adapter selection
        adapter_type=a.get("adapter_type", "lora"),
        checkpoint_dir=a["checkpoint_dir"],
        model_variant=a["model_variant"],
        base_model=a.get("base_model", a["model_variant"]),
        device=a.get("device", "auto"),
        precision=a.get("precision", "auto"),
        dataset_dir=a["dataset_dir"],
        num_workers=nw,
        pin_memory=a.get("pin_memory", True),
        prefetch_factor=a.get("prefetch_factor", 2 if nw > 0 else 0),
        persistent_workers=a.get("persistent_workers", nw > 0),
        learning_rate=a.get("learning_rate", 1e-4),
        batch_size=a.get("batch_size", 1),
        gradient_accumulation=a.get("gradient_accumulation", 4),
        epochs=a.get("epochs", 100),
        warmup_steps=a.get("warmup_steps", 100),
        weight_decay=a.get("weight_decay", 0.01),
        max_grad_norm=a.get("max_grad_norm", 1.0),
        seed=a.get("seed", 42),
        # LoRA args
        rank=a.get("rank", 64),
        alpha=a.get("alpha", 128),
        dropout=a.get("dropout", 0.1),
        target_modules=target_modules,
        attention_type=a.get("attention_type", "both"),
        bias=a.get("bias", "none"),
        # LoKR args
        lokr_linear_dim=a.get("lokr_linear_dim", 64),
        lokr_linear_alpha=a.get("lokr_linear_alpha", 128),
        lokr_factor=a.get("lokr_factor", -1),
        lokr_decompose_both=a.get("lokr_decompose_both", False),
        lokr_use_tucker=a.get("lokr_use_tucker", False),
        lokr_use_scalar=a.get("lokr_use_scalar", False),
        lokr_weight_decompose=a.get("lokr_weight_decompose", False),
        # Output / checkpoints
        output_dir=a["output_dir"],
        save_every=a.get("save_every", 10),
        resume_from=a.get("resume_from"),
        log_dir=a.get("log_dir"),
        log_every=a.get("log_every", 10),
        log_heavy_every=a.get("log_heavy_every", 50),
        sample_every_n_epochs=a.get("sample_every_n_epochs", 0),
        shift=a.get("shift", 3.0),
        num_inference_steps=a.get("num_inference_steps", 8),
        optimizer_type=a.get("optimizer_type", "adamw"),
        scheduler_type=a.get("scheduler_type", "cosine"),
        gradient_checkpointing=a.get("gradient_checkpointing", True),
        offload_encoder=a.get("offload_encoder", False),
        preprocess=False,
        audio_dir=None,
        dataset_json=None,
        tensor_output=None,
        max_duration=240.0,
        cfg_ratio=a.get("cfg_ratio", 0.15),
        estimate_batches=None,
        top_k=16,
        granularity="module",
        module_config=None,
        auto_estimate=False,
        estimate_output=None,
    )
