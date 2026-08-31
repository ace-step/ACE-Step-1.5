"""Tests for preserving a caller's requested vocal language through CoT.

The guarded branch lives inside ``generate_music``, which cannot be exercised
without standing up the whole pipeline, so these tests cover the decision helper
plus the two defaults that give it its meaning.
"""

import unittest

from acestep.api.http.release_task_models import GenerateMusicRequest
from acestep.inference import GenerationParams, _is_vocal_language_unset


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

    def test_release_task_language_default_is_none(self):
        """Defaulting to "en" would make an omitted language look explicit."""
        self.assertIsNone(GenerateMusicRequest.model_fields["vocal_language"].default)

    def test_explicit_english_is_treated_as_a_choice(self):
        """An explicit "en" must survive a conflicting CoT detection."""
        self.assertFalse(_is_vocal_language_unset("en"))


if __name__ == "__main__":
    unittest.main()
