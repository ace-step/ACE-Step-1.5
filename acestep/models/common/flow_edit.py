"""Flow-edit sampling loop, shared across DiT base variants (issue #1156).

Ports ACE-Step 1.0's ``flowedit_diffusion_process``: edit an existing clip
toward a new caption/lyrics by integrating ``V_delta = V_tar - V_src`` over
a sub-window ``[n_min, n_max]`` of the diffusion schedule.

Edit window step::

    fwd_noise = randn(x_src.shape)                       # fresh per inner avg
    zt_src    = (1 - t) · x_src + t · fwd_noise
    zt_tar    = zt_edit + zt_src - x_src
    V_src, V_tar = paired_decoder_forward(...)            # may use CFG/APG
    V_delta_avg += (1/n_avg) · (V_tar - V_src)
    zt_edit   += (t_prev - t_curr) · V_delta_avg

After ``i ≥ n_max`` we Euler-step a target-only running variable
``xt_tar = zt_edit + xt_src - x_src``, denoising the edited content.

v1 supports euler + plain CFG + APG + CFG interval + velocity clamp/EMA,
all with **independent state per trajectory** (separate APG momentum,
prev_vt, KV cache for src and tar).  Inside the n_avg inner loop APG
momentum is snapshot-and-restored so each MC draw uses the same
pre-step state — without that the buffer would advance n_avg times,
making guidance depend on draw order.  EMA is applied once per step
on the averaged velocity.  DCW, heun, ADG are deferred to follow-ups.

Helpers live in :mod:`.flow_edit_helpers` per the 200 LOC module cap.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import torch
from loguru import logger
from tqdm import tqdm
from transformers.cache_utils import DynamicCache, EncoderDecoderCache

from .apg_guidance import MomentumBuffer
from .flow_edit_helpers import (
    apply_cfg_branch,
    apply_velocity_clamp,
    apply_velocity_ema,
    build_timestep_schedule,
    draw_fwd_noise,
    pack_for_cfg,
    restore_and_advance_momentum,
    snapshot_momentum,
)


@torch.no_grad()
def flowedit_sampling_loop(
    model,
    *,
    src_encoder_hidden_states: torch.Tensor,
    src_encoder_attention_mask: torch.Tensor,
    src_context_latents: torch.Tensor,
    tar_encoder_hidden_states: torch.Tensor,
    tar_encoder_attention_mask: torch.Tensor,
    tar_context_latents: torch.Tensor,
    src_latents: torch.Tensor,
    attention_mask: torch.Tensor,
    null_condition_emb: torch.Tensor,
    retake_generators: Optional[Any] = None,
    infer_steps: int = 60,
    timesteps: Optional[torch.Tensor] = None,
    shift: float = 1.0,
    diffusion_guidance_scale: float = 15.0,
    cfg_interval_start: float = 0.0,
    cfg_interval_end: float = 1.0,
    velocity_norm_threshold: float = 0.0,
    velocity_ema_factor: float = 0.0,
    n_min: float = 0.0,
    n_max: float = 1.0,
    n_avg: int = 1,
    use_progress_bar: bool = True,
) -> Dict[str, Any]:
    """Run the shared flow-edit sampling loop. See module docstring for the
    algorithm.  ``model`` is the DiT variant (must expose ``.decoder(...)``).
    Returns ``{"target_latents": zt_edit, "time_costs": {...}}``.
    """
    if n_avg < 1:
        raise ValueError(f"n_avg must be >= 1, got {n_avg}")
    if not 0.0 <= n_min <= n_max <= 1.0:
        raise ValueError(f"Expected 0<=n_min<=n_max<=1; got {n_min=}, {n_max=}")

    device, dtype, bsz = src_latents.device, src_latents.dtype, src_latents.shape[0]
    t = build_timestep_schedule(infer_steps, shift, timesteps, device, dtype)
    infer_steps = int(t.shape[0] - 1)
    n_min_step, n_max_step = int(infer_steps * n_min), int(infer_steps * n_max)
    zt_edit = src_latents.clone()
    do_cfg = diffusion_guidance_scale > 1.0

    src_pack = pack_for_cfg(
        src_encoder_hidden_states, src_encoder_attention_mask,
        src_context_latents, attention_mask, null_condition_emb, do_cfg,
    )
    tar_pack = pack_for_cfg(
        tar_encoder_hidden_states, tar_encoder_attention_mask,
        tar_context_latents, attention_mask, null_condition_emb, do_cfg,
    )

    src_kv = EncoderDecoderCache(DynamicCache(), DynamicCache())
    tar_kv = EncoderDecoderCache(DynamicCache(), DynamicCache())
    src_momentum, tar_momentum = MomentumBuffer(), MomentumBuffer()
    prev_vt_src: Optional[torch.Tensor] = None
    prev_vt_tar: Optional[torch.Tensor] = None
    xt_tar: Optional[torch.Tensor] = None  # post-window running variable
    iterator = zip(t[:-1], t[1:])
    if use_progress_bar:
        iterator = tqdm(iterator, total=infer_steps, desc="flow-edit")
    logger.info(
        "[flow_edit] start — infer_steps={}, n_min_step={}, n_max_step={}, n_avg={}, "
        "guidance_scale={:.2f}, cfg_interval=[{:.2f}, {:.2f}]",
        infer_steps, n_min_step, n_max_step, n_avg,
        diffusion_guidance_scale, cfg_interval_start, cfg_interval_end,
    )
    time_costs: Dict[str, float] = {}
    total_start = time.time()

    def _fwd(zt, pack, t_curr, kv):
        enc_hs, enc_am, ctx, attn = pack
        x = torch.cat([zt, zt], dim=0) if do_cfg else zt
        t_tensor = t_curr * torch.ones((x.shape[0],), device=device, dtype=dtype)
        out = model.decoder(
            hidden_states=x, timestep=t_tensor, timestep_r=t_tensor,
            attention_mask=attn, encoder_hidden_states=enc_hs,
            encoder_attention_mask=enc_am, context_latents=ctx,
            use_cache=True, past_key_values=kv,
        )
        return out[0], out[1]

    for step_idx, (t_curr, t_prev) in enumerate(iterator):
        if step_idx < n_min_step:
            continue
        t_curr_f = float(t_curr)
        apply_cfg_now = cfg_interval_start <= t_curr_f <= cfg_interval_end
        dt_b = (t_prev - t_curr).to(device=device, dtype=dtype) * torch.ones(
            (bsz, 1, 1), device=device, dtype=dtype,
        )

        if step_idx < n_max_step:
            # Snapshot APG so each MC draw starts from the same pre-step
            # momentum; we apply one update with the averaged diff after.
            src_pre, tar_pre = snapshot_momentum(src_momentum, tar_momentum)
            V_src_sum = torch.zeros_like(zt_edit)
            V_tar_sum = torch.zeros_like(zt_edit)
            diff_src_sum: Optional[torch.Tensor] = None
            diff_tar_sum: Optional[torch.Tensor] = None
            for _ in range(n_avg):
                src_momentum.running_average = src_pre
                tar_momentum.running_average = tar_pre
                fwd_noise = draw_fwd_noise(src_latents.shape, retake_generators, device, dtype)
                zt_src = (1.0 - t_curr_f) * src_latents + t_curr_f * fwd_noise
                zt_tar = zt_edit + zt_src - src_latents
                pred_src, src_kv = _fwd(zt_src, src_pack, t_curr, src_kv)
                pred_tar, tar_kv = _fwd(zt_tar, tar_pack, t_curr, tar_kv)
                if do_cfg and apply_cfg_now:
                    cs, us = pred_src.chunk(2)
                    ct, ut = pred_tar.chunk(2)
                    diff_src_sum = (cs - us) if diff_src_sum is None else diff_src_sum + (cs - us)
                    diff_tar_sum = (ct - ut) if diff_tar_sum is None else diff_tar_sum + (ct - ut)
                V_src = apply_cfg_branch(pred_src, do_cfg, apply_cfg_now,
                                         diffusion_guidance_scale, src_momentum)
                V_tar = apply_cfg_branch(pred_tar, do_cfg, apply_cfg_now,
                                         diffusion_guidance_scale, tar_momentum)
                V_src_sum = V_src_sum + apply_velocity_clamp(V_src, zt_src, velocity_norm_threshold)
                V_tar_sum = V_tar_sum + apply_velocity_clamp(V_tar, zt_tar, velocity_norm_threshold)
            restore_and_advance_momentum(
                src_momentum, tar_momentum, src_pre, tar_pre,
                None if diff_src_sum is None else diff_src_sum / n_avg,
                None if diff_tar_sum is None else diff_tar_sum / n_avg,
            )
            V_src_avg = apply_velocity_ema(V_src_sum / n_avg, prev_vt_src, velocity_ema_factor)
            V_tar_avg = apply_velocity_ema(V_tar_sum / n_avg, prev_vt_tar, velocity_ema_factor)
            prev_vt_src, prev_vt_tar = V_src_avg, V_tar_avg
            zt_edit = zt_edit + dt_b * (V_tar_avg - V_src_avg)
        else:
            if xt_tar is None:
                fwd_noise = draw_fwd_noise(src_latents.shape, retake_generators, device, dtype)
                xt_src = (1.0 - t_curr_f) * src_latents + t_curr_f * fwd_noise
                xt_tar = zt_edit + xt_src - src_latents
            pred_tar, tar_kv = _fwd(xt_tar, tar_pack, t_curr, tar_kv)
            V_tar = apply_cfg_branch(pred_tar, do_cfg, apply_cfg_now,
                                     diffusion_guidance_scale, tar_momentum)
            V_tar = apply_velocity_clamp(V_tar, xt_tar, velocity_norm_threshold)
            V_tar = apply_velocity_ema(V_tar, prev_vt_tar, velocity_ema_factor)
            prev_vt_tar = V_tar
            xt_tar = xt_tar + dt_b * V_tar

    elapsed = time.time() - total_start
    active_steps = max(1, infer_steps - n_min_step)
    time_costs["diffusion_time_cost"] = elapsed
    time_costs["diffusion_per_step_time_cost"] = elapsed / active_steps
    time_costs["total_time_cost"] = elapsed
    target_latents = zt_edit if xt_tar is None else xt_tar
    return {"target_latents": target_latents, "time_costs": time_costs}
