"""Restore saved LoRA adapter weights into a live decoder when resuming.

PEFT's ``save_pretrained`` strips the adapter name from tensor keys
(``...lora_A.weight``), while a live ``PeftModel`` names them
``...lora_A.default.weight``.  A plain ``load_state_dict(strict=False)``
therefore matches nothing and silently resumes from an untrained adapter.
This module loads through ``set_peft_model_state_dict`` (which restores the
adapter name) and refuses to continue when no saved tensor was applied.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import torch

logger = logging.getLogger(__name__)


class AdapterResumeError(RuntimeError):
    """Raised when checkpoint adapter weights cannot be applied to the model."""


def load_adapter_state_dict(decoder: Any, state_dict: Dict[str, torch.Tensor]) -> int:
    """Apply saved adapter weights to *decoder*.

    Args:
        decoder: The training decoder, usually a PEFT ``PeftModel``.
        state_dict: Tensors read from ``adapter_model.safetensors``.

    Returns:
        Number of saved tensors that were applied to the decoder.

    Raises:
        AdapterResumeError: If the file is empty or no tensor matches the decoder.
    """
    if not state_dict:
        raise AdapterResumeError("Checkpoint adapter file contains no tensors")

    if hasattr(decoder, "peft_config"):
        from peft import set_peft_model_state_dict

        result = set_peft_model_state_dict(decoder, state_dict)
    else:
        result = decoder.load_state_dict(state_dict, strict=False)

    unexpected = list(getattr(result, "unexpected_keys", None) or [])
    loaded = len(state_dict) - len(unexpected)
    if loaded <= 0:
        raise AdapterResumeError(
            "None of the checkpoint adapter weights match the model "
            "(check rank, alpha and target modules are identical to the original run)"
        )
    if unexpected:
        logger.warning(
            "[Side-Step] %d checkpoint tensors did not match the model, e.g. %s",
            len(unexpected),
            unexpected[0],
        )
    return loaded
