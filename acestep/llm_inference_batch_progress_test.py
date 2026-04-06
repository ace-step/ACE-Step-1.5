"""Regression tests for sequential batch progress closure."""

import sys
import types
import unittest
from contextlib import nullcontext
from unittest.mock import patch

try:
    from acestep.llm_inference import LLMHandler

    _IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover - dependency guard
    LLMHandler = None
    _IMPORT_ERROR = exc


def _make_handler() -> "LLMHandler":
    """Return a minimal handler with model-loading context stubbed out."""
    handler = LLMHandler()
    handler._load_model_context = lambda: nullcontext()
    return handler


@unittest.skipIf(LLMHandler is None, f"llm_inference import unavailable: {_IMPORT_ERROR}")
class SequentialBatchProgressTests(unittest.TestCase):
    """Sequential batch generation should close each item before the next begins."""

    def test_run_pt_closes_early_item_progress_before_next_item(self):
        handler = _make_handler()
        updates = []

        def fake_run_pt_single(*args, **kwargs):
            progress_callback = kwargs["progress_callback"]
            if len(updates) == 0:
                progress_callback(2, 10, "LLM CFG Generation")
                return "first"
            progress_callback(1, 10, "LLM CFG Generation")
            return "second"

        with patch.object(handler, "_run_pt_single", side_effect=fake_run_pt_single):
            out = handler._run_pt(
                formatted_prompts=["p1", "p2"],
                temperature=0.6,
                cfg_scale=1.0,
                negative_prompt="",
                top_k=None,
                top_p=None,
                repetition_penalty=1.0,
                progress_callback=lambda current, total, desc: updates.append((current, total, desc)),
            )

        self.assertEqual(out, ["first", "second"])
        self.assertEqual(
            updates,
            [
                (2, 20, "LLM CFG Generation"),
                (10, 20, "LLM CFG Generation"),
                (11, 20, "LLM CFG Generation"),
                (20, 20, "LLM CFG Generation"),
            ],
        )

    def test_run_mlx_closes_early_item_progress_before_next_item(self):
        handler = _make_handler()
        updates = []
        fake_mlx = types.ModuleType("mlx")
        fake_mx_core = types.ModuleType("mlx.core")
        fake_mx_core.random = types.SimpleNamespace(seed=lambda *_: None)

        def fake_run_mlx_single(*args, **kwargs):
            progress_callback = kwargs["progress_callback"]
            if len(updates) == 0:
                progress_callback(3, 12, "LLM CFG Generation")
                return "first"
            progress_callback(2, 12, "LLM CFG Generation")
            return "second"

        with patch.dict(sys.modules, {"mlx": fake_mlx, "mlx.core": fake_mx_core}):
            with patch.object(handler, "_run_mlx_single", side_effect=fake_run_mlx_single):
                out = handler._run_mlx(
                    formatted_prompts=["p1", "p2"],
                    temperature=0.6,
                    cfg_scale=1.0,
                    negative_prompt="",
                    top_k=None,
                    top_p=None,
                    repetition_penalty=1.0,
                    progress_callback=lambda current, total, desc: updates.append((current, total, desc)),
                )

        self.assertEqual(out, ["first", "second"])
        self.assertEqual(
            updates,
            [
                (3, 24, "LLM CFG Generation"),
                (12, 24, "LLM CFG Generation"),
                (14, 24, "LLM CFG Generation"),
                (24, 24, "LLM CFG Generation"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
