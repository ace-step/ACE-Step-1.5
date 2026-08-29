"""Tests for the default ``generate_music`` latent decode path."""

import unittest
from unittest.mock import patch

import torch

from acestep.core.generation.handler.generate_music_decode_test_support import (
    GENERATE_MUSIC_DECODE_MODULE,
    DecodeTestHost,
)


class GenerateMusicDecodeBasicTests(unittest.TestCase):
    """Verify successful decode timing and output behavior."""

    def test_decode_pred_latents_updates_decode_time_and_returns_cpu_latents(self):
        host = DecodeTestHost()
        pred_latents = torch.ones(1, 4, 3)
        time_costs = {"total_time_cost": 1.0}

        def _progress(value, desc=None):
            host.progress_calls.append((value, desc))

        with patch.object(GENERATE_MUSIC_DECODE_MODULE.time, "time", side_effect=[10.0, 11.5]):
            pred_wavs, pred_latents_cpu, updated_costs = host._decode_generate_music_pred_latents(
                pred_latents=pred_latents,
                progress=_progress,
                use_tiled_decode=False,
                time_costs=time_costs,
            )

        self.assertEqual(tuple(pred_wavs.shape), (1, 2, 8))
        self.assertEqual(pred_latents_cpu.device.type, "cpu")
        self.assertAlmostEqual(updated_costs["vae_decode_time_cost"], 1.5, places=6)
        self.assertAlmostEqual(updated_costs["total_time_cost"], 2.5, places=6)
        self.assertAlmostEqual(updated_costs["offload_time_cost"], 0.25, places=6)
        self.assertEqual(host.progress_calls[0][0], 0.8)


if __name__ == "__main__":
    unittest.main()
