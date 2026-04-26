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


class AutoMlxVaeChunkSizeTests(unittest.TestCase):
    """Tests for memory-based MLX VAE chunk size selection."""

    def test_low_memory_returns_256(self):
        from acestep.gpu_config import _auto_mlx_vae_chunk_size
        self.assertEqual(_auto_mlx_vae_chunk_size(mem_gb=16), 256)

    def test_mid_memory_returns_512(self):
        from acestep.gpu_config import _auto_mlx_vae_chunk_size
        self.assertEqual(_auto_mlx_vae_chunk_size(mem_gb=36), 512)

    def test_high_memory_returns_1024(self):
        from acestep.gpu_config import _auto_mlx_vae_chunk_size
        self.assertEqual(_auto_mlx_vae_chunk_size(mem_gb=64), 1024)

    def test_very_high_memory_returns_2048(self):
        from acestep.gpu_config import _auto_mlx_vae_chunk_size
        self.assertEqual(_auto_mlx_vae_chunk_size(mem_gb=128), 2048)

    def test_env_var_override(self):
        import os
        from acestep.gpu_config import _auto_mlx_vae_chunk_size
        with patch.dict(os.environ, {"ACESTEP_MLX_VAE_CHUNK": "1024"}):
            self.assertEqual(_auto_mlx_vae_chunk_size(mem_gb=16), 1024)

    def test_env_var_clamps_to_minimum(self):
        import os
        from acestep.gpu_config import _auto_mlx_vae_chunk_size
        with patch.dict(os.environ, {"ACESTEP_MLX_VAE_CHUNK": "32"}):
            self.assertEqual(_auto_mlx_vae_chunk_size(mem_gb=16), 192)

    def test_invalid_env_var_falls_back_to_memory(self):
        import os
        from acestep.gpu_config import _auto_mlx_vae_chunk_size
        with patch.dict(os.environ, {"ACESTEP_MLX_VAE_CHUNK": "not_a_number"}):
            self.assertEqual(_auto_mlx_vae_chunk_size(mem_gb=16), 256)

    def test_boundary_17gb(self):
        from acestep.gpu_config import _auto_mlx_vae_chunk_size
        self.assertEqual(_auto_mlx_vae_chunk_size(mem_gb=17), 512)

    def test_boundary_37gb(self):
        from acestep.gpu_config import _auto_mlx_vae_chunk_size
        self.assertEqual(_auto_mlx_vae_chunk_size(mem_gb=37), 1024)

    def test_boundary_65gb(self):
        from acestep.gpu_config import _auto_mlx_vae_chunk_size
        self.assertEqual(_auto_mlx_vae_chunk_size(mem_gb=65), 2048)


if __name__ == "__main__":
    unittest.main()
