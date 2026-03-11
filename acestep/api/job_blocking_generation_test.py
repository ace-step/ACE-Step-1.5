"""Unit tests for blocking generation orchestration helper."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from acestep.api.job_blocking_generation import run_blocking_generate


class JobBlockingGenerationTests(unittest.TestCase):
    """Behavior tests for blocking generation orchestration decomposition."""

    def _base_req(self) -> SimpleNamespace:
        return SimpleNamespace(inference_steps=25)

    def test_run_blocking_generate_success_path_updates_progress_and_builds_payload(self) -> None:
        """Helper should preserve progress/cache update flow and success payload assembly."""

        app_state = SimpleNamespace(_llm_initialized=True, temp_audio_dir="tmp")
        req = self._base_req()
        store = MagicMock()
        llm_handler = MagicMock()
        selected_handler = SimpleNamespace(device="cuda")
        prepared = SimpleNamespace(
            caption="cap",
            lyrics="lyr",
            bpm=120,
            key_scale="C major",
            time_signature="4/4",
            audio_duration=12.0,
            thinking=False,
            sample_mode=False,
            format_has_duration=False,
            use_cot_caption=False,
            use_cot_language=False,
            lm_top_k=0,
            lm_top_p=0.9,
            original_prompt="orig cap",
            original_lyrics="orig lyr",
        )
        setup = SimpleNamespace(
            params=SimpleNamespace(caption="cap", lyrics="lyr"),
            config=SimpleNamespace(),
        )
        generation_result = SimpleNamespace(success=True, audios=[{"audio_path": "a.wav"}])

        def _run_generation_side_effect(**kwargs):
            kwargs["progress_cb"](0.5, "generating")
            return generation_result

        with patch("acestep.api.job_blocking_generation.prepare_llm_generation_inputs", return_value=prepared), \
                patch("acestep.api.job_blocking_generation.build_generation_setup", return_value=setup), \
                patch("acestep.api.job_blocking_generation.maybe_handle_analysis_only_modes", return_value=None), \
                patch(
                    "acestep.api.job_blocking_generation.run_generation_with_optional_sequential_cover_mode",
                    side_effect=_run_generation_side_effect,
                ), \
                patch(
                    "acestep.api.job_blocking_generation.build_generation_success_response",
                    return_value={"status_message": "Success"},
                ) as build_resp_mock, \
                patch("acestep.api.job_blocking_generation.update_progress_job_cache") as cache_progress_mock:
            result = run_blocking_generate(
                app_state=app_state,
                req=req,
                job_id="job-1",
                store=store,
                llm_handler=llm_handler,
                selected_handler=selected_handler,
                selected_model_name="model-A",
                map_status=MagicMock(return_value="running"),
                result_key_prefix="prefix_",
                result_expire_seconds=3600,
                get_project_root=MagicMock(return_value="root"),
                get_model_name=MagicMock(return_value="m"),
                ensure_model_downloaded=MagicMock(),
                env_bool=MagicMock(return_value=False),
                parse_description_hints=MagicMock(return_value=("en", False)),
                parse_timesteps=MagicMock(return_value=None),
                is_instrumental=MagicMock(return_value=False),
                create_sample_fn=MagicMock(),
                format_sample_fn=MagicMock(),
                generate_music_fn=MagicMock(),
                default_dit_instruction="default",
                task_instructions={},
                build_generation_info_fn=MagicMock(return_value="info"),
                path_to_audio_url_fn=MagicMock(side_effect=lambda p: p),
                log_fn=MagicMock(),
            )

        self.assertEqual({"status_message": "Success"}, result)
        store.update_progress.assert_called_once()
        cache_progress_mock.assert_called_once()
        build_resp_mock.assert_called_once()

    def test_run_blocking_generate_returns_analysis_result_without_generation(self) -> None:
        """Helper should short-circuit when analysis mode returns payload."""

        app_state = SimpleNamespace(_llm_initialized=False, temp_audio_dir="tmp")
        req = self._base_req()
        store = MagicMock()
        llm_handler = MagicMock()
        selected_handler = SimpleNamespace(device="cuda")
        prepared = SimpleNamespace(
            caption="cap",
            lyrics="lyr",
            bpm=None,
            key_scale="",
            time_signature="",
            audio_duration=None,
            thinking=False,
            sample_mode=False,
            format_has_duration=False,
            use_cot_caption=False,
            use_cot_language=False,
            lm_top_k=0,
            lm_top_p=0.9,
            original_prompt="orig cap",
            original_lyrics="orig lyr",
        )
        setup = SimpleNamespace(
            params=SimpleNamespace(caption="cap", lyrics="lyr"),
            config=SimpleNamespace(),
        )
        analysis_payload = {"status_message": "Analysis Only Mode Complete"}

        with patch("acestep.api.job_blocking_generation.prepare_llm_generation_inputs", return_value=prepared), \
                patch("acestep.api.job_blocking_generation.build_generation_setup", return_value=setup), \
                patch(
                    "acestep.api.job_blocking_generation.maybe_handle_analysis_only_modes",
                    return_value=analysis_payload,
                ) as analysis_mock, \
                patch("acestep.api.job_blocking_generation.run_generation_with_optional_sequential_cover_mode") as run_mock, \
                patch("acestep.api.job_blocking_generation.build_generation_success_response") as build_resp_mock:
            result = run_blocking_generate(
                app_state=app_state,
                req=req,
                job_id="job-2",
                store=store,
                llm_handler=llm_handler,
                selected_handler=selected_handler,
                selected_model_name="model-B",
                map_status=MagicMock(return_value="running"),
                result_key_prefix="prefix_",
                result_expire_seconds=3600,
                get_project_root=MagicMock(return_value="root"),
                get_model_name=MagicMock(return_value="m"),
                ensure_model_downloaded=MagicMock(),
                env_bool=MagicMock(return_value=False),
                parse_description_hints=MagicMock(return_value=("en", False)),
                parse_timesteps=MagicMock(return_value=None),
                is_instrumental=MagicMock(return_value=False),
                create_sample_fn=MagicMock(),
                format_sample_fn=MagicMock(),
                generate_music_fn=MagicMock(),
                default_dit_instruction="default",
                task_instructions={},
                build_generation_info_fn=MagicMock(return_value="info"),
                path_to_audio_url_fn=MagicMock(side_effect=lambda p: p),
                log_fn=MagicMock(),
            )

        self.assertEqual(analysis_payload, result)
        self.assertIsNone(analysis_mock.call_args.kwargs["llm_handler"])
        run_mock.assert_not_called()
        build_resp_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
