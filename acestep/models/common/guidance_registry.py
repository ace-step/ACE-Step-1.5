"""Pluggable guidance-variant registry for DiT diffusion samplers.

This module decouples the choice of classifier-free-guidance style (APG, CFG,
ADG family) from the sampler call sites.  The sampler holds a single
``guidance_state`` dictionary for the lifetime of one ``generate_audio`` call
and supplies per-step values (``latents``, ``sigma``) via that dictionary
before invoking the selected guidance function.

Wrapper signature
-----------------
Every registered guidance function obeys the following callable contract::

    fn(pred_cond, pred_uncond, guidance_scale, state, **params) -> Tensor

* ``pred_cond`` / ``pred_uncond`` — conditional / unconditional model
  predictions for the current step.
* ``guidance_scale`` — CFG-style guidance strength.
* ``state`` — mutable per-generation dictionary.  Wrappers read per-step
  values such as ``state["latents"]`` and ``state["sigma"]`` and are free to
  store cross-step bookkeeping (for example the APG momentum buffer) in it.
  The dictionary is created empty by the sampler and discarded when the
  ``generate_audio`` call returns.
* ``**params`` — static, user-configurable variant parameters (for example
  ``eta``, ``norm_threshold``, ``angle_clip``).

Wrappers do NOT modify the raw functions in ``apg_guidance.py``; they are a
thin translation layer that calls into them with the required per-variant
arguments.

A small ``state["step_role"]`` convention — ``"main"`` (default) versus
``"corrector"`` — keeps the Heun second-order sampler byte-compatible with
the pre-refactor behaviour:

* APG corrector steps fall back to plain CFG to avoid mutating the momentum
  buffer twice per step.
* ADG corrector steps degrade to CFG when ``sigma == 0`` to avoid NaNs from
  the division by sigma inside ``adg_forward``.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Protocol

import torch

from acestep.models.common.apg_guidance import (
    MomentumBuffer,
    adg_forward,
    adg_w_norm_forward,
    adg_wo_clip_forward,
    apg_forward,
    cfg_forward,
)


_MOMENTUM_KEY = "_apg_momentum_buffer"
_STEP_ROLE_MAIN = "main"
_STEP_ROLE_CORRECTOR = "corrector"


class GuidanceFn(Protocol):
    """Callable contract for guidance-variant wrappers."""

    def __call__(
        self,
        pred_cond: torch.Tensor,
        pred_uncond: torch.Tensor,
        guidance_scale: float,
        state: Dict[str, Any],
        **params: Any,
    ) -> torch.Tensor: ...


_GUIDANCE_REGISTRY: Dict[str, GuidanceFn] = {}


def register_guidance(name: str) -> Callable[[GuidanceFn], GuidanceFn]:
    """Register ``fn`` in the global guidance registry under ``name``."""

    def decorator(fn: GuidanceFn) -> GuidanceFn:
        _GUIDANCE_REGISTRY[name] = fn
        return fn

    return decorator


def get_guidance_fn(name: str) -> GuidanceFn:
    """Look up a registered guidance wrapper by name.

    Raises:
        ValueError: when ``name`` is not present in the registry.  The
            message enumerates the currently registered variants so callers
            can quickly see the valid set.
    """

    try:
        return _GUIDANCE_REGISTRY[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown guidance_variant: {name}. "
            f"Registered: {list(_GUIDANCE_REGISTRY)}"
        ) from exc


def registered_guidance_names() -> list[str]:
    """Return the sorted list of currently registered guidance variant names."""

    return sorted(_GUIDANCE_REGISTRY.keys())


def _get_step_role(state: Dict[str, Any]) -> str:
    """Read the current sampler step role from ``state`` (default: main)."""

    return state.get("step_role", _STEP_ROLE_MAIN)


@register_guidance("apg_classic")
def guidance_apg_classic(
    pred_cond: torch.Tensor,
    pred_uncond: torch.Tensor,
    guidance_scale: float,
    state: Dict[str, Any],
    *,
    eta: float = 0.0,
    norm_threshold: float = 2.5,
    momentum: float = -0.75,
    dims: Any = (1,),
) -> torch.Tensor:
    """Adaptive Projected Guidance (APG) with momentum carry-over.

    On the main sampler step the wrapper calls ``apg_forward`` and uses a
    ``MomentumBuffer`` kept in ``state`` so momentum accumulates across
    timesteps.  On Heun corrector steps the wrapper falls back to plain CFG
    to avoid updating the momentum buffer twice per step — this matches the
    pre-registry behaviour exactly.
    """

    if _get_step_role(state) == _STEP_ROLE_CORRECTOR:
        return cfg_forward(pred_cond, pred_uncond, guidance_scale)

    buffer = state.get(_MOMENTUM_KEY)
    if buffer is None:
        buffer = MomentumBuffer(momentum=momentum)
        state[_MOMENTUM_KEY] = buffer

    return apg_forward(
        pred_cond=pred_cond,
        pred_uncond=pred_uncond,
        guidance_scale=guidance_scale,
        momentum_buffer=buffer,
        eta=eta,
        norm_threshold=norm_threshold,
        dims=list(dims),
    )


@register_guidance("cfg")
def guidance_cfg(
    pred_cond: torch.Tensor,
    pred_uncond: torch.Tensor,
    guidance_scale: float,
    state: Dict[str, Any],
    **_: Any,
) -> torch.Tensor:
    """Classic classifier-free guidance.

    Note: when ``guidance_scale == 1.0`` the formula collapses to
    ``pred_cond`` by construction, so no special-case handling is required.
    """

    del state  # CFG has no cross-step state.
    return cfg_forward(pred_cond, pred_uncond, guidance_scale)


def _resolve_adg_latents_and_sigma(state: Dict[str, Any]) -> tuple[torch.Tensor, Any]:
    """Extract per-step ``latents`` and ``sigma`` required by ADG variants."""

    try:
        latents = state["latents"]
        sigma = state["sigma"]
    except KeyError as exc:  # pragma: no cover - defensive only
        raise KeyError(
            "ADG guidance requires 'latents' and 'sigma' in the guidance state dict."
        ) from exc
    return latents, sigma


def _adg_corrector_safe(
    pred_cond: torch.Tensor,
    pred_uncond: torch.Tensor,
    guidance_scale: float,
    latents: torch.Tensor,
    sigma: Any,
    adg_caller: Callable[..., torch.Tensor],
    **adg_kwargs: Any,
) -> torch.Tensor:
    """Apply ADG on the Heun corrector, degrading to CFG when ``sigma == 0``.

    ``adg_forward`` divides by ``sigma`` to recover a velocity from a latent
    delta, so the last corrector step (where ``t_prev == 0``) must fall back
    to plain CFG to keep the output finite.  This mirrors the pre-registry
    hand-written branch in the sampler.
    """

    sigma_scalar = float(sigma) if not torch.is_tensor(sigma) else float(sigma.detach().cpu().item())
    if sigma_scalar <= 0.0:
        return cfg_forward(pred_cond, pred_uncond, guidance_scale)
    return adg_caller(
        latents=latents,
        noise_pred_cond=pred_cond,
        noise_pred_uncond=pred_uncond,
        sigma=sigma,
        guidance_scale=guidance_scale,
        **adg_kwargs,
    )


@register_guidance("adg")
def guidance_adg(
    pred_cond: torch.Tensor,
    pred_uncond: torch.Tensor,
    guidance_scale: float,
    state: Dict[str, Any],
    *,
    angle_clip: float = 3.14 / 6,
) -> torch.Tensor:
    """Angle-based Dynamic Guidance (ADG) with angle clipping enabled."""

    latents, sigma = _resolve_adg_latents_and_sigma(state)
    if _get_step_role(state) == _STEP_ROLE_CORRECTOR:
        return _adg_corrector_safe(
            pred_cond,
            pred_uncond,
            guidance_scale,
            latents,
            sigma,
            adg_forward,
            angle_clip=angle_clip,
        )
    return adg_forward(
        latents=latents,
        noise_pred_cond=pred_cond,
        noise_pred_uncond=pred_uncond,
        sigma=sigma,
        guidance_scale=guidance_scale,
        angle_clip=angle_clip,
    )


@register_guidance("adg_w_norm")
def guidance_adg_w_norm(
    pred_cond: torch.Tensor,
    pred_uncond: torch.Tensor,
    guidance_scale: float,
    state: Dict[str, Any],
    *,
    angle_clip: float = 3.14 / 3,
) -> torch.Tensor:
    """ADG variant that renormalises the final latent to preserve magnitude."""

    latents, sigma = _resolve_adg_latents_and_sigma(state)
    if _get_step_role(state) == _STEP_ROLE_CORRECTOR:
        return _adg_corrector_safe(
            pred_cond,
            pred_uncond,
            guidance_scale,
            latents,
            sigma,
            adg_w_norm_forward,
            angle_clip=angle_clip,
        )
    return adg_w_norm_forward(
        latents=latents,
        noise_pred_cond=pred_cond,
        noise_pred_uncond=pred_uncond,
        sigma=sigma,
        guidance_scale=guidance_scale,
        angle_clip=angle_clip,
    )


@register_guidance("adg_wo_clip")
def guidance_adg_wo_clip(
    pred_cond: torch.Tensor,
    pred_uncond: torch.Tensor,
    guidance_scale: float,
    state: Dict[str, Any],
) -> torch.Tensor:
    """ADG variant with angle clipping disabled (unbounded angle update)."""

    latents, sigma = _resolve_adg_latents_and_sigma(state)
    if _get_step_role(state) == _STEP_ROLE_CORRECTOR:
        return _adg_corrector_safe(
            pred_cond,
            pred_uncond,
            guidance_scale,
            latents,
            sigma,
            adg_wo_clip_forward,
        )
    return adg_wo_clip_forward(
        latents=latents,
        noise_pred_cond=pred_cond,
        noise_pred_uncond=pred_uncond,
        sigma=sigma,
        guidance_scale=guidance_scale,
    )
