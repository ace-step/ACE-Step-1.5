"""Tests for ``generate_music`` decode-state preparation."""

import unittest

import torch

from acestep.core.generation.handler.generate_music_decode_test_support import DecodeTestHost


class GenerateMusicDecodePrepareTests(unittest.TestCase):
    """Verify decode-state preparation helper behavior."""

    def test_prepare_decode_state_updates_progress_estimates(self):
        host = DecodeTestHost()
        outputs = {
            "target_latents": torch.ones(1, 4, 3),
            "time_costs": {"total_time_cost": 1.0, "diffusion_per_step_time_cost": 0.2},
        }
        pred_latents, time_costs = host._prepare_generate_music_decode_state(
            outputs=outputs,
            infer_steps_for_progress=8,
            actual_batch_size=1,
            audio_duration=12.0,
            latent_shift=0.0,
            latent_rescale=1.0,
        )
        self.assertEqual(tuple(pred_latents.shape), (1, 4, 3))
        self.assertEqual(time_costs["offload_time_cost"], 0.25)
        self.assertEqual(host._last_diffusion_per_step_sec, 0.2)
        self.assertEqual(host.estimate_calls[0]["infer_steps"], 8)

    def test_prepare_decode_state_raises_for_nan_latents(self):
        host = DecodeTestHost()
        outputs = {
            "target_latents": torch.tensor([[[float("nan")]]]),
            "time_costs": {"total_time_cost": 1.0},
        }
        with self.assertRaises(RuntimeError):
            host._prepare_generate_music_decode_state(
                outputs=outputs,
                infer_steps_for_progress=8,
                actual_batch_size=1,
                audio_duration=None,
                latent_shift=0.0,
                latent_rescale=1.0,
            )


if __name__ == "__main__":
    unittest.main()
