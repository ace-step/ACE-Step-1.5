# Weight conversion from PyTorch AutoencoderOobleck to native MLX format.
#
# Handles:
#   - weight_norm fusion:  weight_g + weight_v  →  fused weight
#   - Conv1d axis swap:    PT [out, in, K]      →  MLX [out, K, in]
#   - ConvTranspose1d:     PT [in, out, K]      →  MLX [out, K, in]
#   - Snake1d parameters:  PT [1, C, 1]         →  MLX [C]
#   - Bias:                no change

import logging
from typing import Dict, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def _fuse_weight_norm(
    weight_g: np.ndarray,
    weight_v: np.ndarray,
    eps: float = 1e-9,
) -> np.ndarray:
    """Fuse weight_norm parameters into a single weight tensor.

    weight_norm decomposes ``w = g * v / ||v||`` where:
        weight_g: per-output-channel scale  [out, 1, 1]  (Conv1d)
                  or [in, 1, 1] for ConvTranspose1d
        weight_v: direction tensor with same shape as the original weight

    Returns the fused weight in the *original PyTorch shape* (before axis swap).
    """
    v_flat = weight_v.reshape(weight_v.shape[0], -1)
    norm = np.linalg.norm(v_flat, axis=1).reshape(weight_g.shape)
    return weight_g * weight_v / (norm + eps)


def convert_vae_weights(
    pytorch_vae,
) -> List[Tuple[str, "mx.array"]]:
    """Convert PyTorch AutoencoderOobleck weights to MLX format.

    The function extracts the state dict from ``pytorch_vae`` and converts
    each parameter to the format expected by ``MLXAutoEncoderOobleck``,
    handling weight_norm fusion, Conv axis reordering, and Snake1d
    parameter reshaping.

    Args:
        pytorch_vae: A ``diffusers.AutoencoderOobleck`` instance.

    Returns:
        List of ``(param_name, mx.array)`` pairs for ``model.load_weights()``.
    """
    import mlx.core as mx

    state_dict = pytorch_vae.state_dict()
    weights: List[Tuple[str, "mx.array"]] = []
    processed: set = set()

    # Sort keys so we process weight_v / weight_g pairs together
    all_keys = sorted(state_dict.keys())

    for key in all_keys:
        if key in processed:
            continue

        # ------------------------------------------------------------------
        # 1) weight_norm fusion:  *_weight_g + *_weight_v  →  *.weight
        # ------------------------------------------------------------------
        if key.endswith(".weight_g"):
            # The companion weight_v key
            base = key[: -len(".weight_g")]
            v_key = base + ".weight_v"

            if v_key not in state_dict:
                logger.warning(
                    "[MLX-VAE] weight_g without weight_v: %s — skipping", key
                )
                processed.add(key)
                continue

            g = state_dict[key].detach().cpu().float().numpy()
            v = state_dict[v_key].detach().cpu().float().numpy()
            w = _fuse_weight_norm(g, v)

            # Determine layer type and swap axes
            if "conv_t1" in base:
                # ConvTranspose1d: PT [in, out, K] → MLX [out, K, in]
                w = w.transpose(1, 2, 0)
            else:
                # Conv1d: PT [out, in, K] → MLX [out, K, in]
                w = w.swapaxes(1, 2)

            new_key = base + ".weight"
            weights.append((new_key, mx.array(w)))
            processed.add(key)
            processed.add(v_key)
            continue

        if key.endswith(".weight_v"):
            # Will be / was handled together with weight_g above
            continue

        # ------------------------------------------------------------------
        # 2) Snake1d parameters:  PT [1, C, 1] → MLX [C]
        # ------------------------------------------------------------------
        if key.endswith(".alpha") or key.endswith(".beta"):
            val = state_dict[key].detach().cpu().float().numpy().squeeze()
            weights.append((key, mx.array(val)))
            processed.add(key)
            continue

        # ------------------------------------------------------------------
        # 3) Bias:  shape [C] — no transformation needed
        # ------------------------------------------------------------------
        if key.endswith(".bias"):
            val = state_dict[key].detach().cpu().float().numpy()
            weights.append((key, mx.array(val)))
            processed.add(key)
            continue

        # ------------------------------------------------------------------
        # 4) Catch-all for any remaining parameters (unlikely in this model)
        # ------------------------------------------------------------------
        val = state_dict[key].detach().cpu().float().numpy()
        logger.debug("[MLX-VAE] Pass-through key: %s  shape=%s", key, val.shape)
        weights.append((key, mx.array(val)))
        processed.add(key)

    logger.info(
        "[MLX-VAE] Converted %d parameters to MLX format.", len(weights)
    )
    return weights


def convert_and_load(
    pytorch_vae,
    mlx_vae: "MLXAutoEncoderOobleck",
) -> None:
    """Convert PyTorch VAE weights and load them into an MLX VAE.

    Args:
        pytorch_vae: ``diffusers.AutoencoderOobleck`` instance (PyTorch).
        mlx_vae: An ``MLXAutoEncoderOobleck`` instance (already constructed).
    """
    import mlx.core as mx

    weights = convert_vae_weights(pytorch_vae)
    mlx_vae.load_weights(weights)
    mx.eval(mlx_vae.parameters())
    logger.info("[MLX-VAE] Weights loaded and evaluated successfully.")
