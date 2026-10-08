"""Keep the Qwen3 LM inside float16's range when it runs in float16 (GPUs without bfloat16).

ACE-Step's 5 Hz LM (Qwen3, 1.7B) has one "massive activation": decoder layer 2's MLP writes
~2,000,000 into channel 1793 at the ``<|im_start|>`` token (an attention sink), and the SwiGLU
product feeding its ``down_proj`` is already ~85,000 -- both past float16's 65,504 (layer 27's
MLP output, ~68,000, is past it too). In float16 the logits turn NaN and every sampled token is
id 0 ('!').

Two changes, float16 only, numerically equivalent to the original model:
- each MLP's "up" weights are divided by ``MLP_SCALE`` and its output multiplied back by it in
  float32 (a power of two), keeping the product and ``down_proj`` in range;
- the residual stream is carried in float32 (RMSNorm.add_rms_forward), so the 2-million value
  never touches float16.
"""

import math

import torch
from torch import nn

# 2.08M / 128 = 16,264 for the 5 Hz LM's worst MLP: ~4x headroom (32 is the smallest that fits).
MLP_SCALE = 128.0


def apply_fp16_mlp_scale(model: nn.Module, factor: float = MLP_SCALE) -> int:
    """Divide every Qwen3 MLP's up projection by ``factor`` and make the MLP undo it in float32.

    Args:
        model: The loaded nano-vllm model (``Qwen3ForCausalLM``).
        factor: A power of two, so dividing and multiplying back loses nothing.

    Returns:
        How many MLPs were changed (0 if already applied).

    Raises:
        ValueError: If ``factor`` is not a positive power of two.
    """
    if factor <= 0 or math.frexp(factor)[0] != 0.5:
        raise ValueError(f"factor must be a positive power of two, got {factor}")
    changed = 0
    for module in model.modules():
        gate_up = getattr(module, "gate_up_proj", None)
        if gate_up is None or not hasattr(module, "out_scale") or module.out_scale != 1.0:
            continue
        with torch.no_grad():
            weight = gate_up.weight            # [gate; up] -- also per tensor-parallel shard
            weight[weight.shape[0] // 2:].div_(factor)
        module.out_scale = factor
        changed += 1
    return changed


def maybe_apply_fp16_range(model: nn.Module, dtype: torch.dtype) -> int:
    """Apply the MLP scale to a freshly loaded model if (and only if) it runs in float16.

    Args:
        model: The loaded nano-vllm model (``Qwen3ForCausalLM``).
        dtype: The dtype the model runs in (``ModelRunner.dtype``).

    Returns:
        How many MLPs were changed (0 for bfloat16 / float32 models).
    """
    if dtype != torch.float16:
        return 0
    return apply_fp16_mlp_scale(model)
