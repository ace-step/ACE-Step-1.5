"""Unit tests for local-cache job payload update helpers."""

import unittest
from types import SimpleNamespace

from acestep.api.jobs.local_cache_updates import (
    update_local_cache,
    update_local_cache_progress,
)


def _map_status(status: str) -> int:
    """Map text status to legacy integer status used by API responses."""

    return {"queued": 0, "running": 0, "succeeded": 1, "failed": 2}.get(status, 2)


class _FakeLocalCache:
    """Capture local-cache set calls for deterministic assertions."""

    def __init__(self) -> None:
        """Initialize an empty call log."""

        self.calls = []

    def set(self, key: str, value, ex: int) -> None:
        """Record one cache write call."""

        self.calls.append((key, value, ex))


class _FakeStore:
    """Return preconfigured records by job id."""

    def __init__(self, records: dict[str, object] | None = None) -> None:
        """Store test records in memory."""

        self._records = records or {}

    def get(self, job_id: str):
        """Return record for job id or None when missing."""

        return self._records.get(job_id)


class LocalCacheUpdatesTests(unittest.TestCase):
    """Behavior tests for local cache update helpers."""

    def test_update_local_cache_writes_full_analysis_payload(self):
        """Full-analysis success payload should be cached unchanged inside list wrapper."""

        cache = _FakeLocalCache()
        store = _FakeStore({"job-1": SimpleNamespace(created_at=123.0, env="development")})
        result = {"status_message": "Full Hardware Analysis Success", "analysis": "ok"}

        update_local_cache(
            local_cache=cache,
            store=store,
            job_id="job-1",
            result=result,
            status="succeeded",
            map_status=_map_status,
            result_key_prefix="prefix:",
            result_expire_seconds=600,
        )

        self.assertEqual(1, len(cache.calls))
        key, payload, ttl = cache.calls[0]
        self.assertEqual("prefix:job-1", key)
        self.assertEqual(600, ttl)
        self.assertEqual([result], payload)

    def test_update_local_cache_writes_success_audio_payload(self):
        """Succeeded payload should include transformed audio entries and preserved metadata fields."""

        cache = _FakeLocalCache()
        store = _FakeStore({"job-2": SimpleNamespace(created_at=200.0, env="development")})
        result = {
            "audio_paths": ["a.mp3", "b.mp3"],
            "prompt": "final prompt",
            "lyrics": "final lyrics",
            "metas": {
                "bpm": 120,
                "duration": 8.0,
                "genres": "pop",
                "keyscale": "C",
                "timesignature": "4/4",
                "prompt": "original prompt",
                "lyrics": "original lyrics",
            },
            "generation_info": "info",
            "seed_value": "42",
            "lm_model": "lm-model",
            "dit_model": "dit-model",
        }

        update_local_cache(
            local_cache=cache,
            store=store,
            job_id="job-2",
            result=result,
            status="succeeded",
            map_status=_map_status,
            result_key_prefix="prefix:",
            result_expire_seconds=600,
        )

        _, payload, _ = cache.calls[0]
        self.assertEqual(2, len(payload))
        self.assertEqual("a.mp3", payload[0]["file"])
        self.assertEqual("final prompt", payload[0]["prompt"])
        self.assertEqual("original prompt", payload[0]["metas"]["prompt"])
        self.assertEqual(1.0, payload[0]["progress"])
        self.assertEqual("succeeded", payload[0]["stage"])

    def test_update_local_cache_writes_failed_payload(self):
        """Failed status should emit failed stage with zero progress."""

        cache = _FakeLocalCache()
        store = _FakeStore({"job-3": SimpleNamespace(created_at=300.0, env="development")})

        update_local_cache(
            local_cache=cache,
            store=store,
            job_id="job-3",
            result=None,
            status="failed",
            map_status=_map_status,
            result_key_prefix="prefix:",
            result_expire_seconds=600,
        )

        _, payload, _ = cache.calls[0]
        self.assertEqual(2, payload[0]["status"])
        self.assertEqual(0.0, payload[0]["progress"])
        self.assertEqual("failed", payload[0]["stage"])

    def test_update_local_cache_progress_writes_running_payload(self):
        """Progress updates should write running payload with provided stage and progress value."""

        cache = _FakeLocalCache()
        store = _FakeStore({"job-4": SimpleNamespace(created_at=400.0, env="development")})

        update_local_cache_progress(
            local_cache=cache,
            store=store,
            job_id="job-4",
            progress=0.25,
            stage="running",
            map_status=_map_status,
            result_key_prefix="prefix:",
            result_expire_seconds=600,
        )

        _, payload, _ = cache.calls[0]
        self.assertEqual(0, payload[0]["status"])
        self.assertEqual(0.25, payload[0]["progress"])
        self.assertEqual("running", payload[0]["stage"])

    def test_update_helpers_are_noop_without_local_cache(self):
        """Update helpers should return without writes when local cache backend is absent."""

        store = _FakeStore({"job-5": SimpleNamespace(created_at=500.0, env="development")})

        update_local_cache(
            local_cache=None,
            store=store,
            job_id="job-5",
            result={"audio_paths": []},
            status="succeeded",
            map_status=_map_status,
            result_key_prefix="prefix:",
            result_expire_seconds=600,
        )
        update_local_cache_progress(
            local_cache=None,
            store=store,
            job_id="job-5",
            progress=0.1,
            stage="running",
            map_status=_map_status,
            result_key_prefix="prefix:",
            result_expire_seconds=600,
        )


if __name__ == "__main__":
    unittest.main()
