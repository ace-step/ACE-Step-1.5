"""Unit tests for ``generate_next_batch_background`` behavior."""

import unittest
from unittest.mock import patch

from _batch_management_test_support import build_progress_result
from _batch_management_test_support import load_batch_management_module


class BatchManagementBackgroundTests(unittest.TestCase):
    """Tests for background AutoGen batch generation flow."""

    def test_autogen_disabled_returns_noop_state(self):
        """Disabled AutoGen should not trigger generation or queue mutations."""
        module, _state = load_batch_management_module(is_windows=False)

        result = module.generate_next_batch_background(
            None,
            None,
            autogen_enabled=False,
            generation_params={},
            current_batch_index=0,
            total_batches=1,
            batch_queue={},
            is_format_caption=False,
        )

        self.assertEqual(result[1], 1)
        self.assertEqual(result[2], "")
        self.assertFalse(result[3]["interactive"])

    def test_precompleted_next_batch_returns_ready(self):
        """Already-completed next batch should return ready state immediately."""
        module, _state = load_batch_management_module(is_windows=False)
        batch_queue = {1: {"status": "completed"}}

        result = module.generate_next_batch_background(
            None,
            None,
            autogen_enabled=True,
            generation_params={},
            current_batch_index=0,
            total_batches=1,
            batch_queue=batch_queue,
            is_format_caption=False,
        )

        self.assertEqual(result[1], 2)
        self.assertIn("messages.batch_ready", result[2])
        self.assertTrue(result[3]["interactive"])

    def test_background_generation_success_stores_batch(self):
        """Successful background generation should store next batch and enable next button."""
        module, state = load_batch_management_module(is_windows=False)

        def _gen(*_args, **_kwargs):
            """Yield one synthetic final result for background success path."""
            yield build_progress_result(length=48)

        with patch.dict(module.generate_next_batch_background.__globals__, {"generate_with_progress": _gen}):
            result = module.generate_next_batch_background(
                None,
                None,
                autogen_enabled=True,
                generation_params={"batch_size_input": 2, "allow_lm_batch": False, "auto_lrc": False},
                current_batch_index=0,
                total_batches=1,
                batch_queue={},
                is_format_caption=False,
            )

        self.assertEqual(len(state["store_calls"]), 1)
        self.assertIn(1, result[0])
        self.assertIn("messages.batch_ready", result[2])
        self.assertTrue(result[3]["interactive"])

    def test_background_auto_lrc_copies_lrc_fields(self):
        """Background Auto-LRC should copy LRC/subtitle lists into queue entry."""
        module, _state = load_batch_management_module(is_windows=False)
        lrcs = [f"lrc-{idx}" for idx in range(8)]
        subtitles = [f"sub-{idx}" for idx in range(8)]

        def _gen(*_args, **_kwargs):
            """Yield one result carrying LRC and subtitle lists."""
            result = list(build_progress_result(length=48))
            result[46] = {"lrcs": lrcs, "subtitles": subtitles}
            yield tuple(result)

        with patch.dict(module.generate_next_batch_background.__globals__, {"generate_with_progress": _gen}):
            result = module.generate_next_batch_background(
                None,
                None,
                autogen_enabled=True,
                generation_params={"batch_size_input": 2, "allow_lm_batch": False, "auto_lrc": True},
                current_batch_index=0,
                total_batches=1,
                batch_queue={},
                is_format_caption=False,
            )

        self.assertEqual(result[0][1]["lrcs"], lrcs)
        self.assertEqual(result[0][1]["subtitles"], subtitles)

    def test_background_generation_exception_sets_error_entry(self):
        """Background exceptions should produce warning and mark batch as error."""
        module, state = load_batch_management_module(is_windows=False)

        def _raising_gen(*_args, **_kwargs):
            """Raise to simulate background generation failure."""
            raise RuntimeError("boom")

        with patch.dict(module.generate_next_batch_background.__globals__, {"generate_with_progress": _raising_gen}):
            result = module.generate_next_batch_background(
                None,
                None,
                autogen_enabled=True,
                generation_params={},
                current_batch_index=0,
                total_batches=1,
                batch_queue={},
                is_format_caption=False,
            )

        self.assertIn("messages.batch_failed", result[2])
        self.assertFalse(result[3]["interactive"])
        self.assertEqual(result[0][1]["status"], "error")
        self.assertTrue(state["warning_messages"])

    def test_background_empty_generator_sets_error_entry(self):
        """Empty inner generator should return error state instead of indexing None."""
        module, state = load_batch_management_module(is_windows=False)

        def _empty_gen(*_args, **_kwargs):
            """Yield nothing to simulate empty background generation output."""
            if False:
                yield None

        with patch.dict(module.generate_next_batch_background.__globals__, {"generate_with_progress": _empty_gen}):
            result = module.generate_next_batch_background(
                None,
                None,
                autogen_enabled=True,
                generation_params={},
                current_batch_index=0,
                total_batches=1,
                batch_queue={},
                is_format_caption=False,
            )

        self.assertIn("messages.batch_failed", result[2])
        self.assertFalse(result[3]["interactive"])
        self.assertEqual(result[0][1]["status"], "error")
        self.assertTrue(state["warning_messages"])


if __name__ == "__main__":
    unittest.main()
