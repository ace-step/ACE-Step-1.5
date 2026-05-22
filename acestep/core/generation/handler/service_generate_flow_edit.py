"""Flow-edit overlay dispatch on text2music task (issue #1156).

The user's ``caption`` / ``lyrics`` already flowed through the regular
text2music preprocessing pipeline and ended up in ``payload`` as the
*target* text + lyric embeddings.  Flow-edit overlay adds:

  * a *source* branch encoded from ``flow_edit_source_caption`` /
    ``flow_edit_source_lyrics`` — describes the original audio;
  * paired ``prepare_condition`` calls fed ``silence_latent`` for the
    audio context (the text2music shape, identical for both branches),
    so V_src and V_tar differ only in encoder text/lyric;
  * the user's encoded ``src_audio`` (already in ``payload['src_latents']``
    because we let it through for ``flow_edit_morph=True``) drives the
    sampling-loop ``zt_src`` / ``zt_tar`` formation.

Source tokenization + embedding helpers live in
``service_generate_flow_edit_source.py`` (split per the 200 LOC cap).
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

import torch
from loguru import logger

from .service_generate_flow_edit_source import embed_source, tokenize_source


def dispatch_flow_edit_overlay(
    handler,
    *,
    payload: Dict[str, Any],
    generate_kwargs: Dict[str, Any],
    seed_param: Any,
    flow_edit_ctx: Dict[str, Any],
) -> Tuple[Dict[str, Any], torch.Tensor, torch.Tensor, torch.Tensor]:
    """Run paired flow-edit on top of text2music dispatch.

    Builds source text/lyric embeddings from
    ``flow_edit_ctx['source_caption']`` / ``['source_lyrics']``, then
    calls :func:`flow_edit_pipeline.flowedit_generate_audio` which
    handles the two ``prepare_condition`` calls (one per branch, both
    fed silence-context like text2music) and the sampling-loop V_delta
    integration.
    """
    if not hasattr(handler.model, "flowedit_generate_audio"):
        raise RuntimeError(
            "Flow-edit overlay requires a base DiT variant — the loaded "
            "model does not expose flowedit_generate_audio.  Supported "
            "variants: xl_base, xl_sft, sft, base."
        )
    real_src_latents = payload["src_latents"]
    bsz, seq, ch = real_src_latents.shape
    task_type = flow_edit_ctx.get("task_type") or "text2music"
    n_min = float(flow_edit_ctx.get("n_min", 0.0))
    n_max = float(flow_edit_ctx.get("n_max", 1.0))
    n_avg = int(flow_edit_ctx.get("n_avg", 1))
    src_caption = flow_edit_ctx.get("source_caption") or ""
    src_lyrics = flow_edit_ctx.get("source_lyrics") or ""
    if not src_caption and not src_lyrics:
        logger.warning(
            "[flow_edit_overlay] both source_caption and source_lyrics are "
            "empty — V_src ≈ V_tar so the overlay will be a near no-op.",
        )
    logger.info(
        "[flow_edit_overlay] dispatch — task={}, bsz={}, n_min={}, n_max={}, n_avg={}",
        task_type, bsz, n_min, n_max, n_avg,
    )

    # Source side text/lyric embeddings (target side is already in payload).
    src_text_ids, src_text_am, src_lyric_ids, src_lyric_am = tokenize_source(
        handler,
        source_caption=src_caption,
        source_lyrics=src_lyrics,
        vocal_languages=flow_edit_ctx.get("vocal_languages"),
        metas=flow_edit_ctx.get("metas"),
        instructions=flow_edit_ctx.get("instructions"),
        batch_size=bsz,
    )
    src_text_hs, src_lyric_hs = embed_source(handler, src_text_ids, src_lyric_ids)

    device, dtype = real_src_latents.device, real_src_latents.dtype
    src_text_am = src_text_am.to(device=device, dtype=dtype)
    src_lyric_am = src_lyric_am.to(device=device, dtype=dtype)

    # Audio context for ``prepare_condition``: choose by task.
    #
    # text2music — force silence-context.  text2music's training
    # distribution is (clean target, silence audio context).  Sharing
    # the source audio's encoded latents (or LM codes derived from one
    # prompt) as the context is OOD: the velocity head produces unstable
    # predictions, V_delta integration accumulates into a near-zero
    # latent, and VAE decode + auto-normalization amplifies the residual
    # noise to full scale.  Verified empirically by a 4-way sweep
    # (sft60, tb60, tb8w05, tb8s1) — every variant collapsed to peak
    # ≈ 0.007 the moment the natural context was used.
    #
    # cover / cover-nofsq — keep payload's natural context.  The cover
    # task IS trained on (clean target, LM-codes-derived audio context),
    # so both branches share an in-distribution context and V_delta
    # captures the text-only delta cleanly.
    if task_type == "text2music":
        sil = handler.silence_latent.to(device=device, dtype=dtype)
        available = sil.shape[1]
        if seq <= available:
            sil_slice = sil[0, :seq, :]
        else:
            repeats = (seq + available - 1) // available
            sil_slice = sil[0].repeat(repeats, 1)[:seq, :]
        ctx_input = sil_slice.unsqueeze(0).expand(bsz, seq, ch).contiguous()
        is_covers_arg = torch.zeros(bsz, dtype=torch.long, device=device)
        # Drop the precomputed LM hints — they were generated from the
        # user's caption/lyrics, not silence; even though is_covers=0
        # leaves them unused in the where-clause, the tensor lingers in
        # downstream paths and empirically collapses the latent (peak
        # 0.007 in the user's repro).  Force ``prepare_condition`` to
        # tokenize silence afresh, matching the no-codes case that
        # produced peak 0.92.
        precomputed_lm_hints_arg = None
    else:
        ctx_input = real_src_latents
        is_covers_arg = payload["is_covers"]
        precomputed_lm_hints_arg = payload.get("precomputed_lm_hints_25Hz")

    with torch.inference_mode():
        with handler._load_model_context("model"):
            outputs = handler.model.flowedit_generate_audio(
                # Target = the user's caption/lyrics already in payload.
                target_text_hidden_states=payload["text_hidden_states"],
                target_text_attention_mask=payload["text_attention_mask"],
                target_lyric_hidden_states=payload["lyric_hidden_states"],
                target_lyric_attention_mask=payload["lyric_attention_mask"],
                # Source = the freshly encoded original-prompt side.
                text_hidden_states=src_text_hs,
                text_attention_mask=src_text_am,
                lyric_hidden_states=src_lyric_hs,
                lyric_attention_mask=src_lyric_am,
                # Audio context: silence for both branches (text2music shape).
                refer_audio_acoustic_hidden_states_packed=payload["refer_audio_acoustic_hidden_states_packed"],
                refer_audio_order_mask=payload["refer_audio_order_mask"],
                src_latents=real_src_latents,        # for zt_src/zt_tar formation
                ctx_src_latents=ctx_input,           # silence (text2music) or real (cover)
                chunk_masks=payload["chunk_mask"],
                is_covers=is_covers_arg,             # 0 (text2music) or payload (cover)
                silence_latent=handler.silence_latent,
                seed=seed_param,
                retake_seed=generate_kwargs.get("retake_seed"),
                infer_steps=generate_kwargs.get("infer_steps"),
                timesteps=generate_kwargs.get("timesteps"),
                diffusion_guidance_scale=generate_kwargs.get("diffusion_guidance_scale", 1.0),
                cfg_interval_start=generate_kwargs.get("cfg_interval_start", 0.0),
                cfg_interval_end=generate_kwargs.get("cfg_interval_end", 1.0),
                shift=generate_kwargs.get("shift", 1.0),
                velocity_norm_threshold=generate_kwargs.get("velocity_norm_threshold", 0.0),
                velocity_ema_factor=generate_kwargs.get("velocity_ema_factor", 0.0),
                edit_n_min=n_min,
                edit_n_max=n_max,
                edit_n_avg=n_avg,
                precomputed_lm_hints_25Hz=precomputed_lm_hints_arg,
                # v1-disabled tricks — pipeline logs them and bypasses.
                sampler_mode=generate_kwargs.get("sampler_mode", "euler"),
                use_adg=generate_kwargs.get("use_adg", False),
                dcw_enabled=generate_kwargs.get("dcw_enabled", False),
            )

    # Return target-side encoder/context for downstream auto-LRC + scoring.
    attn = torch.ones(bsz, seq, device=device, dtype=dtype)
    enc_hs, enc_am, ctx = handler.model.prepare_condition(
        text_hidden_states=payload["text_hidden_states"],
        text_attention_mask=payload["text_attention_mask"],
        lyric_hidden_states=payload["lyric_hidden_states"],
        lyric_attention_mask=payload["lyric_attention_mask"],
        refer_audio_acoustic_hidden_states_packed=payload["refer_audio_acoustic_hidden_states_packed"],
        refer_audio_order_mask=payload["refer_audio_order_mask"],
        hidden_states=ctx_input,
        attention_mask=attn,
        silence_latent=handler.silence_latent,
        src_latents=ctx_input,
        chunk_masks=payload["chunk_mask"],
        is_covers=is_covers_arg,
        precomputed_lm_hints_25Hz=precomputed_lm_hints_arg,
    )
    return outputs, enc_hs, enc_am, ctx
