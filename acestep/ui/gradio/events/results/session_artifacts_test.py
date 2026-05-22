"""Tests for generated-session artifact persistence."""

import json
import os
import tempfile
import unittest
from pathlib import Path

import torch

from acestep.ui.gradio.events.results.session_artifacts import (
    ARTIFACT_KIND,
    get_audio_codes_from_sidecar,
    load_batch_sample_session_tensors,
    load_session_artifacts,
    persist_sample_session_artifacts,
)


class SessionArtifactsTests(unittest.TestCase):
    """Verify session artifact sidecars can restore generated tensors."""

    def test_persist_and_load_session_artifact(self):
        """A complete tensor set is persisted and loaded from the audio sidecar."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "sample.json"
            audio_path = Path(tmpdir) / "sample.wav"
            audio_params = {"audio_codes": "<|audio_code_1|>"}
            extra_outputs = self._extra_outputs()

            persist_sample_session_artifacts(extra_outputs, 1, str(json_path), audio_params)
            json_path.write_text(json.dumps(audio_params), encoding="utf-8")

            self.assertEqual(ARTIFACT_KIND, audio_params["session_artifact_kind"])
            self.assertTrue((Path(tmpdir) / audio_params["session_artifact_file"]).exists())

            loaded = load_session_artifacts(audio_path)
            self.assertIsNotNone(loaded)
            self.assertTrue(torch.equal(loaded["pred_latents"], extra_outputs["pred_latents"][1:2]))
            self.assertTrue(
                torch.equal(loaded["lyric_token_ids"], extra_outputs["lyric_token_idss"][1:2])
            )

    def test_load_batch_sample_session_tensors_uses_audio_index(self):
        """Batch lookup ignores JSON entries and loads the selected audio sample."""
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_paths = []
            extra_outputs = self._extra_outputs()
            for index, key in enumerate(["one", "two"]):
                json_path = Path(tmpdir) / f"{key}.json"
                audio_path = Path(tmpdir) / f"{key}.wav"
                audio_params = {}
                persist_sample_session_artifacts(extra_outputs, index, str(json_path), audio_params)
                json_path.write_text(json.dumps(audio_params), encoding="utf-8")
                audio_paths.extend([str(audio_path), str(json_path)])

            loaded = load_batch_sample_session_tensors({"audio_paths": audio_paths}, 2)

            self.assertIsNotNone(loaded)
            self.assertTrue(torch.equal(loaded["pred_latents"], extra_outputs["pred_latents"][1:2]))

    def test_get_audio_codes_from_sidecar(self):
        """Generated audio codes are read from the JSON sidecar when present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "sample.json"
            audio_path = Path(tmpdir) / "sample.wav"
            json_path.write_text(json.dumps({"audio_codes": "cached-codes"}), encoding="utf-8")

            self.assertEqual("cached-codes", get_audio_codes_from_sidecar(audio_path))

    def test_gradio_output_code_lookup_uses_literal_latest_match(self):
        """Fallback sidecar lookup should escape glob chars and prefer newest JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            older_dir = root / "gradio_outputs" / "batch_1"
            newer_dir = root / "gradio_outputs" / "batch_2"
            older_dir.mkdir(parents=True)
            newer_dir.mkdir(parents=True)
            (older_dir / "sample[1].json").write_text(
                json.dumps({"audio_codes": "older-codes"}),
                encoding="utf-8",
            )
            (newer_dir / "sample[1].json").write_text(
                json.dumps({"audio_codes": "newer-codes"}),
                encoding="utf-8",
            )
            os.utime(older_dir / "sample[1].json", (1, 1))
            os.utime(newer_dir / "sample[1].json", (2, 2))
            old_cwd = os.getcwd()
            try:
                os.chdir(root)
                codes = get_audio_codes_from_sidecar(root / "tmp" / "sample[1].wav")
            finally:
                os.chdir(old_cwd)

            self.assertEqual("newer-codes", codes)

    def test_incomplete_artifact_is_not_recorded(self):
        """Missing required tensors should not expose a session artifact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_params = {}
            persist_sample_session_artifacts({}, 0, str(Path(tmpdir) / "sample.json"), audio_params)

            self.assertNotIn("session_artifact_file", audio_params)

    @staticmethod
    def _extra_outputs():
        return {
            "pred_latents": torch.arange(24, dtype=torch.float32).reshape(2, 3, 4),
            "encoder_hidden_states": torch.arange(40, dtype=torch.float32).reshape(2, 5, 4),
            "encoder_attention_mask": torch.ones(2, 5, dtype=torch.float32),
            "context_latents": torch.arange(24, dtype=torch.float32).reshape(2, 3, 4),
            "lyric_token_idss": torch.arange(10, dtype=torch.long).reshape(2, 5),
        }


if __name__ == "__main__":
    unittest.main()
