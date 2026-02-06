import torch

from acestep.constants import DEFAULT_DIT_INSTRUCTION, SFT_GEN_PROMPT

from .models import AudioSample
from .preprocess_utils import build_metas_str


def build_text_prompt(sample: AudioSample, tag_position: str, use_genre: bool) -> str:
    """Build the text prompt for the text encoder."""
    caption = sample.get_training_prompt(tag_position, use_genre=use_genre)
    metas_str = build_metas_str(sample)
    return SFT_GEN_PROMPT.format(DEFAULT_DIT_INSTRUCTION, caption, metas_str)


def encode_text(text_encoder, text_tokenizer, text_prompt: str, device, dtype):
    """Encode caption/genre prompt into text hidden states."""
    text_inputs = text_tokenizer(
        text_prompt,
        padding="max_length",
        max_length=256,
        truncation=True,
        return_tensors="pt",
    )
    text_input_ids = text_inputs.input_ids.to(device)
    text_attention_mask = text_inputs.attention_mask.to(device).to(dtype)

    text_dev = next(text_encoder.parameters()).device
    if text_input_ids.device != text_dev:
        text_input_ids = text_input_ids.to(text_dev)
        text_attention_mask = text_attention_mask.to(text_dev)

    with torch.no_grad():
        text_outputs = text_encoder(text_input_ids)
        text_hidden_states = text_outputs.last_hidden_state.to(dtype)

    return text_hidden_states, text_attention_mask
