"""Tests for legacy NVIDIA torch compatibility launcher guards."""

from __future__ import annotations

from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LauncherLegacyTorchFixTests(unittest.TestCase):
    """Ensure launcher compatibility fixes are narrowly scoped and opt-out capable."""

    def _read(self, rel_path: str) -> str:
        """Read a launcher script from the project root."""
        return (PROJECT_ROOT / rel_path).read_text(encoding="utf-8")

    def test_linux_gradio_launcher_calls_shared_probe(self) -> None:
        """Linux Gradio launcher should call shared Python compatibility probe."""
        content = self._read("start_gradio_ui.sh")
        self.assertIn("ACESTEP_SKIP_LEGACY_TORCH_FIX", content)
        self.assertIn("legacy_torch_fix_probe_exit_code", content)
        self.assertIn("legacy NVIDIA compatibility probe failed with exit code $compat_status", content)
        self.assertIn("return 1", content)
        self.assertIn("torch==2.5.1+cu121", content)

    def test_linux_api_launcher_calls_shared_probe(self) -> None:
        """Linux API launcher should call shared Python compatibility probe."""
        content = self._read("start_api_server.sh")
        self.assertIn("ACESTEP_SKIP_LEGACY_TORCH_FIX", content)
        self.assertIn("legacy_torch_fix_probe_exit_code", content)
        self.assertIn("legacy NVIDIA compatibility probe failed with exit code $compat_status", content)
        self.assertIn("return 1", content)
        self.assertIn("torch==2.5.1+cu121", content)

    def test_windows_gradio_launcher_calls_shared_probe(self) -> None:
        """Windows Gradio launcher should call shared Python compatibility probe."""
        content = self._read("start_gradio_ui.bat")
        self.assertIn('if /i "%ACESTEP_SKIP_LEGACY_TORCH_FIX%"=="true"', content)
        self.assertIn("legacy_torch_fix_probe_exit_code", content)
        self.assertIn("torch==2.5.1+cu121", content)
        self.assertGreaterEqual(content.count("call :EnsureLegacyNvidiaTorchCompat"), 1)
        self.assertGreaterEqual(content.count("if !ERRORLEVEL! NEQ 0 exit /b !ERRORLEVEL!"), 1)
        self.assertRegex(
            content,
            r"call :EnsureLegacyNvidiaTorchCompat\s+if !ERRORLEVEL! NEQ 0 exit /b !ERRORLEVEL!",
        )
        self.assertIn('if "!LEGACY_CHECK_EXIT!"=="0" (', content)
        self.assertIn("exit /b !LEGACY_CHECK_EXIT!", content)

    def test_windows_api_launcher_calls_shared_probe(self) -> None:
        """Windows API launcher should call shared Python compatibility probe."""
        content = self._read("start_api_server.bat")
        self.assertIn('if /i "%ACESTEP_SKIP_LEGACY_TORCH_FIX%"=="true"', content)
        self.assertIn("legacy_torch_fix_probe_exit_code", content)
        self.assertIn("torch==2.5.1+cu121", content)
        self.assertIn("uv run --no-sync !ACESTEP_ARGS!", content)
        self.assertIn("uv run --offline --no-sync !ACESTEP_ARGS!", content)
        self.assertGreaterEqual(content.count("call :EnsureLegacyNvidiaTorchCompat"), 1)
        self.assertGreaterEqual(content.count("if !ERRORLEVEL! NEQ 0 exit /b !ERRORLEVEL!"), 1)
        self.assertRegex(
            content,
            r"call :EnsureLegacyNvidiaTorchCompat\s+if !ERRORLEVEL! NEQ 0 exit /b !ERRORLEVEL!",
        )
        self.assertIn('if "!LEGACY_CHECK_EXIT!"=="0" (', content)
        self.assertIn("exit /b !LEGACY_CHECK_EXIT!", content)


if __name__ == "__main__":
    unittest.main()
