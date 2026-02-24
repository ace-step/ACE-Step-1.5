"""Unit tests for event-wiring context helpers."""

import importlib.util
from pathlib import Path
import unittest


AUTO_OUTPUT_EXPECTED = [
    "bpm_auto",
    "key_auto",
    "timesig_auto",
    "vocal_lang_auto",
    "duration_auto",
    "bpm",
    "key_scale",
    "time_signature",
    "vocal_language",
    "audio_duration",
]

AUTO_INPUT_EXPECTED = [
    "bpm",
    "key_scale",
    "time_signature",
    "vocal_language",
    "audio_duration",
]

MODE_OUTPUT_EXPECTED = [
    "simple_mode_group",
    "custom_mode_group",
    "generate_btn",
    "simple_sample_created",
    "optional_params_accordion",
    "task_type",
    "src_audio_row",
    "repainting_group",
    "text2music_audio_codes_group",
    "track_name",
    "complete_track_classes",
    "generate_btn_row",
    "generation_mode",
    "results_wrapper",
    "think_checkbox",
    "load_file_col",
    "load_file",
    "audio_cover_strength",
    "cover_noise_strength",
    "captions",
    "lyrics",
    "bpm",
    "key_scale",
    "time_signature",
    "vocal_language",
    "audio_duration",
    "auto_score",
    "autogen_checkbox",
    "auto_lrc",
    "analyze_btn",
    "repainting_header_html",
    "repainting_start",
    "repainting_end",
    "previous_generation_mode",
    "remix_help_group",
    "extract_help_group",
    "complete_help_group",
    "bpm_auto",
    "key_auto",
    "timesig_auto",
    "vocal_lang_auto",
    "duration_auto",
    "text2music_audio_code_string",
    "src_audio",
]


def _load_context_module():
    """Load the context module directly from disk without package side effects."""
    module_path = Path(__file__).with_name("context.py")
    spec = importlib.util.spec_from_file_location("events_wiring_context", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_context_module()
GenerationWiringContext = _MODULE.GenerationWiringContext
TrainingWiringContext = _MODULE.TrainingWiringContext
build_auto_checkbox_inputs = _MODULE.build_auto_checkbox_inputs
build_auto_checkbox_outputs = _MODULE.build_auto_checkbox_outputs
build_mode_ui_outputs = _MODULE.build_mode_ui_outputs


class GenerationWiringContextTests(unittest.TestCase):
    """Verify ordered component-list builders used by event wiring."""

    def setUp(self):
        """Build a minimal context with deterministic component values."""
        required_keys = set(MODE_OUTPUT_EXPECTED + AUTO_OUTPUT_EXPECTED + AUTO_INPUT_EXPECTED)
        self.generation_section = {key: key for key in required_keys}
        self.context = GenerationWiringContext(
            demo=object(),
            dit_handler=object(),
            llm_handler=object(),
            dataset_handler=object(),
            dataset_section={},
            generation_section=self.generation_section,
            results_section={},
        )

    def test_build_auto_checkbox_outputs_uses_expected_order(self):
        """Auto checkbox output order must remain stable across refactors."""
        self.assertEqual(build_auto_checkbox_outputs(self.context), AUTO_OUTPUT_EXPECTED)

    def test_build_auto_checkbox_inputs_uses_expected_order(self):
        """Auto checkbox input order must remain stable across refactors."""
        self.assertEqual(build_auto_checkbox_inputs(self.context), AUTO_INPUT_EXPECTED)

    def test_build_mode_ui_outputs_uses_expected_order(self):
        """Mode output list must match wiring contract for event handlers."""
        self.assertEqual(build_mode_ui_outputs(self.context), MODE_OUTPUT_EXPECTED)


class TrainingWiringContextTests(unittest.TestCase):
    """Verify the training context stores expected references."""

    def test_training_context_keeps_training_section_reference(self):
        """Training context should keep the original section mapping."""
        training_section = {"training_progress": "training_progress"}
        context = TrainingWiringContext(
            demo=object(),
            dit_handler=object(),
            llm_handler=object(),
            training_section=training_section,
        )
        self.assertIs(context.training_section, training_section)


if __name__ == "__main__":
    unittest.main()
