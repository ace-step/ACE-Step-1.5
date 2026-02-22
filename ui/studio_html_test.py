"""Unit tests for studio HTML audio volume persistence guards."""

from pathlib import Path
import unittest


class StudioHtmlVolumeGuardTests(unittest.TestCase):
    """Tests for trusted-event gating in studio volume persistence logic."""

    @classmethod
    def setUpClass(cls):
        """Load studio HTML content once for all assertions."""
        cls._html = Path(__file__).with_name("studio.html").read_text(encoding="utf-8")

    def test_contains_trusted_event_helper(self):
        """Success path: trusted-event helper should exist."""
        self.assertIn("function isTrustedUserEvent(event)", self._html)
        self.assertIn("event && event.isTrusted", self._html)

    def test_volumechange_listener_guards_non_trusted_events(self):
        """Regression path: listener should reject non-user volumechange events."""
        self.assertIn("audioEl.addEventListener('volumechange', (event) => {", self._html)
        self.assertIn("if (!isTrustedUserEvent(event)) {", self._html)
        self.assertIn("applyPreferredVolumeToAudio(audioEl);", self._html)


if __name__ == "__main__":
    unittest.main()
