"""Tests for result-audio transfer helpers."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from acestep.ui.gradio.events.results.audio_transfer import (
    convert_result_audio_to_codes,
    send_audio_to_repaint,
)


class SendAudioToRepaintTests(unittest.TestCase):
    """Verify generated-source repaint transfer behavior."""

    def test_send_to_repaint_resets_seed_to_random(self):
        """Generated-source repaint should not reuse the source generation seed."""
        updates = send_audio_to_repaint(
            audio_file="/tmp/generated.wav",
            lm_metadata={"lyrics": "new words", "caption": "new caption"},
            current_lyrics="old words",
            current_caption="old caption",
            current_mode="Custom",
            llm_handler=None,
        )

        self.assertEqual("/tmp/generated.wav", updates[0])
        self.assertEqual(True, updates[6]["value"])
        self.assertEqual("-1", updates[7]["value"])


class ConvertResultAudioToCodesTests(unittest.TestCase):
    """Verify generated audio code conversion can reuse sidecar metadata."""

    def test_convert_uses_generated_sidecar_codes_without_model(self):
        """A generated JSON sidecar avoids re-encoding audio through the VAE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / "generated.wav"
            audio_path.with_suffix(".json").write_text(
                json.dumps({"audio_codes": "cached-codes"}),
                encoding="utf-8",
            )

            with patch("gradio.Info"):
                codes_update, accordion_update = convert_result_audio_to_codes(None, str(audio_path))

            self.assertEqual("cached-codes", codes_update["value"])
            self.assertTrue(accordion_update["open"])

    def test_convert_falls_back_to_handler_without_sidecar_codes(self):
        """Uploaded or uncached audio still uses the existing conversion path."""
        handler = MagicMock()
        handler.model = object()
        handler.convert_src_audio_to_codes.return_value = "fresh-codes"

        with tempfile.TemporaryDirectory() as tmpdir, patch("gradio.Info"):
            audio_path = Path(tmpdir) / "uploaded.wav"
            codes_update, _accordion_update = convert_result_audio_to_codes(handler, str(audio_path))

        self.assertEqual("fresh-codes", codes_update["value"])
        handler.convert_src_audio_to_codes.assert_called_once_with(str(audio_path))


if __name__ == "__main__":
    unittest.main()
