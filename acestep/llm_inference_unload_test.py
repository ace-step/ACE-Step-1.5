"""Unit tests for ``LLMHandler.unload`` vLLM teardown.

Regression test for the reinit memory-leak fix: on a vLLM-backed handler,
``unload()`` must fully tear down the engine via ``llm.exit()`` (not a partial
``reset()``) and deregister the ``exit`` callback that ``LLMEngine.__init__``
registers with ``atexit``, so a reinit does not leak the old engine's weights,
KV cache, and CUDA graphs and does not re-run ``exit()`` on an already-released
runner at process shutdown.
"""

import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

try:
    from acestep.llm_inference import LLMHandler
    _IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover - dependency guard
    LLMHandler = None
    _IMPORT_ERROR = exc


def _make_vllm_handler() -> LLMHandler:
    """Handler already holding a vLLM engine, with CUDA/distributed/gc mocked."""
    handler = LLMHandler()
    handler.llm_backend = "vllm"
    handler.llm = MagicMock()
    handler.llm.exit = MagicMock()  # emulate LLMEngine.exit
    return handler


@unittest.skipIf(LLMHandler is None, f"llm_inference import unavailable: {_IMPORT_ERROR}")
class LlmUnloadVllmTests(unittest.TestCase):
    """Verify ``unload`` tears down a vLLM engine and deregisters its callback."""

    def _base_patches(self):
        """Common stubs so unload() reaches the vLLM branch without real CUDA/DDP."""
        return (
            patch("torch.cuda.is_available", return_value=False),
            patch("torch.distributed.is_available", return_value=False),
            patch("torch.distributed.is_initialized", return_value=False),
        )

    def test_calls_exit_on_vllm_engine(self) -> None:
        """The engine is fully ``exit()``-ed, not merely ``reset()``."""
        handler = _make_vllm_handler()
        handler._hf_model_for_scoring = "stale-scoring-model"
        engine = handler.llm
        with ExitStack() as stack:
            for p in self._base_patches():
                stack.enter_context(p)
            handler.unload()
        engine.exit.assert_called_once()
        self.assertFalse(handler.llm_initialized)
        self.assertIsNone(handler.llm)
        self.assertIsNone(handler.llm_backend)
        # New: unload must drop the cached scoring model so get_hf_model_for_scoring()
        # reloads the current LM on the next call instead of returning stale weights.
        self.assertIsNone(handler._hf_model_for_scoring)

    def test_deregisters_exit_from_atexit(self) -> None:
        """The engine's atexit entry is removed so it cannot re-run after teardown."""
        handler = _make_vllm_handler()
        engine = handler.llm
        with ExitStack() as stack:
            for p in self._base_patches():
                stack.enter_context(p)
            unregister_mock = stack.enter_context(patch("atexit.unregister"))
            handler.unload()
        unregister_mock.assert_called_once_with(engine.exit)

    def test_exit_callback_not_deregistered_when_missing(self) -> None:
        """An engine without ``exit`` is left for gc; unregister is skipped."""
        handler = LLMHandler()
        handler.llm_backend = "vllm"
        handler.llm = MagicMock()
        del handler.llm.exit  # this backend exposes no exit()
        with ExitStack() as stack:
            for p in self._base_patches():
                stack.enter_context(p)
            unregister_mock = stack.enter_context(patch("atexit.unregister"))
            handler.unload()
        unregister_mock.assert_not_called()

    def test_noop_for_non_vllm_backend(self) -> None:
        """``pt``/``mlx`` backends are not touched as vLLM; no exit() is called."""
        handler = LLMHandler()
        handler.llm_backend = "pt"
        handler.llm = MagicMock()
        handler.llm.exit = MagicMock()
        engine = handler.llm
        with ExitStack() as stack:
            for p in self._base_patches():
                stack.enter_context(p)
            handler.unload()
        engine.exit.assert_not_called()

    def test_exit_exception_is_swallowed(self) -> None:
        """A failing teardown must not break unload(), and must keep the atexit
        callback registered so process shutdown can retry the incomplete cleanup."""
        handler = _make_vllm_handler()
        engine = handler.llm
        engine.exit.side_effect = RuntimeError("engine already released")
        with ExitStack() as stack:
            for p in self._base_patches():
                stack.enter_context(p)
            unregister_mock = stack.enter_context(patch("atexit.unregister"))
            handler.unload()  # must not raise
        engine.exit.assert_called_once()
        unregister_mock.assert_not_called()


@unittest.skipIf(LLMHandler is None, f"llm_inference import unavailable: {_IMPORT_ERROR}")
class LlmInitializeAfterFailedTeardownTests(unittest.TestCase):
    """Verify initialize() aborts when unload() reports an incomplete teardown.

    ChuxiJ review: if a previous vLLM engine's exit() raised, clearing the handler
    state and silently building a replacement engine can stack a new runtime on an
    un-released one (leaked weights/KV cache/CUDA graphs/workers). initialize()
    must stop when unload() reports failure.
    """

    def test_initialize_aborts_when_unload_fails(self) -> None:
        """A failed teardown must prevent building a replacement engine."""
        handler = LLMHandler()
        # unload() returning False is the guard this test locks down.
        handler.unload = MagicMock(return_value=False)
        status, success = handler.initialize(
            checkpoint_dir="/tmp", lm_model_path="acestep-5Hz-lm-1.7B",
            backend="vllm", device="cpu",
        )
        handler.unload.assert_called_once()
        self.assertFalse(success)
        self.assertIn("Failed to release", status)
        # No new engine should be constructed after a failed teardown.
        self.assertIsNone(handler.llm)
        self.assertFalse(handler.llm_initialized)

    def test_initialize_proceeds_when_unload_succeeds(self) -> None:
        """A clean teardown lets initialize() continue past the guard."""
        handler = LLMHandler()
        handler.unload = MagicMock(return_value=True)
        # Guard returns early only on failure; on success the code proceeds. Mock
        # the model load path so numpy/tokenizer construction throws a controlled
        # error, proving we got past the unload() guard (the guard itself is not
        # what failed here).
        with patch("acestep.llm_inference.LLMHandler.unload", return_value=True):
            status, success = handler.initialize(
                checkpoint_dir="/tmp", lm_model_path="acestep-5Hz-lm-1.7B",
                backend="vllm", device="cpu",
            )
        # We cannot assert success(True) here (engine build would need real torch/
        # model), but the guard passed: the failure, if any, is downstream of the
        # teardown guard, not "Failed to release".
        self.assertNotIn("Failed to release", status)


if __name__ == "__main__":
    unittest.main()
