"""Tests for ``get_lm_gpu_memory_ratio`` in ``gpu_config``.

Regression: the LM ratio's ``current_usage`` must be the *live tensor* count
(``torch.cuda.memory_allocated``), NOT the driver's ``total - free``. The
driver view counts the CUDA caching allocator's ``inactive`` pool plus the fixed
CUDA-context floor, both of which grow across reloads and inflate ``ratio``
-> KV cache. Using the live-tensor view keeps the ratio stable and matches
``allocate_kv_cache`` (model_runner.py), so a re-init no longer grows the KV
cache.

The tests assert:
  1. ratio derives from ``memory_allocated()``, not ``total - free``.
  2. ratio is IDENTICAL when live tensors are the same, even as ``total - free``
     drifts (simulating allocator fragmentation / context growth), *as long as*
     ``usable_for_lm`` is capped by the LM design budget (the common case; the
     cap hides the free term). This property fails under the old ``total - free``
     implementation.
  3. once ``free`` is low enough that ``usable_for_lm`` is NOT capped, the ratio
     follows ``free`` (more conservative when the GPU is tight) — that is
     intended safety behavior, not a regression.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import acestep.gpu_config as _GPU_CONFIG_MOD
from acestep.gpu_config import get_lm_gpu_memory_ratio


def _make_torch_cuda_mock(device_free_bytes: int, total_bytes: int, allocated_bytes: int) -> MagicMock:
    """Build a torch mock with deterministic CUDA memory stats."""
    mock_cuda = MagicMock()
    mock_cuda.is_available.return_value = True
    mock_cuda.mem_get_info.return_value = (device_free_bytes, total_bytes)
    mock_cuda.memory_allocated.return_value = allocated_bytes
    mock_torch = MagicMock()
    mock_torch.cuda = mock_cuda
    return mock_torch


class GetLmGpuMemoryRatioTests(unittest.TestCase):
    """Unit tests for ``get_lm_gpu_memory_ratio``."""

    GB = 1024 ** 3

    def _run(self, mock_torch: MagicMock, env_debug_vram: str | None = None) -> float:
        """Invoke ``get_lm_gpu_memory_ratio`` with ``torch`` injected via sys.modules."""
        env_overrides = {}
        if env_debug_vram is not None:
            env_overrides["MAX_CUDA_VRAM"] = env_debug_vram
        original_torch = sys.modules.get("torch")
        sys.modules["torch"] = mock_torch
        saved_env = os.environ.pop("MAX_CUDA_VRAM", None)
        try:
            with patch.dict("os.environ", env_overrides, clear=False):
                ratio, _target = get_lm_gpu_memory_ratio("acestep-5Hz-lm-0.6B", 16.0)
                return ratio
        finally:
            if original_torch is None:
                sys.modules.pop("torch", None)
            else:
                sys.modules["torch"] = original_torch
            if saved_env is not None:
                os.environ["MAX_CUDA_VRAM"] = saved_env

    def test_ratio_uses_live_allocated_not_total_free(self):
        """current_usage must be memory_allocated, not total - free.

        16 GB total, 6 GB live tensors, 8 GB driver-free. Old code took
        current_usage = total - free = 8 GB -> ratio 0.631; live view -> 0.506.
        """
        mock_torch = _make_torch_cuda_mock(
            device_free_bytes=8 * self.GB, total_bytes=16 * self.GB, allocated_bytes=6 * self.GB
        )
        ratio = self._run(mock_torch)
        # (6.0 live + 2.1 usable) / 16.0 = 0.50625 (NOT the driver-view 0.63125)
        self.assertAlmostEqual(ratio, 0.50625, places=4)

    def test_ratio_stable_across_free_drift_given_same_live_tensors(self):
        """Same live tensors -> same ratio across total-free drift (usable capped).

        free=8 vs free=6 changes total-free by 2 GB (simulates growing allocator
        pool / context). With the live view, current_usage stays 6 GB, so ratio
        is identical. This holds because usable_for_lm caps at total_target
        (2.1 GB) in both cases, masking the free term. Old code gave 0.631 vs
        0.756 -> fails.
        """
        r_high_free = self._run(
            _make_torch_cuda_mock(device_free_bytes=8 * self.GB, total_bytes=16 * self.GB, allocated_bytes=6 * self.GB)
        )
        r_low_free = self._run(
            _make_torch_cuda_mock(device_free_bytes=6 * self.GB, total_bytes=16 * self.GB, allocated_bytes=6 * self.GB)
        )
        self.assertAlmostEqual(r_high_free, r_low_free, places=4)
        # Sanity: the value is the live-view one in both cases.
        self.assertAlmostEqual(r_high_free, 0.50625, places=4)

    def test_ratio_tracks_free_when_usable_uncapped(self):
        """Tight free (usable_for_lm NOT capped) -> ratio follows free (safe).

        free=3.5 -> usable_raw = 3.5-2.0 = 1.5 < 2.1 cap -> usable=1.5, so the
        ratio is smaller than the capped-case 0.50625. This documents that the
        live-view fix stops inflating the cache when there is room, but still
        tightens when the GPU is genuinely short on free VRAM.
        """
        ratio = self._run(
            _make_torch_cuda_mock(device_free_bytes=3.5 * self.GB, total_bytes=16 * self.GB, allocated_bytes=6 * self.GB)
        )
        # (6.0 live + 1.5 usable) / 16.0 = 0.46875, NOT the capped 0.50625
        self.assertAlmostEqual(ratio, 0.46875, places=4)
        self.assertNotAlmostEqual(ratio, 0.50625, places=4)


if __name__ == "__main__":
    unittest.main()
