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
        engine = handler.llm
        with ExitStack() as stack:
            for p in self._base_patches():
                stack.enter_context(p)
            handler.unload()
        engine.exit.assert_called_once()
        self.assertFalse(handler.llm_initialized)
        self.assertIsNone(handler.llm)
        self.assertIsNone(handler.llm_backend)

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
        """A failing engine teardown must not break unload()/subsequent cleanup."""
        handler = _make_vllm_handler()
        engine = handler.llm
        engine.exit.side_effect = RuntimeError("engine already released")
        with ExitStack() as stack:
            for p in self._base_patches():
                stack.enter_context(p)
            unregister_mock = stack.enter_context(patch("atexit.unregister"))
            handler.unload()  # must not raise
        unregister_mock.assert_called_once_with(engine.exit)


if __name__ == "__main__":
    unittest.main()
