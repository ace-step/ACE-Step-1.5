"""Tests for enhanced sampler modes in dit_generate.py (issue #957)."""

import unittest
from unittest.mock import MagicMock

import numpy as np

from acestep.models.mlx.dit_generate import (
    VALID_SAMPLER_MODES,
    get_timestep_schedule,
    mlx_generate_diffusion,
)


def _make_fake_decoder():
    """Build a mock decoder that returns input-dependent velocity predictions.

    Uses a simple function of the input so that Heun (which evaluates at a
    different point) produces genuinely different averaged velocity.
    """
    import mlx.core as mx

    def _forward(hidden_states, timestep, timestep_r,
                 encoder_hidden_states, context_latents,
                 cache=None, use_cache=False):
        # Input-dependent: v = 0.01 * hidden + 0.005 * t
        # This makes v(xt) != v(xt_predicted), so Heun differs from Euler
        t_expand = timestep.reshape(-1, 1, 1)
        vt = 0.01 * hidden_states + 0.005 * t_expand
        return vt, cache

    decoder = MagicMock()
    decoder.side_effect = _forward
    return decoder


class SamplerModeValidationTests(unittest.TestCase):
    """Validate sampler_mode parameter handling."""

    def test_valid_sampler_modes(self):
        self.assertIn("euler", VALID_SAMPLER_MODES)
        self.assertIn("heun", VALID_SAMPLER_MODES)

    def test_invalid_sampler_mode_raises(self):
        with self.assertRaises(ValueError):
            mlx_generate_diffusion(
                mlx_decoder=_make_fake_decoder(),
                encoder_hidden_states_np=np.zeros((1, 2, 4), dtype=np.float32),
                context_latents_np=np.zeros((1, 4, 4), dtype=np.float32),
                src_latents_shape=(1, 4, 4),
                seed=42,
                sampler_mode="bad_mode",
            )


class EulerSamplerTests(unittest.TestCase):
    """Verify default Euler sampler produces valid output."""

    def test_euler_ode_basic(self):
        result = mlx_generate_diffusion(
            mlx_decoder=_make_fake_decoder(),
            encoder_hidden_states_np=np.zeros((1, 2, 4), dtype=np.float32),
            context_latents_np=np.zeros((1, 4, 4), dtype=np.float32),
            src_latents_shape=(1, 4, 4),
            seed=42,
            infer_method="ode",
            sampler_mode="euler",
            shift=3.0,
            disable_tqdm=True,
        )
        self.assertIn("target_latents", result)
        self.assertEqual(result["target_latents"].shape, (1, 4, 4))
        self.assertFalse(np.any(np.isnan(result["target_latents"])))
        self.assertEqual(result["time_costs"]["sampler_mode"], "euler")

    def test_euler_sde_basic(self):
        result = mlx_generate_diffusion(
            mlx_decoder=_make_fake_decoder(),
            encoder_hidden_states_np=np.zeros((1, 2, 4), dtype=np.float32),
            context_latents_np=np.zeros((1, 4, 4), dtype=np.float32),
            src_latents_shape=(1, 4, 4),
            seed=42,
            infer_method="sde",
            sampler_mode="euler",
            shift=3.0,
            disable_tqdm=True,
        )
        self.assertIn("target_latents", result)
        self.assertFalse(np.any(np.isnan(result["target_latents"])))


class HeunSamplerTests(unittest.TestCase):
    """Verify Heun (second-order) sampler produces valid output."""

    def test_heun_ode_basic(self):
        result = mlx_generate_diffusion(
            mlx_decoder=_make_fake_decoder(),
            encoder_hidden_states_np=np.zeros((1, 2, 4), dtype=np.float32),
            context_latents_np=np.zeros((1, 4, 4), dtype=np.float32),
            src_latents_shape=(1, 4, 4),
            seed=42,
            infer_method="ode",
            sampler_mode="heun",
            shift=3.0,
            disable_tqdm=True,
        )
        self.assertIn("target_latents", result)
        self.assertEqual(result["target_latents"].shape, (1, 4, 4))
        self.assertFalse(np.any(np.isnan(result["target_latents"])))
        self.assertEqual(result["time_costs"]["sampler_mode"], "heun")

    def test_heun_sde_falls_back_to_euler_sde(self):
        """Heun + SDE should still produce valid output (SDE path used)."""
        result = mlx_generate_diffusion(
            mlx_decoder=_make_fake_decoder(),
            encoder_hidden_states_np=np.zeros((1, 2, 4), dtype=np.float32),
            context_latents_np=np.zeros((1, 4, 4), dtype=np.float32),
            src_latents_shape=(1, 4, 4),
            seed=42,
            infer_method="sde",
            sampler_mode="heun",
            shift=3.0,
            disable_tqdm=True,
        )
        self.assertIn("target_latents", result)
        self.assertFalse(np.any(np.isnan(result["target_latents"])))

    def test_heun_differs_from_euler(self):
        """Heun should produce different results than Euler given same seed."""
        common_kwargs = dict(
            encoder_hidden_states_np=np.zeros((1, 2, 4), dtype=np.float32),
            context_latents_np=np.zeros((1, 4, 4), dtype=np.float32),
            src_latents_shape=(1, 4, 4),
            seed=42,
            infer_method="ode",
            shift=3.0,
            disable_tqdm=True,
        )
        euler_result = mlx_generate_diffusion(
            mlx_decoder=_make_fake_decoder(),
            sampler_mode="euler",
            **common_kwargs,
        )
        heun_result = mlx_generate_diffusion(
            mlx_decoder=_make_fake_decoder(),
            sampler_mode="heun",
            **common_kwargs,
        )
        self.assertEqual(euler_result["target_latents"].shape, heun_result["target_latents"].shape)
        # Heun averages two evaluations so should produce numerically different output
        self.assertFalse(
            np.allclose(euler_result["target_latents"], heun_result["target_latents"]),
            "Heun and Euler should produce different results with the same seed",
        )

    def test_heun_sde_logs_warning(self):
        """Heun + SDE should still work but the combination falls back to Euler SDE."""
        import logging
        with self.assertLogs("acestep.models.mlx.dit_generate", level=logging.WARNING) as cm:
            mlx_generate_diffusion(
                mlx_decoder=_make_fake_decoder(),
                encoder_hidden_states_np=np.zeros((1, 2, 4), dtype=np.float32),
                context_latents_np=np.zeros((1, 4, 4), dtype=np.float32),
                src_latents_shape=(1, 4, 4),
                seed=42,
                infer_method="sde",
                sampler_mode="heun",
                shift=3.0,
                disable_tqdm=True,
            )
        self.assertTrue(any("not supported with SDE" in msg for msg in cm.output))


class VelocityNormClampTests(unittest.TestCase):
    """Verify velocity norm clamping produces valid output."""

    def test_norm_clamping_produces_valid_output(self):
        result = mlx_generate_diffusion(
            mlx_decoder=_make_fake_decoder(),
            encoder_hidden_states_np=np.zeros((1, 2, 4), dtype=np.float32),
            context_latents_np=np.zeros((1, 4, 4), dtype=np.float32),
            src_latents_shape=(1, 4, 4),
            seed=42,
            sampler_mode="euler",
            velocity_norm_threshold=2.0,
            shift=3.0,
            disable_tqdm=True,
        )
        self.assertIn("target_latents", result)
        self.assertFalse(np.any(np.isnan(result["target_latents"])))

    def test_norm_clamping_with_heun(self):
        result = mlx_generate_diffusion(
            mlx_decoder=_make_fake_decoder(),
            encoder_hidden_states_np=np.zeros((1, 2, 4), dtype=np.float32),
            context_latents_np=np.zeros((1, 4, 4), dtype=np.float32),
            src_latents_shape=(1, 4, 4),
            seed=42,
            sampler_mode="heun",
            velocity_norm_threshold=1.5,
            shift=3.0,
            disable_tqdm=True,
        )
        self.assertIn("target_latents", result)
        self.assertFalse(np.any(np.isnan(result["target_latents"])))


class VelocityEMATests(unittest.TestCase):
    """Verify velocity EMA smoothing produces valid output."""

    def test_ema_smoothing_produces_valid_output(self):
        result = mlx_generate_diffusion(
            mlx_decoder=_make_fake_decoder(),
            encoder_hidden_states_np=np.zeros((1, 2, 4), dtype=np.float32),
            context_latents_np=np.zeros((1, 4, 4), dtype=np.float32),
            src_latents_shape=(1, 4, 4),
            seed=42,
            sampler_mode="euler",
            velocity_ema_factor=0.1,
            shift=3.0,
            disable_tqdm=True,
        )
        self.assertIn("target_latents", result)
        self.assertFalse(np.any(np.isnan(result["target_latents"])))

    def test_ema_with_heun_and_norm_clamping(self):
        """All three techniques combined should produce valid output."""
        result = mlx_generate_diffusion(
            mlx_decoder=_make_fake_decoder(),
            encoder_hidden_states_np=np.zeros((1, 2, 4), dtype=np.float32),
            context_latents_np=np.zeros((1, 4, 4), dtype=np.float32),
            src_latents_shape=(1, 4, 4),
            seed=42,
            sampler_mode="heun",
            velocity_norm_threshold=2.0,
            velocity_ema_factor=0.15,
            shift=3.0,
            disable_tqdm=True,
        )
        self.assertIn("target_latents", result)
        self.assertFalse(np.any(np.isnan(result["target_latents"])))


class GenerationParamsValidationTests(unittest.TestCase):
    """Verify GenerationParams validates sampler parameters."""

    def test_invalid_sampler_mode_raises(self):
        from acestep.inference import GenerationParams
        with self.assertRaises(ValueError):
            GenerationParams(sampler_mode="invalid")

    def test_negative_norm_threshold_raises(self):
        from acestep.inference import GenerationParams
        with self.assertRaises(ValueError):
            GenerationParams(velocity_norm_threshold=-1.0)

    def test_ema_factor_out_of_range_raises(self):
        from acestep.inference import GenerationParams
        with self.assertRaises(ValueError):
            GenerationParams(velocity_ema_factor=1.5)

    def test_valid_params_accepted(self):
        from acestep.inference import GenerationParams
        p = GenerationParams(sampler_mode="heun", velocity_norm_threshold=2.0, velocity_ema_factor=0.1)
        self.assertEqual(p.sampler_mode, "heun")


class DiffusionBridgeNewParamsTests(unittest.TestCase):
    """Verify new parameters pass through the DiffusionMixin bridge."""

    def test_new_params_forwarded_to_mlx_generate(self):
        from unittest.mock import patch
        import torch
        from acestep.core.generation.handler.diffusion import DiffusionMixin

        class _Host(DiffusionMixin):
            def __init__(self):
                self.mlx_decoder = object()
                self.device = "cpu"
                self.dtype = torch.float32

        host = _Host()
        captured = {}

        def _fake_generate(**kwargs):
            captured.update(kwargs)
            return {"target_latents": np.zeros((1, 2, 3), dtype=np.float32), "time_costs": {}}

        with patch("acestep.core.generation.handler.diffusion.mlx_generate_diffusion", side_effect=_fake_generate):
            host._mlx_run_diffusion(
                encoder_hidden_states=torch.randn(1, 2, 3),
                encoder_attention_mask=torch.ones(1, 2),
                context_latents=torch.randn(1, 4, 3),
                src_latents=torch.randn(1, 2, 3),
                seed=1,
                sampler_mode="heun",
                velocity_norm_threshold=2.5,
                velocity_ema_factor=0.1,
            )

        self.assertEqual(captured["sampler_mode"], "heun")
        self.assertEqual(captured["velocity_norm_threshold"], 2.5)
        self.assertEqual(captured["velocity_ema_factor"], 0.1)


if __name__ == "__main__":
    unittest.main()
