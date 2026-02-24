"""Unit tests for extracted MLX VAE initialization mixin."""
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
def _load_handler_module(filename: str, module_name: str) -> types.ModuleType:
    """Load a handler mixin module for isolated tests.

    Args:
        filename: Module filename in the current test directory.
        module_name: Fully-qualified module name used for import execution.
    Returns:
        Loaded module object.
    Raises:
        FileNotFoundError, ImportError, SyntaxError: On module load failures.
    """
    repo_root = Path(__file__).resolve().parents[4]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    package_paths = {
        "acestep": repo_root / "acestep",
        "acestep.core": repo_root / "acestep" / "core",
        "acestep.core.generation": repo_root / "acestep" / "core" / "generation",
        "acestep.core.generation.handler": repo_root / "acestep" / "core" / "generation" / "handler",
    }
    previous_modules = {name: sys.modules.get(name) for name in package_paths}
    try:
        for package_name, package_path in package_paths.items():
            if package_name in sys.modules:
                continue
            package_module = types.ModuleType(package_name)
            package_module.__path__ = [str(package_path)]
            sys.modules[package_name] = package_module
        module_path = Path(__file__).with_name(filename)
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load module spec for {module_name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for package_name, previous in previous_modules.items():
            if previous is None:
                sys.modules.pop(package_name, None)
            else:
                sys.modules[package_name] = previous
MLX_VAE_INIT_MODULE = _load_handler_module(
    "mlx_vae_init.py",
    "acestep.core.generation.handler.mlx_vae_init",
)
MlxVaeInitMixin = MLX_VAE_INIT_MODULE.MlxVaeInitMixin
class _VaeHost(MlxVaeInitMixin):
    """Minimal host exposing VAE init state used by tests."""

    def __init__(self):
        """Initialize deterministic VAE placeholders."""
        self.vae = object()
        self.mlx_vae = None
        self.use_mlx_vae = False
        self._mlx_vae_dtype = None
class _FakeMlxVae:
    """Simple fake MLX VAE object with decode/encode callables."""

    def decode(self, value):
        """Return tagged decode output."""
        return ("decode", value)

    def encode_and_sample(self, value):
        """Return tagged encode output."""
        return ("encode", value)

    @classmethod
    def from_pytorch_config(cls, _vae):
        """Build fake MLX VAE from PyTorch VAE placeholder."""
        return cls()

    def update(self, _params):
        """Accept parameter update requests."""
        return None

    def parameters(self):
        """Return placeholder params tree."""
        return {}
def _build_fake_mx_core(raise_compile: bool) -> tuple[types.ModuleType, dict[str, int]]:
    """Build fake ``mlx.core`` and compile-call tracking for tests.

    Args:
        raise_compile: Whether inner ``_compile`` raises ``CompileError``.
    Returns:
        ``(fake_mx_core, calls)`` where ``calls`` tracks ``_compile`` count.
    Raises:
        CompileError: Raised by ``_compile`` when ``raise_compile`` is True.
    """
    class CompileError(RuntimeError):
        """Raised when fake MLX compile is configured to fail."""

    fake_mx_core = types.ModuleType("mlx.core")
    fake_mx_core.float16 = "float16"
    fake_mx_core.float32 = "float32"
    fake_mx_core.floating = "floating"
    fake_mx_core.array = tuple
    fake_mx_core.issubdtype = lambda *_args, **_kwargs: False
    fake_mx_core.eval = lambda *_args, **_kwargs: None
    calls = {"compile": 0}

    def _compile(fn):
        """Track compile invocations and optionally simulate compile failure."""
        calls["compile"] += 1
        if raise_compile:
            raise CompileError("compile failed")
        return fn

    fake_mx_core.compile = _compile
    return fake_mx_core, calls
class MlxVaeInitMixinTests(unittest.TestCase):
    """Behavior tests for extracted ``MlxVaeInitMixin``."""

    def test_init_mlx_vae_unavailable_returns_false(self):
        """It returns False and leaves MLX VAE flags unset when unavailable."""
        host = _VaeHost()
        fake_mlx = types.ModuleType("acestep.models.mlx")
        fake_mlx.mlx_available = lambda: False
        with patch.dict(sys.modules, {"acestep.models.mlx": fake_mlx}):
            self.assertFalse(host._init_mlx_vae())
        self.assertIsNone(host.mlx_vae)
        self.assertFalse(host.use_mlx_vae)

    def test_init_mlx_vae_success_sets_compiled_callables(self):
        """It initializes MLX VAE and stores compiled decode/encode callables."""
        host = _VaeHost()
        fake_mx_core, calls = _build_fake_mx_core(raise_compile=False)
        fake_mlx = types.ModuleType("acestep.models.mlx")
        fake_mlx.mlx_available = lambda: True
        fake_vae_model = types.ModuleType("acestep.models.mlx.vae_model")
        fake_vae_model.MLXAutoEncoderOobleck = _FakeMlxVae
        fake_vae_convert = types.ModuleType("acestep.models.mlx.vae_convert")
        fake_vae_convert.convert_and_load = Mock()
        fake_mlx_pkg = types.ModuleType("mlx")
        fake_mlx_pkg.__path__ = []
        fake_utils = types.ModuleType("mlx.utils")
        fake_utils.tree_map = lambda _fn, params: params
        with patch.dict(
            sys.modules,
            {
                "mlx": fake_mlx_pkg,
                "mlx.core": fake_mx_core,
                "mlx.utils": fake_utils,
                "acestep.models.mlx": fake_mlx,
                "acestep.models.mlx.vae_model": fake_vae_model,
                "acestep.models.mlx.vae_convert": fake_vae_convert,
            },
        ):
            with patch.dict(os.environ, {"ACESTEP_MLX_VAE_FP16": "0"}, clear=False):
                self.assertTrue(host._init_mlx_vae())
        self.assertEqual(calls["compile"], 2)
        self.assertTrue(host.use_mlx_vae)
        self.assertEqual(host._mlx_vae_dtype, "float32")

    def test_init_mlx_vae_compile_failure_falls_back(self):
        """It keeps uncompiled methods when ``mx.compile`` fails."""
        host = _VaeHost()
        fake_mx_core, _calls = _build_fake_mx_core(raise_compile=True)
        fake_mlx = types.ModuleType("acestep.models.mlx")
        fake_mlx.mlx_available = lambda: True
        fake_vae_model = types.ModuleType("acestep.models.mlx.vae_model")
        fake_vae_model.MLXAutoEncoderOobleck = _FakeMlxVae
        fake_vae_convert = types.ModuleType("acestep.models.mlx.vae_convert")
        fake_vae_convert.convert_and_load = Mock()
        fake_mlx_pkg = types.ModuleType("mlx")
        fake_mlx_pkg.__path__ = []
        fake_utils = types.ModuleType("mlx.utils")
        fake_utils.tree_map = lambda _fn, params: params
        with patch.dict(
            sys.modules,
            {
                "mlx": fake_mlx_pkg,
                "mlx.core": fake_mx_core,
                "mlx.utils": fake_utils,
                "acestep.models.mlx": fake_mlx,
                "acestep.models.mlx.vae_model": fake_vae_model,
                "acestep.models.mlx.vae_convert": fake_vae_convert,
            },
        ):
            self.assertTrue(host._init_mlx_vae())
        self.assertEqual(host._mlx_compiled_decode("x"), host.mlx_vae.decode("x"))
        self.assertEqual(host._mlx_compiled_encode_sample("x"), host.mlx_vae.encode_and_sample("x"))
if __name__ == "__main__":
    unittest.main()
