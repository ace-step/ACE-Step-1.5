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

    def test_cuda_syncs_before_clearing(self):
        """CUDA path must synchronize BEFORE emptying cache."""
        handler = LLMHandler()
        handler.device = "cuda"
        call_order = []
        with patch("torch.cuda.is_available", return_value=True), \
             patch("torch.cuda.synchronize", side_effect=lambda: call_order.append("sync")), \
             patch("torch.cuda.empty_cache", side_effect=lambda: call_order.append("clear")):
            handler._clear_accelerator_cache()
        self.assertEqual(call_order, ["sync", "clear"])

    def test_xpu_syncs_before_clearing(self):
        """XPU path must synchronize BEFORE emptying cache."""
        handler = LLMHandler()
        handler.device = "xpu"
        call_order = []
        fake_xpu = SimpleNamespace(
            is_available=lambda: True,
            empty_cache=MagicMock(side_effect=lambda: call_order.append("clear")),
            synchronize=MagicMock(side_effect=lambda: call_order.append("sync")),
        )
        with patch.object(torch, "xpu", fake_xpu, create=True):
            handler._clear_accelerator_cache()
        self.assertEqual(call_order, ["sync", "clear"])

    def test_mps_syncs_before_clearing(self):
        """MPS path must synchronize BEFORE emptying cache."""
        handler = LLMHandler()
        handler.device = "mps"
        call_order = []
        fake_mps_backend = SimpleNamespace(is_available=lambda: True)
        fake_mps = SimpleNamespace(
            empty_cache=MagicMock(side_effect=lambda: call_order.append("clear")),
            synchronize=MagicMock(side_effect=lambda: call_order.append("sync")),
        )
        with patch.object(torch.backends, "mps", fake_mps_backend), \
             patch.object(torch, "mps", fake_mps, create=True):
            handler._clear_accelerator_cache()
        self.assertEqual(call_order, ["sync", "clear"])

    def test_noop_when_device_is_cpu(self):
        """Method should be a safe no-op when device is CPU."""
        handler = LLMHandler()
        handler.device = "cpu"
        with patch("torch.cuda.empty_cache") as cuda_mock:
            handler._clear_accelerator_cache()
        cuda_mock.assert_not_called()

    def test_falls_back_to_cuda_when_device_unset(self):
        """When self.device is None, should fall back to CUDA if available."""
        handler = LLMHandler()
        handler.device = None
        with patch("torch.cuda.is_available", return_value=True), \
             patch("torch.cuda.synchronize") as sync_mock, \
             patch("torch.cuda.empty_cache") as cache_mock:
            handler._clear_accelerator_cache()
        sync_mock.assert_called_once()
        cache_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
