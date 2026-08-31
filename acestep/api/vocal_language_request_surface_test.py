"""Request-surface tests for omitted vs explicit vocal_language.

Exercises the real chain (RequestParser -> build_generate_music_request ->
build_generation_setup -> GenerationParams -> the CoT guard), because the
distinction lives at the request boundary rather than in the guard helper.
"""

from __future__ import annotations

import unittest

try:
    from acestep.api.http.release_task_models import GenerateMusicRequest
    from acestep.api.http.release_task_param_parser import RequestParser
    from acestep.api.http.release_task_request_builder import build_generate_music_request
    from acestep.api.job_generation_setup import build_generation_setup
    from acestep.constants import DEFAULT_DIT_INSTRUCTION
    from acestep.inference import _is_vocal_language_unset

    _IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover
    GenerateMusicRequest = None
    RequestParser = None
    build_generate_music_request = None
    build_generation_setup = None
    DEFAULT_DIT_INSTRUCTION = ""
    _is_vocal_language_unset = None
    _IMPORT_ERROR = exc


def _request(body: dict):
    """Build a GenerateMusicRequest from a raw request body."""
    return build_generate_music_request(
        RequestParser(body), GenerateMusicRequest, DEFAULT_DIT_INSTRUCTION, 1.0, 1.0, 0.9
    )


def _params(body: dict, use_cot_language: bool = True):
    """Take a raw request body all the way to GenerationParams."""
    setup = build_generation_setup(
        req=_request(body),
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
        use_cot_language=use_cot_language,
        lm_top_k=0,
        lm_top_p=0.9,
        parse_timesteps=lambda _value: None,
        is_instrumental=lambda _lyrics: False,
        default_dit_instruction=DEFAULT_DIT_INSTRUCTION,
        task_instructions={},
    )
    return setup.params


@unittest.skipIf(build_generation_setup is None, f"import unavailable: {_IMPORT_ERROR}")
class OmittedVocalLanguageTests(unittest.TestCase):
    """An omitted language must leave CoT detection free to fill it in."""

    def test_omitted_language_parses_as_none(self):
        """The request model preserves absence rather than defaulting to "en"."""
        self.assertIsNone(_request({"prompt": "a punjabi song"}).vocal_language)

    def test_omitted_language_allows_cot_detection(self):
        """Regression: omitting the field must not pin generation to English."""
        params = _params({"prompt": "a punjabi song"}, use_cot_language=True)

        self.assertTrue(
            _is_vocal_language_unset(params.vocal_language),
            f"omitted language resolved to {params.vocal_language!r}, which blocks "
            "CoT detection and pins non-English prompts to English",
        )

    def test_omitted_language_without_cot_keeps_english_default(self):
        """With detection disabled nothing would fill it, so "en" is kept."""
        params = _params({"prompt": "a song"}, use_cot_language=False)

        self.assertEqual(params.vocal_language, "en")


@unittest.skipIf(build_generation_setup is None, f"import unavailable: {_IMPORT_ERROR}")
class ExplicitVocalLanguageTests(unittest.TestCase):
    """An explicitly supplied language must be preserved against detection."""

    def test_explicit_english_is_preserved(self):
        """The case the previous revision could not express."""
        params = _params({"vocal_language": "en"}, use_cot_language=True)

        self.assertEqual(params.vocal_language, "en")
        self.assertFalse(
            _is_vocal_language_unset(params.vocal_language),
            "an explicit 'en' must not be replaced by a conflicting CoT detection",
        )

    def test_explicit_non_english_is_preserved(self):
        """The original bug: a requested language survives to generation."""
        for code in ("pa", "hi", "ur"):
            with self.subTest(vocal_language=code):
                params = _params({"vocal_language": code}, use_cot_language=True)
                self.assertEqual(params.vocal_language, code)
                self.assertFalse(_is_vocal_language_unset(params.vocal_language))

    def test_explicit_language_accepted_through_aliases(self):
        """camelCase and bare 'language' are aliases and must behave the same."""
        for key in ("vocal_language", "vocalLanguage", "language"):
            with self.subTest(key=key):
                params = _params({key: "pa"}, use_cot_language=True)
                self.assertEqual(params.vocal_language, "pa")

    def test_explicit_placeholder_still_allows_detection(self):
        """An explicit "unknown" names no language, so detection may proceed."""
        params = _params({"vocal_language": "unknown"}, use_cot_language=True)

        self.assertTrue(_is_vocal_language_unset(params.vocal_language))


if __name__ == "__main__":
    unittest.main()
