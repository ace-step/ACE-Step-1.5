"""Unit tests for extracted native MLX VAE encode/decode mixins."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

import numpy as np
import torch
from unittest.mock import patch
def _load_handler_module(module_filename: str, module_name: str):
    """Load a handler mixin module directly from disk for isolated tests."""
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
    module_path = Path(__file__).with_name(module_filename)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
MLX_VAE_DECODE_NATIVE_MODULE = _load_handler_module(
    "mlx_vae_decode_native.py",
    "acestep.core.generation.handler.mlx_vae_decode_native",
)
MLX_VAE_ENCODE_NATIVE_MODULE = _load_handler_module(
    "mlx_vae_encode_native.py",
    "acestep.core.generation.handler.mlx_vae_encode_native",
)
MlxVaeDecodeNativeMixin = MLX_VAE_DECODE_NATIVE_MODULE.MlxVaeDecodeNativeMixin
MlxVaeEncodeNativeMixin = MLX_VAE_ENCODE_NATIVE_MODULE.MlxVaeEncodeNativeMixin


class _Progress:
    """Minimal progress object tracking update calls."""

    def __init__(self, *_args, **_kwargs):
        """Initialize an empty update counter."""
        self.count = 0

    def update(self, amount):
        """Record update increments from mixin helpers."""
        self.count += amount

    def close(self):
        """Provide close API parity with tqdm."""
        return None


class _Host(MlxVaeDecodeNativeMixin, MlxVaeEncodeNativeMixin):
    """Minimal host exposing extracted native MLX encode/decode helper methods."""

    def __init__(self):
        """Initialize fake MLX runtime attributes used by helper methods."""
        self.disable_tqdm = True
        self._mlx_vae_dtype = np.float32
        self.mlx_vae = types.SimpleNamespace(
            decode=lambda chunk: np.repeat(chunk, 2, axis=1),
            encode_and_sample=lambda chunk: chunk[:, ::2, :],
        )
        self._mlx_compiled_decode = self.mlx_vae.decode
        self._mlx_compiled_encode_sample = self.mlx_vae.encode_and_sample


_DEFAULT_FAKE_CACHE_LIMIT = 48 * 1024**3


def _fake_mx_core_module():
    """Create a minimal fake ``mlx.core`` module backed by NumPy arrays."""
    fake_mx_core = types.ModuleType("mlx.core")
    fake_mx_core.float32 = np.float32
    fake_mx_core.float16 = np.float16
    fake_mx_core.array = lambda values: np.array(values)
    fake_mx_core.eval = lambda *_args, **_kwargs: None
    fake_mx_core.clear_cache = lambda *_args, **_kwargs: None
    fake_mx_core.concatenate = lambda values, axis=0: np.concatenate(values, axis=axis)
    fake_mx_core.cache_limit = _DEFAULT_FAKE_CACHE_LIMIT
    fake_mx_core.cache_limit_calls = []

    def set_cache_limit(limit):
        """Record the new cache limit and return the previous one, like MLX."""
        fake_mx_core.cache_limit_calls.append(limit)
        previous = fake_mx_core.cache_limit
        fake_mx_core.cache_limit = limit
        return previous

    fake_mx_core.set_cache_limit = set_cache_limit
    return fake_mx_core


class MlxVaeNativeMixinTests(unittest.TestCase):
    """Behavior tests for extracted native MLX VAE encode/decode helpers."""

    def test_mlx_decode_single_without_tiling_uses_decode_fn(self):
        """It decodes short sequences without entering overlap-discard tiling."""
        host = _Host()
        fake_mx_core = _fake_mx_core_module()
        fake_mlx_pkg = types.ModuleType("mlx")
        fake_mlx_pkg.__path__ = []
        z_nlc = np.ones((1, 64, 1), dtype=np.float32)
        def decode_fn(chunk):
            """Expand latent time axis by factor two for decode test behavior."""
            return np.repeat(chunk, 2, axis=1)
        with patch.dict(sys.modules, {"mlx": fake_mlx_pkg, "mlx.core": fake_mx_core}):
            out = host._mlx_decode_single(z_nlc, decode_fn=decode_fn)
        self.assertEqual(tuple(out.shape), (1, 128, 1))

    def test_mlx_decode_single_with_tiling_concatenates_trimmed_chunks(self):
        """It applies overlap-discard tiling for long latent sequences."""
        host = _Host()
        fake_mx_core = _fake_mx_core_module()
        fake_mlx_pkg = types.ModuleType("mlx")
        fake_mlx_pkg.__path__ = []
        z_nlc = np.ones((1, 2200, 1), dtype=np.float32)
        def decode_fn(chunk):
            """Expand latent time axis by factor two for tiled decode test behavior."""
            return np.repeat(chunk, 2, axis=1)
        with patch.dict(sys.modules, {"mlx": fake_mlx_pkg, "mlx.core": fake_mx_core}):
            out = host._mlx_decode_single(z_nlc, decode_fn=decode_fn)
        self.assertEqual(tuple(out.shape), (1, 4400, 1))

    def test_mlx_vae_decode_returns_torch_tensor_with_expected_shape(self):
        """It converts NCL latents to MLX, decodes, and returns NCL torch tensor."""
        host = _Host()
        fake_mx_core = _fake_mx_core_module()
        fake_mlx_pkg = types.ModuleType("mlx")
        fake_mlx_pkg.__path__ = []
        latents = torch.ones(2, 1, 32, dtype=torch.float32)
        with patch.dict(sys.modules, {"mlx": fake_mlx_pkg, "mlx.core": fake_mx_core}):
            out = host._mlx_vae_decode(latents)
        self.assertEqual(tuple(out.shape), (2, 1, 64))
        self.assertIsInstance(out, torch.Tensor)

    def test_mlx_vae_decode_caps_cache_limit_during_decode_and_restores_it(self):
        """It lowers the MLX cache limit while decoding and restores the previous limit."""
        host = _Host()
        fake_mx_core = _fake_mx_core_module()
        fake_mlx_pkg = types.ModuleType("mlx")
        fake_mlx_pkg.__path__ = []
        limits_seen_by_decode = []

        def decode(chunk):
            """Record the active cache limit and expand latent time axis by two."""
            limits_seen_by_decode.append(fake_mx_core.cache_limit)
            return np.repeat(chunk, 2, axis=1)

        host._mlx_compiled_decode = decode
        latents = torch.ones(2, 1, 32, dtype=torch.float32)
        with patch.dict(sys.modules, {"mlx": fake_mlx_pkg, "mlx.core": fake_mx_core}):
            out = host._mlx_vae_decode(latents)
        cap = MLX_VAE_DECODE_NATIVE_MODULE._MLX_VAE_DECODE_CACHE_LIMIT_BYTES
        self.assertEqual(tuple(out.shape), (2, 1, 64))
        self.assertEqual(limits_seen_by_decode, [cap, cap])
        self.assertEqual(fake_mx_core.cache_limit_calls, [cap, _DEFAULT_FAKE_CACHE_LIMIT])
        self.assertEqual(fake_mx_core.cache_limit, _DEFAULT_FAKE_CACHE_LIMIT)

    def test_mlx_vae_decode_restores_cache_limit_when_decode_raises(self):
        """It restores the previous MLX cache limit even if decoding fails."""
        host = _Host()
        fake_mx_core = _fake_mx_core_module()
        fake_mlx_pkg = types.ModuleType("mlx")
        fake_mlx_pkg.__path__ = []

        def failing_decode(_chunk):
            """Simulate a decode failure."""
            raise RuntimeError("decode failed")

        host._mlx_compiled_decode = failing_decode
        latents = torch.ones(1, 1, 32, dtype=torch.float32)
        with patch.dict(sys.modules, {"mlx": fake_mlx_pkg, "mlx.core": fake_mx_core}):
            with self.assertRaises(RuntimeError):
                host._mlx_vae_decode(latents)
        cap = MLX_VAE_DECODE_NATIVE_MODULE._MLX_VAE_DECODE_CACHE_LIMIT_BYTES
        self.assertEqual(fake_mx_core.cache_limit_calls, [cap, _DEFAULT_FAKE_CACHE_LIMIT])
        self.assertEqual(fake_mx_core.cache_limit, _DEFAULT_FAKE_CACHE_LIMIT)

    def test_mlx_cache_limit_context_restores_previous_limit_on_error(self):
        """It applies the given limit inside the block and restores the old one on exit."""
        fake_mx_core = _fake_mx_core_module()
        limit_inside = []
        with self.assertRaises(ValueError):
            with MLX_VAE_DECODE_NATIVE_MODULE._mlx_cache_limit(fake_mx_core, 123):
                limit_inside.append(fake_mx_core.cache_limit)
                raise ValueError("boom")
        self.assertEqual(limit_inside, [123])
        self.assertEqual(fake_mx_core.cache_limit_calls, [123, _DEFAULT_FAKE_CACHE_LIMIT])
        self.assertEqual(fake_mx_core.cache_limit, _DEFAULT_FAKE_CACHE_LIMIT)

    def test_mlx_cache_limit_context_keeps_lower_previous_limit(self):
        """It does not raise a cache limit the caller already set below the cap."""
        fake_mx_core = _fake_mx_core_module()
        fake_mx_core.cache_limit = 512 * 1024**2
        cap = MLX_VAE_DECODE_NATIVE_MODULE._MLX_VAE_DECODE_CACHE_LIMIT_BYTES
        with MLX_VAE_DECODE_NATIVE_MODULE._mlx_cache_limit(fake_mx_core, cap):
            limit_inside = fake_mx_core.cache_limit
        self.assertEqual(limit_inside, 512 * 1024**2)
        self.assertEqual(fake_mx_core.cache_limit, 512 * 1024**2)

    def test_mlx_cache_limit_context_holds_lock_until_exit(self):
        """It serializes cache-limit scopes and releases the lock even on errors."""
        fake_mx_core = _fake_mx_core_module()
        lock = MLX_VAE_DECODE_NATIVE_MODULE._MLX_CACHE_LIMIT_LOCK
        locked_inside = []
        with self.assertRaises(ValueError):
            with MLX_VAE_DECODE_NATIVE_MODULE._mlx_cache_limit(fake_mx_core, 123):
                locked_inside.append(lock.locked())
                raise ValueError("boom")
        self.assertEqual(locked_inside, [True])
        self.assertFalse(lock.locked())

    def test_mlx_encode_single_without_tiling_updates_progress(self):
        """It encodes short audio in one pass and updates progress once."""
        host = _Host()
        fake_mx_core = _fake_mx_core_module()
        fake_mlx_pkg = types.ModuleType("mlx")
        fake_mlx_pkg.__path__ = []
        progress = _Progress()
        audio_nlc = np.ones((1, 1000, 1), dtype=np.float32)
        with patch.dict(sys.modules, {"mlx": fake_mlx_pkg, "mlx.core": fake_mx_core}):
            out = host._mlx_encode_single(audio_nlc, pbar=progress)
        self.assertEqual(tuple(out.shape), (1, 500, 1))
        self.assertEqual(progress.count, 1)

    def test_mlx_encode_single_with_tiling_updates_progress_per_chunk(self):
        """It applies overlap-discard tiling for long audio inputs."""
        host = _Host()
        fake_mx_core = _fake_mx_core_module()
        fake_mlx_pkg = types.ModuleType("mlx")
        fake_mlx_pkg.__path__ = []
        progress = _Progress()
        audio_nlc = np.ones((1, 1_500_000, 1), dtype=np.float32)
        with patch.dict(sys.modules, {"mlx": fake_mlx_pkg, "mlx.core": fake_mx_core}):
            out = host._mlx_encode_single(audio_nlc, pbar=progress)
        self.assertTrue(out.shape[1] > 0)
        self.assertEqual(progress.count, 2)

    def test_mlx_vae_encode_sample_returns_torch_tensor(self):
        """It encodes batched audio and returns NCL torch latents."""
        host = _Host()
        fake_mx_core = _fake_mx_core_module()
        fake_mlx_pkg = types.ModuleType("mlx")
        fake_mlx_pkg.__path__ = []
        audio = torch.ones(2, 1, 1200, dtype=torch.float32)
        with patch.dict(sys.modules, {"mlx": fake_mlx_pkg, "mlx.core": fake_mx_core}):
            with patch.object(MLX_VAE_ENCODE_NATIVE_MODULE, "tqdm", _Progress):
                out = host._mlx_vae_encode_sample(audio)
        self.assertIsInstance(out, torch.Tensor)
        self.assertEqual(tuple(out.shape), (2, 1, 600))

    def test_mlx_decode_single_respects_custom_chunk_size(self):
        """It uses self.mlx_vae_chunk_size when set on the host instance."""
        host = _Host()
        # Set a small chunk size so tiling is triggered on a moderately long sequence
        host.mlx_vae_chunk_size = 256
        fake_mx_core = _fake_mx_core_module()
        fake_mlx_pkg = types.ModuleType("mlx")
        fake_mlx_pkg.__path__ = []
        # 512 frames > 256 chunk size, so tiling should activate
        z_nlc = np.ones((1, 512, 1), dtype=np.float32)
        decode_calls = []

        def tracking_decode_fn(chunk):
            """Track chunk sizes passed to decode and expand by factor two."""
            decode_calls.append(chunk.shape[1])
            return np.repeat(chunk, 2, axis=1)

        with patch.dict(sys.modules, {"mlx": fake_mlx_pkg, "mlx.core": fake_mx_core}):
            out = host._mlx_decode_single(z_nlc, decode_fn=tracking_decode_fn)
        # Tiling was used: multiple decode calls were made
        self.assertGreater(len(decode_calls), 1)
        # Output length should match input * upsample factor
        self.assertEqual(tuple(out.shape), (1, 1024, 1))

    def test_mlx_decode_single_no_tiling_with_large_chunk_size(self):
        """It skips tiling when mlx_vae_chunk_size exceeds the latent length."""
        host = _Host()
        host.mlx_vae_chunk_size = 2048
        fake_mx_core = _fake_mx_core_module()
        fake_mlx_pkg = types.ModuleType("mlx")
        fake_mlx_pkg.__path__ = []
        z_nlc = np.ones((1, 256, 1), dtype=np.float32)
        decode_calls = []

        def tracking_decode_fn(chunk):
            """Track decode calls and expand latent time axis by factor two."""
            decode_calls.append(chunk.shape[1])
            return np.repeat(chunk, 2, axis=1)

        with patch.dict(sys.modules, {"mlx": fake_mlx_pkg, "mlx.core": fake_mx_core}):
            out = host._mlx_decode_single(z_nlc, decode_fn=tracking_decode_fn)
        # No tiling: single decode call
        self.assertEqual(len(decode_calls), 1)
        self.assertEqual(tuple(out.shape), (1, 512, 1))

    def test_mlx_decode_single_raises_when_mlx_vae_missing(self):
        """It raises a clear runtime error when decode is requested without MLX VAE."""
        host = _Host()
        host._mlx_compiled_decode = None
        host.mlx_vae = None
        fake_mx_core = _fake_mx_core_module()
        fake_mlx_pkg = types.ModuleType("mlx")
        fake_mlx_pkg.__path__ = []
        with patch.dict(sys.modules, {"mlx": fake_mlx_pkg, "mlx.core": fake_mx_core}):
            with self.assertRaises(RuntimeError) as ctx:
                host._mlx_decode_single(np.ones((1, 16, 1), dtype=np.float32))
        self.assertIn("mlx_vae is not initialized", str(ctx.exception))

    def test_mlx_encode_single_raises_when_mlx_vae_missing(self):
        """It raises a clear runtime error when encode is requested without MLX VAE."""
        host = _Host()
        host._mlx_compiled_encode_sample = None
        host.mlx_vae = None
        fake_mx_core = _fake_mx_core_module()
        fake_mlx_pkg = types.ModuleType("mlx")
        fake_mlx_pkg.__path__ = []
        with patch.dict(sys.modules, {"mlx": fake_mlx_pkg, "mlx.core": fake_mx_core}):
            with self.assertRaises(RuntimeError) as ctx:
                host._mlx_encode_single(np.ones((1, 1000, 1), dtype=np.float32))
        self.assertIn("mlx_vae is not initialized", str(ctx.exception))


    def test_mlx_decode_single_default_chunk_tiles_at_512(self):
        """Default chunk=512 tiles sequences that previously decoded in one shot."""
        host = _Host()
        fake_mx_core = _fake_mx_core_module()
        fake_mlx_pkg = types.ModuleType("mlx")
        fake_mlx_pkg.__path__ = []
        z_nlc = np.ones((1, 1500, 1), dtype=np.float32)
        call_sizes = []
        def tracking_decode(chunk):
            call_sizes.append(chunk.shape[1])
            return np.repeat(chunk, 2, axis=1)
        with patch.dict(sys.modules, {"mlx": fake_mlx_pkg, "mlx.core": fake_mx_core}):
            out = host._mlx_decode_single(z_nlc, decode_fn=tracking_decode)
        self.assertEqual(tuple(out.shape), (1, 3000, 1))
        self.assertGreater(len(call_sizes), 1)
        for size in call_sizes:
            self.assertLessEqual(size, 512)


if __name__ == "__main__":
    unittest.main()
