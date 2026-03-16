"""Unit tests for analysis-only runtime helpers."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from acestep.api.job_analysis_runtime import maybe_handle_analysis_only_modes


class JobAnalysisRuntimeTests(unittest.TestCase):
    """Behavior tests for analysis-only and full-analysis runtime branches."""

    def _base_req(self) -> SimpleNamespace:
        return SimpleNamespace(
            full_analysis_only=False,
            analysis_only=False,
            extract_codes_only=False,
            lm_temperature=0.85,
            lm_top_p=0.9,
            use_cot_caption=False,
            use_cot_language=False,
        )

    def test_full_analysis_returns_expected_payload(self) -> None:
        """Full analysis should convert audio and return metadata payload."""

        req = self._base_req()
        req.full_analysis_only = True
        params = SimpleNamespace(src_audio="src.wav", caption="cap", lyrics="lyr")
        config = SimpleNamespace(constrained_decoding_debug=True)
        llm_handler = MagicMock()
        llm_handler.understand_audio_from_codes.return_value = (
            {
                "bpm": 120,
                "keyscale": "C major",
                "timesignature": "4/4",
                "duration": 8.0,
                "caption": "meta cap",
                "lyrics": "meta lyr",
                "language": "en",
                "genres": "pop",
            },
            "ok",
        )
        dit_handler = MagicMock()
        dit_handler.convert_src_audio_to_codes.return_value = "<|audio_code_1|>"
        store = MagicMock()

        result = maybe_handle_analysis_only_modes(
            req=req,
            params=params,
            config=config,
            llm_handler=llm_handler,
            dit_handler=dit_handler,
            store=store,
            job_id="job-1",
        )

        self.assertEqual("Full Hardware Analysis Success", result["status_message"])
        self.assertEqual("pop", result["genre"])
        self.assertEqual("<|audio_code_1|>", result["audio_codes"])
        store.update_progress_text.assert_called_once_with("job-1", "Starting Deep Analysis...")

    def test_analysis_only_uses_lm_and_returns_payload(self) -> None:
        """Analysis-only mode should return LM metadata with fixed response contract."""

        req = self._base_req()
        req.analysis_only = True
        req.use_cot_caption = True
        params = SimpleNamespace(caption="cap", lyrics="lyr")
        config = SimpleNamespace(constrained_decoding_debug=False)
        llm_handler = MagicMock()
        llm_handler.generate_with_stop_condition.return_value = {
            "success": True,
            "metadata": {"bpm": 123, "caption": "better cap", "duration": 9.0},
        }
        dit_handler = MagicMock()
        store = MagicMock()

        with patch.dict(os.environ, {"ACESTEP_LM_MODEL_PATH": "lm-path"}, clear=True):
            result = maybe_handle_analysis_only_modes(
                req=req,
                params=params,
                config=config,
                llm_handler=llm_handler,
                dit_handler=dit_handler,
                store=store,
                job_id="job-2",
            )

        self.assertEqual("Success", result["status_message"])
        self.assertEqual("lm-path", result["lm_model"])
        self.assertEqual("None (Analysis Only)", result["dit_model"])

    def test_extract_codes_only_returns_expected_payload(self) -> None:
        """extract_codes_only should convert audio and return codes without LLM call."""

        req = self._base_req()
        req.extract_codes_only = True
        params = SimpleNamespace(src_audio="src.wav", caption="cap", lyrics="lyr")
        config = SimpleNamespace(constrained_decoding_debug=False)
        dit_handler = MagicMock()
        dit_handler.convert_src_audio_to_codes.return_value = "<|audio_code_1|>"
        llm_handler = MagicMock()
        store = MagicMock()

        result = maybe_handle_analysis_only_modes(
            req=req,
            params=params,
            config=config,
            llm_handler=llm_handler,
            dit_handler=dit_handler,
            store=store,
            job_id="job-ec-1",
        )

        self.assertEqual("Audio Codes Extraction Success", result["status_message"])
        self.assertEqual("<|audio_code_1|>", result["audio_codes"])
        self.assertEqual([], result["audio_paths"])
        self.assertIsNone(result["first_audio_path"])
        store.update_progress_text.assert_called_once_with("job-ec-1", "Extracting Audio Codes...")
        llm_handler.understand_audio_from_codes.assert_not_called()
        llm_handler.generate_with_stop_condition.assert_not_called()

    def test_extract_codes_only_raises_when_no_src_audio(self) -> None:
        """extract_codes_only should raise ValueError when src_audio is not provided."""

        req = self._base_req()
        req.extract_codes_only = True
        params = SimpleNamespace(src_audio=None, caption="cap", lyrics="lyr")
        config = SimpleNamespace(constrained_decoding_debug=False)

        with self.assertRaisesRegex(ValueError, "extract_codes_only requires src_audio_path to be set"):
            maybe_handle_analysis_only_modes(
                req=req,
                params=params,
                config=config,
                llm_handler=MagicMock(),
                dit_handler=MagicMock(),
                store=MagicMock(),
                job_id="job-ec-2",
            )

    def test_extract_codes_only_raises_on_extraction_failure(self) -> None:
        """extract_codes_only should raise RuntimeError when audio extraction fails."""

        req = self._base_req()
        req.extract_codes_only = True
        params = SimpleNamespace(src_audio="bad.wav", caption="cap", lyrics="lyr")
        config = SimpleNamespace(constrained_decoding_debug=False)
        dit_handler = MagicMock()
        dit_handler.convert_src_audio_to_codes.return_value = "❌ encoding error"
        store = MagicMock()

        with self.assertRaises(RuntimeError):
            maybe_handle_analysis_only_modes(
                req=req,
                params=params,
                config=config,
                llm_handler=MagicMock(),
                dit_handler=dit_handler,
                store=store,
                job_id="job-ec-3",
            )

    def test_returns_none_when_no_analysis_flags(self) -> None:
        """Helper should no-op when neither analysis mode is enabled."""

        req = self._base_req()
        params = SimpleNamespace(caption="cap", lyrics="lyr", src_audio="src.wav")
        config = SimpleNamespace(constrained_decoding_debug=False)

        result = maybe_handle_analysis_only_modes(
            req=req,
            params=params,
            config=config,
            llm_handler=MagicMock(),
            dit_handler=MagicMock(),
            store=MagicMock(),
            job_id="job-3",
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
