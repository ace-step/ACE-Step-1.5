"""Regression tests for LRC cache ownership after session-artifact recovery."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import torch

from acestep.ui.gradio.events.results.lrc_utils import generate_lrc_handler
from acestep.ui.gradio.events.results.session_artifacts import (
    persist_sample_session_artifacts,
)


class LrcSessionSampleTests(unittest.TestCase):
    """Keep the selected result slot separate from a restored tensor's index."""

    def test_persisted_lrc_updates_selected_sample(self) -> None:
        """Restoring one sample must preserve every other song's cached lyrics."""
        for sample_idx in (1, 2, 8):
            with self.subTest(sample_idx=sample_idx):
                self._check_selected_sample(sample_idx, use_artifact=True)

    def test_in_memory_lrc_updates_selected_sample(self) -> None:
        """The original in-memory batch path must keep using the selected sample."""
        for sample_idx in (1, 2, 8):
            with self.subTest(sample_idx=sample_idx):
                self._check_selected_sample(sample_idx, use_artifact=False)

    def test_restored_lrc_initializes_selected_cache_slot(self) -> None:
        """New LRC and subtitle lists must also populate the requested slot."""
        self._check_selected_sample(2, use_artifact=True, existing_cache=False)

    def _check_selected_sample(
        self, sample_idx: int, *, use_artifact: bool, existing_cache: bool = True
    ) -> None:
        """Invoke the real handler with a batch or a persisted CPU artifact."""
        extra_outputs = {
            "pred_latents": torch.arange(96, dtype=torch.float32).reshape(8, 3, 4),
            "encoder_hidden_states": torch.arange(160, dtype=torch.float32).reshape(8, 5, 4),
            "encoder_attention_mask": torch.ones(8, 5),
            "context_latents": torch.arange(96, dtype=torch.float32).reshape(8, 3, 4),
            "lyric_token_idss": torch.arange(40, dtype=torch.long).reshape(8, 5),
        }
        cached_lrcs = [f"Existing lyrics {i}" for i in range(8)] if existing_cache else [""] * 8
        cached_subtitles = [f"existing-{i}.vtt" for i in range(8)] if existing_cache else [None] * 8
        batch_data = {
            "extra_outputs": {} if use_artifact else extra_outputs,
            "generation_params": {"audio_duration": 3.0},
        }
        if existing_cache:
            batch_data.update(lrcs=cached_lrcs.copy(), subtitles=cached_subtitles.copy())
        batch_queue = {0: batch_data}
        lrc_text = f"[00:00.00] Lyrics for sample {sample_idx}"
        dit_handler = MagicMock()
        dit_handler.get_lyric_timestamp.return_value = {"success": True, "lrc_text": lrc_text}

        with tempfile.TemporaryDirectory() as tmp:
            audio_paths = [str(Path(tmp) / f"sample-{i}.wav") for i in range(8)]
            batch_data["audio_paths"] = audio_paths
            if use_artifact:
                json_path = Path(audio_paths[sample_idx - 1]).with_suffix(".json")
                audio_params = {}
                persist_sample_session_artifacts(
                    extra_outputs, sample_idx - 1, str(json_path), audio_params
                )
                json_path.write_text(json.dumps(audio_params), encoding="utf-8")
            with (
                patch(
                    "acestep.gpu_config.get_global_gpu_config",
                    return_value=SimpleNamespace(save_memory_mode=use_artifact),
                ),
                patch(
                    "acestep.ui.gradio.events.results.lrc_utils.lrc_to_vtt_file",
                    return_value="selected.vtt",
                ),
            ):
                update, _, returned_queue = generate_lrc_handler(
                    dit_handler, sample_idx, 0, batch_queue, "en", 8
                )

        self.assertIs(returned_queue, batch_queue)
        self.assertEqual(update["value"], lrc_text)
        call_kwargs = dit_handler.get_lyric_timestamp.call_args.kwargs
        for argument, key in (
            ("pred_latent", "pred_latents"),
            ("encoder_hidden_states", "encoder_hidden_states"),
            ("encoder_attention_mask", "encoder_attention_mask"),
            ("context_latents", "context_latents"),
            ("lyric_token_ids", "lyric_token_idss"),
        ):
            self.assertTrue(
                torch.equal(call_kwargs[argument], extra_outputs[key][sample_idx - 1:sample_idx])
            )
        cached_lrcs[sample_idx - 1] = lrc_text
        cached_subtitles[sample_idx - 1] = "selected.vtt"
        self.assertEqual(batch_data["lrcs"], cached_lrcs)
        self.assertEqual(batch_data["subtitles"], cached_subtitles)


if __name__ == "__main__":
    unittest.main()
