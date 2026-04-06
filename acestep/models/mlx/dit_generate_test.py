import sys
import types
import unittest
from unittest.mock import patch

import numpy as np

from acestep.models.mlx.dit_generate import mlx_generate_diffusion


class _FakeRandom:
    def normal(self, shape, key=None):
        _ = key
        return np.zeros(shape, dtype=np.float32)

    def key(self, seed):
        return seed


class _FakeDecoder:
    def __call__(
        self,
        hidden_states,
        timestep,
        timestep_r,
        encoder_hidden_states,
        context_latents,
        cache=None,
        use_cache=False,
    ):
        _ = timestep
        _ = timestep_r
        _ = encoder_hidden_states
        _ = context_latents
        _ = use_cache
        return np.zeros_like(hidden_states), cache


class MlxGenerateDiffusionProgressTests(unittest.TestCase):
    def test_progress_callback_fires_once_per_diffusion_step(self):
        fake_mx_core = types.ModuleType("mlx.core")
        fake_mx_core.array = lambda value: np.array(value, dtype=np.float32)
        fake_mx_core.concatenate = lambda values, axis=0: np.concatenate(values, axis=axis)
        fake_mx_core.broadcast_to = lambda value, shape: np.broadcast_to(value, shape)
        fake_mx_core.full = lambda shape, fill_value: np.full(shape, fill_value, dtype=np.float32)
        fake_mx_core.eval = lambda value: value
        fake_mx_core.random = _FakeRandom()

        fake_mlx_pkg = types.ModuleType("mlx")
        fake_mlx_pkg.core = fake_mx_core

        fake_dit_model = types.ModuleType("acestep.models.mlx.dit_model")

        class _FakeCache:
            pass

        fake_dit_model.MLXCrossAttentionCache = _FakeCache

        updates = []
        with patch.dict(
            sys.modules,
            {
                "mlx": fake_mlx_pkg,
                "mlx.core": fake_mx_core,
                "acestep.models.mlx.dit_model": fake_dit_model,
            },
        ):
            result = mlx_generate_diffusion(
                mlx_decoder=_FakeDecoder(),
                encoder_hidden_states_np=np.zeros((1, 2, 3), dtype=np.float32),
                context_latents_np=np.zeros((1, 2, 3), dtype=np.float32),
                src_latents_shape=(1, 2, 3),
                timesteps=[1.0, 0.75, 0.5],
                progress_callback=lambda step, total, desc: updates.append((step, total, desc)),
                disable_tqdm=True,
            )

        self.assertEqual(
            updates,
            [
                (1, 3, "DiT diffusion..."),
                (2, 3, "DiT diffusion..."),
                (3, 3, "DiT diffusion..."),
            ],
        )
        self.assertEqual(tuple(result["target_latents"].shape), (1, 2, 3))


if __name__ == "__main__":
    unittest.main()
