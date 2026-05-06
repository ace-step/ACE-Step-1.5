"""Build the *source* text/lyric conditioning for flow-edit overlay (#1156).

The user's ``caption`` / ``lyrics`` go through the regular cover dispatch
and become the *target* condition.  Flow-edit overlay also needs a
*source* condition (``flow_edit_source_caption`` /
``flow_edit_source_lyrics``) describing the original audio so we can
compute V_delta = V_tar - V_src.  We tokenize and encode that source
side here using the handler's existing helpers so SFT prompt formatting,
lyric-language handling, and padding stay consistent with the target
side.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

import torch

from acestep.constants import DEFAULT_DIT_INSTRUCTION


def _pad_to_batch(values: Optional[List[Any]], default: Any, batch_size: int) -> List[Any]:
    """Right-pad/copy ``values`` to ``batch_size``, falling back to ``default``."""
    out = list(values) if values else [default] * batch_size
    if len(out) < batch_size:
        out = out + [default] * (batch_size - len(out))
    return out


def tokenize_source(
    handler,
    *,
    source_caption: str,
    source_lyrics: str,
    vocal_languages: Optional[List[str]],
    metas: Optional[List[Any]],
    instructions: Optional[List[str]],
    batch_size: int,
):
    """Build padded source text/lyric token tensors via handler helpers.

    Reuses ``_prepare_text_conditioning_inputs`` so the SFT prompt format,
    lyric-language formatting, and padding stay consistent with the
    target-side preparation already done by the regular cover dispatch.
    """
    captions = [source_caption] * batch_size
    lyrics = [source_lyrics] * batch_size
    langs = _pad_to_batch(vocal_languages, "unknown", batch_size)
    raw_metas = _pad_to_batch(metas, "", batch_size)
    parsed_metas_list = handler._parse_metas(raw_metas)
    instr_list = _pad_to_batch(instructions, DEFAULT_DIT_INSTRUCTION, batch_size)

    (
        _text_inputs,
        text_token_idss,
        text_attention_masks,
        lyric_token_idss,
        lyric_attention_masks,
        _nc_text_ids,
        _nc_text_am,
    ) = handler._prepare_text_conditioning_inputs(
        batch_size=batch_size,
        instructions=instr_list,
        captions=captions,
        lyrics=lyrics,
        parsed_metas=parsed_metas_list,
        vocal_languages=langs,
        audio_cover_strength=1.0,
    )
    return text_token_idss, text_attention_masks, lyric_token_idss, lyric_attention_masks


def embed_source(
    handler,
    text_token_idss: torch.Tensor,
    lyric_token_idss: torch.Tensor,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Run text + lyric encoders on the source tokens.

    Tokens come back from the tokenizer on CPU; the regular batch path
    moves them to ``handler.device`` before encoding (see
    ``preprocess_batch``), so we mirror that here.
    """
    device = handler.device
    text_token_idss = text_token_idss.to(device=device)
    lyric_token_idss = lyric_token_idss.to(device=device)
    with handler._load_model_context("text_encoder"):
        text_hs = handler.infer_text_embeddings(text_token_idss)
        lyric_hs = handler.infer_lyric_embeddings(lyric_token_idss)
    return text_hs, lyric_hs
