"""Shared unittest fakes for API job helper tests."""

from __future__ import annotations

from typing import Any, Optional


class _FakeJobQueue:
    """Track task completion calls made by worker helper."""

    def __init__(self) -> None:
        """Initialize task_done call counter."""

        self.task_done_calls = 0

    def task_done(self) -> None:
        """Record one task completion."""

        self.task_done_calls += 1


class _FakeStore:
    """In-memory store stub for worker helper tests."""

    def __init__(self, record: Optional[Any] = None) -> None:
        """Initialize store with optional record."""

        self.record = record
        self.mark_failed_calls = []
        self.cleanup_returns = [0]
        self.cleanup_call_count = 0
        self.stats = {"total": 0}

    def get(self, _job_id: str) -> Any:
        """Return configured record."""

        return self.record

    def mark_failed(self, job_id: str, error: str) -> None:
        """Record mark_failed invocations."""

        self.mark_failed_calls.append((job_id, error))
        if self.record is not None:
            self.record.status = "failed"
            self.record.error = error

    def cleanup_old_jobs(self) -> int:
        """Return deterministic cleanup counts for each invocation."""

        index = min(self.cleanup_call_count, len(self.cleanup_returns) - 1)
        self.cleanup_call_count += 1
        result = self.cleanup_returns[index]
        if isinstance(result, Exception):
            raise result
        return int(result)

    def get_stats(self) -> dict[str, int]:
        """Return deterministic stats payload."""

        return self.stats


class _DoneEvent:
    """Simple event stub tracking whether set() was called."""

    def __init__(self) -> None:
        """Initialize unset event state."""

        self.was_set = False

    def set(self) -> None:
        """Mark event as set."""

        self.was_set = True
