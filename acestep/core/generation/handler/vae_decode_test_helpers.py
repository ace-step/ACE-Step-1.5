"""Shared stubs used by VAE decode unit tests."""

import torch

from acestep.core.generation.handler.vae_decode import VaeDecodeMixin
from acestep.core.generation.handler.vae_decode_chunks import VaeDecodeChunksMixin


class _DecodeOutput:
    """Minimal decoder output wrapper exposing ``sample``."""

    def __init__(self, sample: torch.Tensor):
        """Store decoded sample tensor."""
        self.sample = sample


class _FakeVae:
    """Simple VAE stub with injectable decode behavior."""

    def __init__(self, decode_fn=None):
        """Bind optional decode function and initialize default parameter."""
        self._decode_fn = decode_fn
        self._param = torch.nn.Parameter(torch.zeros(1))

    def parameters(self):
        """Yield a single parameter to emulate module parameter iteration."""
        yield self._param

    def cpu(self):
        """Return self to emulate in-place module migration."""
        return self

    def float(self):
        """Return self to emulate in-place dtype cast."""
        return self

    def to(self, target):
        """Return self for chained ``to(...)`` transitions in tests."""
        _ = target
        return self

    def decode(self, latents: torch.Tensor):
        """Decode latents using injected behavior or default upsample stub."""
        if self._decode_fn is not None:
            return _DecodeOutput(self._decode_fn(latents))
        bsz, _channels, latent_frames = latents.shape
        return _DecodeOutput(torch.ones(bsz, 2, latent_frames * 2))


class _DecodeHost(VaeDecodeMixin):
    """Host stub for testing VaeDecodeMixin orchestration behavior."""

    def __init__(self):
        """Initialize deterministic decode host state."""
        self.use_mlx_vae = False
        self.mlx_vae = None
        self.device = "mps"
        self.disable_tqdm = True
        self.recorded = {}

    def _get_auto_decode_chunk_size(self):
        """Return deterministic chunk size used by default path."""
        return 64

    def _should_offload_wav_to_cpu(self):
        """Return deterministic offload policy used by default path."""
        return False

    def _tiled_decode_inner(self, latents, chunk_size, overlap, offload_wav_to_cpu):
        """Record routed args and return sentinel audio tensor."""
        _ = latents
        self.recorded["chunk_size"] = chunk_size
        self.recorded["overlap"] = overlap
        self.recorded["offload"] = offload_wav_to_cpu
        return torch.ones(1, 2, 8)

    def _tiled_decode_cpu_fallback(self, latents):
        """Return fallback tensor for failure-path assertions."""
        _ = latents
        return torch.full((1, 2, 8), 2.0)

    def _mlx_vae_decode(self, latents):
        """Return MLX sentinel tensor for MLX path assertions."""
        _ = latents
        return torch.full((1, 2, 6), 3.0)


class _ChunksHost(VaeDecodeChunksMixin):
    """Host stub for testing chunk decode implementations."""

    def __init__(self):
        """Initialize default dependencies and call counters."""
        self.disable_tqdm = True
        self.vae = _FakeVae()
        self.empty_cache_calls = 0
        self.decode_on_cpu_calls = 0
        self.recorded = {}

    def _empty_cache(self):
        """Track cache-empty calls to validate OOM paths."""
        self.empty_cache_calls += 1

    def _decode_on_cpu(self, latents):
        """Return sentinel tensor for CPU-fallback assertions."""
        self.decode_on_cpu_calls += 1
        bsz = latents.shape[0]
        return torch.full((bsz, 2, 7), 9.0)
