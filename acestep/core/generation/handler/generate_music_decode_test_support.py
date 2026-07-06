"""Shared fixtures for ``generate_music_decode`` mixin tests."""

import importlib.util
import sys
import types
from contextlib import contextmanager
from pathlib import Path

import torch


def load_generate_music_decode_module():
    """Load ``generate_music_decode.py`` from disk and return its module object."""
    repo_root = Path(__file__).resolve().parents[4]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    package_paths = {
        "acestep": repo_root / "acestep",
        "acestep.core": repo_root / "acestep" / "core",
        "acestep.core.generation": repo_root / "acestep" / "core" / "generation",
        "acestep.core.generation.handler": repo_root / "acestep" / "core" / "generation" / "handler",
    }
    for package_name, package_path in package_paths.items():
        if package_name in sys.modules:
            continue
        package_module = types.ModuleType(package_name)
        package_module.__path__ = [str(package_path)]
        sys.modules[package_name] = package_module
    module_path = Path(__file__).with_name("generate_music_decode.py")
    spec = importlib.util.spec_from_file_location(
        "acestep.core.generation.handler.generate_music_decode",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


GENERATE_MUSIC_DECODE_MODULE = load_generate_music_decode_module()
GenerateMusicDecodeMixin = GENERATE_MUSIC_DECODE_MODULE.GenerateMusicDecodeMixin


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
