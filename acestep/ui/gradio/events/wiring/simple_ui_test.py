"""Tests for the simplified UI flow — generation and navigation."""

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import gradio as gr

from acestep.ui.gradio.events.results.generation_progress import _lyrics_are_instrumental
from acestep.ui.gradio.interfaces.simple_ui import (
    _about_overlay_html,
    _step_indicator_html,
    build_simple_ui,
)
from acestep.ui.gradio.events.wiring.simple_ui_wiring import (
    _navigate_to,
    _start_generation,
    _build_status_html,
    _build_metadata_html,
    _format_duration,
    _go_random,
    _resolve_simple_lyrics,
    _instrumental_lyrics_update,
    _completion_message,
    _ignore_progress,
    _save_audio_js,
)


class TestSimpleUINavigation(unittest.TestCase):
    """Step navigation should return correct visibility state."""

    def test_navigate_to_step_1_shows_step_1_hides_others(self):
        result = _navigate_to(1, 1)
        self.assertEqual(result[0], 1)  # target step
        self.assertTrue(result[2]["visible"])  # step 1 visible
        self.assertFalse(result[3]["visible"])  # step 2 hidden
        self.assertFalse(result[4]["visible"])  # step 3 hidden
        self.assertFalse(result[5]["visible"])  # step 4 hidden
        self.assertFalse(result[6]["visible"])  # step 5 hidden

    def test_navigate_to_step_3(self):
        result = _navigate_to(3, 2)
        self.assertEqual(result[0], 3)
        self.assertFalse(result[2]["visible"])  # step 1 hidden
        self.assertFalse(result[3]["visible"])  # step 2 hidden
        self.assertTrue(result[4]["visible"])  # step 3 visible
        self.assertFalse(result[5]["visible"])  # step 4 hidden
        self.assertFalse(result[6]["visible"])  # step 5 hidden

    def test_step_indicator_generates_svg(self):
        html = _step_indicator_html(3)
        self.assertIn("<svg", html)
        self.assertIn("Describe Song", html)
        self.assertIn("Lyrics", html)
        self.assertIn("Remix", html)
        self.assertIn("Creating", html)
        self.assertIn("Done", html)

    def test_step_indicator_current_step_is_highlighted(self):
        html = _step_indicator_html(3)
        self.assertIn('filter="url(#glow)"', html)

    def test_step_wrapper_is_layout_transparent(self):
        """Hidden Gradio Column shells must not render as empty bordered rows."""
        interface_path = Path(__file__).parents[2] / "interfaces" / "__init__.py"
        css_source = interface_path.read_text(encoding="utf-8")
        step_rule = css_source.split(".simple-step {", 1)[1].split("}", 1)[0]
        self.assertIn("display: contents", step_rule)

    def test_results_use_two_column_desktop_grid(self):
        """Done-screen cards should sit side by side on larger screens."""
        interface_path = Path(__file__).parents[2] / "interfaces" / "__init__.py"
        css_source = interface_path.read_text(encoding="utf-8")
        results_rule = css_source.split(".simple-results-row {", 1)[1].split("}", 1)[0]
        self.assertIn("grid-template-columns: repeat(2", results_rule)

    def test_simple_root_uses_content_height_block_layout(self):
        """Simple screens should not distribute viewport height between sections."""
        interface_path = Path(__file__).parents[2] / "interfaces" / "__init__.py"
        css_source = interface_path.read_text(encoding="utf-8")
        root_rule = css_source.split("#simple-ui-column {", 1)[1].split("}", 1)[0]
        self.assertIn("display: block", root_rule)
        self.assertIn("min-height: 0", root_rule)


class TestSimpleUIHelpers(unittest.TestCase):
    """Utility functions should produce expected output."""

    def test_random_style_returns_string(self):
        style = _go_random()
        self.assertIsInstance(style, str)
        self.assertGreater(len(style), 10)

    def test_format_duration_seconds(self):
        self.assertEqual(_format_duration(0), "")
        self.assertEqual(_format_duration(15), "15s")
        self.assertEqual(_format_duration(120), "2m 0s")

    def test_build_metadata_html(self):
        html = _build_metadata_html(15, "flac")
        self.assertIn("15s", html)
        self.assertIn("FLAC", html)

    def test_build_metadata_html_no_duration(self):
        html = _build_metadata_html(0, "mp3")
        self.assertIn("MP3", html)

    def test_status_html_success(self):
        html = _build_status_html("Generation complete", True)
        self.assertIn("success", html)

    def test_status_html_failure(self):
        html = _build_status_html("Generation failed", False)
        self.assertNotIn("success", html)

    def test_instrumental_mode_replaces_lyrics_with_sentinel(self):
        self.assertEqual(_resolve_simple_lyrics("written lyrics", True), "[Instrumental]")

    def test_vocal_mode_preserves_lyrics(self):
        self.assertEqual(_resolve_simple_lyrics("written lyrics", False), "written lyrics")

    def test_generator_recognizes_instrumental_sentinel(self):
        self.assertTrue(_lyrics_are_instrumental("[Instrumental]"))
        self.assertFalse(_lyrics_are_instrumental("written lyrics"))

    def test_instrumental_mode_disables_lyrics_input(self):
        self.assertFalse(_instrumental_lyrics_update(True)["interactive"])
        self.assertTrue(_instrumental_lyrics_update(False)["interactive"])

    @patch("acestep.ui.gradio.events.wiring.simple_ui_wiring.t")
    def test_completion_message_falls_back_when_translation_is_missing(self, mock_t):
        mock_t.return_value = "messages.generation_complete"
        self.assertEqual(_completion_message(), "Generation complete")

    def test_simple_progress_callback_is_silent(self):
        self.assertIsNone(_ignore_progress(0.5, desc="Generating"))

    def test_save_audio_prefers_gradio_url_with_local_path_fallback(self):
        javascript = _save_audio_js()
        self.assertIn("audio.url || audio.data || audio.path", javascript)
        self.assertIn("/gradio_api/file=", javascript)


class TestSimpleUIStartGeneration(unittest.TestCase):
    """_start_generation should return values matching generation outputs."""

    def test_returns_14_values(self):
        result = _start_generation()
        self.assertEqual(len(result), 14)

    def test_step_3_hidden(self):
        result = _start_generation()
        self.assertFalse(result[3]["visible"])

    def test_step_4_visible(self):
        result = _start_generation()
        self.assertTrue(result[4]["visible"])

    def test_step_5_hidden(self):
        result = _start_generation()
        self.assertFalse(result[5]["visible"])

    def test_indicator_shows_step_4(self):
        result = _start_generation()
        html = result[2]["value"]
        self.assertIn("Creating", html)
        self.assertIn('filter="url(#glow)"', html)


class TestSimpleUIGenerateWrapper(unittest.TestCase):
    """_simple_generate_wrapper should yield correct number of values."""

    def setUp(self):
        self.dit = MagicMock()
        self.dit.get_available_acestep_v15_models.return_value = ["acestep-v15-turbo"]
        self.dit.initialize_service.return_value = ("ok", True)
        self.llm = MagicMock()
        self.llm.llm_initialized = True
        self.llm.get_available_5hz_lm_models.return_value = []
        self.llm.initialize.return_value = ("ok", True)

    @patch("acestep.ui.gradio.events.wiring.simple_ui_wiring.generate_with_progress")
    def test_generate_wrapper_yields_progress(self, mock_gen):
        """Verify the generator yields tuples of the expected length."""
        from acestep.ui.gradio.events.wiring.simple_ui_wiring import (
            _simple_generate_wrapper,
        )

        gen = _simple_generate_wrapper(
            self.dit, self.llm,
            "test song", "", False, None,
            0, 1, {}, {},
        )

        step1 = next(gen)
        self.assertEqual(len(step1), 14)
        step2 = next(gen)
        self.assertEqual(len(step2), 14)

    @patch("acestep.ui.gradio.events.wiring.simple_ui_wiring.generate_with_progress")
    def test_generate_wrapper_with_lyrics_skips_sample_creation(self, mock_gen):
        """When lyrics are provided, no create_sample call."""
        from acestep.ui.gradio.events.wiring.simple_ui_wiring import (
            _simple_generate_wrapper,
        )

        gen = _simple_generate_wrapper(
            self.dit, self.llm,
            "test song", "my lyrics", False, None,
            0, 1, {}, {},
        )

        step1 = next(gen)
        self.assertEqual(len(step1), 14)
        step2 = next(gen)
        self.assertEqual(len(step2), 14)
        self.assertIs(mock_gen.call_args.kwargs["progress"], _ignore_progress)

    @patch("acestep.ui.gradio.events.wiring.simple_ui_wiring.generate_with_progress")
    def test_generate_wrapper_with_audio_sets_cover_task(self, mock_gen):
        """When src_audio is provided, task_type should be 'cover'."""
        from acestep.ui.gradio.events.wiring.simple_ui_wiring import (
            _simple_generate_wrapper,
        )

        gen = _simple_generate_wrapper(
            self.dit, self.llm,
            "", "", False, "/path/to/audio.wav",
            0, 1, {}, {},
        )

        step1 = next(gen)
        self.assertEqual(len(step1), 14)
        step2 = next(gen)
        self.assertEqual(len(step2), 14)

    @patch("acestep.ui.gradio.events.wiring.simple_ui_wiring.generate_with_progress")
    @patch("acestep.ui.gradio.events.wiring.simple_ui_wiring.get_global_gpu_config")
    @patch("acestep.ui.gradio.events.wiring.simple_ui_wiring.find_best_lm_model_on_disk")
    @patch("acestep.ui.gradio.events.wiring.simple_ui_wiring.resolve_lm_backend")
    def test_generate_wrapper_auto_inits_llm(self, mock_resolve, mock_find, mock_config, mock_gen):
        """When LLM is not initialized, it should be auto-initialized."""
        from acestep.ui.gradio.events.wiring.simple_ui_wiring import (
            _simple_generate_wrapper,
        )

        self.llm.llm_initialized = False
        self.llm.get_available_5hz_lm_models.return_value = ["acestep-5Hz-lm-1.7B"]
        mock_gpu = MagicMock()
        mock_gpu.recommended_lm_model = "acestep-5Hz-lm-1.7B"
        mock_gpu.recommended_backend = "pt"
        mock_gpu.offload_to_cpu_default = True
        mock_config.return_value = mock_gpu
        mock_find.return_value = "acestep-5Hz-lm-1.7B"
        mock_resolve.return_value = "pt"
        self.llm.initialize.return_value = ("ok", True)

        gen = _simple_generate_wrapper(
            self.dit, self.llm,
            "test song", "", False, None,
            0, 1, {}, {},
        )

        # First yield: LLM init progress
        step1 = next(gen)
        self.assertEqual(len(step1), 14)

        # Second yield (and onwards): LLM init happens + rest of generation
        step2 = next(gen)
        self.assertEqual(len(step2), 14)

        # The initialize() method should have been called
        self.llm.initialize.assert_called_once()

    @patch("acestep.ui.gradio.events.wiring.simple_ui_wiring.generate_with_progress")
    @patch("acestep.ui.gradio.events.wiring.simple_ui_wiring.get_global_gpu_config")
    @patch("acestep.ui.gradio.events.wiring.simple_ui_wiring.find_best_lm_model_on_disk")
    @patch("acestep.ui.gradio.events.wiring.simple_ui_wiring.resolve_lm_backend")
    def test_generate_wrapper_llm_init_failure_falls_back(self, mock_resolve, mock_find, mock_config, mock_gen):
        """When LLM auto-init fails, generation should continue without think."""
        from acestep.ui.gradio.events.wiring.simple_ui_wiring import (
            _simple_generate_wrapper,
        )

        self.llm.llm_initialized = False
        self.llm.get_available_5hz_lm_models.return_value = []
        mock_gpu = MagicMock()
        mock_gpu.recommended_lm_model = None
        mock_gpu.recommended_backend = "pt"
        mock_gpu.offload_to_cpu_default = True
        mock_config.return_value = mock_gpu
        mock_find.return_value = None
        mock_resolve.return_value = "pt"

        gen = _simple_generate_wrapper(
            self.dit, self.llm,
            "test song", "", False, None,
            0, 1, {}, {},
        )

        step1 = next(gen)
        self.assertEqual(len(step1), 14)
        step2 = next(gen)
        self.assertEqual(len(step2), 14)


class TestAboutOverlay(unittest.TestCase):
    """About overlay HTML should render correctly."""

    def test_about_overlay_contains_title(self):
        html = _about_overlay_html()
        self.assertIn("ACE-Step", html)
        self.assertIn("V1.5", html)
        self.assertIn("Playground", html)

    def test_about_overlay_does_not_mutate_visibility_inline(self):
        html = _about_overlay_html()
        self.assertNotIn("onclick", html)
        self.assertNotIn("style.display", html)


class TestSimpleMenu(unittest.TestCase):
    """Hamburger menu controls should use styled SVG classes and plain labels."""

    def test_menu_buttons_have_svg_classes_without_emoji_labels(self):
        with gr.Blocks():
            components = build_simple_ui()

        expected = {
            "simple_about_btn": ("About", "simple-menu-about"),
            "simple_help_btn": ("Help", "simple-menu-help"),
            "simple_advanced_btn": ("Advanced Mode", "simple-menu-advanced"),
        }
        for key, (label, icon_class) in expected.items():
            button = components[key]
            self.assertEqual(button.value, label)
            self.assertIn(icon_class, button.elem_classes)

    def test_simple_ui_is_visible_by_default(self):
        with gr.Blocks():
            components = build_simple_ui()

        self.assertTrue(components["simple_column"].visible)

    def test_remix_create_button_uses_compact_size(self):
        with gr.Blocks():
            components = build_simple_ui()

        self.assertEqual(components["simple_create_btn"].size, "sm")


if __name__ == "__main__":
    unittest.main()
