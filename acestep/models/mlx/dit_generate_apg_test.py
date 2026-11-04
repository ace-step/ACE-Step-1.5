"""Parity tests: MLX APG guidance must match the PyTorch ``apg_forward``.

Regression for the MLX extract bug on ``acestep-v15-base``: the MLX APG
momentum accumulated ``running = diff + running`` (momentum ``+1``) instead of
PyTorch's ``MomentumBuffer`` update ``running = diff - 0.75 * running``. With
CFG over many base-model steps the guidance drifted and extract returned an
attenuated copy of the source mix instead of the requested stem.
"""

import importlib.util
import unittest

import numpy as np
import torch

from acestep.models.common.apg_guidance import MomentumBuffer, apg_forward

_MLX_AVAILABLE = importlib.util.find_spec("mlx") is not None


def _random_preds(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Return a (cond, uncond) velocity pair shaped ``[B, T, C]``."""
    cond = rng.standard_normal((2, 40, 8)).astype(np.float32)
    uncond = rng.standard_normal((2, 40, 8)).astype(np.float32)
    return cond, uncond


@unittest.skipUnless(_MLX_AVAILABLE, "MLX is not installed")
class MlxApgParityTests(unittest.TestCase):
    """Compare MLX APG against the PyTorch reference used by base models."""

    def test_default_momentum_matches_pytorch_momentum_buffer(self):
        """The MLX default momentum constant must equal MomentumBuffer's."""
        from acestep.models.mlx.dit_generate import APG_MOMENTUM

        self.assertEqual(APG_MOMENTUM, MomentumBuffer().momentum)

    def test_multi_step_apg_with_momentum_matches_pytorch(self):
        """Across several CFG steps the momentum-carrying output must match."""
        import mlx.core as mx

        from acestep.models.mlx.dit_generate import _mlx_apg_forward

        rng = np.random.default_rng(0)
        buffer, state = MomentumBuffer(), {}
        for step in range(8):
            cond, uncond = _random_preds(rng)
            expected = apg_forward(
                torch.from_numpy(cond), torch.from_numpy(uncond), 7.0, buffer, dims=[1]
            ).numpy()
            actual = np.array(_mlx_apg_forward(mx.array(cond), mx.array(uncond), 7.0, state))
            np.testing.assert_allclose(actual, expected, atol=1e-4, err_msg=f"step {step}")

    def test_legacy_accumulating_momentum_diverges_from_pytorch(self):
        """Regression guard: the old ``+1`` momentum must not match PyTorch."""
        import mlx.core as mx

        from acestep.models.mlx.dit_generate import _mlx_apg_forward

        rng = np.random.default_rng(1)
        buffer, state = MomentumBuffer(), {}
        max_err = 0.0
        for _ in range(4):
            cond, uncond = _random_preds(rng)
            expected = apg_forward(
                torch.from_numpy(cond), torch.from_numpy(uncond), 7.0, buffer, dims=[1]
            ).numpy()
            legacy = np.array(
                _mlx_apg_forward(mx.array(cond), mx.array(uncond), 7.0, state, momentum=1.0)
            )
            max_err = max(max_err, float(np.abs(legacy - expected).max()))
        self.assertGreater(max_err, 1e-2)

    def test_apg_without_momentum_state_matches_pytorch(self):
        """Non-target path: APG with no momentum buffer is unchanged."""
        import mlx.core as mx

        from acestep.models.mlx.dit_generate import _mlx_apg_forward

        cond, uncond = _random_preds(np.random.default_rng(2))
        expected = apg_forward(
            torch.from_numpy(cond), torch.from_numpy(uncond), 3.0, None, dims=[1]
        ).numpy()
        actual = np.array(_mlx_apg_forward(mx.array(cond), mx.array(uncond), 3.0, None))
        np.testing.assert_allclose(actual, expected, atol=1e-4)


if __name__ == "__main__":
    unittest.main()
