"""Unit tests for ACESTEP_DTYPE CUDA dtype override resolution.

Covers acestep.core.generation.handler.init_service_orchestrator's
_resolve_cuda_dtype_override() (ACE_STEP_DTYPE_OVERRIDE_V1) and its wiring
into initialize_service()'s pre-Ampere CUDA branch.
"""

import os
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

from acestep.core.generation.handler import init_service_orchestrator as orch
from acestep.core.generation.handler.init_service import InitServiceMixin


class _Host(InitServiceMixin):
    """Minimal host object exposing InitServiceMixin for focused unit testing."""

    def __init__(self, project_root: str, device: str = "cpu", config=None):
        """Initialize a lightweight host state used by mixin tests."""
        self._project_root = project_root
        self.device = device
        self.config = config
        self.model = None
        self.vae = None
        self.text_encoder = None
        self.text_tokenizer = None
        self.dtype = torch.float32
        self.offload_to_cpu = False
        self.offload_dit_to_cpu = False
        self.compiled = False
        self.quantization = None
        self.last_init_params = None
        self.mlx_decoder = None
        self.use_mlx_dit = False
        self.mlx_vae = None
        self.use_mlx_vae = False
        self.current_offload_cost = 0.0

    def _get_project_root(self):
        """Return the fake project root path configured for the test host."""
        return self._project_root

    def _get_vae_dtype(self, _device: str = "cpu"):
        """Return a stable dtype for VAE-related tests."""
        return torch.float32

    def _init_mlx_dit(self, compile_model: bool = False) -> bool:
        """Stub MLX DiT init hook and always report unavailable in tests."""
        _ = compile_model
        return False

    def _init_mlx_vae(self) -> bool:
        """Stub MLX VAE init hook and always report unavailable in tests."""
        return False


def _clear_acestep_dtype_env():
    """Return an os.environ snapshot with ACESTEP_DTYPE removed."""
    env = dict(os.environ)
    env.pop("ACESTEP_DTYPE", None)
    return env


class ResolveCudaDtypeOverrideTests(unittest.TestCase):
    """Direct unit tests for _resolve_cuda_dtype_override()."""

    def test_unset_returns_none(self):
        """Unset ACESTEP_DTYPE preserves upstream auto-selection (returns None)."""
        with patch.dict(os.environ, _clear_acestep_dtype_env(), clear=True):
            self.assertIsNone(orch._resolve_cuda_dtype_override())

    def test_float32(self):
        """ACESTEP_DTYPE=float32 resolves to torch.float32."""
        env = {**_clear_acestep_dtype_env(), "ACESTEP_DTYPE": "float32"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(orch._resolve_cuda_dtype_override(), torch.float32)

    def test_float16(self):
        """ACESTEP_DTYPE=float16 resolves to torch.float16."""
        env = {**_clear_acestep_dtype_env(), "ACESTEP_DTYPE": "float16"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(orch._resolve_cuda_dtype_override(), torch.float16)

    def test_bfloat16_when_supported(self):
        """ACESTEP_DTYPE=bfloat16 resolves to torch.bfloat16 when the device supports it."""
        env = {**_clear_acestep_dtype_env(), "ACESTEP_DTYPE": "bfloat16"}
        with patch.dict(os.environ, env, clear=True):
            with patch.object(orch.gpu_config, "cuda_supports_bfloat16", return_value=True):
                self.assertEqual(orch._resolve_cuda_dtype_override(), torch.bfloat16)

    def test_bfloat16_unsupported_raises_explicitly(self):
        """ACESTEP_DTYPE=bfloat16 fails loudly rather than silently substituting a dtype."""
        env = {**_clear_acestep_dtype_env(), "ACESTEP_DTYPE": "bfloat16"}
        with patch.dict(os.environ, env, clear=True):
            with patch.object(orch.gpu_config, "cuda_supports_bfloat16", return_value=False):
                with self.assertRaises(ValueError) as ctx:
                    orch._resolve_cuda_dtype_override()
        self.assertIn("bfloat16", str(ctx.exception))

    def test_unknown_value_raises_explicitly(self):
        """A garbage ACESTEP_DTYPE value is an explicit configuration error."""
        env = {**_clear_acestep_dtype_env(), "ACESTEP_DTYPE": "int8"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError) as ctx:
                orch._resolve_cuda_dtype_override()
        self.assertIn("int8", str(ctx.exception))

    def test_whitespace_and_case_are_normalized(self):
        """Surrounding whitespace and mixed case resolve deterministically."""
        env = {**_clear_acestep_dtype_env(), "ACESTEP_DTYPE": "  Float32  "}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(orch._resolve_cuda_dtype_override(), torch.float32)

    def test_empty_string_is_an_explicit_error_not_unset(self):
        """An explicitly-set empty string is treated as a bad value, not 'unset'."""
        env = {**_clear_acestep_dtype_env(), "ACESTEP_DTYPE": ""}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError):
                orch._resolve_cuda_dtype_override()


class InitializeServiceCudaDtypeRegressionTests(unittest.TestCase):
    """Regression coverage for the causal branch: pre-Ampere CUDA dtype selection."""

    def _run_initialize_service_on_mocked_pre_ampere_cuda(self, env: dict):
        """Run initialize_service() against a mocked pre-Ampere CUDA device.

        Mocks device resolution to "cuda", gpu_config to report ROCm absent
        and bfloat16 unsupported (the pre-Ampere signature), and stubs out
        every downstream model-loading helper so only dtype selection is
        under test. Returns the resulting host.dtype.
        """
        host = _Host(project_root="K:/fake_root", device="cuda")

        def _fake_load_main_model(**_kwargs):
            host.config = types.SimpleNamespace(_attn_implementation="sdpa")
            host.model = object()

        with patch.dict(os.environ, env, clear=True):
            with patch.object(orch.gpu_config, "is_rocm_available", return_value=False):
                with patch.object(orch.gpu_config, "cuda_supports_bfloat16", return_value=False):
                    with patch.object(host, "_resolve_initialize_device", return_value="cuda"):
                        with patch.object(host, "_ensure_models_present", return_value=None):
                            with patch.object(host, "_sync_model_code_if_needed"):
                                with patch.object(
                                    host, "_load_main_model_from_checkpoint", side_effect=_fake_load_main_model
                                ):
                                    with patch.object(
                                        host, "_load_vae_model", return_value="K:/fake_root/checkpoints/vae"
                                    ):
                                        with patch.object(
                                            host,
                                            "_load_text_encoder_and_tokenizer",
                                            return_value="K:/fake_root/checkpoints/Qwen3-Embedding-0.6B",
                                        ):
                                            with patch.object(
                                                host,
                                                "_initialize_mlx_backends",
                                                return_value=("Disabled", "Disabled"),
                                            ):
                                                status, ok = host.initialize_service(
                                                    project_root="K:/fake_root",
                                                    config_path="acestep-v15-turbo",
                                                    device="cuda",
                                                )
        self.assertTrue(ok, msg=status)
        return host.dtype

    def test_pre_ampere_without_override_uses_float16(self):
        """Mocked pre-Ampere GPU without ACESTEP_DTYPE keeps the existing float16 default."""
        dtype = self._run_initialize_service_on_mocked_pre_ampere_cuda(_clear_acestep_dtype_env())
        self.assertEqual(dtype, torch.float16)

    def test_pre_ampere_with_float32_override_uses_float32(self):
        """Mocked pre-Ampere GPU with ACESTEP_DTYPE=float32 uses float32 (the Pascal NaN workaround)."""
        env = {**_clear_acestep_dtype_env(), "ACESTEP_DTYPE": "float32"}
        dtype = self._run_initialize_service_on_mocked_pre_ampere_cuda(env)
        self.assertEqual(dtype, torch.float32)

    def test_pre_ampere_with_invalid_override_fails_initialization(self):
        """An invalid ACESTEP_DTYPE surfaces as a failed initialize_service() call, not a crash."""
        host = _Host(project_root="K:/fake_root", device="cuda")
        env = {**_clear_acestep_dtype_env(), "ACESTEP_DTYPE": "garbage"}
        with patch.dict(os.environ, env, clear=True):
            with patch.object(orch.gpu_config, "is_rocm_available", return_value=False):
                with patch.object(orch.gpu_config, "cuda_supports_bfloat16", return_value=False):
                    with patch.object(host, "_resolve_initialize_device", return_value="cuda"):
                        status, ok = host.initialize_service(
                            project_root="K:/fake_root",
                            config_path="acestep-v15-turbo",
                            device="cuda",
                        )
        self.assertFalse(ok)
        self.assertIn("garbage", status)


if __name__ == "__main__":
    unittest.main()
