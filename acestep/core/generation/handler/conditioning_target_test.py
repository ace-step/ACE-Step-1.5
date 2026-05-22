"""Tests for target-latent preparation helpers."""

import unittest
from contextlib import nullcontext

import torch

from acestep.core.generation.handler.conditioning_target import ConditioningTargetMixin


class _Host(ConditioningTargetMixin):
    """Minimal host exposing target-conditioning dependencies."""

    def __init__(self):
        """Initialize deterministic conditioning state."""
        self.device = torch.device("cpu")
        self.dtype = torch.float32
        self.silence_latent = torch.zeros(1, 16, 3)
        self.encode_calls = 0

    def _get_vae_dtype(self):
        """Return the test latent dtype."""
        return torch.float32

    def _ensure_silence_latent_on_device(self):
        """Keep silence latent on the target test device."""
        self.silence_latent = self.silence_latent.to(self.device)

    def _load_model_context(self, _name):
        """Return a no-op model context manager."""
        return nullcontext()

    def is_silence(self, wav):
        """Return whether the test wav is silent."""
        return bool(torch.all(wav == 0))

    def _encode_audio_to_latents(self, _wav):
        """Count VAE encode calls and return a sentinel latent."""
        self.encode_calls += 1
        return torch.ones(4, 3) * 9.0

    def _decode_audio_codes_to_latents(self, _code_hint):
        """Audio-code decoding is not used by these tests."""
        return None


class ConditioningTargetMixinTests(unittest.TestCase):
    """Verify target audio/cache latent preparation behavior."""

    def test_non_silent_target_wav_is_vae_encoded_without_cache(self):
        """Uploaded repaint sources should keep the normal VAE path."""
        host = _Host()
        target_wavs = torch.ones(1, 2, 4 * 1920)

        _, target_latents, latent_masks, max_len, _ = host._prepare_target_latents_and_wavs(
            batch_size=1,
            target_wavs=target_wavs,
            audio_code_hints=[None],
        )

        self.assertEqual(1, host.encode_calls)
        self.assertEqual(128, max_len)
        torch.testing.assert_close(target_latents[0, :4], torch.ones(4, 3) * 9.0)
        self.assertEqual(4, int(latent_masks[0].sum().item()))

    def test_cached_repaint_source_latents_skip_vae_encode(self):
        """Generated-source repaint should reuse cached source latents."""
        host = _Host()
        target_wavs = torch.ones(1, 2, 4 * 1920)
        source_latents = torch.ones(2, 3) * 5.0

        _, target_latents, latent_masks, max_len, _ = host._prepare_target_latents_and_wavs(
            batch_size=1,
            target_wavs=target_wavs,
            audio_code_hints=[None],
            source_repaint_latents=source_latents,
        )

        self.assertEqual(0, host.encode_calls)
        self.assertEqual(128, max_len)
        torch.testing.assert_close(target_latents[0, :2], source_latents)
        torch.testing.assert_close(target_latents[0, 2:4], torch.zeros(2, 3))
        self.assertEqual(4, int(latent_masks[0].sum().item()))


if __name__ == "__main__":
    unittest.main()
