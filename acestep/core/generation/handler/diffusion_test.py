"""Unit tests for the PyTorch-to-MLX diffusion bridge."""

import unittest
from unittest.mock import patch

import numpy as np
import torch

from acestep.core.generation.handler.diffusion import DiffusionMixin


class _Host(DiffusionMixin):
    def __init__(self, device: str = "cpu", dtype: torch.dtype = torch.float32):
        self.mlx_decoder = object()
        self.device = device
        self.dtype = dtype


class _IterableTimesteps:
    def __init__(self, values):
        self._values = values

    def __iter__(self):
        return iter(self._values)


class DiffusionMixinTests(unittest.TestCase):
    """Validate diffusion input conversion and argument forwarding."""

    def test_mlx_run_diffusion_converts_inputs_and_outputs_tensor(self) -> None:
        """Forward cover strength and source values as float32 NumPy arrays."""
        host = _Host(dtype=torch.float16)
        encoder_hidden_states = torch.randn(2, 4, 8, dtype=torch.float64)
        encoder_attention_mask = torch.ones(2, 4, dtype=torch.int64)
        context_latents = torch.randn(2, 16, 8, dtype=torch.float64)
        src_latents = torch.arange(30, dtype=torch.float64).reshape(2, 3, 5)
        timesteps = torch.tensor([1.0, 0.5], dtype=torch.float32)
        non_cover_hidden = torch.randn(2, 4, 8, dtype=torch.float64)
        non_cover_mask = torch.ones(2, 4, dtype=torch.int64)
        non_cover_context = torch.randn(2, 16, 8, dtype=torch.float64)
        fake_target = np.ones((2, 3, 5), dtype=np.float32)

        def _fake_generate(**kwargs):
            """Check the bridge inputs and return a fixed latent result."""
            self.assertIs(kwargs["mlx_decoder"], host.mlx_decoder)
            self.assertEqual(kwargs["src_latents_shape"], (2, 3, 5))
            self.assertEqual(kwargs["cover_noise_strength"], 0.42)
            self.assertEqual(kwargs["src_latents_np"].dtype, np.float32)
            np.testing.assert_array_equal(
                kwargs["src_latents_np"], np.arange(30, dtype=np.float32).reshape(2, 3, 5)
            )
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
                cover_noise_strength=0.42,
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

    def test_mlx_run_diffusion_handles_optional_and_iterable_timesteps(self) -> None:
        """Keep zero-strength calls free of unnecessary source-array transfers."""
        host = _Host(dtype=torch.float32)
        encoder_hidden_states = torch.randn(1, 2, 3, dtype=torch.float32)
        encoder_attention_mask = torch.ones(1, 2, dtype=torch.int64)
        context_latents = torch.randn(1, 4, 3, dtype=torch.float32)
        src_latents = torch.zeros(1, 2, 3, dtype=torch.float32)
        timesteps = _IterableTimesteps([0.9, 0.8, 0.7])

        def _fake_generate(**kwargs):
            """Check default cover arguments and return a fixed latent result."""
            self.assertEqual(kwargs["timesteps"], [0.9, 0.8, 0.7])
            self.assertEqual(kwargs["cover_noise_strength"], 0.0)
            self.assertIsNone(kwargs["src_latents_np"])
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

    def test_mlx_run_diffusion_rejects_invalid_infer_method(self):
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
        class _BrokenHost(DiffusionMixin):
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
