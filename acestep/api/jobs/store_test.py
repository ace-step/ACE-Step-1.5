"""Unit tests for API job store state tracking and persistence helpers."""

import json
import os
import time
import unittest
from pathlib import Path
from unittest import mock

from acestep.api.jobs.store import _JobStore, _append_jsonl, _atomic_write_json

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPO_TMP_ROOT = _REPO_ROOT / "acestep" / "api" / "jobs"


class JobStoreTests(unittest.TestCase):
    """Tests for queue/job lifecycle behavior in the in-memory store."""

    def test_create_mark_running_mark_succeeded_updates_state(self):
        """Store should transition job state through queued->running->succeeded."""

        store = _JobStore()
        store.create_with_id("job-1")

        queued = store.get("job-1")
        self.assertIsNotNone(queued)
        self.assertEqual("queued", queued.status)

        store.mark_running("job-1")
        running = store.get("job-1")
        self.assertEqual("running", running.status)
        self.assertIsNotNone(running.started_at)
        self.assertGreaterEqual(running.progress, 0.01)

        result = {"audio_paths": ["a.wav"]}
        store.mark_succeeded("job-1", result=result)
        succeeded = store.get("job-1")
        self.assertEqual("succeeded", succeeded.status)
        self.assertEqual(result, succeeded.result)
        self.assertEqual(1.0, succeeded.progress)

        stats = store.get_stats()
        self.assertEqual(1, stats["total"])
        self.assertEqual(1, stats["succeeded"])

    def test_cleanup_old_jobs_removes_only_completed_jobs(self):
        """Cleanup should remove stale finished jobs while preserving queued jobs."""

        store = _JobStore()
        store.create_with_id("queued")
        store.create_with_id("failed")
        store.mark_failed("failed", error="boom")

        failed = store.get("failed")
        failed.finished_at = time.time() - 10

        removed = store.cleanup_old_jobs(max_age_seconds=1)

        self.assertEqual(1, removed)
        self.assertIsNotNone(store.get("queued"))
        self.assertIsNone(store.get("failed"))

    def test_update_progress_clamps_values_and_ignores_missing_jobs(self):
        """Progress updates should clamp to [0,1] and no-op for unknown IDs."""

        store = _JobStore()
        store.create_with_id("job-2")

        store.update_progress("job-2", 2.0, stage="running")
        high = store.get("job-2")
        self.assertEqual(1.0, high.progress)
        self.assertEqual("running", high.stage)

        store.update_progress("job-2", -1.0)
        low = store.get("job-2")
        self.assertEqual(0.0, low.progress)

        store.update_progress("missing", 0.5)


class JobStorePersistenceTests(unittest.TestCase):
    """Tests for JSON and JSONL helper functions used by job persistence."""

    def test_atomic_write_json_uses_atomic_replace_flow(self):
        """Atomic write should write+flush+fsync and then replace target path."""

        target_path = str(_REPO_TMP_ROOT / "record.json")
        payload = {"id": "job-1", "status": "running"}
        fake_fd = 101
        fake_tmp_path = str(_REPO_TMP_ROOT / ".tmp_record.json")

        fake_file = mock.MagicMock()
        fake_file.__enter__.return_value = fake_file
        fake_file.fileno.return_value = 202

        with mock.patch("acestep.api.jobs.store.tempfile.mkstemp", return_value=(fake_fd, fake_tmp_path)) as mkstemp_mock, \
             mock.patch("acestep.api.jobs.store.os.fdopen", return_value=fake_file) as fdopen_mock, \
             mock.patch("acestep.api.jobs.store.json.dump") as dump_mock, \
             mock.patch("acestep.api.jobs.store.os.fsync") as fsync_mock, \
             mock.patch("acestep.api.jobs.store.os.replace") as replace_mock:
            _atomic_write_json(target_path, payload)

        mkstemp_mock.assert_called_once()
        fdopen_mock.assert_called_once_with(fake_fd, "w", encoding="utf-8")
        dump_mock.assert_called_once()
        fsync_mock.assert_called_once_with(202)
        replace_mock.assert_called_once_with(fake_tmp_path, target_path)

    def test_append_jsonl_writes_one_json_line_per_record(self):
        """JSONL append should serialize each record with a newline terminator."""

        target_path = str(_REPO_TMP_ROOT / "events.jsonl")
        first = {"event": "queued"}
        expected = json.dumps(first, ensure_ascii=False) + "\n"

        fake_file = mock.MagicMock()
        fake_file.__enter__.return_value = fake_file

        with mock.patch("acestep.api.jobs.store.open", return_value=fake_file, create=True) as open_mock:
            _append_jsonl(target_path, first)

        open_mock.assert_called_once_with(target_path, "a", encoding="utf-8")
        fake_file.write.assert_called_once_with(expected)


if __name__ == "__main__":
    unittest.main()
