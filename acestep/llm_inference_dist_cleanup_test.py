"""Unit tests for torch.distributed cleanup in ``LLMHandler``."""

import unittest
from unittest.mock import patch

try:
    from acestep.llm_inference import LLMHandler
    _IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover - dependency guard
    LLMHandler = None
    _IMPORT_ERROR = exc


@unittest.skipIf(LLMHandler is None, f"llm_inference import unavailable: {_IMPORT_ERROR}")
class LlmDistributedCleanupTests(unittest.TestCase):
    """Verify process-group cleanup helper avoids double initialization issues."""

    def test_cleanup_destroys_initialized_process_group(self):
        """Cleanup should call destroy when torch.distributed is initialized."""
        handler = LLMHandler()
        with patch("torch.distributed.is_available", return_value=True), patch(
            "torch.distributed.is_initialized", return_value=True
        ), patch("torch.distributed.destroy_process_group") as destroy_mock:
            handler._cleanup_torch_distributed_state()
        destroy_mock.assert_called_once()

    def test_cleanup_is_noop_when_not_initialized(self):
        """Cleanup should not destroy when process group is not initialized."""
        handler = LLMHandler()
        with patch("torch.distributed.is_available", return_value=True), patch(
            "torch.distributed.is_initialized", return_value=False
        ), patch("torch.distributed.destroy_process_group") as destroy_mock:
            handler._cleanup_torch_distributed_state()
        destroy_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
