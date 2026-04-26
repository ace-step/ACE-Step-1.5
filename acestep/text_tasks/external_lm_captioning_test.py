"""Tests for external LM caption and metadata helpers."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from acestep.text_tasks.external_lm_captioning import (
    apply_user_metadata_overrides,
    build_fallback_caption,
    build_format_request_intent,
    caption_needs_retry,
)


class ExternalLmCaptioningTests(unittest.TestCase):
    """Verify caption formatting helpers stay deterministic and local."""

    def test_caption_needs_retry_for_unchanged_or_too_short_result(self) -> None:
        """Simple echoes and very short captions should trigger one retry."""

        self.assertTrue(
            caption_needs_retry(
                original_caption="Salsa dura with brass section, call-and-response vocals",
                generated_caption="Salsa dura with brass section, call-and-response vocals",
            )
        )
        self.assertTrue(
            caption_needs_retry(
                original_caption="Progressive trance instrumental",
                generated_caption="Progressive trance instrumental with pads",
            )
        )
        self.assertFalse(
            caption_needs_retry(
                original_caption="Progressive trance instrumental",
                generated_caption=(
                    "A progressive trance instrumental opens with evolving pads and "
                    "arpeggiators, builds through a long breakdown, and resolves in a "
                    "euphoric outro."
                ),
            )
        )

    def test_apply_user_metadata_overrides_preserves_constrained_values(self) -> None:
        """User-supplied metadata should win over provider drift."""

        plan = SimpleNamespace(
            bpm=1,
            duration=2.4,
            keyscale="C minor",
            timesignature="3/4",
            language="English",
        )

        result = apply_user_metadata_overrides(
            plan=plan,
            user_metadata={
                "bpm": "125.0",
                "duration": 240,
                "keyscale": "D major",
                "timesignature": "4/4",
                "language": "es",
            },
        )

        self.assertEqual(result.bpm, 125)
        self.assertEqual(result.duration, 240.0)
        self.assertEqual(result.keyscale, "D major")
        self.assertEqual(result.key_scale, "D major")
        self.assertEqual(result.timesignature, "4/4")
        self.assertEqual(result.time_signature, "4/4")
        self.assertEqual(result.language, "es")
        self.assertEqual(result.vocal_language, "es")

    def test_build_fallback_caption_preserves_literal_braces_in_caption(self) -> None:
        """Literal braces in user captions should pass through the fallback safely."""

        caption = build_fallback_caption(
            caption="Track {remix} edition",
            user_metadata={"bpm": 120},
        )

        self.assertIn("Track {remix} edition", caption)
        self.assertIn("120 BPM", caption)

    def test_build_fallback_caption_uses_prompt_and_metadata(self) -> None:
        """Fallback caption should expand the original prompt into a narrative."""

        caption = build_fallback_caption(
            caption="Salsa dura with brass section, call-and-response vocals, live club energy",
            user_metadata={
                "bpm": 125,
                "duration": 240,
                "keyscale": "D major",
                "timesignature": "4/4",
            },
        )

        self.assertIn("Salsa dura with brass section", caption)
        self.assertIn("125 BPM", caption)
        self.assertIn("4/4", caption)
        self.assertIn("D major", caption)
        self.assertIn("240 seconds", caption)

    def test_build_fallback_caption_falls_back_for_whitespace_input(self) -> None:
        """Whitespace-only captions should fall back to the generic source phrase."""

        caption = build_fallback_caption(
            caption="   ",
            user_metadata={},
        )

        self.assertIn("music piece unfolds", caption)

    def test_build_fallback_caption_localizes_supported_languages(self) -> None:
        """Supported language codes should switch the local fallback prose."""

        caption = build_fallback_caption(
            caption="Dreamy city-pop",
            user_metadata={
                "language": "ja-JP",
                "bpm": 118,
            },
        )

        self.assertIn("Dreamy city-pop", caption)
        self.assertIn("BPM前後", caption)
        self.assertNotIn("The groove stays anchored", caption)

    def test_build_fallback_caption_localizes_zh_and_he_languages(self) -> None:
        """Chinese and Hebrew locale fallbacks should use localized prose too."""

        zh_caption = build_fallback_caption(
            caption="霓虹 city-pop",
            user_metadata={"language": "zh-CN", "bpm": 118},
        )
        he_caption = build_fallback_caption(
            caption="לילה אלקטרוני",
            user_metadata={"language": "he-IL", "bpm": 118},
        )

        self.assertIn("霓虹 city-pop", zh_caption)
        self.assertIn("律动大致稳定在 118 BPM", zh_caption)
        self.assertNotIn("The groove stays anchored", zh_caption)

        self.assertIn("לילה אלקטרוני", he_caption)
        self.assertIn("הגרוב נשאר מעוגן סביב 118 BPM", he_caption)
        self.assertNotIn("The groove stays anchored", he_caption)

    def test_build_fallback_caption_accepts_missing_metadata(self) -> None:
        """Missing user metadata should behave like an empty metadata dict."""

        caption = build_fallback_caption(
            caption="Track {remix} edition",
            user_metadata=None,
        )

        self.assertIn("Track {remix} edition", caption)

    def test_build_format_request_intent_omits_unknown_metadata(self) -> None:
        """Unknown metadata values should not be emitted into the request intent."""

        intent = build_format_request_intent(
            caption="Dreamy synth-pop",
            lyrics="City lights / carry me home",
            user_metadata={
                "bpm": 118,
                "duration": "",
                "keyscale": "C Major",
                "timesignature": "4/4",
                "language": "unknown",
            },
        )

        self.assertIn("Caption: Dreamy synth-pop", intent)
        self.assertIn("Lyrics: City lights / carry me home", intent)
        self.assertIn("bpm: 118", intent)
        self.assertIn("keyscale: C Major", intent)
        self.assertIn("timesignature: 4/4", intent)
        self.assertNotIn("language: unknown", intent)
        self.assertNotIn("duration:", intent)

    def test_build_format_request_intent_normalizes_unknown_string_metadata(self) -> None:
        """Whitespace-padded unknown strings should still be filtered from the intent."""

        intent = build_format_request_intent(
            caption="Dreamy synth-pop",
            lyrics="City lights / carry me home",
            user_metadata={
                "bpm": 118,
                "duration": "  ",
                "keyscale": " C Major ",
                "timesignature": "4/4",
                "language": " Unknown ",
            },
        )

        self.assertIn("bpm: 118", intent)
        self.assertIn("keyscale: C Major", intent)
        self.assertIn("timesignature: 4/4", intent)
        self.assertNotIn("language:", intent)
        self.assertNotIn("duration:", intent)

    def test_build_format_request_intent_filters_other_placeholder_metadata_values(self) -> None:
        """Common placeholder strings should not be emitted into the provider intent."""

        intent = build_format_request_intent(
            caption="Dreamy synth-pop",
            lyrics="City lights / carry me home",
            user_metadata={
                "bpm": "none",
                "duration": "n/a",
                "keyscale": "default",
                "timesignature": "4/4",
                "language": "N/A",
            },
        )

        self.assertIn("timesignature: 4/4", intent)
        self.assertNotIn("bpm:", intent)
        self.assertNotIn("duration:", intent)
        self.assertNotIn("keyscale:", intent)
        self.assertNotIn("language:", intent)

    def test_build_format_request_intent_accepts_missing_metadata(self) -> None:
        """Missing user metadata should behave like an empty metadata dict."""

        intent = build_format_request_intent(
            caption="Dreamy synth-pop",
            lyrics="City lights / carry me home",
            user_metadata=None,
        )

        self.assertIn("Caption: Dreamy synth-pop", intent)
        self.assertIn("Lyrics: City lights / carry me home", intent)


if __name__ == "__main__":
    unittest.main()
