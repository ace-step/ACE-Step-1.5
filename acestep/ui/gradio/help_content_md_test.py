"""Markdown conversion unit tests for help-content rendering."""

import unittest

from acestep.ui.gradio.help_content_test_helpers import ensure_gradio_mocked

ensure_gradio_mocked()

from acestep.ui.gradio.help_content import _md_to_html  # noqa: E402


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
        result = _md_to_html("- [Guide](https://example.com/guide) - Full guide")
        self.assertIn('<a href="https://example.com/guide"', result)
        self.assertIn(">Guide</a>", result)

    def test_link_in_blockquote(self):
        """[text](url) in a blockquote becomes an <a> tag."""
        result = _md_to_html("> See [docs](https://example.com)")
        self.assertIn('<a href="https://example.com"', result)
        self.assertIn(">docs</a>", result)

    def test_link_in_heading(self):
        """[text](url) in a heading becomes an <a> tag."""
        result = _md_to_html("### [Docs](https://example.com)")
        self.assertIn('<a href="https://example.com"', result)
        self.assertIn(">Docs</a>", result)


if __name__ == "__main__":
    unittest.main()
