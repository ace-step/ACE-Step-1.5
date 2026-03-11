"""Unit tests for ``generate_with_batch_management`` wrapper behavior."""

import inspect
import unittest
from unittest.mock import patch

from _batch_management_test_support import build_progress_result
from _batch_management_test_support import load_batch_management_module


def _build_call_kwargs(module):
    """Build complete kwargs for ``generate_with_batch_management``."""
    kwargs = {}
    for name in list(inspect.signature(module.generate_with_batch_management).parameters)[2:]:
        if name == "progress":
            continue
        if name == "batch_size_input":
            kwargs[name] = 2
        elif name in ("allow_lm_batch", "auto_lrc", "autogen_checkbox", "auto_score"):
            kwargs[name] = False
        elif name == "current_batch_index":
            kwargs[name] = 0
        elif name == "total_batches":
            kwargs[name] = 0
        elif name in ("batch_queue", "generation_params_state"):
            kwargs[name] = {}
        elif name == "complete_track_classes":
            kwargs[name] = []
        else:
            kwargs[name] = None
    return kwargs


class BatchManagementWrapperTests(unittest.TestCase):
    """Tests for streaming and final wrapper output mapping."""

    def test_non_windows_streams_partial_and_final_outputs(self):
        """Non-Windows path should emit partial UI updates plus final state."""
        module, state = load_batch_management_module(is_windows=False)

        def _gen(*_args, **_kwargs):
            """Yield one standard progress result for wrapper streaming."""
            yield build_progress_result(length=48)

        kwargs = _build_call_kwargs(module)
        with patch.dict(module.generate_with_batch_management.__globals__, {"generate_with_progress": _gen}):
            outputs = list(module.generate_with_batch_management(None, None, **kwargs))

        self.assertEqual(len(outputs), 2)
        self.assertEqual(len(outputs[0]), 55)
        self.assertEqual(len(outputs[1]), 55)
        self.assertEqual(outputs[0][0]["playback_position"], 0)
        self.assertEqual(outputs[1][0]["playback_position"], 0)
        self.assertEqual(len(state["store_calls"]), 1)

    def test_windows_emits_only_final_output(self):
        """Windows path should skip intermediate yields and emit final state only."""
        module, _state = load_batch_management_module(is_windows=True)

        def _gen(*_args, **_kwargs):
            """Yield one standard progress result for Windows final-output path."""
            yield build_progress_result(length=48)

        kwargs = _build_call_kwargs(module)
        with patch.dict(module.generate_with_batch_management.__globals__, {"generate_with_progress": _gen}):
            outputs = list(module.generate_with_batch_management(None, None, **kwargs))

        self.assertEqual(len(outputs), 1)
        self.assertEqual(len(outputs[0]), 55)
        self.assertEqual(outputs[0][0]["playback_position"], 0)

    def test_all_audio_paths_none_skips_batch_storage(self):
        """When inner result has no audio paths, wrapper should not store a batch."""
        module, state = load_batch_management_module(is_windows=False)

        def _gen(*_args, **_kwargs):
            """Yield a result with no audio paths to trigger early return."""
            yield build_progress_result(length=48, all_audio_paths=None)

        kwargs = _build_call_kwargs(module)
        with patch.dict(module.generate_with_batch_management.__globals__, {"generate_with_progress": _gen}):
            outputs = list(module.generate_with_batch_management(None, None, **kwargs))

        self.assertEqual(len(outputs), 2)
        self.assertEqual(outputs[1][8], None)
        self.assertEqual(len(state["store_calls"]), 0)

    def test_allow_lm_batch_stores_multiple_codes(self):
        """Batch mode should store a list of generated codes up to batch size."""
        module, state = load_batch_management_module(is_windows=False)

        def _gen(*_args, **_kwargs):
            """Yield a result carrying a list of generated codes."""
            result = list(build_progress_result(length=48))
            result[47] = [f"code-{idx}" for idx in range(8)]
            yield tuple(result)

        kwargs = _build_call_kwargs(module)
        kwargs["allow_lm_batch"] = True
        kwargs["batch_size_input"] = 3
        with patch.dict(module.generate_with_batch_management.__globals__, {"generate_with_progress": _gen}):
            list(module.generate_with_batch_management(None, None, **kwargs))

        self.assertEqual(state["store_calls"][0]["codes"], ["code-0", "code-1", "code-2"])

    def test_auto_lrc_copies_lrc_fields_to_batch_queue(self):
        """Auto-LRC mode should copy LRC/subtitle payloads into stored queue entry."""
        module, _state = load_batch_management_module(is_windows=False)

        lrcs = [f"lrc-{idx}" for idx in range(8)]
        subtitles = [f"sub-{idx}" for idx in range(8)]

        def _gen(*_args, **_kwargs):
            """Yield a result with explicit LRC/subtitle payload."""
            result = list(build_progress_result(length=48))
            result[46] = {"lrcs": lrcs, "subtitles": subtitles}
            yield tuple(result)

        kwargs = _build_call_kwargs(module)
        kwargs["auto_lrc"] = True
        outputs = []
        with patch.dict(module.generate_with_batch_management.__globals__, {"generate_with_progress": _gen}):
            outputs = list(module.generate_with_batch_management(None, None, **kwargs))

        final_batch_queue = outputs[-1][48]
        self.assertEqual(final_batch_queue[0]["lrcs"], lrcs)
        self.assertEqual(final_batch_queue[0]["subtitles"], subtitles)

    def test_auto_lrc_sets_lrc_display_in_final_yield(self):
        """Final yield should carry gr.update(value=lrc) at positions 36-43."""
        module, _state = load_batch_management_module(is_windows=False)

        lrcs = [f"[00:01.00]Line {idx}" for idx in range(8)]
        subtitles = [f"sub-{idx}" for idx in range(8)]

        def _gen(*_args, **_kwargs):
            """Yield a result with LRC data in extra_outputs."""
            result = list(build_progress_result(length=48))
            result[46] = {"lrcs": lrcs, "subtitles": subtitles}
            yield tuple(result)

        kwargs = _build_call_kwargs(module)
        kwargs["auto_lrc"] = True
        with patch.dict(module.generate_with_batch_management.__globals__, {"generate_with_progress": _gen}):
            outputs = list(module.generate_with_batch_management(None, None, **kwargs))

        final_yield = outputs[-1]
        for i in range(8):
            lrc_val = final_yield[36 + i]
            self.assertIsInstance(lrc_val, dict, f"LRC position {36 + i} should be a gr.update dict")
            self.assertEqual(
                lrc_val.get("value"), lrcs[i],
                f"LRC position {36 + i} should contain the LRC text",
            )

    def test_auto_lrc_disabled_preserves_passthrough_values(self):
        """When auto_lrc is off, LRC positions pass through from inner generator."""
        module, _state = load_batch_management_module(is_windows=False)

        def _gen(*_args, **_kwargs):
            """Yield a standard result without auto_lrc."""
            yield build_progress_result(length=48)

        kwargs = _build_call_kwargs(module)
        kwargs["auto_lrc"] = False
        with patch.dict(module.generate_with_batch_management.__globals__, {"generate_with_progress": _gen}):
            outputs = list(module.generate_with_batch_management(None, None, **kwargs))

        final_yield = outputs[-1]
        for i in range(8):
            lrc_val = final_yield[36 + i]
            self.assertIsNone(lrc_val, f"LRC position {36 + i} should be None when auto_lrc is off")

    def test_empty_inner_generator_returns_skip_tuple_and_warning(self):
        """Empty inner generator should fail gracefully without indexing None."""
        module, state = load_batch_management_module(is_windows=False)

        def _gen(*_args, **_kwargs):
            """Yield nothing to simulate a defensive empty-generator edge case."""
            if False:
                yield None

        kwargs = _build_call_kwargs(module)
        with patch.dict(module.generate_with_batch_management.__globals__, {"generate_with_progress": _gen}):
            outputs = list(module.generate_with_batch_management(None, None, **kwargs))

        self.assertEqual(len(outputs), 1)
        self.assertEqual(len(outputs[0]), 55)
        self.assertTrue(all(item.get("kind") == "skip" for item in outputs[0]))
        self.assertEqual(len(state["store_calls"]), 0)
        self.assertTrue(state["warning_messages"])
        self.assertIn("messages.batch_failed", state["warning_messages"][0])


if __name__ == "__main__":
    unittest.main()
