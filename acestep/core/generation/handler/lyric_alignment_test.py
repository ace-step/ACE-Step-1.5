"""Unit tests for lyric timestamp and lyric score mixins."""

import contextlib
import types
import unittest
from unittest.mock import patch

import torch

from acestep.core.generation.handler.lyric_score import LyricScoreMixin
from acestep.core.generation.handler.lyric_timestamp import LyricTimestampMixin


class _Tokenizer:
    """Minimal tokenizer stub with deterministic header ids."""

    def encode(self, _text, add_special_tokens=False):
        """Return a fixed header-token shape for deterministic slicing."""
        _ = add_special_tokens
        return [1, 2]


class _Decoder:
    """Minimal decoder stub returning configured cross-attention outputs."""

    def __init__(self, cross_attns):
        """Store decoder output tuple index-2 payload."""
        self._cross_attns = cross_attns

    def eval(self):
        """Mirror torch module API used by score mixin."""

    def __call__(self, **kwargs):
        """Return an output tuple compatible with handler expectations."""
        _ = kwargs
        return (None, None, self._cross_attns)


class _Model:
    """Model wrapper containing a fake decoder."""

    def __init__(self, decoder):
        """Bind the test decoder."""
        self.decoder = decoder


class _Host(LyricTimestampMixin, LyricScoreMixin):
    """Host object exposing the minimal attributes expected by mixins."""

    def __init__(self, decoder):
        """Initialize runtime attributes consumed by lyric mixins."""
        self.model = _Model(decoder)
        self.text_tokenizer = _Tokenizer()
        self.device = "cpu"
        self.dtype = torch.float32
        self.custom_layers_config = {2: [6]}

    def _load_model_context(self, _name):
        """Return a no-op context manager to mimic handler model context."""
        return contextlib.nullcontext()


class SyncAlignmentConfigTests(unittest.TestCase):
    """Test _sync_alignment_config picks up model config values."""

    _DEFAULT = {2: [6], 3: [10, 11], 4: [3], 5: [8, 9], 6: [8]}

    def _make_host(self):
        """Build a _Host with a None decoder for config-only tests."""
        return _Host(decoder=_Decoder(cross_attns=None))

    def test_sync_from_model_config_with_string_keys(self):
        """Model config with string keys (JSON-serialized) should be converted to int keys."""
        host = self._make_host()
        host.config = types.SimpleNamespace(
            lyric_alignment_layers_config={"3": [18, 27], "4": [22], "5": [5, 6, 7]}
        )
        host._sync_alignment_config()
        self.assertEqual(host.custom_layers_config, {3: [18, 27], 4: [22], 5: [5, 6, 7]})

    def test_sync_from_model_config_with_int_keys(self):
        """Model config with int keys should work directly."""
        host = self._make_host()
        host.config = types.SimpleNamespace(
            lyric_alignment_layers_config={3: [18, 27], 7: [20, 21]}
        )
        host._sync_alignment_config()
        self.assertEqual(host.custom_layers_config, {3: [18, 27], 7: [20, 21]})

    def test_sync_restores_default_when_config_missing(self):
        """When model config has no lyric_alignment_layers_config, default is restored."""
        host = self._make_host()
        host.config = types.SimpleNamespace()
        host._sync_alignment_config()
        self.assertEqual(host.custom_layers_config, self._DEFAULT)

    def test_sync_restores_default_when_config_is_none(self):
        """When lyric_alignment_layers_config is explicitly None, default is restored."""
        host = self._make_host()
        host.config = types.SimpleNamespace(lyric_alignment_layers_config=None)
        host._sync_alignment_config()
        self.assertEqual(host.custom_layers_config, self._DEFAULT)

    def test_sync_restores_default_when_no_config_object(self):
        """When self.config is None (model not loaded), default is restored."""
        host = self._make_host()
        host.config = None
        host._sync_alignment_config()
        self.assertEqual(host.custom_layers_config, self._DEFAULT)

    # --- Re-initialization (stale config) ---

    def test_sync_resets_to_default_on_reinit_without_config(self):
        """Switching from 4B (with config) to 2B (without) must restore the 2B default."""
        host = self._make_host()
        # First load: 4B model with explicit alignment config
        host.config = types.SimpleNamespace(
            lyric_alignment_layers_config={"3": [18, 27], "7": [20, 21]}
        )
        host._sync_alignment_config()
        self.assertEqual(host.custom_layers_config, {3: [18, 27], 7: [20, 21]})

        # Second load: 2B model without the field
        host.config = types.SimpleNamespace()
        host._sync_alignment_config()
        self.assertEqual(host.custom_layers_config, self._DEFAULT)

    # --- Empty dict ---

    def test_sync_restores_default_on_empty_dict(self):
        """An empty dict {} must not wipe custom_layers_config; restore default instead."""
        host = self._make_host()
        host.config = types.SimpleNamespace(lyric_alignment_layers_config={})
        host._sync_alignment_config()
        self.assertEqual(host.custom_layers_config, self._DEFAULT)

    # --- Malformed input validation ---

    def test_sync_ignores_non_dict_config(self):
        """A non-dict value (e.g. a list) should be ignored and default restored."""
        host = self._make_host()
        host.config = types.SimpleNamespace(lyric_alignment_layers_config=[1, 2, 3])
        host._sync_alignment_config()
        self.assertEqual(host.custom_layers_config, self._DEFAULT)

    def test_sync_ignores_non_integer_keys(self):
        """Dict with non-integer-castable keys should be ignored and default restored."""
        host = self._make_host()
        host.config = types.SimpleNamespace(
            lyric_alignment_layers_config={"layer_a": [1], "layer_b": [2]}
        )
        host._sync_alignment_config()
        self.assertEqual(host.custom_layers_config, self._DEFAULT)

    def test_sync_ignores_non_integer_head_values(self):
        """Dict with non-integer head values should be ignored and default restored."""
        host = self._make_host()
        host.config = types.SimpleNamespace(
            lyric_alignment_layers_config={"3": ["a", "b"]}
        )
        host._sync_alignment_config()
        self.assertEqual(host.custom_layers_config, self._DEFAULT)


class LyricAlignmentMixinTests(unittest.TestCase):
    """Cover success and no-attention regression behaviors."""

    def _sample_inputs(self):
        """Build deterministic tensors and lyric token ids for tests."""
        pred = torch.randn(1, 7, 4)
        enc = torch.randn(1, 6, 4)
        enc_mask = torch.ones(1, 6)
        ctx = torch.randn(1, 7, 4)
        lyric_ids = torch.tensor([[1, 2, 101, 102, 103, 151643]], dtype=torch.long)
        return pred, enc, enc_mask, ctx, lyric_ids

    def test_get_lyric_timestamp_success(self):
        """Timestamp generation should return successful payload with aligner output."""
        decoder = _Decoder(cross_attns=[torch.randn(1, 2, 7, 6)])
        host = _Host(decoder=decoder)
        pred, enc, enc_mask, ctx, lyric_ids = self._sample_inputs()

        class _FakeStampsAligner:
            """Fake aligner used to isolate timestamp mixin behavior."""

            def __init__(self, _tokenizer):
                """Match production constructor signature."""

            def stamps_align_info(self, **kwargs):
                """Return a non-empty calc matrix to simulate valid alignment."""
                _ = kwargs
                return {"calc_matrix": torch.ones(2, 2)}

            def get_timestamps_and_lrc(self, **kwargs):
                """Return deterministic timestamp payload."""
                _ = kwargs
                return {
                    "lrc_text": "[00:00.00]hello",
                    "sentence_timestamps": [{"start": 0.0, "end": 1.0}],
                    "token_timestamps": [{"token": "hello", "start": 0.0, "end": 0.5}],
                }

        fake_module = types.SimpleNamespace(MusicStampsAligner=_FakeStampsAligner)
        with patch.dict("sys.modules", {"acestep.core.scoring.dit_alignment": fake_module}):

            result = host.get_lyric_timestamp(
                pred_latent=pred,
                encoder_hidden_states=enc,
                encoder_attention_mask=enc_mask,
                context_latents=ctx,
                lyric_token_ids=lyric_ids,
                total_duration_seconds=3.0,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["lrc_text"], "[00:00.00]hello")
        self.assertIsNone(result["error"])

    def test_get_lyric_score_success(self):
        """Score generation should return LM and DiT scores from the scorer output."""
        decoder = _Decoder(cross_attns=[torch.randn(2, 2, 7, 6)])
        host = _Host(decoder=decoder)
        pred, enc, enc_mask, ctx, lyric_ids = self._sample_inputs()

        class _FakeLyricScorer:
            """Fake lyric scorer used to isolate score mixin behavior."""

            def __init__(self, _tokenizer):
                """Match production constructor signature."""

            def lyrics_alignment_info(self, **kwargs):
                """Return deterministic alignment info for downstream scoring."""
                _ = kwargs
                return {
                    "energy_matrix": torch.ones(2, 2),
                    "type_mask": torch.ones(2, 2),
                    "path_coords": [(0, 0)],
                }

            def calculate_score(self, **kwargs):
                """Return a stable numeric score for assertions."""
                _ = kwargs
                return {"lyrics_score": 0.77, "final_score": 0.66}

        fake_module = types.SimpleNamespace(MusicLyricScorer=_FakeLyricScorer)
        with patch.dict("sys.modules", {"acestep.core.scoring.dit_score": fake_module}):

            result = host.get_lyric_score(
                pred_latent=pred,
                encoder_hidden_states=enc,
                encoder_attention_mask=enc_mask,
                context_latents=ctx,
                lyric_token_ids=lyric_ids,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["lm_score"], 0.77)
        self.assertEqual(result["dit_score"], 0.77)
        self.assertIsNone(result["error"])

    def test_get_lyric_timestamp_returns_error_when_attentions_missing(self):
        """Timestamp generation should fail clearly when decoder returns no attentions."""
        decoder = _Decoder(cross_attns=None)
        host = _Host(decoder=decoder)
        pred, enc, enc_mask, ctx, lyric_ids = self._sample_inputs()

        result = host.get_lyric_timestamp(
            pred_latent=pred,
            encoder_hidden_states=enc,
            encoder_attention_mask=enc_mask,
            context_latents=ctx,
            lyric_token_ids=lyric_ids,
            total_duration_seconds=3.0,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Model did not return attentions")

    def test_get_lyric_score_returns_error_when_attentions_missing(self):
        """Score generation should fail clearly when decoder returns no attentions."""
        decoder = _Decoder(cross_attns=None)
        host = _Host(decoder=decoder)
        pred, enc, enc_mask, ctx, lyric_ids = self._sample_inputs()

        result = host.get_lyric_score(
            pred_latent=pred,
            encoder_hidden_states=enc,
            encoder_attention_mask=enc_mask,
            context_latents=ctx,
            lyric_token_ids=lyric_ids,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Model did not return attentions")


if __name__ == "__main__":
    unittest.main()
