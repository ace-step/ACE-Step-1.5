"""Tests for cached repaint-source latent loading."""

import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

from acestep.inference import (
    _load_cached_repaint_source,
    _load_cached_repaint_source_latents,
    _resample_matching_source_seeds,
)


class RepaintCacheLoadTests(unittest.TestCase):
    """Verify repaint source latent sidecar loading."""

    def test_missing_sidecar_returns_none(self):
        """Uploaded audio without a generated sidecar should use the normal path."""
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(_load_cached_repaint_source_latents(str(Path(tmp) / "upload.wav")))

    def test_loads_relative_latent_file_from_sidecar(self):
        """Generated sidecars should resolve relative cached latent paths."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio_path = root / "sample.wav"
            audio_path.write_bytes(b"")
            np.save(root / "sample.repaint_latents.npy", np.ones((4, 3), dtype=np.float32))
            (root / "sample.json").write_text(
                json.dumps({"repaint_source_latents_file": "sample.repaint_latents.npy"}),
                encoding="utf-8",
            )

            latents = _load_cached_repaint_source_latents(str(audio_path))

            self.assertIsNotNone(latents)
            self.assertEqual((4, 3), tuple(latents.shape))

    def test_loads_source_seed_from_sidecar(self):
        """Generated-source cache should expose the original generation seed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio_path = root / "sample.wav"
            audio_path.write_bytes(b"")
            np.save(root / "sample.repaint_latents.npy", np.ones((4, 3), dtype=np.float32))
            (root / "sample.json").write_text(
                json.dumps({
                    "repaint_source_latents_file": "sample.repaint_latents.npy",
                    "seed": 123,
                }),
                encoding="utf-8",
            )

            cached_source = _load_cached_repaint_source(str(audio_path))

            self.assertIsNotNone(cached_source)
            self.assertEqual(123, cached_source.source_seed)

    def test_resample_matching_source_seed_only_changes_collisions(self):
        """Cached-source repaint should avoid reusing the original generation seed."""
        seeds = _resample_matching_source_seeds([1, 2, 3], source_seed=2)

        self.assertEqual(1, seeds[0])
        self.assertEqual(3, seeds[2])
        self.assertNotEqual(2, seeds[1])

    def test_loads_sidecar_from_gradio_outputs_by_audio_basename(self):
        """Gradio temp audio paths should resolve back to generated output sidecars."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "gradio_outputs" / "batch_123"
            output_dir.mkdir(parents=True)
            np.save(output_dir / "sample.repaint_latents.npy", np.ones((4, 3), dtype=np.float32))
            (output_dir / "sample.json").write_text(
                json.dumps({"repaint_source_latents_file": "sample.repaint_latents.npy"}),
                encoding="utf-8",
            )
            old_cwd = os.getcwd()
            try:
                os.chdir(root)
                latents = _load_cached_repaint_source_latents(str(root / "tmp" / "sample.mp3"))
            finally:
                os.chdir(old_cwd)

            self.assertIsNotNone(latents)
            self.assertEqual((4, 3), tuple(latents.shape))

    def test_gradio_output_sidecar_search_uses_literal_latest_match(self):
        """Generated sidecar fallback should escape glob chars and prefer newest output."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            older_dir = root / "gradio_outputs" / "batch_1"
            newer_dir = root / "gradio_outputs" / "batch_2"
            older_dir.mkdir(parents=True)
            newer_dir.mkdir(parents=True)
            for directory, value in [(older_dir, 1.0), (newer_dir, 2.0)]:
                np.save(
                    directory / "sample[1].repaint_latents.npy",
                    np.full((2, 2), value, dtype=np.float32),
                )
                (directory / "sample[1].json").write_text(
                    json.dumps({"repaint_source_latents_file": "sample[1].repaint_latents.npy"}),
                    encoding="utf-8",
                )
            os.utime(older_dir / "sample[1].json", (1, 1))
            os.utime(newer_dir / "sample[1].json", (2, 2))
            old_cwd = os.getcwd()
            try:
                os.chdir(root)
                latents = _load_cached_repaint_source_latents(str(root / "tmp" / "sample[1].mp3"))
            finally:
                os.chdir(old_cwd)

            self.assertIsNotNone(latents)
            self.assertEqual(2.0, float(latents[0, 0]))


if __name__ == "__main__":
    unittest.main()
