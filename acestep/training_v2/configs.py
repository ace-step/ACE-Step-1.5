"""
Extended Training Configuration for ACE-Step Training V2

Uses base configs from ``acestep.training.configs``.  Extends them with
corrected-training-specific fields (CFG dropout,
continuous timestep sampling parameters, estimation, TensorBoard, sample
generation, etc.).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

# Vendored base configs -- no base ACE-Step installation required
from acestep.training.configs import (  # noqa: F401
    LoRAConfig,
    LoKRConfig,
    TrainingConfig,
)


# ---------------------------------------------------------------------------
# Extended LoRA config (unchanged for now, but available for future extension)
# ---------------------------------------------------------------------------

@dataclass
class LoRAConfigV2(LoRAConfig):
    """Extended LoRA configuration.

    Inherits all fields from the original LoRAConfig and adds:
    - attention_type: Which attention layers to target (self, cross, or both)
    """

    attention_type: str = "both"
    """Which attention layers to target: 'self', 'cross', or 'both'."""

    def to_dict(self) -> dict:
        base = super().to_dict()
        base["attention_type"] = self.attention_type
        return base

    # --- Data loading (declared here for compatibility with base packages
    #     that may not include these fields in TrainingConfig) -----------------
    num_workers: int = 4
    """Number of DataLoader worker processes."""

    pin_memory: bool = True
    """Pin memory in DataLoader for faster host-to-device transfer."""

    prefetch_factor: int = 2
    """Number of batches to prefetch per DataLoader worker."""

    persistent_workers: bool = True
    """Keep DataLoader workers alive between epochs."""

    pin_memory_device: str = ""
    """Device for pinned memory ("" = default CUDA device)."""


# ---------------------------------------------------------------------------
# Extended LoKR config
# ---------------------------------------------------------------------------

@dataclass
class LoKRConfigV2(LoKRConfig):
    """Extended LoKR configuration.

    Inherits all fields from the original LoKRConfig and adds:
    - attention_type: Which attention layers to target (self, cross, or both)
    """

    attention_type: str = "both"
    """Which attention layers to target: 'self', 'cross', or 'both'."""

    def to_dict(self) -> dict:
        base = super().to_dict()
        base["attention_type"] = self.attention_type
        return base


# ---------------------------------------------------------------------------
# Extended Training config
# ---------------------------------------------------------------------------

@dataclass
class TrainingConfigV2(TrainingConfig):
    """Extended training configuration with corrected-training fields.

    New fields compared to the original TrainingConfig:
    - CFG dropout (cfg_ratio)
    - Continuous timestep sampling parameters (timestep_mu, timestep_sigma,
      data_proportion)
    - Model variant selection
    - Device / precision auto-detection
    - Estimation parameters
    - Extended TensorBoard logging
    - Sample generation during training
    - Checkpoint resume
    - Preprocessing flags
    """

    # --- Data loading (declared here for compatibility with base packages
    #     that may not include these fields in TrainingConfig) -----------------
    num_workers: int = 4
    """Number of DataLoader worker processes."""

    pin_memory: bool = True
    """Pin memory in DataLoader for faster host-to-device transfer."""

    prefetch_factor: int = 2
    """Number of batches to prefetch per DataLoader worker."""

    persistent_workers: bool = True
    """Keep DataLoader workers alive between epochs."""

    pin_memory_device: str = ""
    """Device for pinned memory ("" = default CUDA device)."""

    # --- Optimizer / Scheduler ------------------------------------------------
    optimizer_type: str = "adamw"
    """Optimizer: 'adamw', 'adamw8bit', 'adafactor', 'prodigy'."""

    scheduler_type: str = "cosine"
    """LR scheduler: 'cosine', 'cosine_restarts', 'linear', 'constant', 'constant_with_warmup'."""

    # --- VRAM management ------------------------------------------------------
    gradient_checkpointing: bool = True
    """Trade compute for memory by recomputing activations during backward.
    Enabled by default to match ACE-Step's behaviour and save ~40-60%
    activation VRAM.  Adds ~10-30% training time overhead."""

    offload_encoder: bool = False
    """Move encoder/VAE to CPU after setup to free ~2-4 GB VRAM."""

    vram_profile: str = "auto"
    """VRAM preset: 'auto', 'comfortable', 'standard', 'tight', 'minimal'."""

    # --- Corrected training params ------------------------------------------
    cfg_ratio: float = 0.15
    """Classifier-free guidance dropout probability."""

    timestep_mu: float = -0.4
    """Mean for logit-normal timestep sampling (from model config)."""

    timestep_sigma: float = 1.0
    """Std for logit-normal timestep sampling (from model config)."""

    data_proportion: float = 0.5
    """Data proportion for sample_t_r (from model config)."""

    # --- Adapter selection ----------------------------------------------------
    adapter_type: str = "lora"
    """Adapter type: 'lora' (PEFT) or 'lokr' (LyCORIS)."""

    # --- Model / paths ------------------------------------------------------
    model_variant: str = "turbo"
    """Model variant: 'turbo', 'base', or 'sft'."""

    checkpoint_dir: str = "./checkpoints"
    """Path to checkpoints root directory."""

    dataset_dir: str = ""
    """Directory containing preprocessed .pt tensor files."""

    # --- Device / precision -------------------------------------------------
    device: str = "auto"
    """Device selection: 'auto', 'cuda', 'cuda:0', 'mps', 'xpu', 'cpu'."""

    precision: str = "auto"
    """Precision: 'auto', 'bf16', 'fp16', 'fp32'."""

    # --- Checkpointing ------------------------------------------------------
    resume_from: Optional[str] = None
    """Path to checkpoint directory to resume training from."""

    # --- Extended TensorBoard logging ---------------------------------------
    log_dir: Optional[str] = None
    """TensorBoard log directory.  Defaults to {output_dir}/runs."""

    log_every: int = 10
    """Log basic metrics (loss, LR) every N optimiser steps."""

    log_heavy_every: int = 50
    """Log per-layer gradient norms every N optimiser steps."""

    # --- Sample generation --------------------------------------------------
    sample_every_n_epochs: int = 0
    """Generate an audio sample every N epochs (0 = disabled)."""

    # --- Estimation params --------------------------------------------------
    estimate_batches: Optional[int] = None
    """Number of batches for gradient estimation (None = auto from GPU)."""

    top_k: int = 16
    """Number of top modules to select during estimation."""

    granularity: str = "module"
    """Estimation granularity: 'layer' or 'module'."""

    module_config: Optional[str] = None
    """Path to JSON module config produced by the estimate subcommand."""

    auto_estimate: bool = False
    """Run estimation inline before training."""

    estimate_output: Optional[str] = None
    """Path to write module config JSON (estimate subcommand only)."""

    # --- Preprocessing flags ------------------------------------------------
    preprocess: bool = False
    """Run preprocessing before training."""

    audio_dir: Optional[str] = None
    """Source audio directory for preprocessing."""

    dataset_json: Optional[str] = None
    """Labeled dataset JSON for preprocessing."""

    tensor_output: Optional[str] = None
    """Output directory for preprocessed .pt tensor files."""

    max_duration: float = 240.0
    """Maximum audio duration in seconds (preprocessing)."""

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @property
    def effective_log_dir(self) -> Path:
        """Return the resolved TensorBoard log directory."""
        if self.log_dir is not None:
            return Path(self.log_dir)
        return Path(self.output_dir) / "runs"

    def to_dict(self) -> dict:
        """Serialize every field, including new ones."""
        base = super().to_dict()
        base.update(
            {
                "num_workers": self.num_workers,
                "pin_memory": self.pin_memory,
                "prefetch_factor": self.prefetch_factor,
                "persistent_workers": self.persistent_workers,
                "pin_memory_device": self.pin_memory_device,
                "optimizer_type": self.optimizer_type,
                "scheduler_type": self.scheduler_type,
                "gradient_checkpointing": self.gradient_checkpointing,
                "offload_encoder": self.offload_encoder,
                "vram_profile": self.vram_profile,
                "adapter_type": self.adapter_type,
                "cfg_ratio": self.cfg_ratio,
                "timestep_mu": self.timestep_mu,
                "timestep_sigma": self.timestep_sigma,
                "data_proportion": self.data_proportion,
                "model_variant": self.model_variant,
                "checkpoint_dir": self.checkpoint_dir,
                "dataset_dir": self.dataset_dir,
                "device": self.device,
                "precision": self.precision,
                "resume_from": self.resume_from,
                "log_dir": self.log_dir,
                "log_every": self.log_every,
                "log_heavy_every": self.log_heavy_every,
                "sample_every_n_epochs": self.sample_every_n_epochs,
                "estimate_batches": self.estimate_batches,
                "top_k": self.top_k,
                "granularity": self.granularity,
                "module_config": self.module_config,
                "auto_estimate": self.auto_estimate,
                "estimate_output": self.estimate_output,
                "preprocess": self.preprocess,
                "audio_dir": self.audio_dir,
                "dataset_json": self.dataset_json,
                "tensor_output": self.tensor_output,
                "max_duration": self.max_duration,
            }
        )
        return base

    def save_json(self, path: Path) -> None:
        """Persist the full config to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def from_json(cls, path: Path) -> "TrainingConfigV2":
        """Load config from a JSON file."""
        data = json.loads(Path(path).read_text())
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
