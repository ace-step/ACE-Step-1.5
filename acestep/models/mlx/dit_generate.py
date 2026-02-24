# MLX diffusion generation loop for AceStep DiT decoder.
#
# Replicates the timestep scheduling and ODE/SDE stepping from
# ``AceStepConditionGenerationModel.generate_audio`` using pure MLX arrays.

import logging
import time
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
from tqdm import tqdm

logger = logging.getLogger(__name__)

# Pre-defined timestep schedules (from modeling_acestep_v15_turbo.py)
VALID_SHIFTS = [1.0, 2.0, 3.0]

VALID_TIMESTEPS = [
    1.0, 0.9545454545454546, 0.9333333333333333, 0.9, 0.875,
    0.8571428571428571, 0.8333333333333334, 0.7692307692307693, 0.75,
    0.6666666666666666, 0.6428571428571429, 0.625, 0.5454545454545454,
    0.5, 0.4, 0.375, 0.3, 0.25, 0.2222222222222222, 0.125,
]

SHIFT_TIMESTEPS = {
    1.0: [1.0, 0.875, 0.75, 0.625, 0.5, 0.375, 0.25, 0.125],
    2.0: [1.0, 0.9333333333333333, 0.8571428571428571, 0.7692307692307693,
          0.6666666666666666, 0.5454545454545454, 0.4, 0.2222222222222222],
    3.0: [1.0, 0.9545454545454546, 0.9, 0.8333333333333334, 0.75,
          0.6428571428571429, 0.5, 0.3],
}


def get_timestep_schedule(
    shift: float = 3.0,
    timesteps: Optional[list] = None,
) -> List[float]:
    """Compute the timestep schedule for diffusion sampling.

    Replicates the logic from the turbo model's ``generate_audio`` method.

    Args:
        shift: Diffusion timestep shift (1, 2, or 3).
        timesteps: Optional custom list of timesteps.

    Returns:
        List of timestep values (descending, without trailing 0).
    """
    t_schedule_list = None

    if timesteps is not None:
        ts_list = list(timesteps)
        # Remove trailing zeros
        while ts_list and ts_list[-1] == 0:
            ts_list.pop()
        if len(ts_list) < 1:
            logger.warning("timesteps empty after removing zeros; using default shift=%s", shift)
        else:
            if len(ts_list) > 20:
                logger.warning("timesteps length=%d > 20; truncating", len(ts_list))
                ts_list = ts_list[:20]
            # Map each timestep to the nearest valid value
            mapped = [min(VALID_TIMESTEPS, key=lambda x, t=t: abs(x - t)) for t in ts_list]
            t_schedule_list = mapped

    if t_schedule_list is None:
        original_shift = shift
        shift = min(VALID_SHIFTS, key=lambda x: abs(x - shift))
        if original_shift != shift:
            logger.warning("shift=%.2f rounded to nearest valid shift=%.1f", original_shift, shift)
        t_schedule_list = SHIFT_TIMESTEPS[shift]

    return t_schedule_list


def mlx_generate_diffusion(
    mlx_decoder,
    encoder_hidden_states_np: np.ndarray,
    context_latents_np: np.ndarray,
    src_latents_shape: Tuple[int, ...],
    seed: Optional[Union[int, List[int]]] = None,
    infer_method: str = "ode",
    shift: float = 3.0,
    timesteps: Optional[list] = None,
    audio_cover_strength: float = 1.0,
    encoder_hidden_states_non_cover_np: Optional[np.ndarray] = None,
    context_latents_non_cover_np: Optional[np.ndarray] = None,
    compile_model: bool = False,
    disable_tqdm: bool = False,
) -> Dict[str, object]:
    """Run the complete MLX diffusion loop.

    This is the core generation function.  It accepts numpy arrays (converted
    from PyTorch tensors by the handler) and returns numpy arrays that the
    handler converts back to PyTorch.

    Args:
        mlx_decoder: ``MLXDiTDecoder`` instance with loaded weights.
        encoder_hidden_states_np: [B, enc_L, D] from prepare_condition (numpy).
        context_latents_np: [B, T, C] from prepare_condition (numpy).
        src_latents_shape: shape tuple [B, T, 64] for noise generation.
        seed: random seed (int, list[int], or None).
        infer_method: "ode" or "sde".
        shift: timestep shift factor.
        timesteps: optional custom timestep list.
        audio_cover_strength: cover strength (0-1).
        encoder_hidden_states_non_cover_np: optional [B, enc_L, D] for non-cover.
        context_latents_non_cover_np: optional [B, T, C] for non-cover.
        compile_model: If True, compile the decoder step with ``mx.compile``
            for kernel fusion. Cross-attention KV caching is disabled under
            compilation; the fused kernels typically offset this cost.
            Falls back to uncompiled path on failure.
        disable_tqdm: If True, suppress the diffusion progress bar.

    Returns:
        Dict with ``"target_latents"`` (numpy) and ``"time_costs"`` dict.
    """
    import mlx.core as mx
    from .dit_model import MLXCrossAttentionCache

    time_costs = {}
    total_start = time.time()

    # Convert numpy arrays to MLX
    enc_hs = mx.array(encoder_hidden_states_np)
    ctx = mx.array(context_latents_np)

    enc_hs_nc = mx.array(encoder_hidden_states_non_cover_np) if encoder_hidden_states_non_cover_np is not None else None
    ctx_nc = mx.array(context_latents_non_cover_np) if context_latents_non_cover_np is not None else None

    bsz = src_latents_shape[0]
    T = src_latents_shape[1]
    C = src_latents_shape[2]

    # ---- Noise preparation ----
    if seed is None:
        noise = mx.random.normal((bsz, T, C))
    elif isinstance(seed, list):
        parts = []
        for s in seed:
            if s is None or s < 0:
                parts.append(mx.random.normal((1, T, C)))
            else:
                key = mx.random.key(int(s))
                parts.append(mx.random.normal((1, T, C), key=key))
        noise = mx.concatenate(parts, axis=0)
    else:
        key = mx.random.key(int(seed))
        noise = mx.random.normal((bsz, T, C), key=key)

    # ---- Timestep schedule ----
    t_schedule_list = get_timestep_schedule(shift, timesteps)
    num_steps = len(t_schedule_list)

    cover_steps = int(num_steps * audio_cover_strength)

    # ---- Prepare decoder step (compiled or plain with KV cache) ----
    # When compiled, we wrap the decoder call in mx.compile for kernel fusion.
    # Cross-attention KV caching is incompatible with mx.compile graph tracing
    # (cache uses Python dicts with dynamic branching), so it is disabled.
    # The kernel fusion from compilation typically offsets this cost.
    _compiled_step = None
    if compile_model:
        def _raw_step(xt, t, tr, enc, ctx):
            vt, _ = mlx_decoder(
                hidden_states=xt, timestep=t, timestep_r=tr,
                encoder_hidden_states=enc, context_latents=ctx,
                cache=None, use_cache=False,
            )
            return vt

        try:
            _compiled_step = mx.compile(_raw_step)
            logger.info("[MLX-DiT] Diffusion step compiled with mx.compile().")
        except Exception as exc:
            logger.warning(
                "[MLX-DiT] mx.compile() failed (%s); using uncompiled path.", exc
            )

    cache = MLXCrossAttentionCache() if _compiled_step is None else None
    xt = noise

    diff_start = time.time()

    for step_idx in tqdm(range(num_steps), desc="MLX DiT diffusion", disable=disable_tqdm):
        current_t = t_schedule_list[step_idx]
        t_curr = mx.full((bsz,), current_t)

        # Switch to non-cover conditions when appropriate
        if step_idx >= cover_steps and enc_hs_nc is not None:
            enc_hs = enc_hs_nc
            ctx = ctx_nc
            if cache is not None:
                cache = MLXCrossAttentionCache()

        if _compiled_step is not None:
            vt = _compiled_step(xt, t_curr, t_curr, enc_hs, ctx)
        else:
            vt, cache = mlx_decoder(
                hidden_states=xt,
                timestep=t_curr,
                timestep_r=t_curr,
                encoder_hidden_states=enc_hs,
                context_latents=ctx,
                cache=cache,
                use_cache=True,
            )

        # Evaluate to ensure computation is complete before next step
        mx.eval(vt)

        # Final step: compute x0
        if step_idx == num_steps - 1:
            t_unsq = mx.expand_dims(mx.expand_dims(t_curr, axis=-1), axis=-1)
            xt = xt - vt * t_unsq
            mx.eval(xt)
        else:
            # ODE / SDE update
            next_t = t_schedule_list[step_idx + 1]
            if infer_method == "sde":
                t_unsq = mx.expand_dims(mx.expand_dims(t_curr, axis=-1), axis=-1)
                pred_clean = xt - vt * t_unsq
                # Re-noise with next timestep
                new_noise = mx.random.normal(xt.shape)
                xt = next_t * new_noise + (1.0 - next_t) * pred_clean
            else:
                # ODE Euler step: x_{t+1} = x_t - v_t * dt
                dt = current_t - next_t
                dt_arr = mx.full((bsz, 1, 1), dt)
                xt = xt - vt * dt_arr

            mx.eval(xt)

    diff_end = time.time()
    total_end = time.time()

    time_costs["diffusion_time_cost"] = diff_end - diff_start
    time_costs["diffusion_per_step_time_cost"] = time_costs["diffusion_time_cost"] / max(num_steps, 1)
    time_costs["total_time_cost"] = total_end - total_start

    # Convert result back to numpy
    result_np = np.array(xt)
    return {
        "target_latents": result_np,
        "time_costs": time_costs,
    }
