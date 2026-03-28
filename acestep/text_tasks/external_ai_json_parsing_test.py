"""Tests for external AI JSON parsing fallbacks."""

from __future__ import annotations

import unittest

from acestep.text_tasks.external_ai_json_parsing import (
    extract_balanced_json_objects,
    extract_json_block,
    load_plan_json_object,
    repair_json_candidate,
)


class ExternalAIJsonParsingTests(unittest.TestCase):
    """Verify non-JSON but labelled provider replies can still be parsed."""

    def test_load_plan_json_object_accepts_labelled_plain_text(self) -> None:
        """Plain labelled text should fall back into a usable plan object."""

        parsed = load_plan_json_object(
            """
            Caption: Dreamy synth-pop with neon city atmosphere
            Lyrics: City lights / carry me home
            BPM: 118
            Duration: 30
            Key Scale: C Major
            Time Signature: 4/4
            Vocal Language: en
            Instrumental: false
            """
        )

        self.assertEqual(parsed["caption"], "Dreamy synth-pop with neon city atmosphere")
        self.assertEqual(parsed["lyrics"], "City lights / carry me home")
        self.assertEqual(parsed["bpm"], "118")
        self.assertEqual(parsed["key_scale"], "C Major")

    def test_extract_balanced_json_objects_handles_nested_content(self) -> None:
        """Balanced extraction should preserve nested objects and quoted braces."""

        candidates = extract_balanced_json_objects(
            'prefix {"caption":"A {bright} glow","meta":{"bpm":118,"tags":["night"]}} suffix'
        )

        self.assertEqual(
            candidates,
            ['{"caption":"A {bright} glow","meta":{"bpm":118,"tags":["night"]}}'],
        )

    def test_repair_json_candidate_strips_trailing_commas(self) -> None:
        """Simple repair should remove trailing commas before closing braces."""

        repaired = repair_json_candidate('{"caption":"Glow", "bpm":118,}')

        self.assertEqual(repaired, '{"caption":"Glow", "bpm":118}')

    def test_extract_json_block_prefers_fenced_json(self) -> None:
        """Fenced JSON blocks should be extracted before looser brace spans."""

        block = extract_json_block(
            "ignored\n```json\n{\"caption\": \"Neon skyline\", \"bpm\": 118}\n```\ntrailer"
        )

        self.assertEqual(block, '{"caption": "Neon skyline", "bpm": 118}')

    def test_extract_json_block_returns_first_balanced_object_when_multiple_exist(self) -> None:
        """Loose brace fallback should not greedily merge multiple JSON objects."""

        block = extract_json_block(
            'preface {"caption":"Neon skyline"} bridge {"caption":"Night drive"} trailer'
        )

        self.assertEqual(block, '{"caption":"Neon skyline"}')

    def test_load_plan_json_object_accepts_multiline_lyrics_in_labelled_text(self) -> None:
        """Labelled-field fallback should keep multiline lyrics intact."""

        parsed = load_plan_json_object(
            """
            Caption: Dreamy synth-pop with neon city atmosphere
            Lyrics: City lights / carry me home
            We stay awake until the morning glow
            BPM: 118
            Duration: 30
            """
        )

        self.assertIn("City lights / carry me home", parsed["lyrics"])
        self.assertIn("We stay awake until the morning glow", parsed["lyrics"])
        self.assertEqual(parsed["bpm"], "118")

    def test_load_plan_json_object_accepts_runtime_alias_labels(self) -> None:
        """Runtime alias labels without underscores should map to canonical JSON keys."""

        parsed = load_plan_json_object(
            """
            Caption: Dreamy synth-pop with neon city atmosphere
            KeyScale: C Major
            TimeSignature: 4/4
            VocalLanguage: en
            """
        )

        self.assertEqual(parsed["key_scale"], "C Major")
        self.assertEqual(parsed["time_signature"], "4/4")
        self.assertEqual(parsed["vocal_language"], "en")

    def test_load_plan_json_object_accepts_hyphenated_alias_labels(self) -> None:
        """Hyphenated labelled aliases should normalize into the canonical keys."""

        parsed = load_plan_json_object(
            """
            Caption: Dreamy synth-pop with neon city atmosphere
            Key-Scale: C Major
            Time-Signature: 4/4
            Vocal-Language: en
            """
        )

        self.assertEqual(parsed["key_scale"], "C Major")
        self.assertEqual(parsed["time_signature"], "4/4")
        self.assertEqual(parsed["vocal_language"], "en")


if __name__ == "__main__":
    unittest.main()
