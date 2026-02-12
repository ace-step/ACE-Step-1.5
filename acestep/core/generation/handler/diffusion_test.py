"""Unit tests for diffusion mixin behavior and validation guards."""

import unittest
from unittest.mock import patch

import numpy as np
import torch

from acestep.core.generation.handler.diffusion import DiffusionMixin


class _Host(DiffusionMixin):
    """Minimal host implementing attributes required by ``DiffusionMixin``."""

    def __init__(self, device: str = "cpu", dtype: torch.dtype = torch.float32):
        """Initialize host with diffusion-runtime attributes used by tests."""
        self.mlx_decoder = object()
        self.device = device
        self.dtype = dtype


class _IterableTimesteps:
    """Simple iterable wrapper to validate non-list timestep handling."""

    def __init__(self, values):
        """Store timestep values for iteration."""
        self._values = values

    def __iter__(self):
        """Iterate over stored timesteps."""
        return iter(self._values)


class DiffusionMixinTests(unittest.TestCase):
    def test_mlx_run_diffusion_converts_inputs_and_outputs_tensor(self):
        """Diffusion call should convert inputs and return typed tensor output."""
        host = _Host(dtype=torch.float16)
        encoder_hidden_states = torch.randn(2, 4, 8, dtype=torch.float64)
        encoder_attention_mask = torch.ones(2, 4, dtype=torch.int64)
        context_latents = torch.randn(2, 16, 8, dtype=torch.float64)
        src_latents = torch.zeros(2, 3, 5, dtype=torch.float32)
        timesteps = torch.tensor([1.0, 0.5], dtype=torch.float32)
        non_cover_hidden = torch.randn(2, 4, 8, dtype=torch.float64)
        non_cover_mask = torch.ones(2, 4, dtype=torch.int64)
        non_cover_context = torch.randn(2, 16, 8, dtype=torch.float64)
        fake_target = np.ones((2, 3, 5), dtype=np.float32)

        def _fake_generate(**kwargs):
            self.assertIs(kwargs["mlx_decoder"], host.mlx_decoder)
            self.assertEqual(kwargs["src_latents_shape"], (2, 3, 5))
            self.assertEqual(kwargs["timesteps"], [1.0, 0.5])
            self.assertEqual(kwargs["infer_method"], "sde")
            self.assertEqual(kwargs["shift"], 2.0)
            self.assertEqual(kwargs["audio_cover_strength"], 0.6)
            self.assertEqual(kwargs["encoder_hidden_states_np"].dtype, np.float32)
            self.assertEqual(kwargs["context_latents_np"].dtype, np.float32)
            self.assertEqual(kwargs["encoder_hidden_states_non_cover_np"].dtype, np.float32)
            self.assertEqual(kwargs["context_latents_non_cover_np"].dtype, np.float32)
            return {"target_latents": fake_target, "time_costs": {"diffusion_time_cost": 1.2}}

        with patch("acestep.core.generation.handler.diffusion.mlx_generate_diffusion", side_effect=_fake_generate):
            result = host._mlx_run_diffusion(
                encoder_hidden_states=encoder_hidden_states,
                encoder_attention_mask=encoder_attention_mask,
                context_latents=context_latents,
                src_latents=src_latents,
                seed=123,
                infer_method="sde",
                shift=2.0,
                timesteps=timesteps,
                audio_cover_strength=0.6,
                encoder_hidden_states_non_cover=non_cover_hidden,
                encoder_attention_mask_non_cover=non_cover_mask,
                context_latents_non_cover=non_cover_context,
            )

        self.assertIn("target_latents", result)
        self.assertIn("time_costs", result)
        self.assertEqual(result["time_costs"]["diffusion_time_cost"], 1.2)
        self.assertEqual(result["target_latents"].dtype, torch.float16)
        self.assertEqual(result["target_latents"].device.type, "cpu")
        self.assertTrue(torch.allclose(result["target_latents"], torch.ones_like(result["target_latents"])))

    def test_mlx_run_diffusion_handles_optional_and_iterable_timesteps(self):
        """Optional non-cover tensors and iterable timesteps should be handled."""
        host = _Host(dtype=torch.float32)
        encoder_hidden_states = torch.randn(1, 2, 3, dtype=torch.float32)
        encoder_attention_mask = torch.ones(1, 2, dtype=torch.int64)
        context_latents = torch.randn(1, 4, 3, dtype=torch.float32)
        src_latents = torch.zeros(1, 2, 3, dtype=torch.float32)
        timesteps = _IterableTimesteps([0.9, 0.8, 0.7])

        def _fake_generate(**kwargs):
            self.assertEqual(kwargs["timesteps"], [0.9, 0.8, 0.7])
            self.assertIsNone(kwargs["encoder_hidden_states_non_cover_np"])
            self.assertIsNone(kwargs["context_latents_non_cover_np"])
            return {"target_latents": np.zeros((1, 2, 3), dtype=np.float32), "time_costs": {}}

        with patch("acestep.core.generation.handler.diffusion.mlx_generate_diffusion", side_effect=_fake_generate):
            result = host._mlx_run_diffusion(
                encoder_hidden_states=encoder_hidden_states,
                encoder_attention_mask=encoder_attention_mask,
                context_latents=context_latents,
                src_latents=src_latents,
                seed=1,
                timesteps=timesteps,
            )

        self.assertEqual(tuple(result["target_latents"].shape), (1, 2, 3))
        self.assertEqual(result["target_latents"].dtype, torch.float32)

    def test_mlx_run_diffusion_wraps_scalar_tensor_timestep(self):
        """Scalar tensor timestep should be wrapped into a one-item list."""
        host = _Host(dtype=torch.float32)
        encoder_hidden_states = torch.randn(1, 2, 3, dtype=torch.float32)
        encoder_attention_mask = torch.ones(1, 2, dtype=torch.int64)
        context_latents = torch.randn(1, 4, 3, dtype=torch.float32)
        src_latents = torch.zeros(1, 2, 3, dtype=torch.float32)
        scalar_timestep = torch.tensor(0.5, dtype=torch.float32)

        def _fake_generate(**kwargs):
            self.assertEqual(kwargs["timesteps"], [0.5])
            return {"target_latents": np.zeros((1, 2, 3), dtype=np.float32), "time_costs": {}}

        with patch("acestep.core.generation.handler.diffusion.mlx_generate_diffusion", side_effect=_fake_generate):
            result = host._mlx_run_diffusion(
                encoder_hidden_states=encoder_hidden_states,
                encoder_attention_mask=encoder_attention_mask,
                context_latents=context_latents,
                src_latents=src_latents,
                seed=1,
                timesteps=scalar_timestep,
            )

        self.assertEqual(tuple(result["target_latents"].shape), (1, 2, 3))
        self.assertEqual(result["target_latents"].dtype, torch.float32)

    def test_mlx_run_diffusion_rejects_invalid_infer_method(self):
        """Invalid diffusion method should raise ``ValueError``."""
        host = _Host()
        x = torch.randn(1, 2, 3)
        with self.assertRaises(ValueError):
            host._mlx_run_diffusion(
                encoder_hidden_states=x,
                encoder_attention_mask=torch.ones(1, 2, dtype=torch.int64),
                context_latents=torch.randn(1, 4, 3),
                src_latents=torch.randn(1, 2, 3),
                seed=1,
                infer_method="bad",
            )

    def test_mlx_run_diffusion_rejects_non_iterable_timesteps(self):
        """Non-iterable timestep input should raise ``TypeError``."""
        host = _Host()
        x = torch.randn(1, 2, 3)
        with self.assertRaises(TypeError):
            host._mlx_run_diffusion(
                encoder_hidden_states=x,
                encoder_attention_mask=torch.ones(1, 2, dtype=torch.int64),
                context_latents=torch.randn(1, 4, 3),
                src_latents=torch.randn(1, 2, 3),
                seed=1,
                timesteps=123,
            )

    def test_mlx_run_diffusion_rejects_batch_mismatch(self):
        """Batch-size mismatches across tensors should raise ``ValueError``."""
        host = _Host()
        with self.assertRaises(ValueError):
            host._mlx_run_diffusion(
                encoder_hidden_states=torch.randn(2, 2, 3),
                encoder_attention_mask=torch.ones(2, 2, dtype=torch.int64),
                context_latents=torch.randn(1, 4, 3),
                src_latents=torch.randn(2, 2, 3),
                seed=1,
            )

    def test_mlx_run_diffusion_requires_host_attributes(self):
        """Missing required host attributes should raise ``AttributeError``."""
        class _BrokenHost(DiffusionMixin):
            """Host missing required diffusion attributes."""

            pass

        host = _BrokenHost()
        x = torch.randn(1, 2, 3)
        with self.assertRaises(AttributeError):
            host._mlx_run_diffusion(
                encoder_hidden_states=x,
                encoder_attention_mask=torch.ones(1, 2, dtype=torch.int64),
                context_latents=torch.randn(1, 4, 3),
                src_latents=torch.randn(1, 2, 3),
                seed=1,
            )


if __name__ == "__main__":
    unittest.main()
