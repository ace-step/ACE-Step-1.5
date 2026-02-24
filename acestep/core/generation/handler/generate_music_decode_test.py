"""Tests for extracted ``generate_music`` decode helper mixin behavior."""

import importlib.util
import types
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import torch


def _load_generate_music_decode_module():
    """Load ``generate_music_decode.py`` from disk and return its module object.

    Raises ``FileNotFoundError`` or ``ImportError`` when loading fails.
    """
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


GENERATE_MUSIC_DECODE_MODULE = _load_generate_music_decode_module()
GenerateMusicDecodeMixin = GENERATE_MUSIC_DECODE_MODULE.GenerateMusicDecodeMixin


class _FakeDecodeOutput:
    """Minimal VAE decode output container exposing ``sample`` attribute."""

    def __init__(self, sample: torch.Tensor):
        """Store decoded sample tensor for mixin decode flow."""
        self.sample = sample


class _FakeVae:
    """Minimal VAE stand-in with dtype, decode, and parameter iteration hooks."""

    def __init__(self):
        """Initialize deterministic dtype/device state for decode tests."""
        self.dtype = torch.float32
        self._param = torch.nn.Parameter(torch.zeros(1))

    def decode(self, latents: torch.Tensor):
        """Return deterministic decoded waveform output."""
        return _FakeDecodeOutput(torch.ones(latents.shape[0], 2, 8))

    def parameters(self):
        """Yield one parameter so `.device` lookups remain valid."""
        yield self._param

    def cpu(self):
        """Return self for test-only CPU transfer calls."""
        return self

    def to(self, *_args, **_kwargs):
        """Return self for test-only device transfer calls."""
        return self


class _Host(GenerateMusicDecodeMixin):
    """Minimal decode-mixin host exposing deterministic state for assertions."""

    def __init__(self):
        """Initialize deterministic runtime state for decode tests."""
        self.current_offload_cost = 0.25
        self.debug_stats = False
        self._last_diffusion_per_step_sec = None
        self.estimate_calls = []
        self.progress_calls = []
        self.device = "cpu"
        self.use_mlx_vae = True
        self.mlx_vae = object()
        self.vae = _FakeVae()

    def _update_progress_estimate(self, **kwargs):
        """Capture estimate updates for assertions."""
        self.estimate_calls.append(kwargs)

    @contextmanager
    def _load_model_context(self, _model_name):
        """Provide no-op model context manager for decode tests."""
        yield

    def _empty_cache(self):
        """Provide no-op cache clear helper for decode tests."""
        return None

    def _memory_allocated(self):
        """Return deterministic allocated-memory value for debug logging."""
        return 0.0

    def _max_memory_allocated(self):
        """Return deterministic max-memory value for debug logging."""
        return 0.0

    def _mlx_vae_decode(self, latents):
        """Return deterministic decoded waveform for MLX decode branch."""
        _ = latents
        return torch.ones(1, 2, 8)

    def tiled_decode(self, latents):
        """Return deterministic decoded waveform for tiled decode branch."""
        _ = latents
        return torch.ones(1, 2, 8)


class GenerateMusicDecodeMixinTests(unittest.TestCase):
    """Verify decode-state preparation and latent decode helper behavior."""

    def test_prepare_decode_state_updates_progress_estimates(self):
        """It updates timing fields and progress estimate metadata for valid latents."""
        host = _Host()
        outputs = {
            "target_latents": torch.ones(1, 4, 3),
            "time_costs": {"total_time_cost": 1.0, "diffusion_per_step_time_cost": 0.2},
        }
        pred_latents, time_costs = host._prepare_generate_music_decode_state(
            outputs=outputs,
            infer_steps_for_progress=8,
            actual_batch_size=1,
            audio_duration=12.0,
            latent_shift=0.0,
            latent_rescale=1.0,
        )
        self.assertEqual(tuple(pred_latents.shape), (1, 4, 3))
        self.assertEqual(time_costs["offload_time_cost"], 0.25)
        self.assertEqual(host._last_diffusion_per_step_sec, 0.2)
        self.assertEqual(host.estimate_calls[0]["infer_steps"], 8)

    def test_prepare_decode_state_raises_for_nan_latents(self):
        """It raises runtime error when diffusion latents contain NaN values."""
        host = _Host()
        outputs = {
            "target_latents": torch.tensor([[[float("nan")]]]),
            "time_costs": {"total_time_cost": 1.0},
        }
        with self.assertRaises(RuntimeError):
            host._prepare_generate_music_decode_state(
                outputs=outputs,
                infer_steps_for_progress=8,
                actual_batch_size=1,
                audio_duration=None,
                latent_shift=0.0,
                latent_rescale=1.0,
            )

    def test_decode_pred_latents_updates_decode_time_and_returns_cpu_latents(self):
        """It decodes latents and updates decode timing metrics in time_costs."""
        host = _Host()
        pred_latents = torch.ones(1, 4, 3)
        time_costs = {"total_time_cost": 1.0}

        def _progress(value, desc=None):
            """Capture progress updates for assertions."""
            host.progress_calls.append((value, desc))

        with patch.object(GENERATE_MUSIC_DECODE_MODULE.time, "time", side_effect=[10.0, 11.5]):
            pred_wavs, pred_latents_cpu, updated_costs = host._decode_generate_music_pred_latents(
                pred_latents=pred_latents,
                progress=_progress,
                use_tiled_decode=False,
                time_costs=time_costs,
            )

        self.assertEqual(tuple(pred_wavs.shape), (1, 2, 8))
        self.assertEqual(pred_latents_cpu.device.type, "cpu")
        self.assertAlmostEqual(updated_costs["vae_decode_time_cost"], 1.5, places=6)
        self.assertAlmostEqual(updated_costs["total_time_cost"], 2.5, places=6)
        self.assertAlmostEqual(updated_costs["offload_time_cost"], 0.25, places=6)
        self.assertEqual(host.progress_calls[0][0], 0.8)

    def test_decode_pred_latents_restores_vae_device_on_decode_error(self):
        """It restores VAE device in the CPU-offload path even when decode raises."""

        class _FailingVae(_FakeVae):
            """VAE double that raises during decode and records transfer calls."""

            def __init__(self):
                """Initialize transfer call trackers for restoration assertions."""
                super().__init__()
                self.cpu_calls = 0
                self.to_calls = []

            def decode(self, latents: torch.Tensor):
                """Raise decode error to exercise restoration in finally branch."""
                _ = latents
                raise RuntimeError("decode failed")

            def cpu(self):
                """Record explicit CPU transfer and return self."""
                self.cpu_calls += 1
                return self

            def to(self, *args, **kwargs):
                """Record restore transfer target and return self."""
                self.to_calls.append((args, kwargs))
                return self

        class _FailingHost(_Host):
            """Host variant that forces non-MLX VAE decode and tracks cache clears."""

            def __init__(self):
                """Set non-MLX state so CPU offload path is exercised deterministically."""
                super().__init__()
                self.use_mlx_vae = False
                self.mlx_vae = None
                self.vae = _FailingVae()
                self.empty_cache_calls = 0

            def _empty_cache(self):
                """Count cache-clear calls to verify finally cleanup runs."""
                self.empty_cache_calls += 1

        host = _FailingHost()
        pred_latents = torch.ones(1, 4, 3)
        time_costs = {"total_time_cost": 1.0}

        with patch.dict(GENERATE_MUSIC_DECODE_MODULE.os.environ, {"ACESTEP_VAE_ON_CPU": "1"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "decode failed"):
                host._decode_generate_music_pred_latents(
                    pred_latents=pred_latents,
                    progress=None,
                    use_tiled_decode=False,
                    time_costs=time_costs,
                )

        self.assertEqual(host.vae.cpu_calls, 1)
        self.assertEqual(len(host.vae.to_calls), 1)
        self.assertGreaterEqual(host.empty_cache_calls, 2)


if __name__ == "__main__":
    unittest.main()
