"""Unit tests for release-task request-model builder helpers."""

import unittest
from types import SimpleNamespace
from typing import Any

from acestep.api.http.release_task_request_builder import (
    _default_inference_steps_for_model,
    _has_model_token,
    build_generate_music_request,
)


class _FakeParser:
    """Minimal parser stub exposing typed accessors used by request builder."""

    def __init__(self, values: dict) -> None:
        """Store deterministic key/value pairs for parser methods."""

        self._values = values

    def get(self, key: str, default: Any = None):
        """Return raw value for ``key`` from parser payload."""

        return self._values.get(key, default)

    def str(self, key: str, default: str = "") -> str:
        """Return string value for ``key`` with default fallback."""

        value = self._values.get(key, default)
        return default if value is None else str(value)

    def bool(self, key: str, default: bool = False) -> bool:
        """Return boolean value for ``key`` with default fallback."""

        value = self._values.get(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    def int(self, key: str, default=None):
        """Return integer value for ``key`` with default fallback."""

        value = self._values.get(key, default)
        return default if value is None else int(value)

    def float(self, key: str, default=None):
        """Return float value for ``key`` with default fallback."""

        value = self._values.get(key, default)
        return default if value is None else float(value)


class ReleaseTaskRequestBuilderTests(unittest.TestCase):
    """Behavior tests for request-building helper used by `/release_task`."""

    def test_build_request_converts_track_classes_string_to_list(self):
        """Builder should normalize single-string track class to one-item list."""

        parser = _FakeParser(
            {
                "prompt": "hello",
                "track_classes": "vocals",
                "use_random_seed": True,
            }
        )
        request = build_generate_music_request(
            parser=parser,
            request_model_cls=lambda **kwargs: SimpleNamespace(**kwargs),
            default_dit_instruction="default-instruction",
            lm_default_temperature=0.85,
            lm_default_cfg_scale=2.5,
            lm_default_top_p=0.9,
        )

        self.assertEqual("hello", request.prompt)
        self.assertEqual(["vocals"], request.track_classes)
        self.assertEqual("default-instruction", request.instruction)

    def test_build_request_prefers_explicit_audio_path_overrides(self):
        """Builder should prioritize explicit path overrides over parser fields."""

        parser = _FakeParser(
            {
                "reference_audio_path": "from-parser-ref.wav",
                "src_audio_path": "from-parser-src.wav",
            }
        )
        request = build_generate_music_request(
            parser=parser,
            request_model_cls=lambda **kwargs: SimpleNamespace(**kwargs),
            default_dit_instruction="default-instruction",
            lm_default_temperature=0.85,
            lm_default_cfg_scale=2.5,
            lm_default_top_p=0.9,
            reference_audio_path="override-ref.wav",
            src_audio_path="override-src.wav",
        )

        self.assertEqual("override-ref.wav", request.reference_audio_path)
        self.assertEqual("override-src.wav", request.src_audio_path)

    def test_build_request_allows_generic_overrides_without_kwarg_collision(self):
        """Builder should allow overrides for any field without duplicate-kwarg errors."""

        parser = _FakeParser({"prompt": "from-parser", "lyrics": "from-parser"})
        request = build_generate_music_request(
            parser=parser,
            request_model_cls=lambda **kwargs: SimpleNamespace(**kwargs),
            default_dit_instruction="default-instruction",
            lm_default_temperature=0.85,
            lm_default_cfg_scale=2.5,
            lm_default_top_p=0.9,
            prompt="from-override",
            lyrics="override-lyrics",
        )

        self.assertEqual("from-override", request.prompt)
        self.assertEqual("override-lyrics", request.lyrics)

    def test_build_request_forwards_audio_code_string_and_cover_noise_strength(self):
        """Builder should include audio_code_string and cover_noise_strength in payload."""

        parser = _FakeParser(
            {
                "audio_code_string": "<|audio_code_7|>",
                "cover_noise_strength": 0.6,
            }
        )
        request = build_generate_music_request(
            parser=parser,
            request_model_cls=lambda **kwargs: SimpleNamespace(**kwargs),
            default_dit_instruction="default-instruction",
            lm_default_temperature=0.85,
            lm_default_cfg_scale=2.5,
            lm_default_top_p=0.9,
        )

        self.assertEqual("<|audio_code_7|>", request.audio_code_string)
        self.assertAlmostEqual(0.6, request.cover_noise_strength)

    def test_build_request_defaults_sft_model_to_50_steps(self):
        """SFT model requests should default to 50 inference steps when omitted."""

        parser = _FakeParser({"model": "acestep-v15-xl-sft"})
        request = build_generate_music_request(
            parser=parser,
            request_model_cls=lambda **kwargs: SimpleNamespace(**kwargs),
            default_dit_instruction="default-instruction",
            lm_default_temperature=0.85,
            lm_default_cfg_scale=2.5,
            lm_default_top_p=0.9,
        )

        self.assertEqual(50, request.inference_steps)

    def test_build_request_defaults_turbo_model_to_8_steps(self):
        """Turbo model requests should keep 8-step default when omitted."""

        parser = _FakeParser({"model": "acestep-v15-xl-turbo"})
        request = build_generate_music_request(
            parser=parser,
            request_model_cls=lambda **kwargs: SimpleNamespace(**kwargs),
            default_dit_instruction="default-instruction",
            lm_default_temperature=0.85,
            lm_default_cfg_scale=2.5,
            lm_default_top_p=0.9,
        )

        self.assertEqual(8, request.inference_steps)

    def test_build_request_defaults_base_model_to_32_steps(self):
        """Explicit non-turbo/non-sft models should default to 32 steps."""

        parser = _FakeParser({"model": "acestep-v15-base"})
        request = build_generate_music_request(
            parser=parser,
            request_model_cls=lambda **kwargs: SimpleNamespace(**kwargs),
            default_dit_instruction="default-instruction",
            lm_default_temperature=0.85,
            lm_default_cfg_scale=2.5,
            lm_default_top_p=0.9,
        )

        self.assertEqual(32, request.inference_steps)

    def test_build_request_defaults_unspecified_model_to_legacy_8_steps(self):
        """Missing model field should keep the historical API default of 8."""

        parser = _FakeParser({})
        request = build_generate_music_request(
            parser=parser,
            request_model_cls=lambda **kwargs: SimpleNamespace(**kwargs),
            default_dit_instruction="default-instruction",
            lm_default_temperature=0.85,
            lm_default_cfg_scale=2.5,
            lm_default_top_p=0.9,
        )

        self.assertEqual(8, request.inference_steps)


class ReleaseTaskRequestBuilderModelDefaultTests(unittest.TestCase):
    """Coverage for model-token parsing and per-model step defaults."""

    def test_token_matching_uses_word_boundaries(self):
        """Delimiter-bound token matching should reject partial words."""

        self.assertTrue(_has_model_token("turbo", "acestep-v15-xl-turbo"))
        self.assertTrue(_has_model_token("turbo", "turbo"))
        self.assertFalse(_has_model_token("turbo", "turbocharged"))
        self.assertFalse(_has_model_token("turbo", "not-turbulent"))

    def test_default_steps_handle_none_empty_and_case_insensitive(self):
        """Default step resolver should be case-insensitive and robust to empty names."""

        self.assertEqual(8, _default_inference_steps_for_model(None))
        self.assertEqual(8, _default_inference_steps_for_model(""))
        self.assertEqual(50, _default_inference_steps_for_model("ACESTEP-V15-XL-SFT"))
        self.assertEqual(8, _default_inference_steps_for_model("ACESTEP-V15-XL-TURBO"))

    def test_default_steps_prioritize_turbo_over_sft(self):
        """Turbo token should take precedence when both turbo and sft appear."""

        self.assertEqual(8, _default_inference_steps_for_model("acestep-v15-turbo-sft"))


if __name__ == "__main__":
    unittest.main()
