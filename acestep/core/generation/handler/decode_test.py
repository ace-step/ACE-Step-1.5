import sys
import types
import unittest
from unittest.mock import patch

import numpy as np
import torch

from acestep.core.generation.handler.decode import DecodeMixin


class _Host(DecodeMixin):
    def __init__(self):
        self.disable_tqdm = True
        self._mlx_vae_dtype = np.float32
        self.mlx_vae = types.SimpleNamespace(decode=lambda x: x)


def _fake_mlx_modules():
    mx_core = types.ModuleType("mlx.core")
    mx_core.float32 = np.float32
    mx_core.issubdtype = np.issubdtype
    mx_core.array = lambda x: np.array(x)
    mx_core.eval = lambda *_args, **_kwargs: None
    mx_core.clear_cache = lambda: None
    mx_core.concatenate = lambda parts, axis=0: np.concatenate(parts, axis=axis)
    mlx_pkg = types.ModuleType("mlx")
    mlx_pkg.core = mx_core
    return {"mlx": mlx_pkg, "mlx.core": mx_core}


class DecodeMixinTests(unittest.TestCase):
    def test_mlx_decode_single_short_path_uses_decode_fn_directly(self):
        host = _Host()
        z_nlc = np.zeros((1, 32, 8), dtype=np.float32)

        with patch.dict(sys.modules, _fake_mlx_modules()):
            result = host._mlx_decode_single(z_nlc, decode_fn=lambda x: x + 1.0)

        self.assertEqual(result.shape, (1, 32, 8))
        self.assertTrue(np.allclose(result, 1.0))

    def test_mlx_decode_single_long_path_tiles_and_concatenates(self):
        host = _Host()
        z_nlc = np.zeros((1, 4096, 8), dtype=np.float32)
        call_counter = {"count": 0}
        # For T=4096 with MLX_CHUNK=2048 and MLX_OVERLAP=64:
        # windows are [0:1984], [1856:3904], [3776:4096].
        # We encode each decoded chunk using absolute sample positions so the
        # concatenated output must become a continuous 0..8191 timeline.
        win_starts = [0, 1856, 3776]

        def _decode_fn(chunk):
            idx = call_counter["count"]
            call_counter["count"] += 1
            upsample_factor = 2
            start = win_starts[idx] * upsample_factor
            length = chunk.shape[1] * upsample_factor
            values = np.arange(start, start + length, dtype=np.float32)
            return values.reshape(1, length, 1)

        with patch.dict(sys.modules, _fake_mlx_modules()):
            result = host._mlx_decode_single(z_nlc, decode_fn=_decode_fn)

        self.assertGreater(call_counter["count"], 1)
        self.assertEqual(result.shape, (1, 8192, 1))
        expected = np.arange(8192, dtype=np.float32).reshape(1, 8192, 1)
        self.assertTrue(np.array_equal(result, expected))

    def test_mlx_decode_single_handles_collapsed_trim_window(self):
        host = _Host()
        z_nlc = np.zeros((1, 4096, 8), dtype=np.float32)
        call_counter = {"count": 0}

        def _decode_fn(chunk):
            call_counter["count"] += 1
            if call_counter["count"] == 1:
                # Establish a large upsample_factor from the first chunk.
                return np.zeros((1, chunk.shape[1] * 4, 2), dtype=np.float32)
            # Force pathological tiny output on later chunks.
            return np.zeros((1, 1, 2), dtype=np.float32)

        with patch.dict(sys.modules, _fake_mlx_modules()):
            result = host._mlx_decode_single(z_nlc, decode_fn=_decode_fn)

        self.assertGreater(call_counter["count"], 1)
        self.assertEqual(result.shape[0], 1)
        self.assertEqual(result.shape[2], 2)
        self.assertGreater(result.shape[1], 0)

    def test_mlx_vae_decode_returns_torch_tensor_in_ncl_layout(self):
        host = _Host()
        host._mlx_compiled_decode = lambda chunk: np.ones((1, chunk.shape[1] * 2, 1), dtype=np.float32)
        latents = torch.zeros((2, 4, 16), dtype=torch.float32)  # [B, C, T]

        with patch.dict(sys.modules, _fake_mlx_modules()):
            with patch.object(host, "_mlx_decode_single", side_effect=lambda single, decode_fn=None: decode_fn(single)):
                result = host._mlx_vae_decode(latents)

        self.assertIsInstance(result, torch.Tensor)
        self.assertEqual(tuple(result.shape), (2, 1, 32))  # [B, C_audio, T_audio]
        self.assertEqual(result.dtype, torch.float32)

    def test_mlx_decode_single_requires_host_attributes(self):
        class _BrokenHost(DecodeMixin):
            pass

        host = _BrokenHost()
        with patch.dict(sys.modules, _fake_mlx_modules()):
            with self.assertRaises(AttributeError):
                host._mlx_decode_single(np.zeros((1, 32, 8), dtype=np.float32), decode_fn=lambda x: x)

    def test_mlx_vae_decode_requires_host_attributes(self):
        class _BrokenHost(DecodeMixin):
            pass

        host = _BrokenHost()
        with patch.dict(sys.modules, _fake_mlx_modules()):
            with self.assertRaises(AttributeError):
                host._mlx_vae_decode(torch.zeros((1, 4, 16), dtype=torch.float32))


if __name__ == "__main__":
    unittest.main()
