"""Regression tests for releasing nano-vLLM allocations before model reloads."""

import ast
import atexit
import gc
import threading
import unittest
import weakref
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import MagicMock, patch

from acestep.core.scoring.lm_score import _temporary_unload_interactive_lm_for_scoring
from acestep.llm_inference import LLMHandler


def _engine_exit():
    """Load the real engine shutdown method without importing optional CUDA kernels."""
    path = Path(__file__).parent / "third_parts/nano-vllm/nanovllm/engine/llm_engine.py"
    tree = ast.parse(path.read_text())
    engine = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    method = next(node for node in engine.body if isinstance(node, ast.FunctionDef)
                  and node.name == "exit")
    namespace = {"atexit": atexit}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["exit"]


class _EngineHost:
    """Hold the real shutdown method without importing CUDA-only model kernels."""


class RuntimeReleaseTests(unittest.TestCase):
    """Free model workers and shutdown hooks even when engine references survive."""

    def test_exit_drops_worker_and_unregisters_shutdown(self):
        """Repeated close cannot retain GPU weights/cache or run worker shutdown twice."""
        runner = MagicMock()
        process = MagicMock()
        engine = SimpleNamespace(model_runner=runner, ps=[process],
                                 _generate_lock=threading.RLock())
        engine.exit = MethodType(_engine_exit(), engine)
        with patch("atexit.unregister") as unregister:
            engine.exit()
            engine.exit()
        self.assertFalse(hasattr(engine, "model_runner"))
        runner.call.assert_called_once_with("exit")
        unregister.assert_called_once_with(engine.exit)
        process.join.assert_called_once()

    def test_real_shutdown_hook_releases_engine_and_worker(self):
        """Explicit shutdown removes the real atexit reference that kept runtimes alive."""
        engine = _EngineHost()
        engine.model_runner = MagicMock()
        engine.ps = []
        engine._generate_lock = threading.RLock()
        engine.exit = MethodType(_engine_exit(), engine)
        engine_ref = weakref.ref(engine)
        runner_ref = weakref.ref(engine.model_runner)
        atexit.register(engine.exit)
        del engine
        gc.collect()
        try:
            self.assertIsNotNone(engine_ref())
            self.assertIsNotNone(runner_ref())
            engine_ref().exit()
            gc.collect()
            self.assertIsNone(engine_ref())
            self.assertIsNone(runner_ref())
        finally:
            if engine_ref() is not None:
                atexit.unregister(engine_ref().exit)

    def test_exit_drops_worker_when_shutdown_raises(self):
        """An exit failure cannot leave the worker attached to an atexit-held engine."""
        runner = MagicMock()
        runner.call.side_effect = RuntimeError("worker shutdown failed")
        engine = SimpleNamespace(model_runner=runner, ps=[], _generate_lock=threading.RLock())
        engine.exit = MethodType(_engine_exit(), engine)
        with patch("atexit.unregister"), self.assertRaisesRegex(RuntimeError, "shutdown failed"):
            engine.exit()
        self.assertFalse(hasattr(engine, "model_runner"))

    def test_unload_closes_vllm_without_closing_pytorch(self):
        """LLM unload releases vLLM's worker; normal PyTorch objects keep their interface."""
        for backend in ("vllm", "pt"):
            with self.subTest(backend=backend):
                handler = LLMHandler()
                runtime = MagicMock()
                handler.llm = runtime
                handler.llm_backend = backend
                with patch("torch.cuda.is_available", return_value=False), patch.object(
                    handler, "_cleanup_torch_distributed_state",
                ):
                    handler.unload()
                if backend == "vllm":
                    runtime.exit.assert_called_once()
                else:
                    runtime.exit.assert_not_called()
                self.assertIsNone(handler.llm)

    def test_pmi_releases_worker_before_loading_scorer(self):
        """Resetting scheduler requests is insufficient; exit precedes scorer allocation."""
        runtime = MagicMock()
        restore = {"checkpoint_dir": "unused-checkpoints", "backend": "vllm", "device": "cuda"}
        handler = SimpleNamespace(llm_backend="vllm", llm=runtime, llm_initialized=True,
                                  _last_initialize_config=restore, _hf_model_for_scoring=None,
                                  _cleanup_torch_distributed_state=MagicMock(),
                                  initialize=MagicMock(return_value=("ok", True)), device="cuda")
        with patch("torch.cuda.is_available", return_value=True), patch(
            "torch.cuda.empty_cache",
        ), patch("torch.cuda.synchronize"):
            with _temporary_unload_interactive_lm_for_scoring(handler):
                runtime.exit.assert_called_once()
                self.assertIsNone(handler.llm)
                handler.initialize.assert_not_called()
        handler.initialize.assert_called_once_with(**restore)

    def test_reinitialize_releases_old_engine_before_tokenizer_load(self):
        """The normal UI initialization path closes a previous runtime before allocating."""
        handler = LLMHandler()
        old_runtime = MagicMock()
        handler.llm = old_runtime
        handler.llm_backend = "vllm"

        def stop_before_loading(*_args, **_kwargs):
            """Assert release order and stop before real model loading."""
            old_runtime.exit.assert_called_once()
            raise RuntimeError("stop before model load")

        with patch("os.path.exists", return_value=True), patch(
            "torch.cuda.is_available", return_value=False,
        ), patch("acestep.llm_inference.AutoTokenizer.from_pretrained", side_effect=stop_before_loading):
            status, ok = handler.initialize("unused-checkpoints", "lm", backend="pt", device="cpu")
        self.assertFalse(ok)
        self.assertIn("stop before model load", status)
        old_runtime.exit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
