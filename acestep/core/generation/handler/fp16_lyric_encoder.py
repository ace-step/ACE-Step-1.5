"""Compute the lyric encoder's overflowing projection in float32 when the model runs in float16.

On GPUs without bfloat16 (Volta, Turing, Pascal) the model runs in float16. The lyric encoder's
last MLP projection reaches |x| ~ 505,000 on ordinary lyrics -- past float16's 65,504 -- so every
latent turns NaN for songs with lyrics, while instrumentals work (issue #1055). Everything before
that projection stays under ~11,500 (float32 measurements), and the stream goes straight into the
encoder's final norm after it, so only that one projection needs float32.
"""

from typing import Optional

import torch
from loguru import logger


class Float32Linear(torch.nn.Linear):
    """A Linear that computes in float32 from weights stored in any dtype, autocast or not."""

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Return the linear projection of ``x``, computed in float32."""
        with torch.autocast(device_type=x.device.type, enabled=False):
            bias = None if self.bias is None else self.bias.float()
            return torch.nn.functional.linear(x.float(), self.weight.float(), bias)


def _cast_to_weight_dtype(
    module: torch.nn.Module, args: tuple, output: torch.Tensor
) -> torch.Tensor:
    """Forward hook: cast a norm's output back to the dtype of the norm's weight."""
    return output.to(module.weight.dtype)


def _last_down_proj(encoder: torch.nn.Module) -> Optional[torch.nn.Module]:
    """Return the MLP down-projection of the last layer the encoder's forward runs, or None."""
    layers = getattr(encoder, "layers", None)
    if not isinstance(layers, torch.nn.ModuleList):
        return None
    # AceStepLyricEncoder.forward runs layers[: config.num_hidden_layers].
    used = getattr(getattr(encoder, "config", None), "num_hidden_layers", None)
    ran = layers[:used] if isinstance(used, int) else layers
    if len(ran) == 0:
        return None
    return getattr(getattr(ran[-1], "mlp", None), "down_proj", None)


def compute_lyric_encoder_tail_in_float32(model: torch.nn.Module) -> bool:
    """Make the lyric encoder's last MLP projection compute in float32.

    The projection's weights stay as they are (upcast on the fly, so a later
    ``model.to(dtype=...)``, e.g. CPU offload, cannot undo it); the residual add promotes to
    float32 and a hook casts the final norm's output back to the model dtype.

    Args:
        model: The loaded ACE-Step model (``model.encoder.lyric_encoder``).

    Returns:
        True if the lyric encoder has that shape and is now (or already was) patched.
    """
    encoder = getattr(getattr(model, "encoder", None), "lyric_encoder", None)
    if not isinstance(encoder, torch.nn.Module):
        return False
    norm = getattr(encoder, "norm", None)
    down = _last_down_proj(encoder)
    if isinstance(down, Float32Linear):
        return True
    if type(down) is not torch.nn.Linear or not isinstance(norm, torch.nn.Module):
        return False
    down.__class__ = Float32Linear
    norm.register_forward_hook(_cast_to_weight_dtype)
    return True


def apply_float16_lyric_encoder_fix(model: torch.nn.Module) -> None:
    """Apply ``compute_lyric_encoder_tail_in_float32`` to a float16 model and log the outcome."""
    if compute_lyric_encoder_tail_in_float32(model):
        logger.info(
            "[initialize_service] float16 model: lyric encoder's last projection runs in float32."
        )
    else:
        logger.warning(
            "[initialize_service] float16 model: lyric encoder not recognised; "
            "songs with lyrics may come out NaN."
        )
