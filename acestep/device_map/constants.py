"""Shared constants for multi-GPU device placement."""

from __future__ import annotations

import re

GPU_MAPPING_ENV = "ACESTEP_GPU_MAPPING"
LM_DEVICE_ENV = "ACESTEP_LM_DEVICE"

COMPONENT_KEYS = ("dit", "vae", "text_encoder", "lm")
SINGLE_PATTERN = re.compile(r"^single:(\d+)$")
PAIR_PATTERN = re.compile(r"^([a-z_]+):(\d+)$")
