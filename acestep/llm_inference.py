"""Unit tests for accelerator cache cleanup in ``LLMHandler``."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import torch

try:
    from acestep.llm_inference import LLMHandler
    _IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover - dependency guard
    LLMHandler = None
    _IMPORT_ERROR = exc


@unittest.skipIf(LLMHandler is None, f"llm_inference import unavailable: {_IMPORT_ERROR}")
class LlmAcceleratorCacheCleanupTests(unittest.TestCase):
    """Verify _clear_accelerator_cache clears the correct backend based on self.device."""

    def test_clears_cuda_cache_when_device_is_cuda(self):
        """CUDA cache should be emptied and synchronized when self.device is 'cuda'."""
        handler = LLMHandler()
        handler.device = "cuda"
        with patch("torch.cuda.is_available", return_value=True), \
             patch("torch.cuda.empty_cache") as cache_mock, \
             patch("torch.cuda.synchronize") as sync_mock:
            handler._clear_accelerator_cache()
        cache_mock.assert_called_once()
        sync_mock.assert_called_once()

    def test_clears_xpu_cache_when_device_is_xpu(self):
        """XPU cache should be emptied and synchronized when self.device is 'xpu'."""
        handler = LLMHandler()
        handler.device = "xpu"
        fake_xpu = SimpleNamespace(
            is_available=lambda: True,
            empty_cache=MagicMock(),
            synchronize=MagicMock(),
        )
        with patch.object(torch, "xpu", fake_xpu, create=True):
            handler._clear_accelerator_cache()
        fake_xpu.empty_cache.assert_called_once()
        fake_xpu.synchronize.assert_called_once()

    def test_clears_mps_cache_when_device_is_mps(self):
        """MPS cache should be emptied and synchronized when self.device is 'mps'."""
        handler = LLMHandler()
        handler.device = "mps"
        fake_mps_backend = SimpleNamespace(is_available=lambda: True)
        fake_mps = SimpleNamespace(empty_cache=MagicMock(), synchronize=MagicMock())
        with patch.object(torch.backends, "mps", fake_mps_backend), \
             patch.object(torch, "mps", fake_mps, create=True):
            handler._clear_accelerator_cache()
        fake_mps.empty_cache.assert_called_once()
        fake_mps.synchronize.assert_called_once()

    def test_noop_when_device_is_cpu(self):
        """Method should be a safe no-op when device is CPU."""
        handler = LLMHandler()
        handler.device = "cpu"
        with patch("torch.cuda.empty_cache") as cuda_mock:
            handler._clear_accelerator_cache()
        cuda_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
