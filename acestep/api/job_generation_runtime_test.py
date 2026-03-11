"""Unit tests for generation runtime execution helper."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from acestep.api.job_generation_runtime import run_generation_with_optional_sequential_cover_mode


class JobGenerationRuntimeTests(unittest.TestCase):
    """Behavior tests for sequential generation and aggregation logic."""

    def test_runs_once_when_not_mps_cover(self) -> None:
        """Non-MPS/cover mode should invoke generation once with original batch size."""

        req = SimpleNamespace(task_type="text2music")
        config = SimpleNamespace(batch_size=2)
        result = SimpleNamespace(success=True, audios=[{"audio_path": "a.wav"}], error=None, status_message="")
        generate_music_fn = MagicMock(return_value=result)
        progress_cb = MagicMock()

        out = run_generation_with_optional_sequential_cover_mode(
            req=req,
            job_id="job-1",
            handler_device="cuda",
            config=config,
            params=SimpleNamespace(),
            dit_handler=MagicMock(),
            llm_handler=MagicMock(),
            temp_audio_dir="tmp",
            generate_music_fn=generate_music_fn,
            progress_cb=progress_cb,
            log_fn=MagicMock(),
        )

        self.assertIs(out, result)
        self.assertEqual(1, generate_music_fn.call_count)
        self.assertEqual(2, config.batch_size)

    def test_splits_cover_mps_batch_into_sequential_runs(self) -> None:
        """MPS cover mode should run sequentially and aggregate audios."""

        req = SimpleNamespace(task_type="cover")
        config = SimpleNamespace(batch_size=2)
        result1 = SimpleNamespace(success=True, audios=[{"audio_path": "a.wav"}], error=None, status_message="")
        result2 = SimpleNamespace(success=True, audios=[{"audio_path": "b.wav"}], error=None, status_message="")
        generate_music_fn = MagicMock(side_effect=[result1, result2])
        progress_cb = MagicMock()
        log_fn = MagicMock()

        out = run_generation_with_optional_sequential_cover_mode(
            req=req,
            job_id="job-2",
            handler_device="mps",
            config=config,
            params=SimpleNamespace(),
            dit_handler=MagicMock(),
            llm_handler=MagicMock(),
            temp_audio_dir="tmp",
            generate_music_fn=generate_music_fn,
            progress_cb=progress_cb,
            log_fn=log_fn,
        )

        self.assertEqual(2, generate_music_fn.call_count)
        self.assertEqual(1, config.batch_size)
        self.assertEqual(2, len(out.audios))
        self.assertTrue(any("Sequential cover run" in str(call.args[0]) for call in log_fn.call_args_list))

    def test_raises_when_generation_fails(self) -> None:
        """Generation failure should raise with original error message format."""

        req = SimpleNamespace(task_type="text2music")
        config = SimpleNamespace(batch_size=1)
        result = SimpleNamespace(success=False, audios=[], error="boom", status_message="")
        generate_music_fn = MagicMock(return_value=result)

        with self.assertRaisesRegex(RuntimeError, "Music generation failed: boom"):
            run_generation_with_optional_sequential_cover_mode(
                req=req,
                job_id="job-3",
                handler_device="cuda",
                config=config,
                params=SimpleNamespace(),
                dit_handler=MagicMock(),
                llm_handler=MagicMock(),
                temp_audio_dir="tmp",
                generate_music_fn=generate_music_fn,
                progress_cb=MagicMock(),
                log_fn=MagicMock(),
            )


if __name__ == "__main__":
    unittest.main()
