"""
ACE-Step Training Module

This module provides LoRA training functionality for ACE-Step models,
including dataset building, audio labeling, and training utilities.
"""

from acestep.training.dataset_builder import DatasetBuilder, AudioSample
from acestep.training.configs import LoRAConfig, LoKRConfig, TrainingConfig
from acestep.training.lora_injection import (
    inject_lora_into_dit,
    freeze_non_lora_parameters,
)
from acestep.training.lora_checkpoint import (
    save_lora_weights,
    load_lora_weights,
    save_training_checkpoint,
    load_training_checkpoint,
)
from acestep.training.lora_utils import (
    merge_lora_weights,
    check_peft_available,
)
from acestep.training.lokr_utils import (
    inject_lokr_into_dit,
    save_lokr_weights,
    load_lokr_weights,
    check_lycoris_available,
)
from acestep.training.data_module import (
    # Preprocessed (recommended)
    PreprocessedTensorDataset,
    PreprocessedDataModule,
    collate_preprocessed_batch,
    # Legacy (raw audio)
    AceStepTrainingDataset,
    AceStepDataModule,
    collate_training_batch,
    load_dataset_from_json,
)
from acestep.training.trainer import (
    LoRATrainer,
    LoKRTrainer,
    PreprocessedLoRAModule,
    PreprocessedLoKRModule,
    LIGHTNING_AVAILABLE,
)


def check_lightning_available():
    """Check if Lightning Fabric is available."""
    return LIGHTNING_AVAILABLE


__all__ = [
    # Dataset Builder
    "DatasetBuilder",
    "AudioSample",
    # Configs
    "LoRAConfig",
    "LoKRConfig",
    "TrainingConfig",
    # LoRA Injection
    "inject_lora_into_dit",
    "freeze_non_lora_parameters",
    # LoRA Checkpoint
    "save_lora_weights",
    "load_lora_weights",
    "save_training_checkpoint",
    "load_training_checkpoint",
    # LoRA Utils
    "merge_lora_weights",
    "check_peft_available",
    # LoKr Utils
    "inject_lokr_into_dit",
    "save_lokr_weights",
    "load_lokr_weights",
    "check_lycoris_available",
    # Data Module (Preprocessed - Recommended)
    "PreprocessedTensorDataset",
    "PreprocessedDataModule",
    "collate_preprocessed_batch",
    # Data Module (Legacy)
    "AceStepTrainingDataset",
    "AceStepDataModule",
    "collate_training_batch",
    "load_dataset_from_json",
    # Trainer
    "LoRATrainer",
    "LoKRTrainer",
    "PreprocessedLoRAModule",
    "PreprocessedLoKRModule",
    "check_lightning_available",
    "LIGHTNING_AVAILABLE",
]
