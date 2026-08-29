"""Tests for CPU-offload and VAE restoration in ``generate_music`` decode."""

import unittest
from unittest.mock import patch

import torch

from acestep.core.generation.handler.generate_music_decode_test_support import (
    GENERATE_MUSIC_DECODE_MODULE,
    DecodeTestHost,
    FakeDecodeOutput,
    FakeVae,
)


class GenerateMusicDecodeCpuOffloadTests(unittest.TestCase):
    """Verify CPU-offload decode paths and device restoration."""

    def test_decode_pred_latents_restores_vae_device_on_decode_error(self):
        class FailingVae(FakeVae):
            def __init__(self):
                super().__init__()
                self.cpu_calls = 0
                self.to_calls = []

            def decode(self, latents: torch.Tensor):
                _ = latents
                raise RuntimeError("decode failed")

            def cpu(self):
                self.cpu_calls += 1
                return self

            def to(self, *args, **kwargs):
                self.to_calls.append((args, kwargs))
                return self

        class FailingHost(DecodeTestHost):
            def __init__(self):
                super().__init__()
                self.use_mlx_vae = False
                self.mlx_vae = None
                self.vae = FailingVae()
                self.empty_cache_calls = 0

            def _empty_cache(self):
                self.empty_cache_calls += 1

        host = FailingHost()
        with patch.dict(GENERATE_MUSIC_DECODE_MODULE.os.environ, {"ACESTEP_VAE_ON_CPU": "1"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "decode failed"):
                host._decode_generate_music_pred_latents(
                    pred_latents=torch.ones(1, 4, 3),
                    progress=None,
                    use_tiled_decode=False,
                    time_costs={"total_time_cost": 1.0},
                )

        self.assertEqual(host.vae.cpu_calls, 1)
        self.assertEqual(len(host.vae.to_calls), 1)
        self.assertGreaterEqual(host.empty_cache_calls, 2)

    def test_decode_pred_latents_does_not_restore_latents_to_gpu_after_successful_cpu_decode(self):
        class SuccessVae(FakeVae):
            def __init__(self):
                super().__init__()
                self.vae_to_calls = []

            def decode(self, latents: torch.Tensor):
                return FakeDecodeOutput(torch.ones(latents.shape[0], 2, 8))

            def cpu(self):
                return self

            def to(self, *args, **kwargs):
                self.vae_to_calls.append(args[0] if args else kwargs)
                return self

        class SuccessHost(DecodeTestHost):
            def __init__(self):
                super().__init__()
                self.use_mlx_vae = False
                self.mlx_vae = None
                self.vae = SuccessVae()

        host = SuccessHost()
        with patch.dict(GENERATE_MUSIC_DECODE_MODULE.os.environ, {"ACESTEP_VAE_ON_CPU": "1"}, clear=False):
            pred_wavs, _cpu_latents, _costs = host._decode_generate_music_pred_latents(
                pred_latents=torch.ones(1, 4, 3),
                progress=None,
                use_tiled_decode=False,
                time_costs={"total_time_cost": 1.0},
            )

        self.assertEqual(len(host.vae.vae_to_calls), 1)
        self.assertEqual(tuple(pred_wavs.shape), (1, 2, 8))


if __name__ == "__main__":
    unittest.main()
