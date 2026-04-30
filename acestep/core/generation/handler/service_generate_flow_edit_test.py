"""Unit tests for the flow-edit overlay dispatch (#1156).

The overlay is a sampler-level technique layered on cover/cover-nofsq:
the user's ``caption`` / ``lyrics`` are the *target*; the overlay adds a
*source* branch encoded from ``flow_edit_source_caption`` /
``flow_edit_source_lyrics``.  V_delta = V_tar - V_src is integrated by
:mod:`flow_edit_pipeline`.
"""

import unittest

import torch

from acestep.core.generation.handler.service_generate_flow_edit import (
    dispatch_flow_edit_overlay,
)
from acestep.core.generation.handler._flow_edit_dispatch_test_support import (
    FakeHandler,
    make_flow_edit_ctx,
    make_payload,
)


class FlowEditOverlayDispatchTests(unittest.TestCase):

    def test_calls_flowedit_with_paired_conditions(self):
        handler = FakeHandler()
        payload = make_payload()
        dispatch_flow_edit_overlay(
            handler, payload=payload, generate_kwargs={"infer_steps": 4},
            seed_param=42, flow_edit_ctx=make_flow_edit_ctx(),
        )
        self.assertEqual(handler.model.flowedit_generate_audio.call_count, 1)
        call_kwargs = handler.model.flowedit_generate_audio.call_args.kwargs
        # Target side comes from payload (the user's caption/lyrics).
        self.assertIs(call_kwargs["target_text_hidden_states"], payload["text_hidden_states"])
        self.assertIs(call_kwargs["target_lyric_hidden_states"], payload["lyric_hidden_states"])
        # Source side was built fresh from flow_edit_source_caption/lyrics.
        self.assertIsNotNone(call_kwargs["text_hidden_states"])
        self.assertIsNotNone(call_kwargs["lyric_hidden_states"])
        # Window params propagated under the model's edit_n_* kwargs.
        self.assertEqual(call_kwargs["edit_n_min"], 0.2)
        self.assertEqual(call_kwargs["edit_n_max"], 0.8)
        self.assertEqual(call_kwargs["edit_n_avg"], 1)
        self.assertEqual(call_kwargs["seed"], 42)

    def test_source_caption_lyrics_threaded_into_tokenizer(self):
        handler = FakeHandler()
        ctx = make_flow_edit_ctx(source_caption="orig anime pop",
                                 source_lyrics="orig lyrics text")
        dispatch_flow_edit_overlay(
            handler, payload=make_payload(), generate_kwargs={"infer_steps": 4},
            seed_param=None, flow_edit_ctx=ctx,
        )
        self.assertIn("orig anime pop", handler.captured_captions)
        self.assertIn("orig lyrics text", handler.captured_lyrics)

    def test_returns_prepare_condition_tensors_for_downstream(self):
        handler = FakeHandler()
        outputs, enc_hs, enc_am, ctx = dispatch_flow_edit_overlay(
            handler, payload=make_payload(), generate_kwargs={"infer_steps": 4},
            seed_param=None, flow_edit_ctx=make_flow_edit_ctx(),
        )
        self.assertIn("target_latents", outputs)
        self.assertIs(enc_hs, handler.prepared_enc_hs)
        self.assertIs(enc_am, handler.prepared_enc_am)
        self.assertIs(ctx, handler.prepared_ctx)

    def test_missing_flowedit_method_raises(self):
        handler = FakeHandler(model_has_flowedit=False)
        with self.assertRaises(RuntimeError) as cm:
            dispatch_flow_edit_overlay(
                handler, payload=make_payload(),
                generate_kwargs={"infer_steps": 4}, seed_param=None,
                flow_edit_ctx=make_flow_edit_ctx(),
            )
        self.assertIn("flowedit_generate_audio", str(cm.exception))

    def test_token_ids_moved_to_handler_device(self):
        handler = FakeHandler()
        captured_device = []

        def _capture(ids):
            captured_device.append(ids.device)
            return torch.zeros(ids.shape[0], ids.shape[1], 16)

        handler.infer_text_embeddings = _capture
        handler.infer_lyric_embeddings = _capture
        dispatch_flow_edit_overlay(
            handler, payload=make_payload(), generate_kwargs={"infer_steps": 4},
            seed_param=None, flow_edit_ctx=make_flow_edit_ctx(),
        )
        self.assertEqual(len(captured_device), 2)
        for d in captured_device:
            self.assertEqual(d, handler.device)

    def test_default_window_params_when_missing(self):
        handler = FakeHandler()
        dispatch_flow_edit_overlay(
            handler, payload=make_payload(), generate_kwargs={"infer_steps": 4},
            seed_param=None, flow_edit_ctx={"morph": True, "task_type": "text2music"},
        )
        kwargs = handler.model.flowedit_generate_audio.call_args.kwargs
        self.assertEqual(kwargs["edit_n_min"], 0.0)
        self.assertEqual(kwargs["edit_n_max"], 1.0)
        self.assertEqual(kwargs["edit_n_avg"], 1)

    def test_dict_metas_parsed_before_tokenization(self):
        handler = FakeHandler()
        ctx = make_flow_edit_ctx()
        ctx["metas"] = [{"bpm": 120, "key": "C minor"}]
        dispatch_flow_edit_overlay(
            handler, payload=make_payload(), generate_kwargs={"infer_steps": 4},
            seed_param=None, flow_edit_ctx=ctx,
        )
        self.assertTrue(any(
            isinstance(m, str) and m.startswith("PARSED:")
            for m in handler.captured_parsed_metas
        ), f"source metas were not parsed: {handler.captured_parsed_metas}")

    def test_retake_seed_forwarded_from_generate_kwargs(self):
        handler = FakeHandler()
        dispatch_flow_edit_overlay(
            handler, payload=make_payload(),
            generate_kwargs={"infer_steps": 4, "retake_seed": [99, 100]},
            seed_param=42, flow_edit_ctx=make_flow_edit_ctx(),
        )
        kwargs = handler.model.flowedit_generate_audio.call_args.kwargs
        self.assertEqual(kwargs["seed"], 42)
        self.assertEqual(kwargs["retake_seed"], [99, 100])


class CoverStillRunsLmTests(unittest.TestCase):
    """The overlay layers on cover; cover stays in skip_lm_tasks (LM Phase 1
    skipped because cover already extracts codes from the ref audio)."""

    def test_no_edit_in_skip_lm_tasks(self):
        from pathlib import Path
        src = (Path(__file__).resolve().parents[3] / "inference.py").read_text()
        self.assertIn(
            'skip_lm_tasks = {"cover", "cover-nofsq", "repaint", "extract"}',
            src,
            "edit task is removed; skip_lm_tasks should no longer mention it",
        )
        self.assertNotIn('"edit"', src.split("skip_lm_tasks")[1].split("\n")[0])


if __name__ == "__main__":
    unittest.main()
