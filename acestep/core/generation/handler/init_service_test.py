"""Unit tests for InitServiceMixin behavior and initialization orchestration."""

import importlib
import importlib.util
import os
import builtins
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import torch


def _load_init_service_module():
    """Load init_service module directly from file to avoid package side-effect imports."""
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
    module_path = Path(__file__).with_name("init_service.py")
    spec = importlib.util.spec_from_file_location(
        "acestep.core.generation.handler.init_service",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


INIT_SERVICE_MODULE = _load_init_service_module()
InitServiceMixin = INIT_SERVICE_MODULE.InitServiceMixin
INIT_SERVICE_DOWNLOADS_MODULE = importlib.import_module("acestep.core.generation.handler.init_service_downloads")
INIT_SERVICE_MEMORY_BASIC_MODULE = importlib.import_module("acestep.core.generation.handler.init_service_memory_basic")


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


class InitServiceMixinTests(unittest.TestCase):
    """Behavioral tests for InitServiceMixin helpers and initialization flow."""

    def test_device_type_normalizes_device(self):
        """It normalizes device strings with explicit indexes to backend tokens."""
        host = _Host(project_root="K:/fake_root", device="cuda:0")
        self.assertEqual(host._device_type(), "cuda")

    def test_is_on_target_device_handles_device_alias(self):
        """It treats backend aliases like ``cuda`` and ``cuda:0`` as equivalent."""
        host = _Host(project_root="K:/fake_root", device="cpu")
        t = types.SimpleNamespace(device=types.SimpleNamespace(type="cuda"))
        self.assertTrue(host._is_on_target_device(t, "cuda:0"))
        self.assertFalse(host._is_on_target_device(t, "cpu"))

    def test_is_on_target_device_fallback_does_not_assume_cuda(self):
        """It keeps fallback parsing backend-specific instead of defaulting to CUDA."""
        host = _Host(project_root="K:/fake_root", device="cpu")
        t = types.SimpleNamespace(device=types.SimpleNamespace(type="cuda"))
        self.assertFalse(host._is_on_target_device(t, "mps:0"))

    def test_is_on_target_device_malformed_target_logs_and_returns_false(self):
        """It logs and returns False when target device strings are malformed."""
        host = _Host(project_root="K:/fake_root", device="cpu")
        t = types.SimpleNamespace(device=types.SimpleNamespace(type="cuda"))
        with patch.object(INIT_SERVICE_MEMORY_BASIC_MODULE.logger, "warning") as warning:
            self.assertFalse(host._is_on_target_device(t, ":0"))
        warning.assert_called_once()

    def test_move_module_recursive_preserves_parameter_type(self):
        """It preserves ``torch.nn.Parameter`` objects during recursive device moves."""
        host = _Host(project_root="K:/fake_root", device="cpu")
        module = torch.nn.Linear(2, 2)
        with patch.object(host, "_is_on_target_device", return_value=False):
            host._move_module_recursive(module, "cpu")
        self.assertIsInstance(module.weight, torch.nn.Parameter)
        self.assertIsInstance(module.bias, torch.nn.Parameter)

    def test_move_quantized_param_fallback_wraps_parameter(self):
        """It wraps moved quantized parameters back into ``torch.nn.Parameter``."""
        host = _Host(project_root="K:/fake_root", device="cpu")
        param = torch.nn.Parameter(torch.randn(2), requires_grad=True)
        moved = host._move_quantized_param(param, "cpu")
        self.assertIsInstance(moved, torch.nn.Parameter)
        self.assertTrue(moved.requires_grad)

    def test_get_available_checkpoints_returns_expected_list(self):
        """It returns checkpoint paths only when the checkpoints directory exists."""
        host = _Host(project_root="K:/fake_root")
        with patch("os.path.exists", return_value=False):
            self.assertEqual(host.get_available_checkpoints(), [])

        with patch("os.path.exists", return_value=True):
            self.assertEqual(host.get_available_checkpoints(), [os.path.join("K:/fake_root", "checkpoints")])

    def test_get_available_acestep_v15_models_filters_and_sorts(self):
        """It filters to acestep-v15 directories and returns sorted model names."""
        host = _Host(project_root="K:/fake_root")
        with patch("os.path.exists", return_value=True), patch(
            "os.listdir",
            return_value=["acestep-v15-zeta", "acestep-v15-alpha", "not-a-model", "acestep-v15-file"],
        ), patch(
            "os.path.isdir",
            side_effect=lambda p: p.endswith("acestep-v15-zeta")
            or p.endswith("acestep-v15-alpha")
            or p.endswith("not-a-model"),
        ):
            self.assertEqual(
                host.get_available_acestep_v15_models(),
                ["acestep-v15-alpha", "acestep-v15-zeta"],
            )

    def test_is_turbo_model_uses_config_flag(self):
        """It reflects the ``is_turbo`` flag from handler config."""
        host = _Host(project_root="K:/fake_root", config=None)
        self.assertFalse(host.is_turbo_model())

        host.config = types.SimpleNamespace(is_turbo=True)
        self.assertTrue(host.is_turbo_model())

    def test_is_flash_attention_available_rejects_non_cuda(self):
        """It rejects FlashAttention on non-CUDA targets."""
        host = _Host(project_root="K:/fake_root", device="cpu")
        self.assertFalse(host.is_flash_attention_available())
        self.assertFalse(host.is_flash_attention_available(device="mps"))

    def test_is_flash_attention_available_true_when_cuda_and_module_present(self):
        """It reports available when CUDA, Ampere+, and ``flash_attn`` are present."""
        host = _Host(project_root="K:/fake_root", device="cuda")
        with patch("torch.cuda.is_available", return_value=True):
            with patch("torch.cuda.get_device_capability", return_value=(8, 0)):
                with patch.dict("sys.modules", {"flash_attn": types.SimpleNamespace()}):
                    self.assertTrue(host.is_flash_attention_available())

    def test_is_flash_attention_available_false_when_pre_ampere_gpu(self):
        """It rejects FlashAttention on pre-Ampere CUDA GPUs."""
        host = _Host(project_root="K:/fake_root", device="cuda")
        with patch("torch.cuda.is_available", return_value=True):
            with patch("torch.cuda.get_device_capability", return_value=(7, 5)):
                with patch.dict("sys.modules", {"flash_attn": types.SimpleNamespace()}):
                    self.assertFalse(host.is_flash_attention_available())

    def test_is_flash_attention_available_false_when_module_missing(self):
        """It rejects FlashAttention when the module import fails."""
        host = _Host(project_root="K:/fake_root", device="cuda")
        real_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            """Raise ImportError for flash_attn while delegating all other imports."""
            if name == "flash_attn":
                raise ImportError("flash_attn missing")
            return real_import(name, globals, locals, fromlist, level)

        with patch("torch.cuda.is_available", return_value=True):
            with patch("torch.cuda.get_device_capability", return_value=(8, 0)):
                with patch("builtins.__import__", side_effect=fake_import):
                    self.assertFalse(host.is_flash_attention_available())

    def test_resolve_initialize_device_auto_prefers_cuda(self):
        """It prefers CUDA first when resolving the ``auto`` device mode."""
        host = _Host(project_root="K:/fake_root", device="auto")
        with patch("torch.cuda.is_available", return_value=True):
            with patch("torch.backends.mps.is_available", return_value=False, create=True):
                with patch("torch.xpu", new=types.SimpleNamespace(is_available=lambda: False), create=True):
                    self.assertEqual(host._resolve_initialize_device("auto"), "cuda")

    def test_configure_initialize_runtime_redirects_compile_on_mps(self):
        """It converts MPS compile intent to MLX compile and disables quantization."""
        host = _Host(project_root="K:/fake_root", device="mps")
        compile_model, quantization, mlx_compile_requested = host._configure_initialize_runtime(
            device="mps",
            compile_model=True,
            quantization="int8_weight_only",
        )
        self.assertFalse(compile_model)
        self.assertIsNone(quantization)
        self.assertTrue(mlx_compile_requested)

    def test_configure_initialize_runtime_keeps_settings_on_cuda(self):
        """It leaves compile and quantization flags unchanged for CUDA backends."""
        host = _Host(project_root="K:/fake_root", device="cuda")
        compile_model, quantization, mlx_compile_requested = host._configure_initialize_runtime(
            device="cuda",
            compile_model=True,
            quantization="int8_weight_only",
        )
        self.assertTrue(compile_model)
        self.assertEqual(quantization, "int8_weight_only")
        self.assertFalse(mlx_compile_requested)

    def test_resolve_initialize_device_requested_cuda_falls_back_to_cpu(self):
        """It falls back from CUDA to CPU when no accelerator backends are available."""
        host = _Host(project_root="K:/fake_root", device="cuda")
        with patch("torch.cuda.is_available", return_value=False):
            with patch("torch.backends.mps.is_available", return_value=False, create=True):
                with patch("torch.xpu", new=types.SimpleNamespace(is_available=lambda: False), create=True):
                    self.assertEqual(host._resolve_initialize_device("cuda"), "cpu")

    def test_resolve_initialize_device_requested_cuda_falls_back_to_mps(self):
        """It falls back from CUDA to MPS when MPS is the first available backend."""
        host = _Host(project_root="K:/fake_root", device="cuda")
        with patch("torch.cuda.is_available", return_value=False):
            with patch("torch.backends.mps.is_available", return_value=True, create=True):
                with patch("torch.xpu", new=types.SimpleNamespace(is_available=lambda: True), create=True):
                    self.assertEqual(host._resolve_initialize_device("cuda"), "mps")

    def test_validate_quantization_setup_requires_compile_model(self):
        """It raises ValueError when quantization is requested without compile mode."""
        host = _Host(project_root="K:/fake_root", device="cpu")
        with self.assertRaises(ValueError):
            host._validate_quantization_setup(quantization="int8_weight_only", compile_model=False)

    def test_ensure_models_present_returns_download_error_when_main_model_fails(self):
        """It returns an error tuple when main model download fails."""
        host = _Host(project_root="K:/fake_root", device="cpu")
        with patch.object(INIT_SERVICE_DOWNLOADS_MODULE, "check_main_model_exists", return_value=False):
            with patch.object(INIT_SERVICE_DOWNLOADS_MODULE, "ensure_main_model", return_value=(False, "boom")):
                result = host._ensure_models_present(
                    checkpoint_path=Path("K:/fake_root/checkpoints"),
                    config_path="acestep-v15-turbo",
                    prefer_source=None,
                )
        self.assertEqual(result, ("ERROR: Failed to download main model: boom", False))

    def test_build_initialize_status_message_reports_mlx_compile_label(self):
        """It renders the mx.compile label when MLX compile redirection is active."""
        msg = _Host._build_initialize_status_message(
            device="mps",
            model_path="m",
            vae_path="v",
            text_encoder_path="t",
            dtype=torch.float32,
            attention="sdpa",
            compile_model=False,
            mlx_compile_requested=True,
            offload_to_cpu=False,
            offload_dit_to_cpu=False,
            mlx_dit_status="Active",
            mlx_vae_status="Active",
        )
        self.assertIn("Compiled: mx.compile (MLX)", msg)

    def test_initialize_mlx_backends_disables_dit_when_requested(self):
        """It disables MLX DiT state when caller explicitly opts out."""
        host = _Host(project_root="K:/fake_root", device="cpu")
        host.mlx_decoder = object()
        host.use_mlx_dit = True
        dit_status, vae_status = host._initialize_mlx_backends(
            device="cpu",
            use_mlx_dit=False,
            mlx_compile_requested=False,
        )
        self.assertEqual(dit_status, "Disabled by user")
        self.assertIn("Unavailable", vae_status)
        self.assertIsNone(host.mlx_decoder)
        self.assertFalse(host.use_mlx_dit)

    def test_initialize_service_returns_model_precheck_failure(self):
        """It returns precheck failures without continuing initialization work."""
        host = _Host(project_root="K:/fake_root", device="cpu")
        with patch.object(host, "_ensure_models_present", return_value=("download failed", False)):
            status, ok = host.initialize_service(
                project_root="K:/fake_root",
                config_path="acestep-v15-turbo",
                device="cpu",
            )
        self.assertEqual(status, "download failed")
        self.assertFalse(ok)

    def test_initialize_service_clears_stale_state_on_model_precheck_failure(self):
        """It clears stale model attributes before returning a precheck failure."""
        host = _Host(project_root="K:/fake_root", device="cpu")
        host.model = object()
        host.vae = object()
        host.text_encoder = object()
        host.text_tokenizer = object()
        host.config = object()
        host.silence_latent = object()

        with patch.object(host, "_ensure_models_present", return_value=("download failed", False)):
            status, ok = host.initialize_service(
                project_root="K:/fake_root",
                config_path="acestep-v15-turbo",
                device="cpu",
            )

        self.assertEqual(status, "download failed")
        self.assertFalse(ok)
        self.assertIsNone(host.model)
        self.assertIsNone(host.vae)
        self.assertIsNone(host.text_encoder)
        self.assertIsNone(host.text_tokenizer)
        self.assertIsNone(host.config)
        self.assertIsNone(host.silence_latent)

    def test_initialize_service_uses_provided_project_root_for_checkpoints(self):
        """It builds checkpoint paths from the provided project_root when truthy."""
        host = _Host(project_root="K:/fallback_root", device="cpu")

        def _fake_load_main_model(**kwargs):
            """Capture model path and initialize minimal config state."""
            host._captured_model_path = kwargs["model_checkpoint_path"]
            host.config = types.SimpleNamespace(_attn_implementation="sdpa")
            host.model = object()

        with patch.object(host, "_ensure_models_present", return_value=None):
            with patch.object(host, "_sync_model_code_if_needed"):
                with patch.object(host, "_load_main_model_from_checkpoint", side_effect=_fake_load_main_model):
                    with patch.object(host, "_load_vae_model", return_value="K:/custom_root/checkpoints/vae"):
                        with patch.object(
                            host,
                            "_load_text_encoder_and_tokenizer",
                            return_value="K:/custom_root/checkpoints/Qwen3-Embedding-0.6B",
                        ):
                            with patch.object(host, "_initialize_mlx_backends", return_value=("Disabled", "Disabled")):
                                status, ok = host.initialize_service(
                                    project_root="K:/custom_root",
                                    config_path="acestep-v15-turbo",
                                    device="cpu",
                                )
        self.assertTrue(ok)
        expected_model_path = os.path.normpath("K:/custom_root/checkpoints/acestep-v15-turbo")
        self.assertEqual(os.path.normpath(host._captured_model_path), expected_model_path)
        self.assertIn(expected_model_path, os.path.normpath(status))

    def test_initialize_service_success_uses_decomposed_helpers(self):
        """It executes decomposed helper calls and returns a success status payload."""
        host = _Host(project_root="K:/fake_root", device="cpu")

        def _fake_load_main_model(**_kwargs):
            """Simulate successful main-model load by setting minimal config state."""
            host.config = types.SimpleNamespace(_attn_implementation="sdpa")
            host.model = object()

        with patch.object(host, "_ensure_models_present", return_value=None) as ensure_models:
            with patch.object(host, "_sync_model_code_if_needed") as sync_code:
                with patch.object(host, "_load_main_model_from_checkpoint", side_effect=_fake_load_main_model):
                    with patch.object(host, "_load_vae_model", return_value="K:/fake_root/checkpoints/vae"):
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
                                    device="cpu",
                                )
        self.assertTrue(ok)
        self.assertIn("Model initialized successfully on cpu", status)
        expected_keys = {
            "project_root",
            "config_path",
            "device",
            "use_flash_attention",
            "compile_model",
            "offload_to_cpu",
            "offload_dit_to_cpu",
            "quantization",
            "use_mlx_dit",
            "prefer_source",
        }
        self.assertEqual(set(host.last_init_params.keys()), expected_keys)
        self.assertEqual(host.last_init_params["config_path"], "acestep-v15-turbo")
        self.assertEqual(host.last_init_params["device"], "cpu")
        ensure_models.assert_called_once()
        sync_code.assert_called_once()

    def test_initialize_service_returns_error_payload_when_loader_raises(self):
        """It catches init errors and returns a formatted failure message."""
        host = _Host(project_root="K:/fake_root", device="cpu")
        with patch.object(host, "_ensure_models_present", return_value=None):
            with patch.object(host, "_sync_model_code_if_needed"):
                with patch.object(host, "_load_main_model_from_checkpoint", side_effect=RuntimeError("load failed")):
                    status, ok = host.initialize_service(
                        project_root="K:/fake_root",
                        config_path="acestep-v15-turbo",
                        device="cpu",
                    )
        self.assertFalse(ok)
        self.assertIn("Error initializing model", status)
        self.assertIn("load failed", status)
        self.assertIn("Traceback:", status)
        self.assertIn("RuntimeError: load failed", status)

    def test_validate_quantization_setup_raises_import_error_when_torchao_missing(self):
        """It raises ImportError with guidance when torchao is unavailable."""
        host = _Host(project_root="K:/fake_root", device="cpu")
        real_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            """Raise ImportError only for torchao imports."""
            if name == "torchao":
                raise ImportError("torchao missing")
            return real_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(ImportError) as ctx:
                host._validate_quantization_setup(
                    quantization="int8_weight_only",
                    compile_model=True,
                )
        self.assertIn("torchao is required", str(ctx.exception))

    def test_load_model_context_yields_immediately_when_offload_disabled(self):
        """It does not move models when offload_to_cpu is disabled."""
        host = _Host(project_root="K:/fake_root", device="cpu")
        host.offload_to_cpu = False
        host.model = torch.nn.Linear(1, 1)
        with patch.object(host, "_recursive_to_device") as move_mock:
            with host._load_model_context("model"):
                pass
        move_mock.assert_not_called()

    def test_load_model_context_loads_and_offloads_when_enabled_for_vae(self):
        """It performs load/offload calls around the context body for VAE."""
        host = _Host(project_root="K:/fake_root", device="cpu")
        host.offload_to_cpu = True
        host.vae = torch.nn.Linear(1, 1)
        with patch.object(host, "_recursive_to_device") as move_mock:
            with patch.object(host, "_empty_cache") as empty_cache:
                with host._load_model_context("vae"):
                    pass
        self.assertEqual(move_mock.call_count, 2)
        empty_cache.assert_called_once()

    def test_recursive_to_device_uses_quantized_move_fallback(self):
        """It routes parameters through quantized move fallback after to() failure."""
        host = _Host(project_root="K:/fake_root", device="cpu")
        model = torch.nn.Linear(2, 2)

        def _raise_not_implemented(*_args, **_kwargs):
            """Simulate older torch behavior for quantized tensor moves."""
            raise NotImplementedError("no shallow copy")

        model.to = _raise_not_implemented  # type: ignore[assignment]
        with patch.object(host, "_is_on_target_device", return_value=False):
            with patch.object(host, "_is_quantized_tensor", return_value=True):
                with patch.object(
                    host,
                    "_move_quantized_param",
                    side_effect=lambda p, _d: torch.nn.Parameter(p.data, requires_grad=p.requires_grad),
                ) as move_quant:
                    host._recursive_to_device(model, "cpu")
        self.assertGreaterEqual(move_quant.call_count, 1)

    def test_empty_cache_routes_to_cuda(self):
        """It routes cache clearing to CUDA when the host device is CUDA."""
        host = _Host(project_root="K:/fake_root", device="cuda")
        with patch("torch.cuda.is_available", return_value=True), patch("torch.cuda.empty_cache") as empty_cache:
            host._empty_cache()
            empty_cache.assert_called_once()

    def test_empty_cache_routes_to_xpu(self):
        """It routes cache clearing to XPU when the host device is XPU."""
        host = _Host(project_root="K:/fake_root", device="xpu")
        empty_cache = Mock()
        xpu_stub = types.SimpleNamespace(is_available=lambda: True, empty_cache=empty_cache)
        with patch("torch.xpu", new=xpu_stub, create=True):
            host._empty_cache()
        empty_cache.assert_called_once()

    def test_empty_cache_routes_to_mps(self):
        """It routes cache clearing to MPS when the host device is MPS."""
        host = _Host(project_root="K:/fake_root", device="mps")
        with patch("torch.backends.mps.is_available", return_value=True, create=True), patch("torch.mps.empty_cache") as empty_cache:
            host._empty_cache()
            empty_cache.assert_called_once()

    def test_synchronize_routes_to_cuda(self):
        """It routes synchronization to CUDA when the host device is CUDA."""
        host = _Host(project_root="K:/fake_root", device="cuda")
        with patch("torch.cuda.is_available", return_value=True), patch("torch.cuda.synchronize") as sync:
            host._synchronize()
            sync.assert_called_once()

    def test_synchronize_routes_to_xpu(self):
        """It routes synchronization to XPU when the host device is XPU."""
        host = _Host(project_root="K:/fake_root", device="xpu")
        sync = Mock()
        xpu_stub = types.SimpleNamespace(is_available=lambda: True, synchronize=sync)
        with patch("torch.xpu", new=xpu_stub, create=True):
            host._synchronize()
        sync.assert_called_once()

    def test_synchronize_routes_to_mps(self):
        """It routes synchronization to MPS when the host device is MPS."""
        host = _Host(project_root="K:/fake_root", device="mps")
        with patch("torch.backends.mps.is_available", return_value=True, create=True), patch("torch.mps.synchronize") as sync:
            host._synchronize()
            sync.assert_called_once()

    def test_memory_queries_use_cuda_only(self):
        """It reports memory metrics only for CUDA and returns zero elsewhere."""
        host = _Host(project_root="K:/fake_root", device="cpu")
        self.assertEqual(host._memory_allocated(), 0)
        self.assertEqual(host._max_memory_allocated(), 0)

        host.device = "cuda"
        with patch("torch.cuda.is_available", return_value=True):
            with patch("torch.cuda.memory_allocated", return_value=123), patch(
                "torch.cuda.max_memory_allocated", return_value=456
            ):
                self.assertEqual(host._memory_allocated(), 123)
                self.assertEqual(host._max_memory_allocated(), 456)


if __name__ == "__main__":
    unittest.main()
