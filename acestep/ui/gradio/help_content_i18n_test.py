"""I18n key-coverage tests for help-content strings."""

import json
import os
import unittest

from acestep.ui.gradio.help_content_test_helpers import ensure_gradio_mocked

ensure_gradio_mocked()

from acestep.ui.gradio.i18n import I18n  # noqa: E402


class I18nHelpKeysTests(unittest.TestCase):
    """Verify that all language files contain the required help.* keys."""

    REQUIRED_HELP_KEYS = frozenset({
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
    })

    @classmethod
    def setUpClass(cls):
        """Load all i18n language JSON files for help-key assertions."""
        i18n_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "i18n"
        )
        cls.languages: dict[str, dict] = {}
        for fname in sorted(os.listdir(i18n_dir)):
            if fname.endswith(".json"):
                lang = fname[:-5]
                with open(os.path.join(i18n_dir, fname), encoding="utf-8") as handle:
                    cls.languages[lang] = json.load(handle)

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
                        key,
                        help_section,
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
                    value = help_section.get(key)
                    self.assertIsInstance(value, str)
                    self.assertTrue(len(value) > 0)

    def test_i18n_t_returns_help_content(self):
        """i18n t() resolves help.* keys to actual content, not the key."""
        i18n = I18n(default_language="en")
        result = i18n.t("help.getting_started")
        self.assertNotEqual(result, "help.getting_started")
        self.assertIn("##", result)


if __name__ == "__main__":
    unittest.main()
