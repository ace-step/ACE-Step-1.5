"""Unit tests for release-task request-model builder helpers."""

import unittest
from types import SimpleNamespace

from acestep.api.http.release_task_request_builder import build_generate_music_request


class _FakeParser:
    """Minimal parser stub exposing typed accessors used by request builder."""

    def __init__(self, values: dict) -> None:
        """Store deterministic key/value pairs for parser methods."""

        self._values = values

    def get(self, key: str):
        """Return raw value for ``key`` from parser payload."""

        return self._values.get(key)

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


if __name__ == "__main__":
    unittest.main()
