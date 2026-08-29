"""Unit tests for indexed CUDA device resolution in LLMHandler.initialize."""

from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    from acestep.llm_inference import LLMHandler
    from acestep.device_map import is_cuda_device
    _IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover
    LLMHandler = None
    is_cuda_device = None
    _IMPORT_ERROR = exc


@unittest.skipIf(LLMHandler is None, f"llm_inference import unavailable: {_IMPORT_ERROR}")
class TestLmInitializeCudaIndex(unittest.TestCase):
    """Verify auto/cuda:N normalization for LM multi-GPU placement."""

    def _resolved_device(self, device: str) -> str:
        """Run initialize far enough to resolve self.device, then abort cleanly."""
        handler = LLMHandler()
        with patch("acestep.llm_inference.os.path.exists", return_value=False):
            status, ok = handler.initialize(
                checkpoint_dir="/tmp/checkpoints",
                lm_model_path="acestep-5Hz-lm-1.7B",
                backend="pt",
                device=device,
                offload_to_cpu=False,
                dtype=None,
            )
        self.assertFalse(ok)
        self.assertIn("not found", status)
        return handler.device

    @patch("acestep.llm_inference.torch.cuda.is_available", return_value=True)
    def test_auto_normalizes_to_cuda0(self, _mock_cuda):
        """auto on CUDA must become cuda:0, not bare cuda."""
        self.assertEqual(self._resolved_device("auto"), "cuda:0")

    @patch("acestep.llm_inference.torch.cuda.is_available", return_value=True)
    def test_bare_cuda_normalizes_to_cuda0(self, _mock_cuda):
        """Bare cuda must normalize to cuda:0."""
        self.assertEqual(self._resolved_device("cuda"), "cuda:0")

    @patch("acestep.llm_inference.torch.cuda.is_available", return_value=True)
    def test_mapped_cuda_index_preserved(self, _mock_cuda):
        """Explicit cuda:N from device_map must be preserved."""
        self.assertEqual(self._resolved_device("cuda:1"), "cuda:1")

    def test_vllm_gate_accepts_indexed_cuda(self):
        """vLLM CUDA gate must treat cuda:N as CUDA (not force PT)."""
        device = "cuda:1"
        backend = "vllm"
        if backend == "vllm" and not is_cuda_device(device):
            backend = "pt"
        self.assertEqual(backend, "vllm")


if __name__ == "__main__":
    unittest.main()
