"""Tests for generated repaint-source latent persistence."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import torch

from acestep.ui.gradio.events.results.generation_progress import (
    _extract_repaint_source_latents,
    _persist_repaint_source_latents,
    _run_auto_lrc,
    _strip_extra_output_tensors,
)


class RepaintSourceLatentPersistenceTests(unittest.TestCase):
    """Verify generated audio sidecars get a reusable repaint latent pointer."""

    def test_persist_repaint_source_latents_writes_file_and_updates_params(self):
        """The helper should store generated latents beside the sidecar JSON."""
        audio_params = {}
        with tempfile.TemporaryDirectory() as tmp:
            json_path = str(Path(tmp) / "sample.json")

            _persist_repaint_source_latents(
                source_latents=torch.ones(4, 3),
                json_path=json_path,
                audio_params=audio_params,
            )

            latent_name = audio_params["repaint_source_latents_file"]
            latent_path = Path(tmp) / latent_name
            self.assertTrue(latent_path.exists())
            self.assertEqual((4, 3), np.load(latent_path).shape)

    def test_extract_repaint_source_latents_uses_pred_latents_sample(self):
        """The persisted source should come from DiT pred_latents, not audio."""
        pred_latents = torch.arange(24, dtype=torch.float32).reshape(2, 4, 3)

        sample = _extract_repaint_source_latents({"pred_latents": pred_latents}, 1)

        torch.testing.assert_close(sample, pred_latents[1])

    def test_strip_extra_output_tensors_preserves_metadata(self):
        """Batch queue storage should keep metadata but not large tensors."""
        stripped = _strip_extra_output_tensors({
            "pred_latents": torch.ones(1, 2, 3),
            "seed_value": "123",
            "lrcs": ["[00:00.00] hello"],
        })

        self.assertNotIn("pred_latents", stripped)
        self.assertEqual("123", stripped["seed_value"])
        self.assertEqual(["[00:00.00] hello"], stripped["lrcs"])

    def test_run_auto_lrc_forwards_output_dir_to_vtt_generation(self):
        """Auto-LRC should persist VTT files in the provided batch output directory."""
        dit_handler = MagicMock()
        dit_handler.get_lyric_timestamp.return_value = {
            "success": True,
            "lrc_text": "[00:00.00] hello",
        }
        extra_outputs = {
            "pred_latents": torch.ones(1, 50, 4),
            "encoder_hidden_states": torch.ones(1, 2, 4),
            "encoder_attention_mask": torch.ones(1, 2),
            "context_latents": torch.ones(1, 2, 4),
            "lyric_token_idss": torch.ones(1, 2, dtype=torch.long),
        }
        lrcs = [""] * 8
        subtitles = [None] * 8

        with patch(
            "acestep.ui.gradio.events.results.generation_progress.lrc_to_vtt_file",
            return_value="/tmp/auto.vtt",
        ) as mock_lrc_to_vtt_file:
            _run_auto_lrc(
                dit_handler=dit_handler,
                extra_outputs=extra_outputs,
                sample_idx=0,
                audio_duration=3.0,
                vocal_language="en",
                inference_steps=8,
                final_lrcs_list=lrcs,
                final_subtitles_list=subtitles,
                output_dir="/tmp/batch_123",
            )

        self.assertEqual("[00:00.00] hello", lrcs[0])
        self.assertEqual("/tmp/auto.vtt", subtitles[0])
        self.assertEqual("/tmp/batch_123", mock_lrc_to_vtt_file.call_args.kwargs["output_dir"])


if __name__ == "__main__":
    unittest.main()
