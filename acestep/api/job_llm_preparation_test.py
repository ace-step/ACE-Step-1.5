"""Unit tests for LLM readiness and request-input preparation helpers."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from acestep.api.job_llm_preparation import (
    ensure_llm_ready_for_request,
    prepare_llm_generation_inputs,
)


class JobLlmPreparationTests(unittest.TestCase):
    """Behavior tests for LLM initialization guard and input preparation."""

    def _base_req(self) -> SimpleNamespace:
        return SimpleNamespace(
            lm_model_path="",
            lm_backend="",
            lm_temperature=0.85,
            lm_top_k=0,
            lm_top_p=0.9,
            thinking=False,
            sample_mode=False,
            sample_query="",
            use_format=False,
            use_cot_caption=False,
            use_cot_language=False,
            full_analysis_only=False,
            prompt="p",
            lyrics="l",
            bpm=None,
            key_scale="",
            time_signature="",
            audio_duration=None,
            task_type="text2music",
            vocal_language="en",
        )

    def test_ensure_llm_ready_for_request_respects_disabled_env(self) -> None:
        """LLM guard should set lazy-load-disabled error when ACESTEP_INIT_LLM=false."""

        req = self._base_req()
        app_state = SimpleNamespace(
            _llm_init_lock=__import__("threading").Lock(),
            _llm_initialized=False,
            _llm_init_error=None,
            _llm_lazy_load_disabled=False,
        )
        llm = MagicMock()

        with patch.dict(os.environ, {"ACESTEP_INIT_LLM": "false"}, clear=True):
            ensure_llm_ready_for_request(
                app_state=app_state,
                llm_handler=llm,
                req=req,
                get_project_root=MagicMock(return_value="k:/repo"),
                get_model_name=MagicMock(return_value="lm"),
                ensure_model_downloaded=MagicMock(),
                env_bool=lambda _name, default: default,
                log_fn=MagicMock(),
            )

        self.assertTrue(app_state._llm_lazy_load_disabled)
        self.assertIsNotNone(app_state._llm_init_error)
        llm.initialize.assert_not_called()

    def test_prepare_llm_generation_inputs_updates_values_from_sample_mode(self) -> None:
        """Sample mode preparation should replace prompt/lyrics/meta fields from sample output."""

        req = self._base_req()
        req.sample_mode = True
        req.sample_query = "energetic song"
        sample_result = SimpleNamespace(
            success=True,
            caption="generated caption",
            lyrics="generated lyrics",
            bpm=128,
            keyscale="C major",
            timesignature="4/4",
            duration=12.0,
        )
        app_state = SimpleNamespace(
            _llm_initialized=True,
            _llm_init_error=None,
            _llm_lazy_load_disabled=False,
        )
        llm = MagicMock()

        prepared = prepare_llm_generation_inputs(
            app_state=app_state,
            llm_handler=llm,
            req=req,
            selected_handler_device="cuda",
            parse_description_hints=MagicMock(return_value=("en", False)),
            create_sample_fn=MagicMock(return_value=sample_result),
            format_sample_fn=MagicMock(),
            ensure_llm_ready_fn=MagicMock(),
            log_fn=MagicMock(),
        )

        self.assertEqual("generated caption", prepared.caption)
        self.assertEqual("generated lyrics", prepared.lyrics)
        self.assertEqual(128, prepared.bpm)
        self.assertEqual("C major", prepared.key_scale)
        self.assertEqual("4/4", prepared.time_signature)
        self.assertEqual(12.0, prepared.audio_duration)

    def test_prepare_llm_generation_inputs_disables_optional_cot_when_llm_unavailable(self) -> None:
        """Optional CoT flags should auto-disable when LLM is unavailable but not required."""

        req = self._base_req()
        req.use_cot_caption = True
        req.use_cot_language = True
        app_state = SimpleNamespace(
            _llm_initialized=False,
            _llm_init_error="failed",
            _llm_lazy_load_disabled=False,
        )
        llm = MagicMock()

        prepared = prepare_llm_generation_inputs(
            app_state=app_state,
            llm_handler=llm,
            req=req,
            selected_handler_device="cuda",
            parse_description_hints=MagicMock(),
            create_sample_fn=MagicMock(),
            format_sample_fn=MagicMock(),
            ensure_llm_ready_fn=MagicMock(),
            log_fn=MagicMock(),
        )

        self.assertFalse(prepared.use_cot_caption)
        self.assertFalse(prepared.use_cot_language)


if __name__ == "__main__":
    unittest.main()
