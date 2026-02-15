"""
VanillaTrainer -- Thin adapter wrapping the original LoRATrainer for TUI use.

The original ``acestep/training/trainer.py`` ``LoRATrainer`` requires a
``dit_handler`` shim.  This module provides a ``VanillaTrainer`` class with
the same interface as ``FixedTrainer`` so both can be used interchangeably
from the TUI training monitor.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Generator, Optional, Tuple

import torch

try:
    from acestep.training.configs import LoRAConfig, TrainingConfig
    from acestep.training.trainer import LoRATrainer
    _VANILLA_AVAILABLE = True
except ImportError:
    _VANILLA_AVAILABLE = False

    # Stub definitions so the module can be imported for type-checking
    # even when the real package is missing (avoids a second ImportError).
    from dataclasses import dataclass as _dataclass

    @_dataclass
    class LoRAConfig:  # type: ignore[no-redef]
        """Stub for ``acestep.training.configs.LoRAConfig``."""
        r: int = 64
        alpha: int = 128
        dropout: float = 0.0
        target_modules: list = None  # type: ignore[assignment]
        bias: str = "none"

    @_dataclass
    class TrainingConfig:  # type: ignore[no-redef]
        """Stub for ``acestep.training.configs.TrainingConfig``."""
        learning_rate: float = 1e-4
        batch_size: int = 1
        gradient_accumulation_steps: int = 4
        max_epochs: int = 100
        warmup_steps: int = 500
        weight_decay: float = 0.01
        max_grad_norm: float = 1.0
        seed: int = 42
        output_dir: str = "./lora_output"
        save_every_n_epochs: int = 10
        num_workers: int = 0
        pin_memory: bool = True

    LoRATrainer = None  # type: ignore[assignment,misc]
from acestep.training_v2.model_loader import load_decoder_for_training

logger = logging.getLogger(__name__)


class _HandlerShim:
    """Minimal shim satisfying the ``LoRATrainer`` constructor.

    Wraps a decoder model, device string, and dtype so that the upstream
    ``LoRATrainer`` receives the interface it expects from a full
    ``dit_handler``.

    Args:
        model: The decoder ``torch.nn.Module`` to train.
        device: Target device string (e.g. ``"cuda"``, ``"cpu"``).
        dtype: Torch dtype for mixed-precision (e.g. ``torch.bfloat16``).
    """

    def __init__(self, model: torch.nn.Module, device: str, dtype: torch.dtype) -> None:
        self.model = model
        self.device = device
        self.dtype = dtype
        self.quantization = None


class VanillaTrainer:
    """Adapter that wraps the upstream ``LoRATrainer`` to match FixedTrainer's interface.

    Args:
        lora_config: LoRA hyper-parameters (rank, alpha, dropout, targets).
        training_config: Training hyper-parameters (LR, epochs, batch size, ...).
        progress_callback: Optional callable invoked after each upstream
            training update.  Signature:
            ``(epoch: int, step: int, loss: float, lr: float, is_epoch_end: bool) -> Optional[bool]``.
            Return ``False`` to request early stopping.

    Attributes:
        lora_config: Stored LoRA configuration.
        training_config: Stored training configuration.
        progress_callback: Stored callback (may be ``None``).
    """

    def __init__(
        self,
        lora_config: Any,
        training_config: Any,
        progress_callback: Optional[Callable[..., Optional[bool]]] = None,
    ) -> None:
        self.lora_config = lora_config
        self.training_config = training_config
        self.progress_callback = progress_callback

    # -- Private helpers ---------------------------------------------------

    def _build_configs(self) -> Tuple[LoRAConfig, TrainingConfig, int]:
        """Map V2 config objects to base ``LoRAConfig`` / ``TrainingConfig``.

        Returns:
            A tuple of ``(lora_cfg, train_cfg, num_workers)`` where
            *num_workers* is clamped to 0 on Windows.
        """
        cfg = self.training_config

        lora_cfg = LoRAConfig(
            r=getattr(self.lora_config, "rank", 64),
            alpha=getattr(self.lora_config, "alpha", 128),
            dropout=getattr(self.lora_config, "dropout", 0.0),
            target_modules=getattr(self.lora_config, "target_modules", ["to_q", "to_k", "to_v", "to_out.0"]),
            bias=getattr(self.lora_config, "bias", "none"),
        )

        # Windows uses spawn-based multiprocessing which breaks DataLoader workers
        num_workers = getattr(cfg, "num_workers", 4)
        if sys.platform == "win32" and num_workers > 0:
            logger.info("[Side-Step] Windows detected -- setting num_workers=0 (spawn incompatible)")
            num_workers = 0

        train_cfg = TrainingConfig(
            learning_rate=getattr(cfg, "learning_rate", 1e-4),
            batch_size=getattr(cfg, "batch_size", 1),
            gradient_accumulation_steps=getattr(cfg, "gradient_accumulation_steps", 4),
            max_epochs=getattr(cfg, "max_epochs", getattr(cfg, "epochs", 100)),
            warmup_steps=getattr(cfg, "warmup_steps", 500),
            weight_decay=getattr(cfg, "weight_decay", 0.01),
            max_grad_norm=getattr(cfg, "max_grad_norm", 1.0),
            seed=getattr(cfg, "seed", 42),
            output_dir=getattr(cfg, "output_dir", "./lora_output"),
            save_every_n_epochs=getattr(cfg, "save_every_n_epochs", 10),
            num_workers=num_workers,
            pin_memory=getattr(cfg, "pin_memory", True),
        )

        return lora_cfg, train_cfg, num_workers

    @staticmethod
    def _setup_device_and_model(
        cfg: Any,
    ) -> Tuple[Any, torch.dtype, torch.nn.Module]:
        """Auto-detect GPU and load the decoder model.

        Returns:
            A tuple of ``(gpu_info, dtype, model)``.
        """
        from acestep.training_v2.gpu_utils import detect_gpu

        gpu = detect_gpu(
            requested_device=getattr(cfg, "device", "auto"),
            requested_precision=getattr(cfg, "precision", "auto"),
        )
        dtype_map = {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}
        dtype = dtype_map.get(gpu.precision, torch.bfloat16)

        model = load_decoder_for_training(
            checkpoint_dir=getattr(cfg, "checkpoint_dir", "./checkpoints"),
            variant=getattr(cfg, "model_variant", getattr(cfg, "variant", "turbo")),
            device=gpu.device,
            precision=gpu.precision,
        )

        return gpu, dtype, model

    @staticmethod
    def _run_training(
        model: torch.nn.Module,
        gpu: Any,
        dtype: torch.dtype,
        lora_cfg: LoRAConfig,
        train_cfg: TrainingConfig,
        cfg: Any,
    ) -> Generator:
        """Construct handler + LoRATrainer and yield training updates.

        Yields:
            Tuples from the upstream ``LoRATrainer.train_from_preprocessed``.
        """
        handler = _HandlerShim(model=model, device=gpu.device, dtype=dtype)
        trainer = LoRATrainer(handler, lora_cfg, train_cfg)
        dataset_dir = getattr(cfg, "dataset_dir", "")
        resume_from = getattr(cfg, "resume_from", None)

        yield from trainer.train_from_preprocessed(
            tensor_dir=dataset_dir,
            resume_from=resume_from,
        )

    # -- Public API --------------------------------------------------------

    def train(self) -> None:
        """Run vanilla training, calling *progress_callback* for each update.

        Raises:
            RuntimeError: If base ACE-Step is not installed.
        """
        if not _VANILLA_AVAILABLE:
            raise RuntimeError(
                "Vanilla training requires a full ACE-Step 1.5 installation.\n"
                "Install it with:  pip install -e /path/to/ACE-Step-1.5\n"
                "Or use the 'Corrected (fixed)' training mode which is standalone."
            )
        cfg = self.training_config

        lora_cfg, train_cfg, _num_workers = self._build_configs()
        gpu, dtype, model = self._setup_device_and_model(cfg)

        for update in self._run_training(model, gpu, dtype, lora_cfg, train_cfg, cfg):
            if self.progress_callback:
                # Upstream yields (step, loss, msg) tuples
                step, loss, _msg = update if len(update) == 3 else (update[0], update[1], "")
                should_continue = self.progress_callback(
                    epoch=0, step=step, loss=loss, lr=0.0, is_epoch_end=False,
                )
                if should_continue is False:
                    break
