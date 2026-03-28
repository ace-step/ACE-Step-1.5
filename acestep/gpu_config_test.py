"""Unit tests for GPU-config LM backend compatibility helpers."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from acestep.gpu_config import get_gpu_config, resolve_lm_backend


class GpuConfigLegacyCudaTests(unittest.TestCase):
    """Verify legacy CUDA devices steer the LM backend away from vLLM."""

    def test_get_gpu_config_forces_pt_backend_on_legacy_cuda(self) -> None:
        """Pre-Volta CUDA devices should expose a PyTorch-only LM recommendation."""
        with patch("acestep.gpu_config.is_legacy_cuda_gpu", return_value=True):
            config = get_gpu_config(gpu_memory_gb=12.0)

        self.assertEqual("pt", config.recommended_backend)
        self.assertEqual("pt_only", config.lm_backend_restriction)

    def test_resolve_lm_backend_forces_pt_when_gpu_is_legacy(self) -> None:
        """vLLM requests should collapse to PyTorch on legacy CUDA GPUs."""
        config = SimpleNamespace(recommended_backend="pt", lm_backend_restriction="pt_only")
        self.assertEqual("pt", resolve_lm_backend("vllm", config))
        self.assertEqual("pt", resolve_lm_backend(None, config))

    def test_resolve_lm_backend_keeps_vllm_when_hardware_allows_it(self) -> None:
        """Modern CUDA tiers should keep the requested vLLM backend."""
        config = SimpleNamespace(recommended_backend="vllm", lm_backend_restriction="all")
        self.assertEqual("vllm", resolve_lm_backend("vllm", config))


if __name__ == "__main__":
    unittest.main()
