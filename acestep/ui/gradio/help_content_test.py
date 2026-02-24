"""Unit tests for the help content module.

Validates:
- Markdown-to-HTML conversion (_md_to_html)
- Unique DOM id generation (_next_id)
- i18n help key completeness across all language files
- CSS string is non-empty and contains expected selectors
- create_help_button wiring (with Gradio mocked)

Note: This test file pre-mocks ``gradio`` at the sys.modules level so
that the import chain through ``acestep.ui.gradio`` succeeds even when
Gradio is not installed.  Run with ``python <this_file>`` or via a
test runner that discovers it directly.
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Pre-mock gradio so the acestep.ui.gradio package __init__.py
# (which eagerly imports gradio) does not blow up.
# ---------------------------------------------------------------------------
if "gradio" not in sys.modules:
    sys.modules["gradio"] = MagicMock()

from acestep.ui.gradio.help_content import (  # noqa: E402
    HELP_MODAL_CSS,
    _md_to_html,
    _next_id,
    create_help_button,
)
from acestep.ui.gradio.i18n import I18n  # noqa: E402


# ---------------------------------------------------------------------------
# Markdown → HTML converter
# ---------------------------------------------------------------------------
class MdToHtmlTests(unittest.TestCase):
    """Tests for the lightweight Markdown-to-HTML converter."""

    def test_heading_h2(self):
        """## headings become <h3> tags."""
        self.assertIn("<h3>Title</h3>", _md_to_html("## Title"))

    def test_heading_h3(self):
        """### headings become <h4> tags."""
        self.assertIn("<h4>Subtitle</h4>", _md_to_html("### Subtitle"))

    def test_bold_text(self):
        """**bold** becomes <strong>."""
        self.assertIn("<strong>bold</strong>", _md_to_html("Use **bold** here"))

    def test_italic_text(self):
        """*italic* becomes <em>."""
        self.assertIn("<em>italic</em>", _md_to_html("Use *italic* here"))

    def test_inline_code(self):
        """`code` becomes <code>."""
        self.assertIn("<code>pip install</code>", _md_to_html("Run `pip install`"))

    def test_unordered_list(self):
        """Dash list items become <li> inside <ul>."""
        result = _md_to_html("- item one\n- item two")
        self.assertIn("<ul", result)
        self.assertIn("<li>item one</li>", result)
        self.assertIn("<li>item two</li>", result)

    def test_ordered_list(self):
        """Numbered list items become <li>."""
        result = _md_to_html("1. first\n2. second")
        self.assertIn("<li>first</li>", result)
        self.assertIn("<li>second</li>", result)

    def test_blockquote(self):
        """> lines become <blockquote>."""
        result = _md_to_html("> A tip here")
        self.assertIn("<blockquote", result)
        self.assertIn("A tip here", result)

    def test_code_block(self):
        """Fenced code blocks become <pre><code>."""
        result = _md_to_html("```\nprint('hi')\n```")
        self.assertIn("<pre><code>", result)
        self.assertIn("print('hi')", result)
        self.assertIn("</code></pre>", result)

    def test_empty_input(self):
        """Empty string produces output without errors."""
        self.assertIsInstance(_md_to_html(""), str)

    def test_paragraph(self):
        """Plain text becomes a <p> tag."""
        result = _md_to_html("Hello world")
        self.assertIn("<p", result)
        self.assertIn("Hello world", result)

    def test_list_closed_after_non_list_line(self):
        """<ul> opened by list items is closed when a non-list line follows."""
        result = _md_to_html("- a\n- b\n\nParagraph")
        ul_close = result.index("</ul>")
        para = result.index("Paragraph")
        self.assertLess(ul_close, para)

    def test_link_in_paragraph(self):
        """[text](url) in a paragraph becomes an <a> tag."""
        result = _md_to_html("See [Tutorial](https://example.com) for details")
        self.assertIn('<a href="https://example.com"', result)
        self.assertIn(">Tutorial</a>", result)
        self.assertIn('target="_blank"', result)

    def test_link_in_list_item(self):
        """[text](url) in a list item becomes an <a> tag."""
        result = _md_to_html("- [Guide](https://example.com/guide) — Full guide")
        self.assertIn('<a href="https://example.com/guide"', result)
        self.assertIn(">Guide</a>", result)

    def test_link_in_blockquote(self):
        """[text](url) in a blockquote becomes an <a> tag."""
        result = _md_to_html("> See [docs](https://example.com)")
        self.assertIn('<a href="https://example.com"', result)
        self.assertIn(">docs</a>", result)

    def test_link_in_heading(self):
        """[text](url) in a heading becomes an <a> tag."""
        result = _md_to_html("### 📖 [Docs](https://example.com)")
        self.assertIn('<a href="https://example.com"', result)
        self.assertIn(">Docs</a>", result)


# ---------------------------------------------------------------------------
# Unique id counter
# ---------------------------------------------------------------------------
class NextIdTests(unittest.TestCase):
    """Tests for the unique id counter."""

    def test_ids_are_unique(self):
        self.assertNotEqual(_next_id(), _next_id())

    def test_ids_are_strings(self):
        self.assertIsInstance(_next_id(), str)


# ---------------------------------------------------------------------------
# CSS constant
# ---------------------------------------------------------------------------
class HelpModalCssTests(unittest.TestCase):
    """Tests for the exported CSS constant."""

    def test_css_not_empty(self):
        self.assertTrue(len(HELP_MODAL_CSS) > 0)

    def test_css_contains_overlay_selector(self):
        self.assertIn(".help-modal-overlay", HELP_MODAL_CSS)

    def test_css_contains_content_selector(self):
        self.assertIn(".help-modal-content", HELP_MODAL_CSS)

    def test_css_contains_close_selector(self):
        self.assertIn(".help-modal-close", HELP_MODAL_CSS)

    def test_css_contains_inline_btn_selector(self):
        self.assertIn(".help-inline-btn", HELP_MODAL_CSS)

    def test_css_contains_inline_container_selector(self):
        self.assertIn(".help-inline-container", HELP_MODAL_CSS)


# ---------------------------------------------------------------------------
# i18n help keys
# ---------------------------------------------------------------------------
class I18nHelpKeysTests(unittest.TestCase):
    """Verify that all language files contain the required help.* keys."""

    REQUIRED_HELP_KEYS = {
        "btn_label",
        "close_label",
        "getting_started",
        "service_config",
        "generation_simple",
        "generation_custom",
        "generation_remix",
        "generation_repaint",
        "generation_extract",
        "generation_lego",
        "generation_complete",
    }

    @classmethod
    def setUpClass(cls):
        i18n_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "i18n"
        )
        cls.languages: dict[str, dict] = {}
        for fname in sorted(os.listdir(i18n_dir)):
            if fname.endswith(".json"):
                lang = fname[:-5]
                with open(os.path.join(i18n_dir, fname), encoding="utf-8") as f:
                    cls.languages[lang] = json.load(f)

    def test_en_has_help_section(self):
        """English JSON must have a top-level 'help' key."""
        self.assertIn("help", self.languages["en"])

    def test_all_languages_have_required_keys(self):
        """Every language with a help section must contain all required keys."""
        for lang, data in self.languages.items():
            help_section = data.get("help")
            if help_section is None:
                continue
            for key in self.REQUIRED_HELP_KEYS:
                with self.subTest(lang=lang, key=key):
                    self.assertIn(
                        key, help_section,
                        f"Language '{lang}' is missing help.{key}",
                    )

    def test_help_values_are_non_empty_strings(self):
        """Help values must be non-empty strings."""
        for lang, data in self.languages.items():
            help_section = data.get("help")
            if help_section is None:
                continue
            for key in self.REQUIRED_HELP_KEYS:
                with self.subTest(lang=lang, key=key):
                    val = help_section.get(key)
                    self.assertIsInstance(val, str)
                    self.assertTrue(len(val) > 0)

    def test_i18n_t_returns_help_content(self):
        """i18n t() resolves help.* keys to actual content, not the key."""
        i18n = I18n(default_language="en")
        result = i18n.t("help.getting_started")
        self.assertNotEqual(result, "help.getting_started")
        self.assertIn("##", result)


# ---------------------------------------------------------------------------
# create_help_button (Gradio is mocked)
# ---------------------------------------------------------------------------
class CreateHelpButtonTests(unittest.TestCase):
    """Tests for create_help_button with mocked Gradio."""

    def test_create_help_button_calls_gr_html(self):
        """create_help_button should call gr.HTML and return the result."""
        import gradio as gr  # This is the mock

        mock_html = MagicMock()
        gr.HTML.return_value = mock_html

        result = create_help_button("getting_started")

        gr.HTML.assert_called()
        self.assertEqual(result, mock_html)

    def test_create_help_button_html_contains_modal(self):
        """The generated HTML should contain modal markup."""
        import gradio as gr

        # Capture the value= kwarg passed to gr.HTML
        captured = {}

        def capture_html(**kwargs):
            captured.update(kwargs)
            return MagicMock()

        gr.HTML.side_effect = capture_html
        create_help_button("getting_started")

        html_value = captured.get("value", "")
        self.assertIn("help-modal-overlay", html_value)
        self.assertIn("help-inline-btn", html_value)
        self.assertIn("help-modal-close", html_value)


if __name__ == "__main__":
    unittest.main()
