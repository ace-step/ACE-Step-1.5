"""Unit tests for shared API server utility helpers."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from acestep.api.server_utils import (
    env_bool,
    get_model_name,
    is_instrumental,
    map_status,
    parse_description_hints,
    parse_timesteps,
)


class ServerUtilsTests(unittest.TestCase):
    """Behavior tests for server utility parsing and normalization helpers."""

    def test_parse_description_hints_detects_language_and_instrumental(self) -> None:
        """Description parser should detect language and instrumental hints."""

        language, instrumental = parse_description_hints("Epic rock in English solo")
        self.assertEqual("en", language)
        self.assertTrue(instrumental)

    def test_parse_description_hints_empty_input(self) -> None:
        """Description parser should default to no hints for empty input."""

        language, instrumental = parse_description_hints("")
        self.assertIsNone(language)
        self.assertFalse(instrumental)

    def test_parse_description_hints_detects_unicode_language_aliases(self) -> None:
        """Description parser should support non-ASCII language aliases."""

        language, instrumental = parse_description_hints("抒情流行 中文")
        self.assertEqual("zh", language)
        self.assertFalse(instrumental)

    def test_env_bool_uses_truthy_values_and_default(self) -> None:
        """Boolean env parser should support legacy truthy values and default fallback."""

        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(env_bool("NOT_SET", True))
            self.assertFalse(env_bool("NOT_SET", False))

        with patch.dict(os.environ, {"FLAG": "yes"}, clear=True):
            self.assertTrue(env_bool("FLAG", False))

    def test_get_model_name_normalizes_trailing_separators(self) -> None:
        """Model-name parser should return final path segment."""

        self.assertEqual("acestep-v15-turbo", get_model_name("acestep-v15-turbo"))
        self.assertEqual("acestep-v15-turbo", get_model_name("/models/acestep-v15-turbo/"))

    def test_map_status_returns_legacy_integer_codes(self) -> None:
        """Status mapper should preserve legacy integer API mapping."""

        self.assertEqual(0, map_status("queued"))
        self.assertEqual(0, map_status("running"))
        self.assertEqual(1, map_status("succeeded"))
        self.assertEqual(2, map_status("failed"))
        self.assertEqual(2, map_status("unknown"))

    def test_parse_timesteps_parses_valid_and_rejects_invalid(self) -> None:
        """Timesteps parser should parse float lists and return None on invalid input."""

        self.assertEqual([0.5, 0.25, 0.0], parse_timesteps("0.5, 0.25, 0"))
        self.assertIsNone(parse_timesteps("x,0.2"))

    def test_is_instrumental_preserves_legacy_markers(self) -> None:
        """Instrumental detector should match empty/marker lyrics behavior."""

        self.assertTrue(is_instrumental(""))
        self.assertTrue(is_instrumental("  [inst] "))
        self.assertFalse(is_instrumental("hello world"))


if __name__ == "__main__":
    unittest.main()
