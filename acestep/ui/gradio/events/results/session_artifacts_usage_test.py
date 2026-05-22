"""Tests for result actions that recover persisted session artifacts."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import torch

from acestep.ui.gradio.events.results.lrc_utils import generate_lrc_handler
from acestep.ui.gradio.events.results.scoring import calculate_score_handler_with_selection
from acestep.ui.gradio.events.results.session_artifacts import persist_sample_session_artifacts


class SessionArtifactsUsageTests(unittest.TestCase):
    """Verify Score and LRC can use disk artifacts after tensors are cleared."""

    def test_score_uses_session_artifact_when_extra_outputs_are_empty(self):
        """Older batches can still run DiT alignment scoring from disk tensors."""
        batch_queue, extra_outputs = self._batch_queue_with_artifact()
        dit_handler = MagicMock()
        dit_handler.get_lyric_score.return_value = {
            "success": True,
            "lm_score": 0.12,
            "dit_score": 0.34,
        }
        llm_handler = MagicMock()
        llm_handler.llm_initialized = False

        score_update, _accordion, _queue = calculate_score_handler_with_selection(
            dit_handler=dit_handler,
            llm_handler=llm_handler,
            sample_idx=1,
            score_scale=1.0,
            current_batch_index=0,
            batch_queue=batch_queue,
        )

        self.assertIn("DiT Alignment", score_update["value"])
        call_kwargs = dit_handler.get_lyric_score.call_args.kwargs
        self.assertTrue(torch.equal(call_kwargs["pred_latent"], extra_outputs["pred_latents"][0:1]))

    def test_lrc_uses_session_artifact_in_save_memory_mode(self):
        """Persisted tensors allow manual LRC generation after save-memory cleanup."""
        batch_queue, extra_outputs = self._batch_queue_with_artifact()
        dit_handler = MagicMock()
        dit_handler.get_lyric_timestamp.return_value = {
            "success": True,
            "lrc_text": "[00:00.00] hello",
        }

        with (
            patch(
                "acestep.gpu_config.get_global_gpu_config",
                return_value=SimpleNamespace(save_memory_mode=True),
            ),
            patch(
                "acestep.ui.gradio.events.results.lrc_utils.lrc_to_vtt_file",
                return_value="/tmp/test.vtt",
            ),
        ):
            lrc_update, _accordion, updated_queue = generate_lrc_handler(
                dit_handler=dit_handler,
                sample_idx=1,
                current_batch_index=0,
                batch_queue=batch_queue,
                vocal_language="en",
                inference_steps=8,
            )

        self.assertEqual("[00:00.00] hello", lrc_update["value"])
        self.assertEqual("[00:00.00] hello", updated_queue[0]["lrcs"][0])
        call_kwargs = dit_handler.get_lyric_timestamp.call_args.kwargs
        self.assertTrue(torch.equal(call_kwargs["pred_latent"], extra_outputs["pred_latents"][0:1]))

    def _batch_queue_with_artifact(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tmpdir = Path(tmp.name)
        audio_path = tmpdir / "sample.wav"
        json_path = tmpdir / "sample.json"
        audio_params = {}
        extra_outputs = self._extra_outputs()
        persist_sample_session_artifacts(extra_outputs, 0, str(json_path), audio_params)
        json_path.write_text(json.dumps(audio_params), encoding="utf-8")
        batch_queue = {
            0: {
                "audio_paths": [str(audio_path), str(json_path)],
                "extra_outputs": {},
                "generation_params": {
                    "lyrics": "hello",
                    "captions": "song",
                    "audio_duration": 3.0,
                    "vocal_language": "en",
                    "inference_steps": 8,
                },
                "codes": "",
                "allow_lm_batch": False,
                "lm_generated_metadata": {},
            }
        }
        return batch_queue, extra_outputs

    @staticmethod
    def _extra_outputs():
        return {
            "pred_latents": torch.arange(12, dtype=torch.float32).reshape(1, 3, 4),
            "encoder_hidden_states": torch.arange(20, dtype=torch.float32).reshape(1, 5, 4),
            "encoder_attention_mask": torch.ones(1, 5, dtype=torch.float32),
            "context_latents": torch.arange(12, dtype=torch.float32).reshape(1, 3, 4),
            "lyric_token_idss": torch.arange(5, dtype=torch.long).reshape(1, 5),
        }


if __name__ == "__main__":
    unittest.main()
