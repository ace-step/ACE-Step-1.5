"""
Side-Step Optimizer & Scheduler Factories

Provides ``build_optimizer()`` and ``build_scheduler()`` so that
``trainer_fixed.py`` doesn't need to hard-code AdamW / CosineAnnealing.

Supported optimizers:
    adamw       -- torch.optim.AdamW (default, fused on CUDA)
    adamw8bit   -- bitsandbytes.optim.AdamW8bit (optional dep)
    adafactor   -- transformers.optimization.Adafactor
    prodigy     -- prodigyopt.Prodigy (optional dep, auto-tunes LR)

Supported schedulers:
    cosine              -- warmup + CosineAnnealingLR (single smooth decay)
    cosine_restarts     -- warmup + CosineAnnealingWarmRestarts (cyclical)
    linear              -- warmup + LinearLR decay to near-zero
    constant            -- warmup then flat LR
    constant_with_warmup -- alias for constant
"""

from __future__ import annotations

import logging
from typing import Iterable

import torch
from torch.optim import AdamW
from torch.optim.lr_scheduler import (
    CosineAnnealingLR,
    CosineAnnealingWarmRestarts,
    ConstantLR,
    LinearLR,
    SequentialLR,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Optimizer factory
# ---------------------------------------------------------------------------

def build_optimizer(
    params: Iterable,
    optimizer_type: str = "adamw",
    lr: float = 1e-4,
    weight_decay: float = 0.01,
    device_type: str = "cuda",
) -> torch.optim.Optimizer:
    """Create an optimizer from a string key.

    Falls back to AdamW when an optional dependency is missing.
    """
    optimizer_type = optimizer_type.lower().strip()

    if optimizer_type == "adamw8bit":
        try:
            from bitsandbytes.optim import AdamW8bit
            logger.info("[Side-Step] Using AdamW8bit optimizer (lower VRAM)")
            return AdamW8bit(params, lr=lr, weight_decay=weight_decay)
        except ImportError:
            logger.warning(
                "[Side-Step] bitsandbytes not installed -- falling back to AdamW. "
                "Install with: pip install bitsandbytes>=0.45.0"
            )
            optimizer_type = "adamw"

    if optimizer_type == "adafactor":
        try:
            from transformers.optimization import Adafactor
            logger.info("[Side-Step] Using Adafactor optimizer (minimal state memory)")
            return Adafactor(
                params,
                lr=lr,
                weight_decay=weight_decay,
                scale_parameter=False,
                relative_step=False,
            )
        except ImportError:
            logger.warning(
                "[Side-Step] transformers not installed -- falling back to AdamW"
            )
            optimizer_type = "adamw"

    if optimizer_type == "prodigy":
        try:
            from prodigyopt import Prodigy
            logger.info(
                "[Side-Step] Using Prodigy optimizer (adaptive LR -- set LR=1.0 for best results)"
            )
            return Prodigy(
                params,
                lr=lr if lr != 1e-4 else 1.0,  # Default to 1.0 for Prodigy
                weight_decay=weight_decay,
            )
        except ImportError:
            logger.warning(
                "[Side-Step] prodigyopt not installed -- falling back to AdamW. "
                "Install with: pip install prodigyopt>=1.1.2"
            )
            optimizer_type = "adamw"

    # Default: AdamW
    kwargs = {"lr": lr, "weight_decay": weight_decay}
    if device_type == "cuda":
        kwargs["fused"] = True
    logger.info("[Side-Step] Using AdamW optimizer")
    return AdamW(params, **kwargs)


# ---------------------------------------------------------------------------
# Scheduler factory
# ---------------------------------------------------------------------------

def build_scheduler(
    optimizer: torch.optim.Optimizer,
    scheduler_type: str = "cosine",
    total_steps: int = 1000,
    warmup_steps: int = 500,
    lr: float = 1e-4,
    optimizer_type: str = "adamw",
    n_restarts: int = 4,
):
    """Create a learning rate scheduler from a string key.

    Args:
        n_restarts: Number of cosine restart cycles for the
            ``cosine_restarts`` scheduler.  Ignored by other types.

    When the optimizer is Prodigy, defaults to constant schedule
    (Prodigy manages LR internally).
    """
    scheduler_type = scheduler_type.lower().strip()

    # Prodigy handles its own LR -- force constant
    if optimizer_type == "prodigy" and scheduler_type not in ("constant", "constant_with_warmup"):
        logger.info(
            "[Side-Step] Prodigy optimizer detected -- overriding scheduler to 'constant' "
            "(Prodigy adapts LR internally)"
        )
        scheduler_type = "constant"

    # Clamp warmup to avoid exceeding total
    warmup_steps = min(warmup_steps, max(1, total_steps // 10))

    warmup_sched = LinearLR(
        optimizer,
        start_factor=0.1,
        end_factor=1.0,
        total_iters=warmup_steps,
    )

    remaining = max(1, total_steps - warmup_steps)

    if scheduler_type in ("constant", "constant_with_warmup"):
        main_sched = ConstantLR(optimizer, factor=1.0, total_iters=total_steps)
    elif scheduler_type == "linear":
        main_sched = LinearLR(
            optimizer,
            start_factor=1.0,
            end_factor=0.01,
            total_iters=remaining,
        )
    elif scheduler_type == "cosine_restarts":
        # Cyclical cosine: LR resets to peak multiple times during training.
        # T_0 = cycle length = remaining / n_restarts.
        main_sched = CosineAnnealingWarmRestarts(
            optimizer,
            T_0=max(1, remaining // max(1, n_restarts)),
            T_mult=1,
            eta_min=lr * 0.01,
        )
    else:
        # cosine (default) -- single smooth decay to eta_min, no restarts.
        main_sched = CosineAnnealingLR(
            optimizer,
            T_max=remaining,
            eta_min=lr * 0.01,
        )

    return SequentialLR(optimizer, [warmup_sched, main_sched], milestones=[warmup_steps])
