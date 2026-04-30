"""Task and seed helpers for handler decomposition."""

import random
from typing import List, Optional, Tuple

import torch
from loguru import logger

from acestep.constants import TASK_INSTRUCTIONS


class TaskUtilsMixin:
    """Mixin containing generation task and seed utility helpers.

    Depends on host members:
    - No required cross-mixin attributes for seed/instruction helpers.
    """

    def prepare_seeds(
        self, actual_batch_size: int, seed, use_random_seed: bool
    ) -> Tuple[List[int], str]:
        """Prepare per-item seeds and UI seed string."""
        actual_seed_list: List[int] = []
        seed_value_for_ui = ""
        try:
            if use_random_seed:
                actual_seed_list = [random.randint(0, 2**32 - 1) for _ in range(actual_batch_size)]
                seed_value_for_ui = ", ".join(str(s) for s in actual_seed_list)
            else:
                seed_list: List[int] = []
                if isinstance(seed, str):
                    for s in [s.strip() for s in seed.split(",")]:
                        if s == "-1" or s == "":
                            seed_list.append(-1)
                        else:
                            try:
                                seed_list.append(int(float(s)))
                            except (ValueError, TypeError) as exc:
                                logger.debug(f"[prepare_seeds] Failed to parse seed value '{s}': {exc}")
                                seed_list.append(-1)
                elif seed is None or (isinstance(seed, (int, float)) and seed < 0):
                    seed_list = [-1] * actual_batch_size
                elif isinstance(seed, (int, float)):
                    seed_list = [int(seed)]
                else:
                    seed_list = [-1] * actual_batch_size

                has_single_non_negative_seed = len(seed_list) == 1 and seed_list[0] != -1
                for i in range(actual_batch_size):
                    seed_val = seed_list[i] if i < len(seed_list) else -1
                    if has_single_non_negative_seed and actual_batch_size > 1 and i > 0:
                        actual_seed_list.append(random.randint(0, 2**32 - 1))
                    elif seed_val == -1:
                        actual_seed_list.append(random.randint(0, 2**32 - 1))
                    else:
                        actual_seed_list.append(int(seed_val))
                seed_value_for_ui = ", ".join(str(s) for s in actual_seed_list)
        except (TypeError, ValueError, OverflowError):
            logger.exception("[prepare_seeds] Failed to prepare seeds")
            actual_seed_list = [random.randint(0, 2**32 - 1) for _ in range(actual_batch_size)]
            seed_value_for_ui = ", ".join(str(s) for s in actual_seed_list)

        return actual_seed_list, seed_value_for_ui

    def generate_instruction(
        self,
        task_type: str,
        track_name: Optional[str] = None,
        complete_track_classes: Optional[List[str]] = None,
    ) -> str:
        """Generate task instruction text from task type and track context."""
        if task_type == "text2music":
            return TASK_INSTRUCTIONS["text2music"]
        if task_type == "repaint":
            return TASK_INSTRUCTIONS["repaint"]
        if task_type == "cover":
            return TASK_INSTRUCTIONS["cover"]
        if task_type == "cover-nofsq":
            return TASK_INSTRUCTIONS["cover"]
        if task_type == "extract":
            return (
                TASK_INSTRUCTIONS["extract"].format(TRACK_NAME=track_name.upper())
                if track_name
                else TASK_INSTRUCTIONS["extract_default"]
            )
        if task_type == "lego":
            return (
                TASK_INSTRUCTIONS["lego"].format(TRACK_NAME=track_name.upper())
                if track_name
                else TASK_INSTRUCTIONS["lego_default"]
            )
        if task_type == "complete":
            if complete_track_classes and len(complete_track_classes) > 0:
                track_classes_upper = [t.upper() for t in complete_track_classes]
                return TASK_INSTRUCTIONS["complete"].format(
                    TRACK_CLASSES=" | ".join(track_classes_upper)
                )
            return TASK_INSTRUCTIONS["complete_default"]
        return TASK_INSTRUCTIONS["text2music"]

    def determine_task_type(self, task_type, audio_code_string):
        """Compute task-mode booleans for downstream generation logic."""
        is_repaint_task = task_type == "repaint"
        is_lego_task = task_type == "lego"
        is_cover_task = task_type in ("cover", "cover-nofsq")

        if isinstance(audio_code_string, list):
            has_codes = any((c or "").strip() for c in audio_code_string)
        else:
            has_codes = bool(audio_code_string and str(audio_code_string).strip())

        if has_codes:
            is_cover_task = True
        can_use_repainting = is_repaint_task or is_lego_task
        return is_repaint_task, is_lego_task, is_cover_task, can_use_repainting

    def create_target_wavs(self, duration_seconds: float) -> torch.Tensor:
        """Create silent stereo target audio with safe duration handling."""
        try:
            duration_seconds = max(0.1, round(duration_seconds, 1))
            frames = int(duration_seconds * 48000)
            return torch.zeros(2, frames)
        except (TypeError, ValueError, OverflowError):
            logger.exception("[create_target_wavs] Error creating target audio")
            return torch.zeros(2, 30 * 48000)
