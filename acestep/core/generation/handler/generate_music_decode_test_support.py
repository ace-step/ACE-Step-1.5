"""Shared fixtures for ``generate_music_decode`` mixin tests."""

from contextlib import contextmanager

import acestep.core.generation.handler.generate_music_decode as GENERATE_MUSIC_DECODE_MODULE
import torch
from acestep.core.generation.handler.generate_music_decode import GenerateMusicDecodeMixin


class FakeDecodeOutput:
    """Minimal VAE decode output container exposing ``sample`` attribute."""

    def __init__(self, sample: torch.Tensor):
        self.sample = sample


class FakeVae:
    """Minimal VAE stand-in with dtype, decode, and parameter iteration hooks."""

    def __init__(self):
        self.dtype = torch.float32
        self._param = torch.nn.Parameter(torch.zeros(1))

    def decode(self, latents: torch.Tensor):
        return FakeDecodeOutput(torch.ones(latents.shape[0], 2, 8))

    def parameters(self):
        yield self._param

    def cpu(self):
        return self

    def to(self, *_args, **_kwargs):
        return self


class DecodeTestHost(GenerateMusicDecodeMixin):
    """Minimal decode-mixin host exposing deterministic state for assertions."""

    def __init__(self):
        self.current_offload_cost = 0.25
        self.debug_stats = False
        self._last_diffusion_per_step_sec = None
        self.estimate_calls = []
        self.progress_calls = []
        self.device = "cpu"
        self.use_mlx_vae = True
        self.mlx_vae = object()
        self.vae = FakeVae()

    def _update_progress_estimate(self, **kwargs):
        self.estimate_calls.append(kwargs)

    @contextmanager
    def _load_model_context(self, _model_name):
        yield

    def _empty_cache(self):
        return None

    def _memory_allocated(self):
        return 0.0

    def _max_memory_allocated(self):
        return 0.0

    def _get_component_device(self, component: str) -> str:
        _ = component
        return self.device

    def _mlx_vae_decode(self, latents):
        _ = latents
        return torch.ones(1, 2, 8)

    def tiled_decode(self, latents):
        _ = latents
        return torch.ones(1, 2, 8)
