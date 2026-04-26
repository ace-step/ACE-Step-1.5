"""Tests for shared external AI plan types."""

from __future__ import annotations

import unittest

from acestep.text_tasks.external_ai_types import ExternalAIPlan


class ExternalAIPlanTests(unittest.TestCase):
    """Verify serialized plan dictionaries expose downstream metadata aliases."""

    def test_to_dict_includes_canonical_metadata_aliases(self) -> None:
        """Serialized plans should include keyscale and timesignature aliases."""

        payload = ExternalAIPlan(
            caption="Glow",
            lyrics="line",
            bpm=118,
            duration=30.0,
            key_scale="C Major",
            time_signature="4/4",
            vocal_language="en",
            instrumental=False,
        ).to_dict()

        self.assertEqual(payload["key_scale"], "C Major")
        self.assertEqual(payload["time_signature"], "4/4")
        self.assertEqual(payload["keyscale"], "C Major")
        self.assertEqual(payload["timesignature"], "4/4")


if __name__ == "__main__":
    unittest.main()
