"""Tests for result quality score helpers."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import torch

from acestep.ui.gradio.events.results.scoring import calculate_score_handler


class CalculateScoreHandlerTests(unittest.TestCase):
    """Verify PMI and DiT alignment score routing."""

    def test_low_vram_skips_pmi_and_uses_alignment(self):
        """Low free VRAM should not OOM the optional PMI path."""
        llm_handler = self._llm_handler("acestep-5Hz-lm-4B", restorable=False)
        dit_handler = MagicMock()
        dit_handler.get_lyric_score.return_value = {
            "success": True,
            "lm_score": 0.2,
            "dit_score": 0.4,
        }

        with (
            patch("torch.cuda.is_available", return_value=True),
            patch("torch.cuda.mem_get_info", return_value=(1 * 1024**3, 80 * 1024**3)),
            patch(
                "acestep.core.scoring.lm_score.calculate_pmi_score_per_condition"
            ) as pmi_mock,
        ):
            result = calculate_score_handler(
                llm_handler=llm_handler,
                audio_codes_str="<|audio_code_1|>",
                caption="caption",
                lyrics="hello",
                lm_metadata={},
                bpm=120,
                key_scale="C",
                time_signature="4/4",
                audio_duration=10,
                vocal_language="en",
                score_scale=1.0,
                dit_handler=dit_handler,
                extra_tensor_data=self._alignment_tensors(),
                inference_steps=8,
            )

        pmi_mock.assert_not_called()
        dit_handler.get_lyric_score.assert_called_once()
        self.assertIn("PMI unavailable", result)
        self.assertIn("PMI Score Skipped", result)

    def test_low_vram_without_alignment_returns_skip_message(self):
        """When no fallback exists, the user should see a low-VRAM PMI message."""
        llm_handler = self._llm_handler("acestep-5Hz-lm-4B", restorable=False)

        with (
            patch("torch.cuda.is_available", return_value=True),
            patch("torch.cuda.mem_get_info", return_value=(1 * 1024**3, 80 * 1024**3)),
            patch(
                "acestep.core.scoring.lm_score.calculate_pmi_score_per_condition"
            ) as pmi_mock,
        ):
            result = calculate_score_handler(
                llm_handler=llm_handler,
                audio_codes_str="<|audio_code_1|>",
                caption="caption",
                lyrics="hello",
                lm_metadata={},
                bpm=120,
                key_scale="C",
                time_signature="4/4",
                audio_duration=10,
                vocal_language="en",
                score_scale=1.0,
                dit_handler=None,
                extra_tensor_data=None,
                inference_steps=8,
            )

        pmi_mock.assert_not_called()
        self.assertIn("PMI Score Skipped", result)

    def test_sufficient_vram_runs_pmi(self):
        """PMI should still run when enough VRAM is available."""
        llm_handler = self._llm_handler("acestep-5Hz-lm-1.7B")

        with (
            patch("torch.cuda.is_available", return_value=True),
            patch("torch.cuda.mem_get_info", return_value=(24 * 1024**3, 80 * 1024**3)),
            patch(
                "acestep.core.scoring.lm_score.calculate_pmi_score_per_condition",
                return_value=({"caption": 0.8}, 0.8, "ok"),
            ) as pmi_mock,
        ):
            result = calculate_score_handler(
                llm_handler=llm_handler,
                audio_codes_str="<|audio_code_1|>",
                caption="caption",
                lyrics="",
                lm_metadata={},
                bpm=None,
                key_scale="",
                time_signature="",
                audio_duration=-1,
                vocal_language="en",
                score_scale=1.0,
                dit_handler=None,
                extra_tensor_data=None,
                inference_steps=8,
            )

        pmi_mock.assert_called_once()
        self.assertIn("Global Quality Score", result)

    def test_restorable_vllm_runs_pmi_even_when_current_free_vram_is_low(self):
        """Restorable vLLM can be unloaded for PMI instead of skipping."""
        llm_handler = self._llm_handler("acestep-5Hz-lm-4B", restorable=True)

        with (
            patch("torch.cuda.is_available", return_value=True),
            patch("torch.cuda.mem_get_info", return_value=(1 * 1024**3, 80 * 1024**3)),
            patch(
                "acestep.core.scoring.lm_score.calculate_pmi_score_per_condition",
                return_value=({"caption": 0.8}, 0.8, "ok"),
            ) as pmi_mock,
        ):
            result = calculate_score_handler(
                llm_handler=llm_handler,
                audio_codes_str="<|audio_code_1|>",
                caption="caption",
                lyrics="",
                lm_metadata={},
                bpm=None,
                key_scale="",
                time_signature="",
                audio_duration=-1,
                vocal_language="en",
                score_scale=1.0,
                dit_handler=None,
                extra_tensor_data=None,
                inference_steps=8,
            )

        pmi_mock.assert_called_once()
        self.assertIn("Global Quality Score", result)

    def test_pmi_failure_does_not_render_negative_infinity_score(self):
        """PMI errors should render the failure reason, not a bogus score."""
        llm_handler = self._llm_handler("acestep-5Hz-lm-1.7B")

        with (
            patch("torch.cuda.is_available", return_value=True),
            patch("torch.cuda.mem_get_info", return_value=(24 * 1024**3, 80 * 1024**3)),
            patch(
                "acestep.core.scoring.lm_score.calculate_pmi_score_per_condition",
                return_value=({}, float("-inf"), "❌ Error: CUDA out of memory"),
            ),
        ):
            result = calculate_score_handler(
                llm_handler=llm_handler,
                audio_codes_str="<|audio_code_1|>",
                caption="caption",
                lyrics="",
                lm_metadata={},
                bpm=None,
                key_scale="",
                time_signature="",
                audio_duration=-1,
                vocal_language="en",
                score_scale=1.0,
                dit_handler=None,
                extra_tensor_data=None,
                inference_steps=8,
            )

        self.assertIn("PMI Score Failed", result)
        self.assertNotIn("-inf", result)

    @staticmethod
    def _llm_handler(model_path, restorable=True):
        handler = SimpleNamespace(
            llm_initialized=True,
            llm_backend="vllm",
            llm=SimpleNamespace(
                model_runner=SimpleNamespace(config=SimpleNamespace(model=model_path))
            ),
        )
        if restorable:
            handler._last_initialize_config = {"backend": "vllm"}
        return handler

    @staticmethod
    def _alignment_tensors():
        return {
            "pred_latent": torch.zeros(1, 3, 4),
            "encoder_hidden_states": torch.zeros(1, 5, 4),
            "encoder_attention_mask": torch.ones(1, 5),
            "context_latents": torch.zeros(1, 3, 4),
            "lyric_token_ids": torch.ones(1, 5, dtype=torch.long),
        }


if __name__ == "__main__":
    unittest.main()
