"""Tests for ``get_effective_free_vram_gb`` in ``gpu_config``.

Validates that the function correctly accounts for the PyTorch caching
allocator's reserved-but-unused memory so that VRAM checks do not
incorrectly report 0 GB free on machines where all VRAM appears reserved
from the OS perspective but is still internally reusable.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import acestep.gpu_config as _GPU_CONFIG_MOD
from acestep.gpu_config import get_effective_free_vram_gb


def _make_torch_cuda_mock(
    device_free_bytes: int,
    total_bytes: int,
    reserved_bytes: int,
    allocated_bytes: int,
) -> MagicMock:
    """Build a ``torch`` mock whose ``.cuda`` reports deterministic memory stats.

    Args:
        device_free_bytes: Bytes free at the CUDA-driver level.
        total_bytes: Total GPU memory in bytes.
        reserved_bytes: Bytes reserved by the PyTorch caching allocator.
        allocated_bytes: Bytes actively allocated to live tensors.

    Returns:
        A ``MagicMock`` that stands in for the ``torch`` module.
    """
    mock_cuda = MagicMock()
    mock_cuda.is_available.return_value = True
    mock_cuda.mem_get_info.return_value = (device_free_bytes, total_bytes)
    mock_cuda.memory_reserved.return_value = reserved_bytes
    mock_cuda.memory_allocated.return_value = allocated_bytes

    mock_torch = MagicMock()
    mock_torch.cuda = mock_cuda
    # xpu should appear unavailable so the CUDA branch is taken
    mock_torch.xpu.is_available.return_value = False
    return mock_torch


class GetEffectiveFreeVramGbTests(unittest.TestCase):
    """Unit tests for ``get_effective_free_vram_gb``."""

    def _run_with_mock(
        self,
        mock_torch: MagicMock,
        debug_vram_env: str | None = None,
    ) -> float:
        """Invoke ``get_effective_free_vram_gb`` with ``torch`` injected via sys.modules.

        The function does ``import torch`` locally, so we inject our mock into
        ``sys.modules["torch"]`` for the duration of the call.

        Args:
            mock_torch: Replacement ``torch`` module mock.
            debug_vram_env: Value for the ``MAX_CUDA_VRAM`` environment variable,
                or ``None`` to leave it unset.

        Returns:
            The float returned by ``get_effective_free_vram_gb()``.
        """
        env_overrides = {}
        if debug_vram_env is not None:
            env_overrides["MAX_CUDA_VRAM"] = debug_vram_env

        original_torch = sys.modules.get("torch")
        sys.modules["torch"] = mock_torch
        # Remove MAX_CUDA_VRAM from the environment so the non-debug path is
        # exercised unless the caller explicitly provides a value.
        saved_env = os.environ.pop("MAX_CUDA_VRAM", None)
        try:
            with patch.dict("os.environ", env_overrides, clear=False):
                return get_effective_free_vram_gb()
        finally:
            if original_torch is None:
                sys.modules.pop("torch", None)
            else:
                sys.modules["torch"] = original_torch
            if saved_env is not None:
                os.environ["MAX_CUDA_VRAM"] = saved_env

    def test_includes_pytorch_cache_when_device_free_is_zero(self):
        """Returns non-zero free VRAM when device-level free is 0 but allocator cache exists.

        This is the primary regression: models fully occupy VRAM from the OS
        perspective (device_free == 0), but PyTorch's caching allocator holds
        reserved-but-not-allocated memory that can be reused for inference.
        """
        GB = 1024 ** 3
        # Simulate 24 GB card: all reserved by PyTorch, 20 GB actively used
        mock_torch = _make_torch_cuda_mock(
            device_free_bytes=0,
            total_bytes=24 * GB,
            reserved_bytes=24 * GB,
            allocated_bytes=20 * GB,
        )
        result = self._run_with_mock(mock_torch)

        # Expected: 0 (device free) + (24 - 20) GB allocator cache = 4 GB
        self.assertAlmostEqual(result, 4.0, places=2)

    def test_sums_device_free_and_allocator_cache(self):
        """Returns device_free + allocator_cache when both are non-zero."""
        GB = 1024 ** 3
        mock_torch = _make_torch_cuda_mock(
            device_free_bytes=2 * GB,
            total_bytes=24 * GB,
            reserved_bytes=18 * GB,
            allocated_bytes=16 * GB,
        )
        result = self._run_with_mock(mock_torch)

        # Expected: 2 (device free) + (18 - 16) allocator cache = 4 GB
        self.assertAlmostEqual(result, 4.0, places=2)

    def test_returns_zero_when_fully_allocated_no_cache(self):
        """Returns 0 when device free is 0 and all reserved memory is allocated."""
        GB = 1024 ** 3
        mock_torch = _make_torch_cuda_mock(
            device_free_bytes=0,
            total_bytes=8 * GB,
            reserved_bytes=8 * GB,
            allocated_bytes=8 * GB,
        )
        result = self._run_with_mock(mock_torch)

        self.assertAlmostEqual(result, 0.0, places=2)

    def test_returns_zero_when_cuda_unavailable(self):
        """Returns 0 when no CUDA device is present."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.xpu.is_available.return_value = False

        result = self._run_with_mock(mock_torch)

        self.assertEqual(result, 0.0)

    def test_debug_cap_clamps_effective_free(self):
        """Debug MAX_CUDA_VRAM cap limits reported free to the simulated budget."""
        GB = 1024 ** 3
        # Real card: 80 GB; simulating 8 GB; 5 GB allocated, 7 GB reserved
        mock_torch = _make_torch_cuda_mock(
            device_free_bytes=0,
            total_bytes=80 * GB,
            reserved_bytes=7 * GB,
            allocated_bytes=5 * GB,
        )
        result = self._run_with_mock(mock_torch, debug_vram_env="8")

        # Allocator budget = 8 - 0.5 (context) = 7.5 GB
        # process_free = 7.5 - 5 (allocated) = 2.5 GB
        # effective without cap = device_free (0) + pytorch_cache (7 reserved - 5 allocated) = 2 GB
        # clamped = min(2, 2.5) = 2 GB
        self.assertAlmostEqual(result, 2.0, places=1)


if __name__ == "__main__":
    unittest.main()
