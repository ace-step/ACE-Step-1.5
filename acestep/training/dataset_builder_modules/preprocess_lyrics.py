"""Lyric encoding for dataset preprocessing.

Encodes lyrics into the same token sequence the inference lyric branch builds,
so an adapter trained on these tensors sees the prompt shape it is later
generated with.
"""

import torch

from acestep.constants import LYRIC_GEN_PROMPT

# Matches the inference lyric branch (``_prepare_text_conditioning_inputs``).
LYRIC_MAX_LENGTH = 2048


def encode_lyrics(
    text_encoder,
    text_tokenizer,
    lyrics: str,
    vocal_language: str,
    device,
    dtype,
):
    """Encode lyrics into hidden states using the inference prompt format.

    Args:
        text_encoder: Text encoder providing the ``embed_tokens`` table.
        text_tokenizer: Tokenizer shared with the caption branch.
        lyrics: Raw lyric text, or ``"[Instrumental]"``.
        vocal_language: Language code for the prompt header, e.g. ``"pa"``.
            Required so a call site cannot silently omit the header and
            reintroduce a train/inference offset.
        device: Device to place the token tensors on.
        dtype: Target dtype for the returned hidden states and mask.

    Returns:
        Tuple of ``(lyric_hidden_states, lyric_attention_mask)``.
    """
    lyric_prompt = LYRIC_GEN_PROMPT.format(vocal_language, lyrics)
    lyric_inputs = text_tokenizer(
        lyric_prompt,
        padding="longest",
        max_length=LYRIC_MAX_LENGTH,
        truncation=True,
        return_tensors="pt",
    )
    lyric_input_ids = lyric_inputs.input_ids.to(device)
    lyric_attention_mask = lyric_inputs.attention_mask.to(device).to(dtype)

    # Align tensor residency to the actual text encoder device to avoid
    # CPU/CUDA mismatch in embedding/index_select calls.
    text_dev = next(text_encoder.parameters()).device
    if lyric_input_ids.device != text_dev:
        lyric_input_ids = lyric_input_ids.to(text_dev)
        lyric_attention_mask = lyric_attention_mask.to(text_dev)

    with torch.no_grad():
        lyric_hidden_states = text_encoder.embed_tokens(lyric_input_ids).to(dtype)

    return lyric_hidden_states, lyric_attention_mask
