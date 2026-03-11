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
