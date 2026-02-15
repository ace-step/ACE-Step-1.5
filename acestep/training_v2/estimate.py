"""
Gradient Sensitivity Estimation -- Reusable Module

Provides ``run_estimation()`` for use from both the CLI and the TUI.
Measures gradient magnitudes per LoRA-targetable module to rank them
by importance for a given dataset.

Uses the same flow-matching forward pass as ``FixedLoRAModule.training_step``
so that gradient measurements reflect the real training loss surface.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)


def run_estimation(
    checkpoint_dir: str,
    variant: str,
    dataset_dir: str,
    num_batches: int = 10,
    batch_size: int = 1,
    top_k: int = 16,
    granularity: str = "module",
    progress_callback: Optional[Callable] = None,
    cancel_check: Optional[Callable] = None,
    cfg_ratio: float = 0.0,
) -> List[Dict[str, Any]]:
    """Run gradient sensitivity analysis and return ranked modules.

    Args:
        checkpoint_dir: Path to model checkpoints.
        variant: Model variant (turbo, base, sft).
        dataset_dir: Directory with preprocessed .pt files.
        num_batches: Number of forward/backward passes for estimation.
        batch_size: Samples per estimation batch.
        top_k: Number of top modules to return.
        granularity: ``"module"`` or ``"layer"``.
        progress_callback: ``(batch, total, module_name) -> None``.
        cancel_check: ``() -> bool`` -- return True to cancel.
        cfg_ratio: CFG dropout ratio (default 0).  When > 0 and the model
            has a ``null_condition_emb``, CFG dropout is applied to
            ``encoder_hidden_states`` so sensitivity reflects the same
            masking used during training.

    Returns:
        List of dicts ``[{"module": name, "sensitivity": float}, ...]``
        sorted descending by sensitivity.
    """
    from acestep.training_v2.model_loader import (
        load_decoder_for_training,
        read_model_config,
        unload_models,
    )
    from acestep.training_v2.gpu_utils import detect_gpu
    from acestep.training_v2.timestep_sampling import sample_timesteps
    from acestep.training.data_module import PreprocessedDataModule

    gpu = detect_gpu()
    device = gpu.device
    device_type = gpu.device_type
    dtype_map = {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}
    dtype = dtype_map.get(gpu.precision, torch.bfloat16)

    # Read timestep parameters from model config.json
    try:
        mcfg = read_model_config(checkpoint_dir, variant)
    except (FileNotFoundError, json.JSONDecodeError):
        mcfg = {}
    timestep_mu = mcfg.get("timestep_mu", -0.4)
    timestep_sigma = mcfg.get("timestep_sigma", 1.0)
    data_proportion = mcfg.get("data_proportion", 0.5)

    logger.info("[Side-Step] Loading model for estimation (variant=%s)", variant)
    model = load_decoder_for_training(
        checkpoint_dir=checkpoint_dir,
        variant=variant,
        device=device,
        precision=gpu.precision,
    )

    # Identify targetable attention modules
    target_modules = _find_attention_modules(model, granularity)
    logger.info("[Side-Step] Found %d targetable modules", len(target_modules))

    if not target_modules:
        logger.error("[Side-Step] No targetable modules found -- aborting estimation")
        unload_models(model)
        return []

    # Build parameter name -> target module mapping for fast lookup
    param_to_module: Dict[str, str] = {}
    for pname, _ in model.named_parameters():
        for mod_name in target_modules:
            if mod_name in pname:
                param_to_module[pname] = mod_name
                break

    # Load data
    data_module = PreprocessedDataModule(
        tensor_dir=dataset_dir,
        batch_size=batch_size,
        num_workers=0,
        pin_memory=False,
    )
    data_module.setup("fit")
    loader = data_module.train_dataloader()

    # Accumulate gradient norms per module
    grad_accum: Dict[str, float] = {name: 0.0 for name in target_modules}

    batches_done = 0
    for batch in loader:
        if batches_done >= num_batches:
            break
        if cancel_check and cancel_check():
            break

        # Enable gradients ONLY on targetable parameters
        for pname, param in model.named_parameters():
            param.requires_grad = pname in param_to_module

        try:
            # Move batch to device
            target_latents = batch["target_latents"].to(device, dtype=dtype)
            attention_mask = batch["attention_mask"].to(device, dtype=dtype)
            encoder_hidden_states = batch["encoder_hidden_states"].to(device, dtype=dtype)
            encoder_attention_mask = batch["encoder_attention_mask"].to(device, dtype=dtype)
            context_latents = batch["context_latents"].to(device, dtype=dtype)

            bsz = target_latents.shape[0]

            # Autocast for mixed precision
            if device_type in ("cuda", "xpu", "mps"):
                autocast_ctx = torch.autocast(device_type=device_type, dtype=dtype)
            else:
                from contextlib import nullcontext
                autocast_ctx = nullcontext()

            with autocast_ctx:
                # ---- CFG dropout (match training when cfg_ratio > 0) ----
                if cfg_ratio > 0.0 and hasattr(model, "null_condition_emb"):
                    from acestep.training_v2.fixed_lora_module import apply_cfg_dropout
                    encoder_hidden_states = apply_cfg_dropout(
                        encoder_hidden_states,
                        model.null_condition_emb,
                        cfg_ratio=cfg_ratio,
                    )

                # Flow matching noise
                x0 = target_latents
                x1 = torch.randn_like(x0)

                # Continuous timestep sampling (matches trainer_fixed)
                t, _r = sample_timesteps(
                    batch_size=bsz,
                    device=device,
                    dtype=dtype,
                    data_proportion=data_proportion,
                    timestep_mu=timestep_mu,
                    timestep_sigma=timestep_sigma,
                    use_meanflow=False,
                )
                t_ = t.unsqueeze(-1).unsqueeze(-1)

                # Interpolate
                xt = t_ * x1 + (1.0 - t_) * x0

                # Real decoder forward pass
                decoder_outputs = model.decoder(
                    hidden_states=xt,
                    timestep=t,
                    timestep_r=t,
                    attention_mask=attention_mask,
                    encoder_hidden_states=encoder_hidden_states,
                    encoder_attention_mask=encoder_attention_mask,
                    context_latents=context_latents,
                )

                # Flow matching loss
                flow = x1 - x0
                loss = F.mse_loss(decoder_outputs[0], flow)

            loss.backward()

            # Accumulate gradient norms per module
            for pname, param in model.named_parameters():
                if param.grad is not None and pname in param_to_module:
                    mod_name = param_to_module[pname]
                    grad_accum[mod_name] += param.grad.norm().item()

        except Exception as e:
            logger.warning("[Side-Step] Estimation batch %d failed: %s", batches_done, e)
        finally:
            model.zero_grad()
            for param in model.parameters():
                param.requires_grad = False

        batches_done += 1
        if progress_callback:
            progress_callback(batches_done, num_batches, "")

    # Normalize and rank
    if batches_done > 0:
        for name in grad_accum:
            grad_accum[name] /= batches_done

    ranked = sorted(grad_accum.items(), key=lambda x: x[1], reverse=True)
    results = [
        {"module": name, "sensitivity": score}
        for name, score in ranked[:top_k]
    ]

    logger.info(
        "[Side-Step] Estimation complete (%d batches): top module = %s (%.6f)",
        batches_done,
        results[0]["module"] if results else "none",
        results[0]["sensitivity"] if results else 0.0,
    )

    # Clean up
    unload_models(model)

    return results


def _find_attention_modules(model: nn.Module, granularity: str) -> List[str]:
    """Find attention module names in the model.

    ACE-Step uses ``q_proj``, ``k_proj``, ``v_proj``, ``o_proj`` naming.
    """
    modules = []
    for name, _ in model.named_modules():
        if granularity == "module":
            # Individual attention projections (ACE-Step naming)
            if any(proj in name for proj in ("q_proj", "k_proj", "v_proj", "o_proj")):
                modules.append(name)
        else:
            # Layer level -- attention blocks (exclude individual projections)
            if "attn" in name.lower() and not any(
                proj in name for proj in ("q_proj", "k_proj", "v_proj", "o_proj", "norm")
            ):
                modules.append(name)

    if not modules:
        # Fallback: any module with 'attention' or 'attn' in the name
        logger.warning("[Side-Step] No standard attention modules found; using fallback search")
        for name, _ in model.named_modules():
            if "attn" in name.lower():
                modules.append(name)

    return modules
