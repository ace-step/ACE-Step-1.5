"""Shared test fixtures for flow-edit overlay dispatch tests (#1156).

Underscored module name keeps it out of unittest discovery.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock

import torch


class FakeHandler:
    """Minimal handler stand-in exposing the surface the overlay needs."""

    def __init__(self, model_has_flowedit: bool = True):
        self.device = torch.device("cpu")
        self.model = MagicMock()
        if not model_has_flowedit:
            del self.model.flowedit_generate_audio
        else:
            self.model.flowedit_generate_audio.return_value = {
                "target_latents": torch.zeros(1, 8, 16),
                "time_costs": {},
            }
        # Sentinel tensors so tests can verify the dispatch returns
        # ``prepare_condition`` outputs (not raw embeddings).
        self.prepared_enc_hs = torch.full((1, 4, 16), 7.0)
        self.prepared_enc_am = torch.full((1, 4), 7.0)
        self.prepared_ctx = torch.full((1, 8, 32), 7.0)
        self.model.prepare_condition.return_value = (
            self.prepared_enc_hs, self.prepared_enc_am, self.prepared_ctx,
        )
        self.silence_latent = torch.zeros(1, 8, 16)

    @contextmanager
    def _load_model_context(self, name):
        yield

    def _prepare_text_conditioning_inputs(self, *, batch_size, instructions,
                                          captions, lyrics, parsed_metas,
                                          vocal_languages, audio_cover_strength):
        self.captured_parsed_metas = parsed_metas
        self.captured_captions = captions
        self.captured_lyrics = lyrics
        seq = 4
        return (
            ["fake-text-input"] * batch_size,
            torch.zeros(batch_size, seq, dtype=torch.long),
            torch.ones(batch_size, seq),
            torch.zeros(batch_size, seq, dtype=torch.long),
            torch.ones(batch_size, seq),
            None, None,
        )

    def _parse_metas(self, metas):
        out = []
        for m in metas:
            if isinstance(m, dict):
                out.append("PARSED:" + ",".join(f"{k}={v}" for k, v in m.items()))
            else:
                out.append(str(m))
        return out

    def infer_text_embeddings(self, ids):
        return torch.zeros(ids.shape[0], ids.shape[1], 16)

    def infer_lyric_embeddings(self, ids):
        return torch.zeros(ids.shape[0], ids.shape[1], 16)


def make_payload(bsz: int = 1, seq: int = 8, ch: int = 16):
    return {
        "src_latents": torch.randn(bsz, seq, ch),
        # Target side (the user's caption/lyrics already encoded).
        "text_hidden_states": torch.randn(bsz, 4, ch),
        "text_attention_mask": torch.ones(bsz, 4),
        "lyric_hidden_states": torch.randn(bsz, 4, ch),
        "lyric_attention_mask": torch.ones(bsz, 4),
        "refer_audio_acoustic_hidden_states_packed": torch.zeros(0, 4, ch),
        "refer_audio_order_mask": torch.zeros(0, dtype=torch.long),
        "chunk_mask": torch.ones(bsz, seq, ch),
        "is_covers": torch.zeros(bsz, dtype=torch.long),  # text2music
        "precomputed_lm_hints_25Hz": None,
    }


def make_flow_edit_ctx(source_caption="anime pop", source_lyrics="original"):
    return {
        "morph": True,
        "task_type": "text2music",
        "source_caption": source_caption,
        "source_lyrics": source_lyrics,
        "vocal_languages": ["en"],
        "metas": [""],
        "instructions": ["Fill the audio semantic mask based on the given conditions:"],
        "n_min": 0.2,
        "n_max": 0.8,
        "n_avg": 1,
    }
