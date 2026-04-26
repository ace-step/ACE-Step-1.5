"""Unit tests for enforce_eager logic when flash_attn is unavailable.

Regression test for the bug where CUDA graph capture would fail when
``flash_attn`` is not installed because the SDPA paged-cache decode path
calls ``.item()`` inside the capture region (a forbidden CPU-GPU sync).

When flash_attn is absent, nano-vllm must run in ``enforce_eager=True``
(eager mode, no CUDA graph capture) to avoid corrupting the CUDA context.
"""

import unittest
from unittest.mock import MagicMock, patch

try:
    from acestep.llm_inference import LLMHandler
    _IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover - dependency guard
    LLMHandler = None
    _IMPORT_ERROR = exc


def _make_handler() -> "LLMHandler":
    """Return a bare LLMHandler with no models loaded."""
    return LLMHandler()


def _mock_gpu_config():
    """Return a minimal GPU config mock."""
    cfg = MagicMock()
    cfg.tier = "high"
    cfg.max_duration_with_lm = 60.0
    return cfg


@unittest.skipIf(LLMHandler is None, f"llm_inference import unavailable: {_IMPORT_ERROR}")
class TestEnforceEagerWhenFlashAttnMissing(unittest.TestCase):
    """Verify that enforce_eager=True is set when flash_attn is not installed."""

    def _run_initialize_with_mocks(self, flash_attn_available: bool, device_name: str = "NVIDIA GeForce RTX 4090"):
        """Call handler.initialize() with all heavy operations mocked.

        Args:
            flash_attn_available: Whether flash_attn should appear detectable
                via ``importlib.util.find_spec``.
            device_name: Simulated CUDA device name.

        Returns:
            The ``enforce_eager`` value that was passed to ``_initialize_5hz_lm_vllm``.
        """
        handler = _make_handler()

        # find_spec returns None when the module is not found, non-None when found.
        find_spec_return = MagicMock() if flash_attn_available else None

        captured = {}

        def fake_init_vllm(model_path: str, enforce_eager: bool = False) -> str:
            captured["enforce_eager"] = enforce_eager
            return "✅ ok"

        with patch("importlib.util.find_spec", return_value=find_spec_return), \
             patch("os.path.exists", return_value=True), \
             patch("acestep.llm_inference.AutoTokenizer") as mock_tok, \
             patch("acestep.llm_inference.get_global_gpu_config", return_value=_mock_gpu_config()), \
             patch("acestep.llm_inference.MetadataConstrainedLogitsProcessor"), \
             patch("torch.cuda.is_available", return_value=True), \
             patch("torch.cuda.empty_cache"), \
             patch("torch.cuda.synchronize"), \
             patch("torch.cuda.get_device_name", return_value=device_name), \
             patch.object(handler, "_initialize_5hz_lm_vllm", side_effect=fake_init_vllm):

            mock_tok.from_pretrained.return_value = MagicMock()
            handler.initialize(
                checkpoint_dir="/tmp/fake_ckpt",
                lm_model_path="model",
                backend="vllm",
                device="cuda",
            )

        return captured.get("enforce_eager")

    def test_enforce_eager_true_when_flash_attn_missing(self):
        """enforce_eager must be True when flash_attn cannot be found."""
        enforce_eager = self._run_initialize_with_mocks(flash_attn_available=False)
        self.assertTrue(
            enforce_eager,
            "enforce_eager must be True when flash_attn is not installed to prevent "
            "CUDA graph capture from corrupting the CUDA context via SDPA .item() calls",
        )

    def test_enforce_eager_false_when_flash_attn_present(self):
        """enforce_eager must be False when flash_attn is detectable (standard GPU, non-ROCm)."""
        enforce_eager = self._run_initialize_with_mocks(flash_attn_available=True)
        self.assertFalse(
            enforce_eager,
            "enforce_eager should be False on standard CUDA hardware with flash_attn present",
        )

    def test_enforce_eager_still_true_for_jetson_even_with_flash_attn(self):
        """Jetson GPUs must still use enforce_eager=True even if flash_attn is detectable."""
        # Jetson is identified by keywords in the device name
        enforce_eager = self._run_initialize_with_mocks(
            flash_attn_available=True,
            device_name="Jetson Orin NX 16GB",
        )
        self.assertTrue(
            enforce_eager,
            "enforce_eager must be True on Jetson regardless of flash_attn availability",
        )


if __name__ == "__main__":
    unittest.main()
