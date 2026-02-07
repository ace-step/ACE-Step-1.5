"""
Dataset Builder for LoRA Training (facade).

This module preserves the public API while delegating to smaller modules.
"""

from .dataset_builder_modules import AudioSample, DatasetBuilder, DatasetMetadata, SUPPORTED_AUDIO_FORMATS

__all__ = [
    "AudioSample",
    "DatasetBuilder",
    "DatasetMetadata",
    "SUPPORTED_AUDIO_FORMATS",
]
