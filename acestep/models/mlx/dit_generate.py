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
    infer_steps: Optional[int] = None,
) -> List[float]:
    """Compute the timestep schedule for diffusion sampling.

    When ``infer_steps`` is provided and ``timesteps`` is None, a continuous
    linspace schedule is generated (matching the PyTorch base-model behaviour).
    The legacy lookup-table path (8-step ``SHIFT_TIMESTEPS``) is used only when
    neither ``timesteps`` nor ``infer_steps`` is supplied.

    Args:
        shift: Diffusion timestep shift (applied via ``shift*t / (1+(shift-1)*t)``).
        timesteps: Optional custom list of timesteps.
        infer_steps: Number of diffusion steps.  When given, overrides the
            fixed 8-step lookup table.

    Returns:
        List of timestep values (descending, without trailing 0).
    """
    t_schedule_list = None

    if timesteps is not None:
        ts_list = list(timesteps)
        while ts_list and ts_list[-1] == 0:
            ts_list.pop()
        if len(ts_list) < 1:
            logger.warning("timesteps empty after removing zeros; using default shift=%s", shift)
        else:
            if len(ts_list) > 20:
                logger.warning("timesteps length=%d > 20; truncating", len(ts_list))
                ts_list = ts_list[:20]
            mapped = [min(VALID_TIMESTEPS, key=lambda x, t=t: abs(x - t)) for t in ts_list]
            t_schedule_list = mapped

    if t_schedule_list is None and infer_steps is not None and infer_steps > 0:
        raw = [1.0 - i / infer_steps for i in range(infer_steps)]
        if shift != 1.0:
            raw = [shift * t / (1.0 + (shift - 1.0) * t) for t in raw]
        t_schedule_list = raw

    if t_schedule_list is None:
        original_shift = shift
        shift = min(VALID_SHIFTS, key=lambda x: abs(x - shift))
        if original_shift != shift:
            logger.warning("shift=%.2f rounded to nearest valid shift=%.1f", original_shift, shift)
        t_schedule_list = SHIFT_TIMESTEPS[shift]

    return t_schedule_list


def _mlx_apg_forward(
    pred_cond,
    pred_uncond,
    guidance_scale: float,
    momentum_state: Optional[Dict] = None,
    norm_threshold: float = 2.5,
):
    """APG (Adaptive Projected Guidance) in pure MLX — mirrors the PyTorch ``apg_forward``.

    Projection is performed along axis 1 (the time/sequence dimension) to match
    the PyTorch implementation which calls ``apg_forward(..., dims=[1])``.
    """
    import mlx.core as mx

    proj_axis = 1

    diff = pred_cond - pred_uncond
    if momentum_state is not None:
        diff = diff + momentum_state.get("running", 0)
        momentum_state["running"] = diff

    if norm_threshold > 0:
        diff_norm = mx.sqrt((diff * diff).sum(axis=proj_axis, keepdims=True))
        scale_factor = mx.minimum(mx.ones_like(diff_norm), norm_threshold / (diff_norm + 1e-8))
        diff = diff * scale_factor

    v1 = pred_cond / (mx.sqrt((pred_cond * pred_cond).sum(axis=proj_axis, keepdims=True)) + 1e-8)
    parallel = (diff * v1).sum(axis=proj_axis, keepdims=True) * v1
    orthogonal = diff - parallel

    return pred_cond + (guidance_scale - 1) * orthogonal


def mlx_generate_diffusion(
    mlx_decoder,
    encoder_hidden_states_np: np.ndarray,
    context_latents_np: np.ndarray,
    src_latents_shape: Tuple[int, ...],
    seed: Optional[Union[int, List[int]]] = None,
    infer_method: str = "ode",
    shift: float = 3.0,
    timesteps: Optional[list] = None,
    infer_steps: Optional[int] = None,
    guidance_scale: float = 1.0,
    null_condition_emb_np: Optional[np.ndarray] = None,
    cfg_interval_start: float = 0.0,
    cfg_interval_end: float = 1.0,
    audio_cover_strength: float = 1.0,
    encoder_hidden_states_non_cover_np: Optional[np.ndarray] = None,
    context_latents_non_cover_np: Optional[np.ndarray] = None,
    compile_model: bool = False,
    disable_tqdm: bool = False,
) -> Dict[str, object]:
    """Run the complete MLX diffusion loop with optional CFG guidance.

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
        infer_steps: number of diffusion steps.
        guidance_scale: CFG guidance strength (>1.0 enables CFG).
        null_condition_emb_np: [1, 1, D] null condition embedding for CFG.
        cfg_interval_start: timestep ratio below which CFG is disabled.
        cfg_interval_end: timestep ratio above which CFG is disabled.
        audio_cover_strength: cover strength (0-1).
        encoder_hidden_states_non_cover_np: optional [B, enc_L, D] for non-cover.
        context_latents_non_cover_np: optional [B, T, C] for non-cover.
        compile_model: If True, compile the decoder step with ``mx.compile``.
        disable_tqdm: If True, suppress the diffusion progress bar.

    Returns:
        Dict with ``"target_latents"`` (numpy) and ``"time_costs"`` dict.
    """
    import mlx.core as mx
    from .dit_model import MLXCrossAttentionCache

    time_costs = {}
    total_start = time.time()

    enc_hs = mx.array(encoder_hidden_states_np)
    ctx = mx.array(context_latents_np)

    enc_hs_nc = mx.array(encoder_hidden_states_non_cover_np) if encoder_hidden_states_non_cover_np is not None else None
    ctx_nc = mx.array(context_latents_non_cover_np) if context_latents_non_cover_np is not None else None

    bsz = src_latents_shape[0]
    T = src_latents_shape[1]
    C = src_latents_shape[2]

    # ---- CFG setup ----
    do_cfg = guidance_scale > 1.0 and null_condition_emb_np is not None
    null_cond = mx.array(null_condition_emb_np) if do_cfg else None
    if do_cfg:
        null_expanded = mx.broadcast_to(null_cond, enc_hs.shape)
        enc_hs = mx.concatenate([enc_hs, null_expanded], axis=0)
        ctx = mx.concatenate([ctx, ctx], axis=0)
        if enc_hs_nc is not None:
            null_expanded_nc = mx.broadcast_to(null_cond, enc_hs_nc.shape)
            enc_hs_nc = mx.concatenate([enc_hs_nc, null_expanded_nc], axis=0)
        if ctx_nc is not None:
            ctx_nc = mx.concatenate([ctx_nc, ctx_nc], axis=0)
    momentum_state: Optional[Dict] = {} if do_cfg else None

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
    t_schedule_list = get_timestep_schedule(shift, timesteps, infer_steps=infer_steps)
    num_steps = len(t_schedule_list)

    cover_steps = int(num_steps * audio_cover_strength)

    # ---- Prepare decoder step (compiled or plain with KV cache) ----
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
    _switched_to_non_cover = False

    for step_idx in tqdm(range(num_steps), desc="MLX DiT diffusion", disable=disable_tqdm):
        current_t = t_schedule_list[step_idx]

        # Switch to non-cover conditions when appropriate
        if step_idx >= cover_steps and not _switched_to_non_cover:
            _switched_to_non_cover = True
            if enc_hs_nc is not None:
                enc_hs = enc_hs_nc
                ctx = ctx_nc
            if cache is not None:
                cache = MLXCrossAttentionCache()

        # Build input: double batch for CFG
        x_in = mx.concatenate([xt, xt], axis=0) if do_cfg else xt
        t_curr = mx.full((x_in.shape[0],), current_t)

        if _compiled_step is not None:
            vt = _compiled_step(x_in, t_curr, t_curr, enc_hs, ctx)
        else:
            vt, cache = mlx_decoder(
                hidden_states=x_in,
                timestep=t_curr,
                timestep_r=t_curr,
                encoder_hidden_states=enc_hs,
                context_latents=ctx,
                cache=cache,
                use_cache=not do_cfg,
            )

        mx.eval(vt)

        # Apply CFG guidance
        if do_cfg:
            pred_cond = vt[:bsz]
            pred_uncond = vt[bsz:]
            apply_cfg = cfg_interval_start <= current_t <= cfg_interval_end
            if apply_cfg:
                vt = _mlx_apg_forward(pred_cond, pred_uncond, guidance_scale, momentum_state)
            else:
                vt = pred_cond

        # Final step: compute x0
        if step_idx == num_steps - 1:
            t_unsq = mx.full((bsz, 1, 1), current_t)
            xt = xt - vt * t_unsq
            mx.eval(xt)
        else:
            # ODE / SDE update
            next_t = t_schedule_list[step_idx + 1]
            if infer_method == "sde":
                t_unsq = mx.full((bsz, 1, 1), current_t)
                pred_clean = xt - vt * t_unsq
                new_noise = mx.random.normal(xt.shape)
                xt = next_t * new_noise + (1.0 - next_t) * pred_clean
            else:
                dt = current_t - next_t
                dt_arr = mx.full((bsz, 1, 1), dt)
                xt = xt - vt * dt_arr

            mx.eval(xt)

    diff_end = time.time()
    total_end = time.time()

    time_costs["diffusion_time_cost"] = diff_end - diff_start
    time_costs["diffusion_per_step_time_cost"] = time_costs["diffusion_time_cost"] / max(num_steps, 1)
    time_costs["total_time_cost"] = total_end - total_start

    result_np = np.array(xt)
    return {
        "target_latents": result_np,
        "time_costs": time_costs,
    }
