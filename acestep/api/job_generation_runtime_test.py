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

    def _run_sequential_cover(self, *, seeds, use_random_seed=False, batch_size=2, task_type="cover"):
        req = SimpleNamespace(task_type=task_type)
        config = SimpleNamespace(batch_size=batch_size, seeds=seeds, use_random_seed=use_random_seed)
        seen_seeds = []

        def _generate(**kwargs):
            cfg = kwargs["config"]
            seen_seeds.append(list(cfg.seeds) if isinstance(cfg.seeds, list) else cfg.seeds)
            return SimpleNamespace(
                success=True,
                audios=[{"audio_path": f"{len(seen_seeds)}.wav"}],
                error=None,
                status_message="",
            )

        out = run_generation_with_optional_sequential_cover_mode(
            req=req,
            job_id="job-seeds",
            handler_device="mps",
            config=config,
            params=SimpleNamespace(),
            dit_handler=MagicMock(),
            llm_handler=MagicMock(),
            temp_audio_dir="tmp",
            generate_music_fn=_generate,
            progress_cb=MagicMock(),
            log_fn=MagicMock(),
        )
        return out, seen_seeds

    def test_sequential_cover_uses_one_seed_per_run(self) -> None:
        """MPS cover runs must consume per-run seeds instead of repeating the first."""

        out, seen_seeds = self._run_sequential_cover(seeds=[111, 222])

        self.assertEqual([[111], [222]], seen_seeds)
        self.assertEqual(2, len(out.audios))

    def test_sequential_cover_pads_missing_seeds_with_none(self) -> None:
        """Runs beyond the provided seed list should fall back to unseeded generation."""

        _, seen_seeds = self._run_sequential_cover(seeds=[111])

        self.assertEqual([111], seen_seeds[0])
        self.assertIsNone(seen_seeds[1])

    def test_sequential_cover_nofsq_uses_one_seed_per_run(self) -> None:
        """cover-nofsq takes the same sequential path and must slice seeds too."""

        _, seen_seeds = self._run_sequential_cover(seeds=[111, 222], task_type="cover-nofsq")

        self.assertEqual([[111], [222]], seen_seeds)

    def test_sequential_cover_ignores_extra_seeds_beyond_batch(self) -> None:
        """Extra seeds past batch_size are dropped, matching batched truncation."""

        _, seen_seeds = self._run_sequential_cover(seeds=[111, 222, 333])

        self.assertEqual([[111], [222]], seen_seeds)

    def test_sequential_cover_random_seed_leaves_seeds_untouched(self) -> None:
        """Random-seed requests should keep the original config value for every run."""

        _, seen_seeds = self._run_sequential_cover(seeds=None, use_random_seed=True)

        self.assertEqual([None, None], seen_seeds)

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
