"""Unit tests for turbo/non-turbo model-name classification."""

from __future__ import annotations

import unittest

from acestep.model_type import is_turbo_model_path


class IsTurboModelPathTests(unittest.TestCase):
    """Behavior tests for is_turbo_model_path."""

    def test_detects_turbo_models(self) -> None:
        self.assertTrue(is_turbo_model_path("acestep-v15-turbo"))
        self.assertTrue(is_turbo_model_path("acestep-v15-xl-turbo"))
        self.assertTrue(is_turbo_model_path("ACESTEP-V15-TURBO"))
        self.assertTrue(is_turbo_model_path("/models/acestep-v15-turbo/config.json"))

    def test_rejects_non_turbo_models(self) -> None:
        self.assertFalse(is_turbo_model_path("acestep-v15-sft"))
        self.assertFalse(is_turbo_model_path("acestep-v15-base"))
        self.assertFalse(is_turbo_model_path("acestep-v15-xl-sft"))
        self.assertFalse(is_turbo_model_path("acestep-v15-xl-base"))

    def test_does_not_match_turbo_as_a_substring(self) -> None:
        self.assertFalse(is_turbo_model_path("acestep-v15-nonturbolike"))

    def test_handles_missing_input(self) -> None:
        self.assertFalse(is_turbo_model_path(None))
        self.assertFalse(is_turbo_model_path(""))


if __name__ == "__main__":
    unittest.main()
