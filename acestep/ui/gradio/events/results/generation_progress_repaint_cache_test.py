"""Tests for generated repaint-source latent persistence."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from acestep.ui.gradio.events.results.generation_progress import (
    _extract_repaint_source_latents,
    _persist_repaint_source_latents,
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


if __name__ == "__main__":
    unittest.main()
