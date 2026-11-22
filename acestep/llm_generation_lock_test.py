"""Tests for serialized LM generation on a shared ``LLMHandler``."""

import threading
import unittest

from acestep.llm_generation_lock import create_lm_generation_lock, serialize_lm_generation

try:
    from acestep.llm_inference import LLMHandler

    _IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover - depends on optional deps
    LLMHandler = None
    _IMPORT_ERROR = exc


class _FakeHandler:
    """Minimal stand-in that mimics a run method using shared state."""

    def __init__(self) -> None:
        """Create the lock and the events used to pause the first call."""
        self._lm_generation_lock = create_lm_generation_lock()
        self.first_entered = threading.Event()
        self.release_first = threading.Event()
        self.second_entered = threading.Event()
        self.calls = 0

    @serialize_lm_generation
    def run(self) -> str:
        """Hold the lock until released on the first call."""
        self.calls += 1
        if self.calls == 1:
            self.first_entered.set()
            self.release_first.wait(timeout=5)
            return "first"
        self.second_entered.set()
        return "second"

    @serialize_lm_generation
    def run_nested(self) -> str:
        """Call another serialized method from inside the lock."""
        return self.inner()

    @serialize_lm_generation
    def inner(self) -> str:
        """Return a marker value."""
        return "inner"


class SerializeLmGenerationTest(unittest.TestCase):
    """The lock keeps one LM call at a time per handler."""

    def test_second_call_waits_for_first_to_finish(self) -> None:
        """A concurrent call cannot start (and reset state) mid-generation."""
        handler = _FakeHandler()
        first = threading.Thread(target=handler.run)
        first.start()
        self.assertTrue(handler.first_entered.wait(timeout=5))

        second = threading.Thread(target=handler.run)
        second.start()
        self.assertFalse(handler.second_entered.wait(timeout=0.2))

        handler.release_first.set()
        first.join(timeout=5)
        second.join(timeout=5)
        self.assertTrue(handler.second_entered.is_set())

    def test_nested_call_on_same_thread_does_not_deadlock(self) -> None:
        """Backend fallbacks on the same thread re-enter the lock."""
        self.assertEqual(_FakeHandler().run_nested(), "inner")

    def test_preserves_return_value_and_name(self) -> None:
        """The wrapper is transparent to callers."""
        handler = _FakeHandler()
        handler.release_first.set()
        self.assertEqual(handler.run(), "first")
        self.assertEqual(_FakeHandler.run.__name__, "run")


@unittest.skipIf(LLMHandler is None, f"llm_inference import unavailable: {_IMPORT_ERROR}")
class LlmHandlerRunMethodsTest(unittest.TestCase):
    """Every backend entry point that uses the shared processor is serialized."""

    def test_run_methods_are_serialized(self) -> None:
        """vllm, pt and mlx entry points carry the lock wrapper."""
        for name in ("_run_vllm", "_run_pt", "_run_mlx"):
            with self.subTest(method=name):
                self.assertTrue(hasattr(getattr(LLMHandler, name), "__wrapped__"))

    def test_handler_owns_its_lock(self) -> None:
        """Each handler gets its own lock, so separate handlers do not block."""
        first, second = LLMHandler(), LLMHandler()
        self.assertIsNot(first._lm_generation_lock, second._lm_generation_lock)


if __name__ == "__main__":
    unittest.main()
