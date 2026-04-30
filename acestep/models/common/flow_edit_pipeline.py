"""High-level flow-edit entrypoint shared by 4 base DiT variants (#1156).

Each variant exposes a thin ``flowedit_generate_audio`` method that
delegates here.  This module wraps :func:`flow_edit.flowedit_sampling_loop`
with model-side glue: it builds source and target conditions via
``model.prepare_condition`` and threads through the v1 sampler-trick
exclusions (DCW / heun / ADG → forced off with one log line).

Kept separate from ``flow_edit.py`` to honour the 200 LOC module cap.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

import torch
from loguru import logger

from .flow_edit import flowedit_sampling_loop


def _seed_to_generators(
    seed: Optional[Union[int, List[Optional[int]]]],
    batch_size: int,
    device: torch.device,
) -> Optional[Union[torch.Generator, List[Optional[torch.Generator]]]]:
    """Convert seed input to ``torch.Generator``(s) for ``draw_fwd_noise``.

    Mirrors ``prepare_noise`` semantics: ``None`` → unseeded; ``int`` →
    one generator; ``list[int|None]`` → per-sample generators (with
    ``None``/negative entries left unseeded).
    """
    if seed is None:
        return None
    if isinstance(seed, list):
        gens: List[Optional[torch.Generator]] = []
        for s in seed:
            if s is None or (isinstance(s, int) and s < 0):
                gens.append(None)
            else:
                gens.append(torch.Generator(device=device).manual_seed(int(s)))
        # Pad / truncate to batch_size.
        if len(gens) < batch_size:
            gens = gens + [None] * (batch_size - len(gens))
        return gens[:batch_size]
    return torch.Generator(device=device).manual_seed(int(seed))


def _warn_about_disabled_v1_tricks(
    sampler_mode: str,
    use_adg: bool,
    dcw_enabled: bool,
) -> None:
    """One info log if user-supplied sampler tricks are silently bypassed.

    DCW / heun / ADG are deferred to follow-up PRs (each needs paired-
    forward derivation).  v1 forces them off; this surface lets the user
    see why their UI knobs didn't take effect.
    """
    disabled = []
    if sampler_mode == "heun":
        disabled.append("sampler_mode=heun")
    if use_adg:
        disabled.append("use_adg=True")
    if dcw_enabled:
        disabled.append("dcw_enabled=True")
    if disabled:
        logger.info(
            "[flowedit] overlay v1 ignores {}; forcing euler + plain "
            "CFG/APG.  See issue #1156 for the per-feature follow-up plan.",
            ", ".join(disabled),
        )


@torch.no_grad()
def flowedit_generate_audio(
    model,
    *,
    # Source condition raw inputs
    text_hidden_states: torch.Tensor,
    text_attention_mask: torch.Tensor,
    lyric_hidden_states: torch.Tensor,
    lyric_attention_mask: torch.Tensor,
    refer_audio_acoustic_hidden_states_packed: torch.Tensor,
    refer_audio_order_mask: torch.Tensor,
    src_latents: torch.Tensor,
    chunk_masks: torch.Tensor,
    is_covers: torch.Tensor,
    silence_latent: torch.Tensor,
    # Target condition raw inputs (separate prompt/lyrics)
    target_text_hidden_states: torch.Tensor,
    target_text_attention_mask: torch.Tensor,
    target_lyric_hidden_states: torch.Tensor,
    target_lyric_attention_mask: torch.Tensor,
    # Sampling
    attention_mask: Optional[torch.Tensor] = None,
    seed: Optional[Union[int, List[int]]] = None,
    retake_seed: Optional[Union[int, List[int]]] = None,
    infer_steps: int = 60,
    timesteps: Optional[torch.Tensor] = None,
    diffusion_guidance_scale: float = 15.0,
    cfg_interval_start: float = 0.0,
    cfg_interval_end: float = 1.0,
    shift: float = 1.0,
    velocity_norm_threshold: float = 0.0,
    velocity_ema_factor: float = 0.0,
    use_progress_bar: bool = True,
    # Flow-edit window
    edit_n_min: float = 0.0,
    edit_n_max: float = 1.0,
    edit_n_avg: int = 1,
    # Conditioning hints (forwarded to both prepare_condition calls — they
    # describe the *source audio*, which is shared across src and tar).
    precomputed_lm_hints_25Hz: Optional[torch.Tensor] = None,
    audio_codes: Optional[torch.Tensor] = None,
    # Override for the audio-context input to ``prepare_condition``.
    # text2music callers pass ``silence`` here so V_delta is purely
    # text-driven; defaults to ``src_latents`` for back-compat.
    ctx_src_latents: Optional[torch.Tensor] = None,
    # Accepted-but-disabled v1 sampler tricks (logged + bypassed)
    sampler_mode: str = "euler",
    use_adg: bool = False,
    dcw_enabled: bool = False,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Flow-edit entrypoint: prepare paired conditions and run the loop.

    Returns ``{"target_latents": zt_edit, "time_costs": {...}}``.
    """
    _ = kwargs  # tolerate forwarded but unused kwargs (e.g. dcw_*)
    _warn_about_disabled_v1_tricks(sampler_mode, use_adg, dcw_enabled)

    if attention_mask is None:
        latent_length = src_latents.shape[1]
        attention_mask = torch.ones(
            src_latents.shape[0], latent_length,
            device=src_latents.device, dtype=src_latents.dtype,
        )

    ctx_input = ctx_src_latents if ctx_src_latents is not None else src_latents
    def _prep(text_hs, text_am, lyric_hs, lyric_am):
        return model.prepare_condition(
            text_hidden_states=text_hs, text_attention_mask=text_am,
            lyric_hidden_states=lyric_hs, lyric_attention_mask=lyric_am,
            refer_audio_acoustic_hidden_states_packed=refer_audio_acoustic_hidden_states_packed,
            refer_audio_order_mask=refer_audio_order_mask,
            hidden_states=ctx_input, attention_mask=attention_mask,
            silence_latent=silence_latent, src_latents=ctx_input,
            chunk_masks=chunk_masks, is_covers=is_covers,
            precomputed_lm_hints_25Hz=precomputed_lm_hints_25Hz,
            audio_codes=audio_codes,
        )
    src_enc_hs, src_enc_am, src_ctx = _prep(
        text_hidden_states, text_attention_mask,
        lyric_hidden_states, lyric_attention_mask,
    )
    tar_enc_hs, tar_enc_am, tar_ctx = _prep(
        target_text_hidden_states, target_text_attention_mask,
        target_lyric_hidden_states, target_lyric_attention_mask,
    )

    # Forward-noise generators: prefer retake_seed (independent draws), else
    # fall back to the main seed so a fixed (seed, n_min, n_max, n_avg) tuple
    # is reproducible end-to-end.
    bsz = src_latents.shape[0]
    fwd_seed = retake_seed if retake_seed is not None else seed
    retake_generators = _seed_to_generators(fwd_seed, bsz, src_latents.device)

    return flowedit_sampling_loop(
        model,
        src_encoder_hidden_states=src_enc_hs,
        src_encoder_attention_mask=src_enc_am,
        src_context_latents=src_ctx,
        tar_encoder_hidden_states=tar_enc_hs,
        tar_encoder_attention_mask=tar_enc_am,
        tar_context_latents=tar_ctx,
        src_latents=src_latents,
        attention_mask=attention_mask,
        null_condition_emb=model.null_condition_emb,
        retake_generators=retake_generators,
        infer_steps=infer_steps,
        timesteps=timesteps,
        shift=shift,
        diffusion_guidance_scale=diffusion_guidance_scale,
        cfg_interval_start=cfg_interval_start,
        cfg_interval_end=cfg_interval_end,
        velocity_norm_threshold=velocity_norm_threshold,
        velocity_ema_factor=velocity_ema_factor,
        n_min=edit_n_min,
        n_max=edit_n_max,
        n_avg=edit_n_avg,
        use_progress_bar=use_progress_bar,
    )
