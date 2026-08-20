"""Unit tests for canonical request parameter parsing helpers."""

import unittest

from acestep.api.http.release_task_param_parser import RequestParser


class ReleaseTaskParamParserTests(unittest.TestCase):
    """Behavior tests for alias resolution and typed conversion in RequestParser."""

    def test_get_prefers_primary_raw_payload_values(self):
        """Parser should return raw-body values before nested param/meta objects."""

        parser = RequestParser(
            {
                "caption": "raw-caption",
                "param_obj": {"caption": "param-caption"},
                "metas": {"caption": "meta-caption"},
            }
        )
        self.assertEqual("raw-caption", parser.str("prompt"))

    def test_get_falls_back_to_param_obj_then_metas(self):
        """Parser should resolve aliases from param_obj and then metas when raw missing."""

        parser = RequestParser(
            {
                "param_obj": {"keyScale": "C"},
                "metas": {"timeSignature": "3/4"},
            }
        )
        self.assertEqual("C", parser.str("key_scale"))
        self.assertEqual("3/4", parser.str("time_signature"))

    def test_typed_accessors_apply_legacy_conversion_rules(self):
        """Parser typed methods should preserve prior bool/int/float coercion behavior."""

        parser = RequestParser({"seed": "42", "guidanceScale": "7.25", "useRandomSeed": "yes"})
        self.assertEqual(42, parser.int("seed"))
        self.assertAlmostEqual(7.25, parser.float("guidance_scale"))
        self.assertTrue(parser.bool("use_random_seed"))

    def test_cover_noise_strength_and_audio_code_string_aliases_are_resolved(self):
        """Parser should resolve camelCase aliases for the new fields."""

        parser = RequestParser({"coverNoiseStrength": "0.5", "audioCodeString": "<|code|>"})
        self.assertAlmostEqual(0.5, parser.float("cover_noise_strength"))
        self.assertEqual("<|code|>", parser.str("audio_code_string"))

    def test_audio_codes_alias_resolves_to_audio_code_string(self):
        """Legacy `audio_codes` key should resolve via audio_code_string alias list."""

        parser = RequestParser({"audio_codes": "<|audio_code_42|>"})
        self.assertEqual("<|audio_code_42|>", parser.str("audio_code_string"))

    def test_guidance_variant_and_params_aliases_are_resolved(self):
        """Parser should resolve snake_case and camelCase aliases for guidance fields."""

        parser_snake = RequestParser(
            {"guidance_variant": "adg", "guidance_params": {"angle_clip": 0.52}},
        )
        self.assertEqual("adg", parser_snake.str("guidance_variant"))
        self.assertEqual({"angle_clip": 0.52}, parser_snake.get("guidance_params"))

        parser_camel = RequestParser(
            {"guidanceVariant": "cfg", "guidanceParams": {"eta": 0.1}},
        )
        self.assertEqual("cfg", parser_camel.str("guidance_variant"))
        self.assertEqual({"eta": 0.1}, parser_camel.get("guidance_params"))

    def test_non_dict_param_obj_json_is_ignored(self):
        """Parser should ignore parsed param_obj JSON values that are not dictionaries."""

        parser = RequestParser(
            {
                "param_obj": "[\"not-a-dict\"]",
                "metas": {"caption": "meta-caption"},
            }
        )
        self.assertEqual("meta-caption", parser.str("prompt"))


if __name__ == "__main__":
    unittest.main()
