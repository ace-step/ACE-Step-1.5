"""Unit tests for batch_navigation module.

Focuses on the navigate_to_next_batch guard logic that previously
relied on a potentially stale ``total_batches`` Gradio state value.
"""

import unittest
from unittest.mock import patch, MagicMock


def _make_batch(audio_path="/tmp/audio.flac"):
    """Return a minimal completed batch dict for testing."""
    return {
        "status": "completed",
        "audio_paths": [audio_path],
        "generation_info": "test info",
        "seeds": "42",
        "codes": "",
        "scores": [""] * 8,
        "allow_lm_batch": False,
        "batch_size": 2,
        "generation_params": {},
        "lm_generated_metadata": None,
        "extra_outputs": {},
    }


# Patch Gradio helpers that are unavailable in a headless test environment.
@patch("acestep.ui.gradio.events.results.batch_navigation.gr")
@patch("acestep.ui.gradio.events.results.batch_navigation.t", side_effect=lambda key, **kw: key)
class NavigateToNextBatchTests(unittest.TestCase):
    """Tests for navigate_to_next_batch."""

    def _run_first_yield(self, gen):
        """Advance the generator to its first yield and return the tuple."""
        return next(gen)

    def test_stale_total_batches_allows_navigation(self, _mock_t, mock_gr):
        """Navigation should succeed when batch_queue has the next batch
        even if total_batches state is stale (not yet incremented)."""
        mock_gr.update = MagicMock(side_effect=lambda **kw: ("update", kw))
        mock_gr.skip = MagicMock(return_value="skip")
        mock_gr.Warning = MagicMock()

        from acestep.ui.gradio.events.results.batch_navigation import navigate_to_next_batch

        batch_queue = {0: _make_batch(), 1: _make_batch()}
        # total_batches=1 is stale; actual queue has 2 entries.
        gen = navigate_to_next_batch(
            autogen_enabled=True,
            current_batch_index=0,
            total_batches=1,
            batch_queue=batch_queue,
        )
        result = self._run_first_yield(gen)

        # Should NOT have warned "at_last_batch".
        mock_gr.Warning.assert_not_called()
        # The 11th element (index 10) is the new batch index.
        self.assertEqual(result[10], 1)

    def test_no_next_batch_when_truly_last(self, _mock_t, mock_gr):
        """Warning should fire when there really is no next batch."""
        mock_gr.update = MagicMock(return_value="update")
        mock_gr.Warning = MagicMock()

        from acestep.ui.gradio.events.results.batch_navigation import navigate_to_next_batch

        batch_queue = {0: _make_batch()}
        gen = navigate_to_next_batch(
            autogen_enabled=False,
            current_batch_index=0,
            total_batches=1,
            batch_queue=batch_queue,
        )
        result = self._run_first_yield(gen)

        mock_gr.Warning.assert_called_once()
        # All 49 outputs should be gr.update() no-ops.
        self.assertEqual(len(result), 49)

    def test_batch_not_in_queue(self, _mock_t, mock_gr):
        """Warning should fire when total_batches suggests a next batch
        exists but the queue does not actually contain it."""
        mock_gr.update = MagicMock(return_value="update")
        mock_gr.Warning = MagicMock()

        from acestep.ui.gradio.events.results.batch_navigation import navigate_to_next_batch

        # total_batches=3 but queue only has batch 0.
        batch_queue = {0: _make_batch()}
        gen = navigate_to_next_batch(
            autogen_enabled=False,
            current_batch_index=0,
            total_batches=3,
            batch_queue=batch_queue,
        )
        result = self._run_first_yield(gen)

        mock_gr.Warning.assert_called_once()
        self.assertEqual(len(result), 49)


if __name__ == "__main__":
    unittest.main()
