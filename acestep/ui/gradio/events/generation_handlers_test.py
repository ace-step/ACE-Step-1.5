"""Unit tests for generation input event handlers."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

try:
    from acestep.ui.gradio.events import generation_handlers
    from acestep.ui.gradio.i18n import t as _t
    _IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - environment dependency guard
    generation_handlers = None
    _t = None
    _IMPORT_ERROR = exc


class _FakeDitHandler:
    """Minimal DiT handler stub for analyze-src-audio tests."""

    def __init__(self, convert_result):
        self._convert_result = convert_result
        self.model = MagicMock()  # Required by analyze_src_audio guard

    def convert_src_audio_to_codes(self, _src_audio):
        """Return configured conversion output."""
        return self._convert_result


@unittest.skipIf(generation_handlers is None, f"generation_handlers import unavailable: {_IMPORT_ERROR}")
class GenerationHandlersTests(unittest.TestCase):
    """Tests for source-audio analysis validation behavior."""

    @patch("acestep.ui.gradio.events.generation.llm_actions.gr.Warning")
    @patch("acestep.ui.gradio.events.generation.llm_actions.understand_music")
    def test_analyze_src_audio_rejects_non_audio_code_output(
        self,
        understand_music_mock,
        warning_mock,
    ):
        """Reject conversion output that has no serialized audio-code tokens."""
        dit_handler = _FakeDitHandler("ERROR: not an audio file")
        llm_handler = SimpleNamespace(llm_initialized=True)

        result = generation_handlers.analyze_src_audio(
            dit_handler=dit_handler,
            llm_handler=llm_handler,
            src_audio="fake.mp3",
            constrained_decoding_debug=False,
        )

        # When codes_string has no audio-code tokens, the function returns
        # (codes_string, warning_message, "", "", None, None, "", "", "", False)
        from acestep.ui.gradio.i18n import t
        self.assertEqual(
            result,
            ("ERROR: not an audio file", t("messages.no_audio_codes_generated"),
             "", "", None, None, "", "", "", False),
        )
        understand_music_mock.assert_not_called()
        warning_mock.assert_called_once()

    @patch("acestep.ui.gradio.events.generation.llm_actions.gr.Warning")
    @patch("acestep.ui.gradio.events.generation.llm_actions.understand_music")
    def test_analyze_src_audio_allows_valid_audio_code_output(
        self,
        understand_music_mock,
        warning_mock,
    ):
        """Pass valid audio codes through to LM understanding."""
        dit_handler = _FakeDitHandler("<|audio_code_123|><|audio_code_456|>")
        llm_handler = SimpleNamespace(llm_initialized=True)
        understand_music_mock.return_value = SimpleNamespace(
            success=True,
            status_message="ok",
            caption="caption",
            lyrics="lyrics",
            bpm=120,
            duration=30.0,
            keyscale="C major",
            language="en",
            timesignature="4",
        )

        result = generation_handlers.analyze_src_audio(
            dit_handler=dit_handler,
            llm_handler=llm_handler,
            src_audio="real.mp3",
            constrained_decoding_debug=False,
        )

        self.assertEqual(result[0], "<|audio_code_123|><|audio_code_456|>")
        self.assertEqual(result[1], "ok")
        understand_music_mock.assert_called_once()
        warning_mock.assert_not_called()

    @patch("acestep.ui.gradio.events.generation.service_init.get_global_gpu_config")
    @patch("acestep.ui.gradio.events.generation.service_init.get_model_type_ui_settings")
    def test_init_service_wrapper_preserves_batch_size(
        self,
        get_model_type_ui_settings_mock,
        get_global_gpu_config_mock,
    ):
        """Verify that init_service_wrapper preserves current batch_size when provided."""
        # Setup mocks
        gpu_config_mock = MagicMock()
        gpu_config_mock.max_batch_size_with_lm = 8
        gpu_config_mock.max_batch_size_without_lm = 4
        gpu_config_mock.max_duration_with_lm = 600
        gpu_config_mock.max_duration_without_lm = 300
        gpu_config_mock.tier = "tier5"
        gpu_config_mock.available_lm_models = ["acestep-5Hz-lm-1.7B"]
        get_global_gpu_config_mock.return_value = gpu_config_mock

        get_model_type_ui_settings_mock.return_value = (None,) * 9  # 9 model type settings

        dit_handler = MagicMock()
        dit_handler.model = MagicMock()
        dit_handler.is_turbo_model.return_value = True
        dit_handler.initialize_service.return_value = ("Success", True)

        llm_handler = MagicMock()
        llm_handler.llm_initialized = True
        llm_handler.initialize.return_value = ("LLM initialized", True)

        # Test with current_batch_size = 5
        result = generation_handlers.init_service_wrapper(
            dit_handler=dit_handler,
            llm_handler=llm_handler,
            checkpoint=None,
            config_path="acestep-v15-turbo",
            device="cuda",
            init_llm=True,
            lm_model_path=None,
            backend="vllm",
            use_flash_attention=True,
            offload_to_cpu=False,
            offload_dit_to_cpu=False,
            compile_model=False,
            quantization=False,
            mlx_dit=False,
            current_mode="Custom",
            current_batch_size=5,
        )

        # Result is a tuple: (status, btn_update, accordion, *model_settings, duration_update, batch_update, think_update)
        # batch_update is at index -2 (second to last)
        batch_update = result[-2]
        
        # Verify batch_update preserves the value 5 (clamped to max_batch of 8)
        self.assertEqual(batch_update["value"], 5)
        self.assertEqual(batch_update["maximum"], 8)

    @patch("acestep.ui.gradio.events.generation.service_init.get_global_gpu_config")
    @patch("acestep.ui.gradio.events.generation.service_init.get_model_type_ui_settings")
    def test_init_service_wrapper_defaults_batch_size_when_none(
        self,
        get_model_type_ui_settings_mock,
        get_global_gpu_config_mock,
    ):
        """Verify that init_service_wrapper uses default batch_size when current_batch_size is None."""
        # Setup mocks
        gpu_config_mock = MagicMock()
        gpu_config_mock.max_batch_size_with_lm = 8
        gpu_config_mock.max_batch_size_without_lm = 4
        gpu_config_mock.max_duration_with_lm = 600
        gpu_config_mock.max_duration_without_lm = 300
        gpu_config_mock.tier = "tier5"
        gpu_config_mock.available_lm_models = ["acestep-5Hz-lm-1.7B"]
        get_global_gpu_config_mock.return_value = gpu_config_mock

        get_model_type_ui_settings_mock.return_value = (None,) * 9

        dit_handler = MagicMock()
        dit_handler.model = MagicMock()
        dit_handler.is_turbo_model.return_value = True
        dit_handler.initialize_service.return_value = ("Success", True)

        llm_handler = MagicMock()
        llm_handler.llm_initialized = True
        llm_handler.initialize.return_value = ("LLM initialized", True)

        # Test with current_batch_size = None (should default to 2)
        result = generation_handlers.init_service_wrapper(
            dit_handler=dit_handler,
            llm_handler=llm_handler,
            checkpoint=None,
            config_path="acestep-v15-turbo",
            device="cuda",
            init_llm=True,
            lm_model_path=None,
            backend="vllm",
            use_flash_attention=True,
            offload_to_cpu=False,
            offload_dit_to_cpu=False,
            compile_model=False,
            quantization=False,
            mlx_dit=False,
            current_mode="Custom",
            current_batch_size=None,
        )

        batch_update = result[-2]
        
        # Verify batch_update defaults to min(2, max_batch)
        self.assertEqual(batch_update["value"], 2)
        self.assertEqual(batch_update["maximum"], 8)

    @patch("acestep.ui.gradio.events.generation.validation.gr.Warning")
    @patch("acestep.ui.gradio.events.generation.validation.soundfile.info")
    def test_validate_uploaded_audio_file_returns_none_for_invalid_file(
        self,
        info_mock,
        warning_mock,
    ):
        """Invalid audio upload should emit warning toast and clear component value."""
        info_mock.side_effect = RuntimeError("bad file")
        result = generation_handlers.validate_uploaded_audio_file("broken.bin", "reference")
        self.assertEqual(result.get("value"), None)
        warning_mock.assert_called_once()

    @patch("acestep.ui.gradio.events.generation.validation.gr.Warning")
    @patch("acestep.ui.gradio.events.generation.validation.soundfile.info")
    def test_validate_uploaded_audio_file_keeps_valid_file(
        self,
        info_mock,
        warning_mock,
    ):
        """Valid audio upload should pass through unchanged without warning."""
        result = generation_handlers.validate_uploaded_audio_file("ok.wav", "reference")
        self.assertEqual(result, {"__type__": "update"})
        info_mock.assert_called_once_with("ok.wav")
        warning_mock.assert_not_called()

    @patch("acestep.ui.gradio.events.generation.validation.gr.Warning")
    @patch("acestep.ui.gradio.events.generation.validation.soundfile.info")
    def test_validate_uploaded_audio_file_shows_source_role_message(
        self,
        info_mock,
        warning_mock,
    ):
        """Source-role validation should surface a source-specific toast message."""
        info_mock.side_effect = RuntimeError("bad file")
        result = generation_handlers.validate_uploaded_audio_file("broken.bin", "source")
        self.assertEqual(result.get("value"), None)
        expected_role = _t("generation.source_audio")
        expected_message = _t("messages.audio_format_invalid", role=expected_role)
        warning_mock.assert_called_once_with(
            expected_message
        )


@unittest.skipIf(generation_handlers is None, f"generation_handlers import unavailable: {_IMPORT_ERROR}")
class LoadMetadataLmCodesTests(unittest.TestCase):
    """Tests that load_metadata sets think=False when audio_codes are present."""

    def _write_json(self, tmpdir, data):
        """Write a JSON file and return a SimpleNamespace with .name pointing to it."""
        import json, os
        path = os.path.join(tmpdir, "test.json")
        with open(path, "w") as f:
            json.dump(data, f)
        return SimpleNamespace(name=path)

    @patch("acestep.ui.gradio.events.generation.metadata_loading.gr.Info")
    @patch("acestep.ui.gradio.events.generation.metadata_loading.get_global_gpu_config")
    def test_think_set_false_when_audio_codes_present(self, gpu_mock, info_mock):
        """When JSON has thinking=True AND non-empty audio_codes, think should be False."""
        import tempfile
        gpu_cfg = MagicMock()
        gpu_cfg.max_batch_size_with_lm = 8
        gpu_cfg.max_batch_size_without_lm = 8
        gpu_mock.return_value = gpu_cfg

        llm_handler = SimpleNamespace(llm_initialized=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            file_obj = self._write_json(tmpdir, {
                "thinking": True,
                "audio_codes": "<|audio_code_1|><|audio_code_2|>",
            })
            result = generation_handlers.load_metadata(file_obj, llm_handler)

        # think is at return position 30 (0-indexed)
        think_value = result[30]
        audio_codes_value = result[31]
        self.assertFalse(think_value, "think should be False when audio_codes present")
        self.assertEqual(audio_codes_value, "<|audio_code_1|><|audio_code_2|>")

    @patch("acestep.ui.gradio.events.generation.metadata_loading.gr.Info")
    @patch("acestep.ui.gradio.events.generation.metadata_loading.get_global_gpu_config")
    def test_think_unchanged_when_audio_codes_empty(self, gpu_mock, info_mock):
        """When JSON has thinking=True AND empty audio_codes, think stays True."""
        import tempfile
        gpu_cfg = MagicMock()
        gpu_cfg.max_batch_size_with_lm = 8
        gpu_cfg.max_batch_size_without_lm = 8
        gpu_mock.return_value = gpu_cfg

        llm_handler = SimpleNamespace(llm_initialized=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            file_obj = self._write_json(tmpdir, {
                "thinking": True,
                "audio_codes": "",
            })
            result = generation_handlers.load_metadata(file_obj, llm_handler)

        think_value = result[30]
        self.assertTrue(think_value, "think should remain True when audio_codes is empty")


@unittest.skipIf(generation_handlers is None, f"generation_handlers import unavailable: {_IMPORT_ERROR}")
class AutoCheckboxTests(unittest.TestCase):
    """Tests for optional-parameter Auto checkbox handler functions."""

    def test_on_auto_checkbox_change_checked_returns_default_and_non_interactive(self):
        """When Auto is checked, field should reset to default and become non-interactive."""
        result = generation_handlers.on_auto_checkbox_change(True, "bpm")
        # gr.update returns a dict-like object; check value and interactive
        self.assertIsNone(result["value"])
        self.assertFalse(result["interactive"])

    def test_on_auto_checkbox_change_unchecked_returns_interactive(self):
        """When Auto is unchecked, field should become interactive (no value reset)."""
        result = generation_handlers.on_auto_checkbox_change(False, "bpm")
        self.assertTrue(result["interactive"])

    def test_on_auto_checkbox_change_all_fields(self):
        """All supported field names should produce valid defaults when checked."""
        expected = {
            "bpm": None,
            "key_scale": "",
            "time_signature": "",
            "vocal_language": "unknown",
            "audio_duration": -1,
        }
        for field_name, expected_value in expected.items():
            result = generation_handlers.on_auto_checkbox_change(True, field_name)
            self.assertEqual(result["value"], expected_value, f"Field {field_name}")
            self.assertFalse(result["interactive"], f"Field {field_name}")

    def test_reset_all_auto_returns_correct_count(self):
        """reset_all_auto should return exactly 10 gr.update objects."""
        result = generation_handlers.reset_all_auto()
        self.assertEqual(len(result), 10)

    def test_reset_all_auto_checkboxes_are_true(self):
        """First 5 outputs (auto checkboxes) should all be set to True."""
        result = generation_handlers.reset_all_auto()
        for i in range(5):
            self.assertTrue(result[i]["value"], f"Auto checkbox at index {i}")

    def test_reset_all_auto_fields_are_defaults(self):
        """Last 5 outputs (fields) should be reset to auto defaults."""
        result = generation_handlers.reset_all_auto()
        self.assertIsNone(result[5]["value"])         # bpm
        self.assertEqual(result[6]["value"], "")       # key_scale
        self.assertEqual(result[7]["value"], "")       # time_signature
        self.assertEqual(result[8]["value"], "unknown") # vocal_language
        self.assertEqual(result[9]["value"], -1)       # audio_duration

    def test_uncheck_auto_for_populated_fields_all_default(self):
        """When all fields have default values, all auto checkboxes should stay checked."""
        result = generation_handlers.uncheck_auto_for_populated_fields(
            bpm=None, key_scale="", time_signature="",
            vocal_language="unknown", audio_duration=-1,
        )
        self.assertEqual(len(result), 10)
        # Auto checkboxes should be True (checked)
        for i in range(5):
            self.assertTrue(result[i]["value"], f"Auto checkbox at index {i}")
        # Fields should be non-interactive
        for i in range(5, 10):
            self.assertFalse(result[i]["interactive"], f"Field at index {i}")

    def test_uncheck_auto_for_populated_fields_all_populated(self):
        """When all fields have non-default values, all auto checkboxes should be unchecked."""
        result = generation_handlers.uncheck_auto_for_populated_fields(
            bpm=120, key_scale="C major", time_signature="4",
            vocal_language="en", audio_duration=30.0,
        )
        # Auto checkboxes should be False (unchecked)
        for i in range(5):
            self.assertFalse(result[i]["value"], f"Auto checkbox at index {i}")
        # Fields should be interactive
        for i in range(5, 10):
            self.assertTrue(result[i]["interactive"], f"Field at index {i}")

    def test_uncheck_auto_for_populated_fields_mixed(self):
        """Mixed populated/default fields should only uncheck populated ones."""
        result = generation_handlers.uncheck_auto_for_populated_fields(
            bpm=120, key_scale="", time_signature="4",
            vocal_language="unknown", audio_duration=-1,
        )
        self.assertFalse(result[0]["value"])   # bpm_auto unchecked
        self.assertTrue(result[1]["value"])    # key_auto stays checked
        self.assertFalse(result[2]["value"])   # timesig_auto unchecked
        self.assertTrue(result[3]["value"])    # vocal_lang_auto stays checked
        self.assertTrue(result[4]["value"])    # duration_auto stays checked


if __name__ == "__main__":
    unittest.main()
