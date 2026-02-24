"""Unit tests for extracted VAE encode mixins."""

import unittest

import torch

from acestep.core.generation.handler.vae_encode import VaeEncodeMixin
from acestep.core.generation.handler.vae_encode_chunks import VaeEncodeChunksMixin


class _Dist:
    """Minimal distribution wrapper exposing ``sample``."""

    def __init__(self, sample):
        """Store latent sample tensor."""
        self._sample = sample

    def sample(self):
        """Return precomputed latent sample."""
        return self._sample


class _EncOut:
    """Minimal encode output wrapper exposing ``latent_dist``."""

    def __init__(self, sample):
        """Store sample wrapper used by tests."""
        self.latent_dist = _Dist(sample)


class _Vae:
    """Simple VAE stub with deterministic temporal downsample."""

    def __init__(self, fn=None):
        """Configure optional encode callback."""
        self.dtype = torch.float32
        self._fn = fn

    def encode(self, audio_chunk):
        """Return deterministic latent tensor (2x temporal downsample)."""
        if self._fn:
            return _EncOut(self._fn(audio_chunk))
        bsz, _c, s = audio_chunk.shape
        return _EncOut(torch.ones(bsz, 4, max(1, s // 2)))


class _Host(VaeEncodeMixin, VaeEncodeChunksMixin):
    """Host combining both encode mixins with minimal dependencies."""

    def __init__(self):
        """Initialize deterministic state for unit tests."""
        self.use_mlx_vae = False
        self.mlx_vae = None
        self.device = "cpu"
        self.vae = _Vae()
        self.disable_tqdm = True
        self.recorded = {}

    def _get_effective_mps_memory_gb(self):
        """Return no override by default."""
        return None

    def _mlx_vae_encode_sample(self, audio):
        """Return MLX sentinel result for MLX-path tests."""
        _ = audio
        return torch.full((1, 4, 6), 3.0)


class VaeEncodeMixinTests(unittest.TestCase):
    """Validate orchestration and chunk path selection for tiled encode."""

    def test_tiled_encode_uses_mlx_path_when_available(self):
        """MLX path should short-circuit PyTorch path."""
        host = _Host()
        host.use_mlx_vae = True
        host.mlx_vae = object()
        out = host.tiled_encode(torch.zeros(1, 2, 16), chunk_size=8, overlap=2)
        self.assertTrue(torch.equal(out, torch.full((1, 4, 6), 3.0)))

    def test_tiled_encode_direct_path_for_short_audio(self):
        """Short audio should encode directly without chunk helpers."""
        host = _Host()
        out = host.tiled_encode(torch.zeros(1, 2, 16), chunk_size=20, overlap=2)
        self.assertEqual(tuple(out.shape), (1, 4, 8))

    def test_tiled_encode_uses_offload_path(self):
        """Offload mode should route through CPU-offload chunk helper."""
        host = _Host()

        def _offload(*args, **kwargs):
            """Capture invocation and return sentinel latents."""
            _ = args, kwargs
            host.recorded["offload"] = True
            return torch.ones(1, 4, 5)

        host._tiled_encode_offload_cpu = _offload
        out = host.tiled_encode(torch.zeros(1, 2, 48), chunk_size=16, overlap=2, offload_latent_to_cpu=True)
        self.assertTrue(host.recorded["offload"])
        self.assertEqual(tuple(out.shape), (1, 4, 5))

    def test_tiled_encode_rejects_invalid_stride(self):
        """Stride <= 0 should raise ValueError."""
        host = _Host()
        with self.assertRaises(ValueError):
            host.tiled_encode(torch.zeros(1, 2, 48), chunk_size=10, overlap=5)

    def test_tiled_encode_routes_to_gpu_chunk_path(self):
        """Non-offload mode should route through GPU chunk helper."""
        host = _Host()

        def _gpu(*args, **kwargs):
            """Capture GPU routing and return sentinel latents."""
            _ = args, kwargs
            host.recorded["gpu"] = True
            return torch.ones(1, 4, 7)

        host._tiled_encode_gpu = _gpu
        out = host.tiled_encode(torch.zeros(1, 2, 64), chunk_size=16, overlap=2, offload_latent_to_cpu=False)
        self.assertTrue(host.recorded["gpu"])
        self.assertEqual(tuple(out.shape), (1, 4, 7))

    def test_tiled_encode_gpu_and_offload_outputs_match(self):
        """GPU and offload chunk methods should agree on deterministic output."""
        host = _Host()
        audio = torch.zeros(1, 2, 40)
        chunk_size = 16
        overlap = 2
        stride = chunk_size - 2 * overlap
        num_steps = 4
        out_gpu = host._tiled_encode_gpu(audio, 1, 40, stride, overlap, num_steps, chunk_size)
        out_offload = host._tiled_encode_offload_cpu(audio, 1, 40, stride, overlap, num_steps, chunk_size)
        self.assertEqual(tuple(out_gpu.shape), (1, 4, 20))
        self.assertEqual(tuple(out_offload.shape), (1, 4, 20))
        self.assertTrue(torch.equal(out_gpu.cpu(), out_offload))

    def test_tiled_encode_offload_returns_cpu_tensor(self):
        """CPU-offload chunk helper should return latents on CPU."""
        host = _Host()
        audio = torch.zeros(1, 2, 40)
        chunk_size = 16
        overlap = 2
        stride = chunk_size - 2 * overlap
        num_steps = 4
        out = host._tiled_encode_offload_cpu(audio, 1, 40, stride, overlap, num_steps, chunk_size)
        self.assertEqual(out.device.type, "cpu")


if __name__ == "__main__":
    unittest.main()
