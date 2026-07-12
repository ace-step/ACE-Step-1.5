"""Unit tests for conditioning embedding/preprocess mixin."""

from contextlib import contextmanager
import unittest

import torch

from acestep.core.generation.handler.conditioning_embed import ConditioningEmbedMixin


class _FakeTextEncoder:
    """Minimal text encoder stub for preprocess tests."""

    def __call__(self, input_ids, lyric_attention_mask=None):
        """Return a zero embedding matching the input sequence length."""
        del lyric_attention_mask
        b, t = input_ids.shape
        return type("O", (), {"last_hidden_state": torch.zeros(b, t, 6, dtype=torch.float32)})

    def embed_tokens(self, token_ids):
        """Return zero token embeddings with a fixed hidden size."""
        b, t = token_ids.shape
        return torch.zeros(b, t, 6, dtype=torch.float32)


class _Host(ConditioningEmbedMixin):
    """Minimal host implementing ConditioningEmbedMixin dependencies."""

    def __init__(self, text_encoder_device="cpu", dit_device="cpu"):
        """Build a host with optional per-component device placement."""
        self.device = dit_device
        self.dtype = torch.float32
        self.silence_latent = torch.zeros(1, 128, 6, dtype=torch.float32)
        self.text_encoder = _FakeTextEncoder()
        self.tiled_encode_calls = 0
        self._devices = {
            "dit": dit_device,
            "vae": dit_device,
            "text_encoder": text_encoder_device,
            "lm": dit_device,
        }

    def _get_component_device(self, component):
        """Return the stub device string for a named component."""
        return self._devices[component]

    def _ensure_silence_latent_on_device(self):
        """No-op silence-latent placement for unit tests."""
        return None

    @contextmanager
    def _load_model_context(self, _name):
        """Yield without loading real model weights."""
        yield

    def tiled_encode(self, audio, offload_latent_to_cpu=True):
        """Record encode calls and return a zero latent of matching length."""
        del offload_latent_to_cpu
        self.tiled_encode_calls += 1
        t = max(1, audio.shape[-1] // 1920)
        return torch.zeros(1, 6, t, dtype=torch.float32)


class ConditioningEmbedMixinTests(unittest.TestCase):
    """Tests for ConditioningEmbedMixin methods."""

    def test_infer_refer_latent_returns_latents_and_order_mask(self):
        """Infer reference latents and preserve per-batch ordering mask."""
        host = _Host()
        refer_audioss = [
            [torch.ones(2, 96000)],
            [torch.ones(2, 96000)],
        ]
        latents, order_mask = host.infer_refer_latent(refer_audioss)
        self.assertEqual(latents.dim(), 3)
        self.assertEqual(order_mask.tolist(), [0, 1])
        self.assertEqual(host.tiled_encode_calls, 2)

    def test_infer_refer_latent_cache_hit_reuses_encoding(self):
        """Reuse cached latent when the exact same tensor object appears multiple times."""
        host = _Host()
        shared = torch.ones(2, 96000)
        latents, order_mask = host.infer_refer_latent([[shared], [shared]])
        self.assertEqual(latents.shape[0], 2)
        self.assertEqual(order_mask.tolist(), [0, 1])
        self.assertEqual(host.tiled_encode_calls, 1)

    def test_infer_refer_latent_uses_silence_fast_path(self):
        """Use silence-latent shortcut when reference audio is an explicit zero tensor."""
        host = _Host()
        latents, order_mask = host.infer_refer_latent([[torch.zeros(2, 96000)]])
        self.assertEqual(latents.shape, (1, 128, 6))
        self.assertEqual(order_mask.tolist(), [0])
        self.assertEqual(host.tiled_encode_calls, 0)

    def test_infer_refer_latent_handles_multiple_references_per_item(self):
        """Flatten multiple references for one batch item while preserving order index."""
        host = _Host()
        refer_audioss = [[torch.ones(2, 96000), torch.ones(2, 96000)]]
        latents, order_mask = host.infer_refer_latent(refer_audioss)
        self.assertEqual(latents.shape[0], 2)
        self.assertEqual(order_mask.tolist(), [0, 0])

    def test_preprocess_batch_returns_expected_tuple_shape(self):
        """Preprocess batch and return full model-input tuple contract."""
        host = _Host()
        batch = {
            "keys": ["k1", "k2"],
            "target_latents": torch.zeros(2, 128, 6, dtype=torch.float32),
            "src_latents": torch.zeros(2, 128, 6, dtype=torch.float32),
            "latent_masks": torch.ones(2, 128, dtype=torch.long),
            "refer_audioss": [[torch.zeros(2, 96000)], [torch.zeros(2, 96000)]],
            "chunk_masks": torch.ones(2, 128, dtype=torch.bool),
            "spans": [("full", 0, 128), ("full", 0, 128)],
            "text_token_idss": torch.ones(2, 8, dtype=torch.long),
            "text_attention_masks": torch.ones(2, 8, dtype=torch.long),
            "lyric_token_idss": torch.ones(2, 10, dtype=torch.long),
            "lyric_attention_masks": torch.ones(2, 10, dtype=torch.long),
            "text_inputs": ["a", "b"],
            "is_covers": torch.zeros(2, dtype=torch.bool),
            "precomputed_lm_hints_25Hz": None,
            "non_cover_text_input_ids": None,
            "non_cover_text_attention_masks": None,
        }
        result = host.preprocess_batch(batch)
        self.assertEqual(len(result), 20)
        self.assertEqual(result[0], ["k1", "k2"])
        self.assertEqual(result[3].shape, (2, 128, 6))

    def test_infer_text_embeddings_moves_ids_to_text_encoder_device(self):
        """Token ids on DiT device must be moved onto a remote text encoder."""
        if not torch.cuda.is_available() or torch.cuda.device_count() < 2:
            self.skipTest("needs 2+ CUDA devices")

        seen = {}

        class _DeviceCheckingEncoder(_FakeTextEncoder):
            """Text encoder stub that records the device of incoming token ids."""

            def __call__(self, input_ids, lyric_attention_mask=None):
                """Record ``input_ids.device`` then delegate to the fake encoder."""
                seen["device"] = str(input_ids.device)
                return super().__call__(input_ids, lyric_attention_mask)

        host = _Host(text_encoder_device="cuda:1", dit_device="cuda:0")
        host.text_encoder = _DeviceCheckingEncoder()
        ids = torch.ones(1, 4, dtype=torch.long, device="cuda:0")
        out = host.infer_text_embeddings(ids)
        self.assertEqual(seen["device"], "cuda:1")
        self.assertEqual(out.shape, (1, 4, 6))


if __name__ == "__main__":
    unittest.main()
