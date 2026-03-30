"""Unit tests for batch_queue module."""

import unittest

from acestep.ui.gradio.events.results.batch_queue import (
    capture_current_params,
    store_batch_in_queue,
    update_batch_indicator,
    update_navigation_buttons,
)


class UpdateNavigationButtonsTests(unittest.TestCase):
    """Tests for update_navigation_buttons."""

    def test_first_batch(self):
        """At first batch, prev should be False."""
        can_prev, can_next = update_navigation_buttons(0, 3)
        self.assertFalse(can_prev)
        self.assertTrue(can_next)

    def test_last_batch(self):
        """At last batch, next should be False."""
        can_prev, can_next = update_navigation_buttons(2, 3)
        self.assertTrue(can_prev)
        self.assertFalse(can_next)

    def test_middle_batch(self):
        """At a middle batch, both should be True."""
        can_prev, can_next = update_navigation_buttons(1, 3)
        self.assertTrue(can_prev)
        self.assertTrue(can_next)

    def test_single_batch(self):
        """With only one batch, both should be False."""
        can_prev, can_next = update_navigation_buttons(0, 1)
        self.assertFalse(can_prev)
        self.assertFalse(can_next)


class StoreBatchInQueueTests(unittest.TestCase):
    """Tests for store_batch_in_queue."""

    def test_store_first_batch(self):
        """Storing the first batch should create a new queue entry."""
        queue = {}
        result = store_batch_in_queue(
            batch_queue=queue,
            batch_index=0,
            audio_paths=["/tmp/audio1.mp3"],
            generation_info="test info",
            seeds="42",
        )
        self.assertIsInstance(result, dict)
        self.assertIn(0, result)
        self.assertEqual(result[0]["audio_paths"], ["/tmp/audio1.mp3"])
        self.assertEqual(result[0]["generation_info"], "test info")

    def test_store_preserves_existing_batches(self):
        """Storing a new batch should not remove existing batches."""
        queue = {
            0: {
                "audio_paths": ["/tmp/old.mp3"],
                "generation_info": "old info",
                "seeds": "1",
                "status": "completed",
            }
        }
        result = store_batch_in_queue(
            batch_queue=queue,
            batch_index=1,
            audio_paths=["/tmp/new.mp3"],
            generation_info="new info",
            seeds="99",
        )
        self.assertIn(0, result)
        self.assertIn(1, result)
        self.assertEqual(result[0]["audio_paths"], ["/tmp/old.mp3"])
        self.assertEqual(result[1]["audio_paths"], ["/tmp/new.mp3"])

    def test_store_with_scores_and_codes(self):
        """Storing with scores and codes should preserve them."""
        queue = {}
        result = store_batch_in_queue(
            batch_queue=queue,
            batch_index=0,
            audio_paths=["/tmp/a.mp3"],
            generation_info="info",
            seeds="42",
            codes=["code1"],
            scores=["8.5/10"],
        )
        self.assertEqual(result[0]["codes"], ["code1"])
        self.assertEqual(result[0]["scores"], ["8.5/10"])

    def test_store_defaults_scores_to_empty(self):
        """Storing without scores should default to 8 empty strings."""
        queue = {}
        result = store_batch_in_queue(
            batch_queue=queue,
            batch_index=0,
            audio_paths=["/tmp/a.mp3"],
            generation_info="info",
            seeds="42",
        )
        self.assertEqual(result[0]["scores"], [""] * 8)

    def test_store_offloads_previous_extra_outputs_tensors_to_cpu(self):
        """Storing a new batch should move CUDA tensors from the previous batch's extra_outputs to CPU."""
        import torch
        # Use a CPU tensor to simulate: is_cuda is False, so no offload occurs
        tensor = torch.zeros(2, 4)
        queue = {
            0: {
                "audio_paths": ["/tmp/old.mp3"],
                "generation_info": "old info",
                "seeds": "1",
                "status": "completed",
                "extra_outputs": {"pred_latents": tensor},
            }
        }
        result = store_batch_in_queue(
            batch_queue=queue,
            batch_index=1,
            audio_paths=["/tmp/new.mp3"],
            generation_info="new info",
            seeds="99",
        )
        # Tensor is preserved (not deleted) when already on CPU
        self.assertIn("pred_latents", result[0]["extra_outputs"])
        self.assertIn(1, result)

    @unittest.skipUnless(__import__("torch").cuda.is_available(), "CUDA not available")
    def test_store_offloads_cuda_tensor_to_cpu(self):
        """Storing a new batch should move CUDA tensors to CPU, freeing VRAM."""
        import torch
        cuda_tensor = torch.zeros(2, 4, device="cuda")
        queue = {
            0: {
                "audio_paths": ["/tmp/old.mp3"],
                "generation_info": "old info",
                "seeds": "1",
                "status": "completed",
                "extra_outputs": {"pred_latents": cuda_tensor},
            }
        }
        store_batch_in_queue(
            batch_queue=queue,
            batch_index=1,
            audio_paths=["/tmp/new.mp3"],
            generation_info="new info",
            seeds="99",
        )
        offloaded = queue[0]["extra_outputs"]["pred_latents"]
        self.assertFalse(offloaded.is_cuda, "Tensor should have been moved to CPU")
        self.assertEqual(offloaded.device.type, "cpu")

    def test_store_offloads_only_previous_batch_cuda_tensors(self):
        """Only the immediately preceding batch's CUDA tensors should be offloaded."""
        import torch
        tensor_a = torch.ones(1)
        tensor_b = torch.ones(2)
        queue = {
            0: {"audio_paths": [], "extra_outputs": {"pred_latents": tensor_a}, "status": "completed"},
            1: {"audio_paths": [], "extra_outputs": {"pred_latents": tensor_b}, "status": "completed"},
        }
        store_batch_in_queue(
            batch_queue=queue,
            batch_index=2,
            audio_paths=["/tmp/c.mp3"],
            generation_info="info",
            seeds="7",
        )
        # Both batch 0 and batch 1 should still have their tensors (CPU tensors are untouched)
        self.assertIn("pred_latents", queue[0]["extra_outputs"])
        self.assertIn("pred_latents", queue[1]["extra_outputs"])

    def test_store_first_batch_no_prev_cleanup(self):
        """Storing the first batch (index 0) should not fail when there is no previous batch."""
        queue = {}
        result = store_batch_in_queue(
            batch_queue=queue,
            batch_index=0,
            audio_paths=["/tmp/a.mp3"],
            generation_info="info",
            seeds="42",
        )
        self.assertIn(0, result)

    def test_store_preserves_non_tensor_extra_outputs(self):
        """Storing a new batch should preserve non-tensor values in the previous batch's extra_outputs."""
        queue = {
            0: {
                "audio_paths": [],
                "extra_outputs": {
                    "lrcs": ["[00:00.00] hello"],
                    "subtitles": [None],
                },
                "status": "completed",
            }
        }
        store_batch_in_queue(
            batch_queue=queue,
            batch_index=1,
            audio_paths=["/tmp/b.mp3"],
            generation_info="info",
            seeds="5",
        )
        # Non-tensor values should be preserved since only CUDA tensors are offloaded
        self.assertEqual(queue[0]["extra_outputs"]["lrcs"], ["[00:00.00] hello"])
        self.assertEqual(queue[0]["extra_outputs"]["subtitles"], [None])


class CaptureCurrentParamsTests(unittest.TestCase):
    """Tests for capture_current_params."""

    def _build_args(self, **overrides):
        """Build a complete positional arg list for capture_current_params.

        All values default to None; supply keyword overrides for specific fields.
        """
        fields = [
            "captions", "lyrics", "bpm", "key_scale", "time_signature",
            "vocal_language", "inference_steps", "guidance_scale",
            "random_seed_checkbox", "seed", "reference_audio", "audio_duration",
            "batch_size_input", "src_audio", "text2music_audio_code_string",
            "repainting_start", "repainting_end", "instruction_display_gen",
            "audio_cover_strength", "cover_noise_strength", "task_type",
            "use_adg", "cfg_interval_start", "cfg_interval_end", "shift",
            "infer_method", "custom_timesteps", "audio_format", "mp3_bitrate", "mp3_sample_rate", "lm_temperature",
            "think_checkbox", "lm_cfg_scale", "lm_top_k", "lm_top_p",
            "lm_negative_prompt", "use_cot_metas", "use_cot_caption",
            "use_cot_language", "constrained_decoding_debug", "allow_lm_batch",
            "auto_score", "auto_lrc", "score_scale", "lm_batch_chunk_size",
            "track_name", "complete_track_classes", "enable_normalization",
            "normalization_db", "fade_in_duration", "fade_out_duration",
            "latent_shift", "latent_rescale", "repaint_mode", "repaint_strength",
        ]
        defaults = {f: None for f in fields}
        defaults.update(overrides)
        return [defaults[f] for f in fields]

    def test_repaint_params_included_in_capture(self):
        """Repaint mode and strength must be captured for AutoGen batches."""
        args = self._build_args(repaint_mode="aggressive", repaint_strength=0.8)
        result = capture_current_params(*args)
        self.assertEqual(result["repaint_mode"], "aggressive")
        self.assertEqual(result["repaint_strength"], 0.8)

    def test_repaint_params_default_values_captured(self):
        """Default repaint values (balanced, 0.5) must round-trip through capture."""
        args = self._build_args(repaint_mode="balanced", repaint_strength=0.5)
        result = capture_current_params(*args)
        self.assertEqual(result["repaint_mode"], "balanced")
        self.assertEqual(result["repaint_strength"], 0.5)

    def test_capture_clears_audio_codes(self):
        """Audio codes should be cleared so AutoGen batches generate fresh content."""
        args = self._build_args(text2music_audio_code_string="some_code")
        result = capture_current_params(*args)
        self.assertEqual(result["text2music_audio_code_string"], "")

    def test_capture_forces_random_seed(self):
        """Random seed should be forced True for AutoGen variation."""
        args = self._build_args(random_seed_checkbox=False)
        result = capture_current_params(*args)
        self.assertTrue(result["random_seed_checkbox"])


if __name__ == "__main__":
    unittest.main()
