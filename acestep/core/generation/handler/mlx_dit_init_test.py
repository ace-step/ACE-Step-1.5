"""Unit tests for extracted MLX DiT initialization mixin."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


def _load_handler_module(filename: str, module_name: str):
    """Load handler mixin module directly from file path."""
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
    module_path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MLX_DIT_INIT_MODULE = _load_handler_module(
    "mlx_dit_init.py",
    "acestep.core.generation.handler.mlx_dit_init",
)
MlxDitInitMixin = MLX_DIT_INIT_MODULE.MlxDitInitMixin


class _DitHost(MlxDitInitMixin):
    """Minimal host exposing DiT init state used by tests."""

    def __init__(self):
        """Initialize deterministic model/config placeholders."""
        self.config = {"size": "tiny"}
        self.model = object()
        self.mlx_decoder = None
        self.use_mlx_dit = False
        self.mlx_dit_compiled = False


class MlxDitInitMixinTests(unittest.TestCase):
    """Behavior tests for extracted ``MlxDitInitMixin``."""

    def test_init_mlx_dit_unavailable_returns_false(self):
        """It returns False and leaves MLX DiT flags unset when unavailable."""
        host = _DitHost()
        fake_mlx = types.ModuleType("acestep.models.mlx")
        fake_mlx.mlx_available = lambda: False
        with patch.dict(sys.modules, {"acestep.models.mlx": fake_mlx}):
            self.assertFalse(host._init_mlx_dit(compile_model=True))
        self.assertIsNone(host.mlx_decoder)
        self.assertFalse(host.use_mlx_dit)

    def test_init_mlx_dit_success_sets_decoder(self):
        """It loads converted MLX DiT decoder and stores compile flag."""
        host = _DitHost()
        fake_mlx = types.ModuleType("acestep.models.mlx")
        fake_mlx.mlx_available = lambda: True
        fake_dit_model = types.ModuleType("acestep.models.mlx.dit_model")
        fake_dit_model.MLXDiTDecoder = type(
            "FakeDecoder",
            (),
            {"from_config": classmethod(lambda _cls, _cfg: object())},
        )
        fake_dit_convert = types.ModuleType("acestep.models.mlx.dit_convert")
        fake_dit_convert.convert_and_load = Mock()
        with patch.dict(
            sys.modules,
            {
                "acestep.models.mlx": fake_mlx,
                "acestep.models.mlx.dit_model": fake_dit_model,
                "acestep.models.mlx.dit_convert": fake_dit_convert,
            },
        ):
            self.assertTrue(host._init_mlx_dit(compile_model=True))
        self.assertTrue(host.use_mlx_dit)
        self.assertTrue(host.mlx_dit_compiled)
        fake_dit_convert.convert_and_load.assert_called_once()


if __name__ == "__main__":
    unittest.main()
