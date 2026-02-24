"""Unit tests for ``VaeDecodeMixin`` orchestration behavior."""

import unittest

import torch

from acestep.core.generation.handler.vae_decode_test_helpers import _DecodeHost


class VaeDecodeMixinTests(unittest.TestCase):
    """Verify decode orchestrator paths, fallback policy, and error propagation."""

    def test_tiled_decode_reduces_mps_chunk_and_overlap(self):
        """MPS path clamps chunk/overlap to safe configured limits."""
        host = _DecodeHost()
        out = host.tiled_decode(torch.zeros(1, 4, 128), chunk_size=64, overlap=16)
        self.assertEqual(host.recorded["chunk_size"], 32)
        self.assertEqual(host.recorded["overlap"], 8)
        self.assertFalse(host.recorded["offload"])
        self.assertEqual(tuple(out.shape), (1, 2, 8))

    def test_tiled_decode_mps_runtime_failure_uses_cpu_fallback(self):
        """MPS runtime failures fallback to CPU decode helper."""
        host = _DecodeHost()

        def _raise(*args, **kwargs):
            """Simulate runtime failure inside tiled decode implementation."""
            _ = args, kwargs
            raise RuntimeError("mps decode failure")

        host._tiled_decode_inner = _raise
        out = host.tiled_decode(torch.zeros(1, 4, 32), chunk_size=32, overlap=8)
        self.assertTrue(torch.equal(out, torch.full((1, 2, 8), 2.0)))

    def test_tiled_decode_uses_mlx_fast_path_when_available(self):
        """MLX decode should short-circuit before PyTorch path when enabled."""
        host = _DecodeHost()
        host.use_mlx_vae = True
        host.mlx_vae = object()
        out = host.tiled_decode(torch.zeros(1, 4, 32), chunk_size=32, overlap=8)
        self.assertTrue(torch.equal(out, torch.full((1, 2, 6), 3.0)))

    def test_tiled_decode_falls_back_when_mlx_decode_fails(self):
        """MLX decode errors should fallback to normal tiled decode path."""
        host = _DecodeHost()
        host.use_mlx_vae = True
        host.mlx_vae = object()

        def _mlx_raise(_latents):
            """Raise MLX failure to exercise fallback path."""
            raise ValueError("mlx failed")

        host._mlx_vae_decode = _mlx_raise
        out = host.tiled_decode(torch.zeros(1, 4, 32), chunk_size=32, overlap=8)
        self.assertEqual(tuple(out.shape), (1, 2, 8))
        self.assertEqual(host.recorded["chunk_size"], 32)

    def test_tiled_decode_non_mps_runtime_error_is_raised(self):
        """Non-MPS runtime errors should bubble to caller unchanged."""
        host = _DecodeHost()
        host.device = "cuda"

        def _raise(*args, **kwargs):
            """Raise runtime failure for non-MPS path assertion."""
            _ = args, kwargs
            raise RuntimeError("cuda decode failure")

        host._tiled_decode_inner = _raise
        with self.assertRaises(RuntimeError):
            host.tiled_decode(torch.zeros(1, 4, 32), chunk_size=32, overlap=8)


if __name__ == "__main__":
    unittest.main()
