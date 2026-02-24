"""Request models and shared state helpers for training APIs."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field


class StartTrainingRequest(BaseModel):
    """Request payload for starting LoRA training."""

    tensor_dir: str = Field(..., description="Directory with preprocessed tensors")
    lora_rank: int = Field(default=64, ge=1, le=256, description="LoRA rank")
    lora_alpha: int = Field(default=128, ge=1, le=512, description="LoRA alpha")
    lora_dropout: float = Field(default=0.1, ge=0.0, le=1.0, description="LoRA dropout")
    learning_rate: float = Field(default=1e-4, gt=0.0, description="Learning rate")
    train_epochs: int = Field(default=10, ge=1, description="Training epochs")
    train_batch_size: int = Field(default=1, ge=1, description="Batch size")
    gradient_accumulation: int = Field(default=4, ge=1, description="Gradient accumulation steps")
    save_every_n_epochs: int = Field(default=5, ge=1, description="Save checkpoint every N epochs")
    training_shift: float = Field(default=3.0, ge=0.0, description="Training timestep shift")
    training_seed: int = Field(default=42, description="Random seed")
    lora_output_dir: str = Field(default="./lora_output", description="Output directory")
    use_fp8: bool = Field(default=False, description="Use FP8 training when runtime supports it")
    gradient_checkpointing: bool = Field(default=False, description="Trade compute speed for lower VRAM usage")


class StartLoKRTrainingRequest(BaseModel):
    """Request payload for starting LoKr training."""

    tensor_dir: str = Field(..., description="Directory with preprocessed tensors")
    lokr_linear_dim: int = Field(default=64, ge=1, le=256, description="LoKR linear dimension")
    lokr_linear_alpha: int = Field(default=128, ge=1, le=512, description="LoKR linear alpha")
    lokr_factor: int = Field(default=-1, description="Kronecker factor (-1 = auto)")
    lokr_decompose_both: bool = Field(default=False, description="Decompose both matrices")
    lokr_use_tucker: bool = Field(default=False, description="Use Tucker decomposition")
    lokr_use_scalar: bool = Field(default=False, description="Use scalar calibration")
    lokr_weight_decompose: bool = Field(default=True, description="Enable DoRA mode")
    learning_rate: float = Field(default=0.03, gt=0.0, description="Learning rate")
    train_epochs: int = Field(default=500, ge=1, description="Training epochs")
    train_batch_size: int = Field(default=1, ge=1, description="Batch size")
    gradient_accumulation: int = Field(default=4, ge=1, description="Gradient accumulation steps")
    save_every_n_epochs: int = Field(default=5, ge=1, description="Save checkpoint every N epochs")
    training_shift: float = Field(default=3.0, ge=0.0, description="Training timestep shift")
    training_seed: int = Field(default=42, description="Random seed")
    output_dir: str = Field(default="./lokr_output", description="Output directory")
    gradient_checkpointing: bool = Field(default=False, description="Trade compute speed for lower VRAM usage")


class ExportLoRARequest(BaseModel):
    """Request payload for exporting trained adapters."""

    export_path: str = Field(..., description="Export destination path")
    lora_output_dir: str = Field(..., description="Training output directory")


@dataclass
class AutoLabelTask:
    """Runtime status snapshot for async auto-label tasks."""

    task_id: str
    status: str
    progress: str
    current: int
    total: int
    save_path: Optional[str] = None
    last_updated_index: Optional[int] = None
    last_updated_sample: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class PreprocessTask:
    """Runtime status snapshot for async dataset preprocess tasks."""

    task_id: str
    status: str
    progress: str
    current: int
    total: int
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = 0.0


_auto_label_lock = Lock()
_auto_label_tasks: Dict[str, AutoLabelTask] = {}
_auto_label_latest_task_id: Optional[str] = None

_preprocess_lock = Lock()
_preprocess_tasks: Dict[str, PreprocessTask] = {}
_preprocess_latest_task_id: Optional[str] = None


def initialize_training_state(app: FastAPI) -> None:
    """Ensure app state has a stable ``training_state`` mapping."""

    state = getattr(app.state, "training_state", None)
    if not isinstance(state, dict):
        state = {}
        app.state.training_state = state

    defaults: dict[str, Any] = {
        "is_training": False,
        "should_stop": False,
        "run_id": None,
        "trainer": None,
        "tensor_dir": "",
        "tensorboard_logdir": None,
        "tensorboard_url": None,
        "current_step": 0,
        "current_loss": None,
        "status": "Idle",
        "loss_history": [],
        "training_log": "",
        "start_time": None,
        "current_epoch": 0,
        "last_step_time": 0.0,
        "steps_per_second": 0.0,
        "estimated_time_remaining": 0.0,
        "error": None,
        "config": {},
    }
    for key, value in defaults.items():
        if key not in state:
            if isinstance(value, list):
                state[key] = []
            elif isinstance(value, dict):
                state[key] = {}
            else:
                state[key] = value
