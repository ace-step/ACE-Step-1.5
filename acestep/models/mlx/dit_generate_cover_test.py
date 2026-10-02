"""Cover initialization regressions using NumPy-backed MLX mocks, without a GPU."""

import math
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from acestep.models.mlx.dit_generate import mlx_generate_diffusion


class CoverInitializationTests(unittest.TestCase):
    """Exercise the diffusion loop with fixed noise and a zero-velocity decoder."""

    def setUp(self) -> None:
        """Replace MLX array operations and the decoder cache with small CPU mocks."""
        self.noise = np.array([[[-2.0, -1.0], [1.0, 2.0]]], dtype=np.float32)
        self.source = np.arange(4, dtype=np.float32).reshape(1, 2, 2) + 10.0
        self.context = np.zeros((1, 2, 3), dtype=np.float32)
        self.draw_noise = MagicMock(return_value=self.noise)
        core = types.ModuleType("mlx.core")
        core.array = np.array
        core.full = np.full
        core.eval = MagicMock()
        core.random = types.SimpleNamespace(key=int, normal=self.draw_noise)
        mlx = types.ModuleType("mlx")
        mlx.core = core
        model = types.ModuleType("acestep.models.mlx.dit_model")
        model.MLXCrossAttentionCache = MagicMock(return_value=None)
        self.enterContext(patch.dict(sys.modules, {
            "mlx": mlx,
            "mlx.core": core,
            "acestep.models.mlx.dit_model": model,
        }))
        self.decoder = MagicMock(return_value=(np.zeros_like(self.noise), None))

    def _generate(self, **overrides) -> dict:
        """Run the real diffusion loop with small arrays and optional overrides."""
        kwargs = {
            "mlx_decoder": self.decoder,
            "encoder_hidden_states_np": np.zeros((1, 2, 4), dtype=np.float32),
            "context_latents_np": self.context,
            "src_latents_shape": self.source.shape,
            "src_latents_np": self.source,
            "seed": 42,
            "shift": 1.0,
            "infer_steps": 4,
            "dcw_enabled": False,
            "disable_tqdm": True,
        }
        kwargs.update(overrides)
        return mlx_generate_diffusion(**kwargs)

    def test_zero_strength_preserves_noise_and_full_schedule(self) -> None:
        """Omitted and explicit zero strength retain the existing four-step path."""
        for overrides in ({"src_latents_np": None}, {"cover_noise_strength": 0.0}):
            with self.subTest(overrides=overrides):
                self.decoder.reset_mock()
                result = self._generate(**overrides)
                np.testing.assert_array_equal(result["target_latents"], self.noise)
                self.assertEqual(
                    [call.kwargs["timestep"][0] for call in self.decoder.call_args_list],
                    [1.0, 0.75, 0.5, 0.25],
                )

    def test_positive_strength_blends_source_and_truncates_schedule(self) -> None:
        """Use the nearest scheduled timestep, including nonzero t at strength one."""
        for strength, start_t, schedule in (
            (0.42, 0.5, [0.5, 0.25]),
            (0.625, 0.5, [0.5, 0.25]),
            (1.0, 0.25, [0.25]),
        ):
            with self.subTest(strength=strength):
                self.decoder.reset_mock()
                result = self._generate(cover_noise_strength=strength)
                expected = start_t * self.noise + (1.0 - start_t) * self.source
                np.testing.assert_allclose(
                    self.decoder.call_args_list[0].kwargs["hidden_states"], expected
                )
                np.testing.assert_allclose(result["target_latents"], expected)
                self.assertEqual(
                    [call.kwargs["timestep"][0] for call in self.decoder.call_args_list],
                    schedule,
                )

    def test_positive_strength_requires_matching_source_latents(self) -> None:
        """Reject absent source values and shapes that would silently broadcast."""
        for source in (None, np.zeros((1, 1, 2), dtype=np.float32)):
            with self.subTest(source=source):
                with self.assertRaisesRegex(ValueError, "src_latents_np"):
                    self._generate(cover_noise_strength=0.5, src_latents_np=source)
        self.decoder.assert_not_called()

    def test_cover_condition_switch_uses_remaining_steps(self) -> None:
        """Recompute the cover-conditioning duration after shortening the schedule."""
        non_cover_context = np.ones_like(self.context)
        self._generate(
            cover_noise_strength=0.42,
            audio_cover_strength=0.5,
            encoder_hidden_states_non_cover_np=np.ones((1, 2, 4), dtype=np.float32),
            context_latents_non_cover_np=non_cover_context,
        )
        self.assertEqual(self.decoder.call_count, 2)
        np.testing.assert_array_equal(
            self.decoder.call_args_list[0].kwargs["context_latents"], self.context
        )
        np.testing.assert_array_equal(
            self.decoder.call_args_list[1].kwargs["context_latents"], non_cover_context
        )

    def test_cover_initialization_follows_retake_mixing(self) -> None:
        """Blend source latents with the already-mixed retake noise."""
        retake_noise = np.full_like(self.noise, 3.0)
        self.draw_noise.side_effect = [self.noise, retake_noise]
        result = self._generate(
            cover_noise_strength=0.5, retake_variance=0.5, retake_seed=99
        )
        mixed_noise = math.cos(math.pi / 4) * self.noise + math.sin(math.pi / 4) * retake_noise
        np.testing.assert_allclose(
            result["target_latents"], 0.5 * mixed_noise + 0.5 * self.source
        )
        self.assertEqual(self.draw_noise.call_count, 2)

    def test_cover_initialization_is_shared_by_heun_and_sde(self) -> None:
        """Both alternate samplers start from the same cover-adjusted state."""
        for method, sampler in (("ode", "heun"), ("sde", "euler")):
            with self.subTest(method=method, sampler=sampler):
                self.decoder.reset_mock()
                self._generate(
                    cover_noise_strength=0.5, infer_method=method, sampler_mode=sampler
                )
                np.testing.assert_allclose(
                    self.decoder.call_args_list[0].kwargs["hidden_states"],
                    0.5 * self.noise + 0.5 * self.source,
                )
                self.assertEqual(self.decoder.call_args_list[0].kwargs["timestep"][0], 0.5)


if __name__ == "__main__":
    unittest.main()
