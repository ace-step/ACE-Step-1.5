"""Tests for preserving a caller's requested vocal language through CoT.

The guarded branch lives inside ``generate_music``, which cannot be exercised
without standing up the whole pipeline, so these tests cover the decision helper
plus the two defaults that give it its meaning.
"""

import unittest

try:
    from acestep.inference import GenerationParams, _is_vocal_language_unset
    from acestep.api.http.release_task_models import GenerateMusicRequest

    _IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover
    GenerationParams = None
    GenerateMusicRequest = None
    _is_vocal_language_unset = None
    _IMPORT_ERROR = exc


@unittest.skipIf(_is_vocal_language_unset is None, f"import unavailable: {_IMPORT_ERROR}")
class IsVocalLanguageUnsetTests(unittest.TestCase):
    """Cover the guard that decides whether CoT may set the vocal language."""

    def test_requested_language_is_preserved(self):
        """A named language blocks CoT from replacing it ('pa' is the regression)."""
        for code in ("pa", "hi", "en", "ur", "yue"):
            with self.subTest(vocal_language=code):
                self.assertFalse(_is_vocal_language_unset(code))

    def test_placeholder_values_allow_detection(self):
        """Values that name no language stay open to CoT detection."""
        for value in (None, "", "unknown"):
            with self.subTest(vocal_language=value):
                self.assertTrue(_is_vocal_language_unset(value))

    def test_placeholder_matching_ignores_case_and_padding(self):
        """'unknown' is recognized regardless of case or surrounding space."""
        for value in ("UNKNOWN", " unknown ", "  Unknown"):
            with self.subTest(vocal_language=value):
                self.assertTrue(_is_vocal_language_unset(value))

    def test_padded_language_code_is_still_a_choice(self):
        """Whitespace around a real code does not make it a placeholder."""
        self.assertFalse(_is_vocal_language_unset("  pa  "))


@unittest.skipIf(GenerationParams is None, f"import unavailable: {_IMPORT_ERROR}")
class CotLanguageDefaultsTests(unittest.TestCase):
    """Pin the defaults the fix relies on.

    If either default moves, the guard silently changes meaning: callers would
    either lose detection they expected or regain the overwrite this fixes.
    """

    def test_generation_params_default_language_is_a_placeholder(self):
        """The GenerationParams default must read as 'caller did not choose'."""
        self.assertTrue(_is_vocal_language_unset(GenerationParams.vocal_language))

    def test_release_task_defaults_to_cot_language_enabled(self):
        """CoT detection is on by default, so callers must opt out explicitly."""
        self.assertTrue(GenerateMusicRequest.model_fields["use_cot_language"].default)

    def test_release_task_default_language_is_english(self):
        """The HTTP default 'en' reads as a choice, so opting out needs the flag."""
        self.assertEqual(GenerateMusicRequest.model_fields["vocal_language"].default, "en")
        self.assertFalse(_is_vocal_language_unset("en"))


if __name__ == "__main__":
    unittest.main()
