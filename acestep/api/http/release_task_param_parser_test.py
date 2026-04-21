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

    def test_non_dict_param_obj_json_is_ignored(self):
        """Parser should ignore parsed param_obj JSON values that are not dictionaries."""

        parser = RequestParser(
            {
                "param_obj": "[\"not-a-dict\"]",
                "metas": {"caption": "meta-caption"},
            }
        )
        self.assertEqual("meta-caption", parser.str("prompt"))


    def test_sampler_and_dit_param_aliases_are_resolved(self):
        """Parser should resolve camelCase aliases for sampler/DiT params."""

        parser = RequestParser(
            {
                "samplerMode": "heun",
                "velocityNormThreshold": "2.5",
                "latentShift": "0.1",
                "velocityEmaFactor": "0.95",
                "latentRescale": "1.2",
            }
        )
        self.assertEqual("heun", parser.str("sampler_mode"))
        self.assertAlmostEqual(2.5, parser.float("velocity_norm_threshold"))
        self.assertAlmostEqual(0.1, parser.float("latent_shift"))
        self.assertAlmostEqual(0.95, parser.float("velocity_ema_factor"))
        self.assertAlmostEqual(1.2, parser.float("latent_rescale"))

    def test_apg_eta_and_momentum_aliases_are_resolved(self):
        """Parser should resolve eta/momentum APG params from snake_case keys."""

        parser = RequestParser({"eta": "0.5", "momentum": "-0.5"})
        self.assertAlmostEqual(0.5, parser.float("eta"))
        self.assertAlmostEqual(-0.5, parser.float("momentum"))

    def test_apg_eta_and_momentum_resolve_from_nested_param_obj(self):
        """Parser should resolve eta/momentum from nested param_obj payload."""

        parser = RequestParser({"param_obj": {"eta": 0.75, "momentum": -0.9}})
        self.assertAlmostEqual(0.75, parser.float("eta"))
        self.assertAlmostEqual(-0.9, parser.float("momentum"))


if __name__ == "__main__":
    unittest.main()
