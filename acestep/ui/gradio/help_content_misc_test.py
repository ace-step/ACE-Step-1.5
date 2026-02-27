"""Miscellaneous unit tests for help-content ids, CSS, and button wiring."""

import unittest
from unittest.mock import MagicMock, patch

from acestep.ui.gradio.help_content_test_helpers import ensure_gradio_mocked

ensure_gradio_mocked()

from acestep.ui.gradio.help_content import (  # noqa: E402
    HELP_MODAL_CSS,
    _next_id,
    create_help_button,
)


class NextIdTests(unittest.TestCase):
    """Tests for the unique id counter."""

    def test_ids_are_unique(self):
        """Each call should produce a distinct DOM id suffix."""
        self.assertNotEqual(_next_id(), _next_id())

    def test_ids_are_strings(self):
        """Generated id suffixes should be strings for safe HTML formatting."""
        self.assertIsInstance(_next_id(), str)


class HelpModalCssTests(unittest.TestCase):
    """Tests for the exported CSS constant."""

    def test_css_not_empty(self):
        """Help modal CSS should not be empty."""
        self.assertTrue(len(HELP_MODAL_CSS) > 0)

    def test_css_contains_overlay_selector(self):
        """CSS should include modal overlay selector."""
        self.assertIn(".help-modal-overlay", HELP_MODAL_CSS)

    def test_css_contains_content_selector(self):
        """CSS should include modal content selector."""
        self.assertIn(".help-modal-content", HELP_MODAL_CSS)

    def test_css_contains_close_selector(self):
        """CSS should include close-button selector."""
        self.assertIn(".help-modal-close", HELP_MODAL_CSS)

    def test_css_contains_inline_btn_selector(self):
        """CSS should include inline help button selector."""
        self.assertIn(".help-inline-btn", HELP_MODAL_CSS)

    def test_css_contains_inline_container_selector(self):
        """CSS should include inline help container selector."""
        self.assertIn(".help-inline-container", HELP_MODAL_CSS)


class CreateHelpButtonTests(unittest.TestCase):
    """Tests for create_help_button with mocked Gradio."""

    def test_create_help_button_calls_gr_html(self):
        """create_help_button should call gr.HTML and return the result."""
        mock_html = MagicMock()
        with patch("acestep.ui.gradio.help_content.gr.HTML", return_value=mock_html) as mock_gr_html:
            result = create_help_button("getting_started")

        mock_gr_html.assert_called()
        self.assertEqual(result, mock_html)

    def test_create_help_button_html_contains_modal(self):
        """The generated HTML should contain modal markup."""
        captured = {}

        def capture_html(**kwargs):
            """Capture HTML kwargs passed to gr.HTML for markup assertions."""
            captured.update(kwargs)
            return MagicMock()

        with patch("acestep.ui.gradio.help_content.gr.HTML", side_effect=capture_html):
            create_help_button("getting_started")

        html_value = captured.get("value", "")
        self.assertIn("help-modal-overlay", html_value)
        self.assertIn("help-inline-btn", html_value)
        self.assertIn("help-modal-close", html_value)


if __name__ == "__main__":
    unittest.main()
