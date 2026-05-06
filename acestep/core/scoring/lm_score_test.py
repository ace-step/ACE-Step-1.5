"""Tests for LM scoring memory cleanup helpers."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from acestep.core.scoring.lm_score import (
    _offload_cached_hf_scoring_model,
    _temporary_unload_interactive_lm_for_scoring,
    calculate_pmi_score_per_condition,
)


class LmScoreMemoryCleanupTests(unittest.TestCase):
    """Verify auxiliary HF scoring models do not stay on accelerator memory."""

    def test_offloads_vllm_hf_scoring_model_to_cpu(self):
        """vLLM scoring uses a separate HF model that should be released."""
        model = MagicMock()
        llm_handler = SimpleNamespace(llm_backend="vllm", _hf_model_for_scoring=model)

        with (
            patch("torch.cuda.is_available", return_value=True),
            patch("torch.cuda.empty_cache") as empty_cache_mock,
        ):
            _offload_cached_hf_scoring_model(llm_handler)

        model.to.assert_called_once_with("cpu")
        empty_cache_mock.assert_called_once()

    def test_does_not_offload_pt_backend_model(self):
        """PyTorch backend scoring reuses the active LM model."""
        model = MagicMock()
        llm_handler = SimpleNamespace(llm_backend="pt", _hf_model_for_scoring=model)

        _offload_cached_hf_scoring_model(llm_handler)

        model.to.assert_not_called()

    def test_temporary_scoring_context_unloads_and_restores_vllm(self):
        """PMI scoring should free vLLM VRAM then restore the interactive LM."""
        runtime = MagicMock()
        scorer = MagicMock()
        llm_handler = SimpleNamespace(
            llm_backend="vllm",
            llm=runtime,
            llm_initialized=True,
            _hf_model_for_scoring=scorer,
            _last_initialize_config={
                "checkpoint_dir": "/ckpt",
                "lm_model_path": "lm",
                "backend": "vllm",
            },
            _cleanup_torch_distributed_state=MagicMock(),
            initialize=MagicMock(return_value=("ok", True)),
        )

        with (
            patch("torch.cuda.is_available", return_value=True),
            patch("torch.cuda.empty_cache") as empty_cache_mock,
            patch("torch.cuda.synchronize"),
        ):
            with _temporary_unload_interactive_lm_for_scoring(llm_handler):
                self.assertIsNone(llm_handler.llm)
                self.assertFalse(llm_handler.llm_initialized)

        runtime.reset.assert_called_once()
        scorer.to.assert_called_once_with("cpu")
        self.assertIsNone(llm_handler._hf_model_for_scoring)
        llm_handler.initialize.assert_called_once_with(
            checkpoint_dir="/ckpt",
            lm_model_path="lm",
            backend="vllm",
        )
        self.assertTrue(empty_cache_mock.called)

    def test_temporary_scoring_context_raises_when_vllm_restore_fails(self):
        """PMI scoring should surface failures to restore the interactive LM."""
        runtime = MagicMock()
        llm_handler = SimpleNamespace(
            llm_backend="vllm",
            llm=runtime,
            llm_initialized=True,
            _hf_model_for_scoring=None,
            _last_initialize_config={"checkpoint_dir": "/ckpt", "backend": "vllm"},
            _cleanup_torch_distributed_state=MagicMock(),
            initialize=MagicMock(return_value=("restore failed", False)),
        )

        with (
            patch("torch.cuda.is_available", return_value=False),
            self.assertRaisesRegex(RuntimeError, "restore failed"),
        ):
            with _temporary_unload_interactive_lm_for_scoring(llm_handler):
                pass

    def test_pmi_score_accepts_missing_metadata(self):
        """Caption-only PMI scoring should work when metadata is omitted."""
        llm_handler = SimpleNamespace(
            llm_backend="pt",
            llm_initialized=True,
            build_formatted_prompt_for_understanding=MagicMock(
                side_effect=lambda audio_codes, is_negative_prompt=False: f"prompt:{audio_codes}"
            ),
        )

        with patch(
            "acestep.core.scoring.lm_score._calculate_log_prob",
            side_effect=[-1.0, -2.0],
        ):
            scores, global_score, status = calculate_pmi_score_per_condition(
                llm_handler,
                audio_codes="<|audio_code_0|>",
                caption="bright pop track",
                metadata=None,
            )

        self.assertIn("caption", scores)
        self.assertGreater(global_score, 0.0)
        self.assertIn("caption", status)


if __name__ == "__main__":
    unittest.main()
