"""Helper primitives for ``flow_edit.flowedit_sampling_loop`` (#1156).

Split out per the project's 200 LOC module cap.  Each helper is a small,
side-effect-free function that the main loop composes per step.
"""

from __future__ import annotations

from typing import Any, List, Optional

import torch

from .apg_guidance import MomentumBuffer, apg_forward


def build_timestep_schedule(
    infer_steps: int,
    shift: float,
    timesteps: Optional[torch.Tensor],
    device: torch.device,
    dtype: torch.dtype,
) -> torch.Tensor:
    """Return the closed timestep tensor of length ``infer_steps + 1``.

    Mirrors the base-variant logic: ``linspace(1, 0, n+1)`` optionally
    transformed by ``shift * t / (1 + (shift - 1) * t)``.  If the caller
    supplied a tensor we use it verbatim; if its tail is non-zero we
    pad a single zero so the schedule is closed.
    """
    if timesteps is not None:
        t = timesteps.to(device=device, dtype=dtype)
        if t.numel() == 0:
            raise ValueError("timesteps must contain at least one element")
        if t[-1].item() != 0.0:
            t = torch.cat([t, torch.zeros(1, device=device, dtype=dtype)])
        return t
    t = torch.linspace(1.0, 0.0, infer_steps + 1, device=device, dtype=dtype)
    if shift != 1.0:
        t = shift * t / (1 + (shift - 1) * t)
    return t


def apply_cfg_branch(
    pred: torch.Tensor,
    do_cfg: bool,
    apply_cfg_now: bool,
    guidance_scale: float,
    momentum_buffer: MomentumBuffer,
) -> torch.Tensor:
    """Reduce a ``(cond, null)``-packed prediction to a guided velocity.

    ``do_cfg`` is the global gate (``guidance_scale > 1``).
    ``apply_cfg_now`` is the per-step gate (timestep within
    ``[cfg_interval_start, cfg_interval_end]``).  The momentum buffer is
    *per trajectory* — flow-edit maintains separate buffers for src and
    tar so APG's running average doesn't leak between branches.
    """
    if not do_cfg:
        return pred
    pred_cond, pred_null = pred.chunk(2)
    if not apply_cfg_now:
        return pred_cond
    return apg_forward(
        pred_cond=pred_cond,
        pred_uncond=pred_null,
        guidance_scale=guidance_scale,
        momentum_buffer=momentum_buffer,
        dims=[1],
    )


def apply_velocity_clamp(
    vt: torch.Tensor,
    xt: torch.Tensor,
    norm_threshold: float,
) -> torch.Tensor:
    """Per-trajectory velocity-norm clamp.  No-op when ``norm_threshold <= 0``."""
    if norm_threshold <= 0.0:
        return vt
    vt_norm = torch.norm(vt, dim=(1, 2), keepdim=True)
    xt_norm = torch.norm(xt, dim=(1, 2), keepdim=True) + 1e-10
    scale = torch.clamp(norm_threshold * xt_norm / (vt_norm + 1e-10), max=1.0)
    return vt * scale


def apply_velocity_ema(
    vt: torch.Tensor,
    prev_vt: Optional[torch.Tensor],
    ema_factor: float,
) -> torch.Tensor:
    """EMA smoothing across *timesteps* (not across n_avg draws).

    Caller is responsible for invoking this once per scheduler step on
    the averaged velocity.  Applying it inside the n_avg loop with a
    mutating ``prev_vt`` would leak earlier draws into later ones.
    """
    if ema_factor <= 0.0 or prev_vt is None:
        return vt
    return (1.0 - ema_factor) * vt + ema_factor * prev_vt


def snapshot_momentum(
    src_momentum: MomentumBuffer,
    tar_momentum: MomentumBuffer,
):
    """Capture the running averages so the inner n_avg loop can reset them.

    APG's running average is meant to advance *once per scheduler step*;
    if we let ``apply_cfg_branch`` mutate the buffer on every n_avg
    draw, guidance becomes draw-order- and ``n_avg``-dependent.  Pair
    this with :func:`restore_and_advance_momentum` after the loop.
    """
    return src_momentum.running_average, tar_momentum.running_average


def restore_and_advance_momentum(
    src_momentum: MomentumBuffer,
    tar_momentum: MomentumBuffer,
    src_pre,
    tar_pre,
    avg_diff_src: Optional[torch.Tensor],
    avg_diff_tar: Optional[torch.Tensor],
) -> None:
    """Reset to pre-step state and advance once with the averaged diff.

    ``avg_diff_*`` is ``None`` when CFG was inactive this step (no
    averaged diff exists); in that case the buffer simply rolls back
    to its pre-step state.
    """
    src_momentum.running_average = src_pre
    tar_momentum.running_average = tar_pre
    if avg_diff_src is not None:
        src_momentum.update(avg_diff_src)
    if avg_diff_tar is not None:
        tar_momentum.update(avg_diff_tar)


def draw_fwd_noise(
    shape,
    generator: Any,
    device: torch.device,
    dtype: torch.dtype,
) -> torch.Tensor:
    """Generator-aware ``randn`` for per-step forward-diffusion noise.

    ``generator`` may be ``None`` (fully random), a single
    ``torch.Generator``, or a list of per-sample generators (matches the
    semantics of the model's ``prepare_noise`` so ``retake_seeds`` flow
    through unchanged).
    """
    if generator is None:
        return torch.randn(shape, device=device, dtype=dtype)
    if isinstance(generator, list):
        parts: List[torch.Tensor] = []
        for g in generator:
            if g is None:
                parts.append(torch.randn((1, *shape[1:]), device=device, dtype=dtype))
            else:
                parts.append(
                    torch.randn((1, *shape[1:]), generator=g, device=device, dtype=dtype)
                )
        return torch.cat(parts, dim=0)
    return torch.randn(shape, generator=generator, device=device, dtype=dtype)


def pack_for_cfg(
    enc_hs: torch.Tensor,
    enc_am: torch.Tensor,
    ctx: torch.Tensor,
    attn: torch.Tensor,
    null_condition_emb: torch.Tensor,
    do_cfg: bool,
):
    """Double encoder/context/attention tensors for CFG, or pass through.

    Returns a 4-tuple ``(enc_hs, enc_am, ctx, attn)`` ready for one
    ``decoder()`` call.  Source and target each call this independently
    so their CFG packs stay separate.
    """
    if not do_cfg:
        return enc_hs, enc_am, ctx, attn
    null = null_condition_emb.expand_as(enc_hs)
    return (
        torch.cat([enc_hs, null], dim=0),
        torch.cat([enc_am, enc_am], dim=0),
        torch.cat([ctx, ctx], dim=0),
        torch.cat([attn, attn], dim=0),
    )
