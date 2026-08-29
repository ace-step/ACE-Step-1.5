"""Tests for multi-GPU VRAM preflight in ``generate_music`` decode."""

import unittest
from unittest.mock import MagicMock, patch

from acestep.core.generation.handler.generate_music_decode_test_support import (
    GENERATE_MUSIC_DECODE_MODULE,
    DecodeTestHost,
)


class GenerateMusicDecodeVramTests(unittest.TestCase):
    """Verify decode VRAM checks honor mapped component devices."""

    def test_decode_pred_latents_queries_vram_on_mapped_vae_cuda_index(self):
        class VramHost(DecodeTestHost):
            def __init__(self):
                super().__init__()
                self.use_mlx_vae = False
                self.mlx_vae = None
                self.device = "cuda:0"
                self.vae_component_device = "cuda:2"

            def _get_component_device(self, component: str) -> str:
                if component == "vae":
                    return self.vae_component_device
                return self.device

        host = VramHost()
        latent = MagicMock()
        latent.detach.return_value = latent
        latent.transpose.return_value = latent
        latent.contiguous.return_value = latent
        latent.to.return_value = latent

        with patch.object(
            GENERATE_MUSIC_DECODE_MODULE,
            "get_effective_free_vram_gb",
            return_value=8.0,
        ) as free_mock:
            with patch.object(GENERATE_MUSIC_DECODE_MODULE.time, "time", side_effect=[10.0, 11.0]):
                host._decode_generate_music_pred_latents(
                    pred_latents=latent,
                    progress=None,
                    use_tiled_decode=False,
                    time_costs={"total_time_cost": 1.0},
                )

        free_mock.assert_called_once_with(2)


if __name__ == "__main__":
    unittest.main()
