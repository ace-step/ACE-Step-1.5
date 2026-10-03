"""Regression coverage for shutdown failures and invalid LM replacements."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from acestep.core.scoring.lm_score import _temporary_unload_interactive_lm_for_scoring
from acestep.llm_inference import LLMHandler


class LifecycleFailureTests(unittest.TestCase):
    """A destroyed runtime cannot remain ready, even when shutdown raises."""

    def test_unload_clears_state_after_exit_failure(self):
        """Shutdown failures are logged and all readiness references are cleared."""
        handler = LLMHandler()
        handler.llm = MagicMock()
        handler.llm.exit.side_effect = RuntimeError("shutdown failed")
        handler.llm_backend = "vllm"
        handler.llm_initialized = True
        handler.llm_tokenizer = MagicMock()
        handler.constrained_processor = MagicMock()
        with patch("torch.cuda.is_available", return_value=False), patch.object(
            handler, "_cleanup_torch_distributed_state",
        ) as cleanup, patch("acestep.llm_inference.logger") as logger:
            handler.unload()
        self.assertIsNone(handler.llm)
        self.assertFalse(handler.llm_initialized)
        self.assertIsNone(handler.llm_backend)
        self.assertIsNone(handler.llm_tokenizer)
        self.assertIsNone(handler.constrained_processor)
        cleanup.assert_called_once()
        logger.exception.assert_called_once()

    def test_pmi_exit_failure_clears_state_and_attempts_restore(self):
        """Failed shutdown skips scoring but still restores the interactive LM."""
        runtime = MagicMock()
        runtime.exit.side_effect = RuntimeError("shutdown failed")
        config = {"checkpoint_dir": "checkpoints", "backend": "vllm"}
        handler = SimpleNamespace(
            llm=runtime, llm_backend="vllm", llm_initialized=True,
            _last_initialize_config=config, _hf_model_for_scoring=None,
            _cleanup_torch_distributed_state=MagicMock(),
            initialize=MagicMock(return_value=("restored", True)),
        )
        with patch("torch.cuda.is_available", return_value=False), self.assertRaisesRegex(
            RuntimeError, "shutdown failed",
        ):
            with _temporary_unload_interactive_lm_for_scoring(handler):
                self.fail("Scoring must not run after shutdown failure")
        self.assertIsNone(handler.llm)
        self.assertFalse(handler.llm_initialized)
        handler._cleanup_torch_distributed_state.assert_called_once()
        handler.initialize.assert_called_once_with(**config)

    def test_missing_replacement_preserves_working_runtime(self):
        """A missing checkpoint must fail before unloading the existing model."""
        handler = LLMHandler()
        runtime = MagicMock()
        handler.llm = runtime
        handler.llm_backend = "vllm"
        handler.llm_initialized = True
        old_config = {"checkpoint_dir": "checkpoints", "backend": "vllm"}
        handler._last_initialize_config = old_config
        with patch("os.path.exists", return_value=False), patch(
            "torch.cuda.is_available", return_value=False,
        ), patch("acestep.llm_inference.AutoTokenizer.from_pretrained") as tokenizer:
            status, ok = handler.initialize("checkpoints", "missing", device="cpu")
        self.assertFalse(ok)
        self.assertIn("not found", status)
        self.assertIs(handler.llm, runtime)
        self.assertTrue(handler.llm_initialized)
        self.assertIs(handler._last_initialize_config, old_config)
        runtime.exit.assert_not_called()
        tokenizer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
