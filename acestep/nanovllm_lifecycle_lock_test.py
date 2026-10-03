"""Threaded regressions for nano-vLLM generation and runtime shutdown."""

import ast
import atexit
import threading
import unittest
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import MagicMock, patch


def _engine_method(name):
    """Load engine methods without importing optional CUDA kernels."""
    path = Path(__file__).parent / "third_parts/nano-vllm/nanovllm/engine/llm_engine.py"
    tree = ast.parse(path.read_text())
    engine = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    method = next(node for node in engine.body if isinstance(node, ast.FunctionDef)
                  and node.name == name)
    namespace = {"atexit": atexit, "SamplingParams": object}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


class EngineLifecycleLockTests(unittest.TestCase):
    """Runtime destruction waits for the complete active generation."""

    def test_reset_and_exit_wait_for_generation(self):
        """No scheduler mutation or worker destruction while generation holds its lock."""
        for operation in ("reset", "exit"):
            with self.subTest(operation=operation):
                entered = threading.Event()
                release = threading.Event()
                attempted = threading.Event()
                engine = SimpleNamespace(
                    _generate_lock=threading.RLock(), model_runner=MagicMock(), ps=[],
                    scheduler=SimpleNamespace(running=deque(), waiting=deque(),
                                              block_manager=MagicMock()),
                )
                engine.generate = MethodType(_engine_method("generate"), engine)
                engine.reset = MethodType(_engine_method("reset"), engine)
                engine.exit = MethodType(_engine_method("exit"), engine)

                def active_generation(*args):
                    """Hold the real generation lock until the test releases it."""
                    entered.set()
                    if not release.wait(5):
                        raise TimeoutError("Generation was not released")
                    return []

                def shutdown():
                    """Signal the attempted lifecycle operation."""
                    attempted.set()
                    getattr(engine, operation)()

                engine._generate_impl = active_generation
                with ThreadPoolExecutor(max_workers=2) as executor, patch("atexit.unregister"):
                    request = executor.submit(engine.generate, [], [], False)
                    try:
                        self.assertTrue(entered.wait(5))
                        closing = executor.submit(shutdown)
                        self.assertTrue(attempted.wait(5))
                        with self.assertRaises(TimeoutError):
                            closing.result(timeout=0.1)
                        engine.model_runner.call.assert_not_called()
                        engine.scheduler.block_manager.reset.assert_not_called()
                    finally:
                        release.set()
                    request.result(timeout=5)
                    closing.result(timeout=5)
                if operation == "exit":
                    self.assertFalse(hasattr(engine, "model_runner"))
                else:
                    engine.scheduler.block_manager.reset.assert_called_once()

    def test_generation_can_reset_under_the_constructor_lock(self):
        """The real constructor creates a reentrant lock for nested recovery."""
        path = Path(__file__).parent / "third_parts/nano-vllm/nanovllm/engine/llm_engine.py"
        tree = ast.parse(path.read_text())
        lock_assignment = next(
            node for node in ast.walk(tree) if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Attribute) and target.attr == "_generate_lock"
                    for target in node.targets)
        )
        lock = eval(compile(ast.Expression(lock_assignment.value), str(path), "eval"),
                    {"threading": threading})
        with lock:
            self.assertTrue(lock.acquire(blocking=False))
            lock.release()
            engine = SimpleNamespace(_generate_lock=lock, model_runner=MagicMock(),
                                     scheduler=SimpleNamespace(running=deque(), waiting=deque(),
                                                               block_manager=MagicMock()))
            engine.reset = MethodType(_engine_method("reset"), engine)
            engine.generate = MethodType(_engine_method("generate"), engine)
            engine._generate_impl = lambda *_args: engine.reset()
            engine.generate([], [], False)
        engine.scheduler.block_manager.reset.assert_called_once()

    def test_generate_after_exit_fails_explicitly(self):
        """A queued request must not enter inference on a destroyed worker."""
        engine = SimpleNamespace(_generate_lock=threading.RLock(), _generate_impl=MagicMock())
        engine.generate = MethodType(_engine_method("generate"), engine)
        with self.assertRaisesRegex(RuntimeError, "closed"):
            engine.generate([], [], False)
        engine._generate_impl.assert_not_called()


if __name__ == "__main__":
    unittest.main()
