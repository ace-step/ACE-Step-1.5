"""In-memory job store and JSON persistence helpers for API jobs."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, Literal, Optional
from uuid import uuid4

JobStatus = Literal["queued", "running", "succeeded", "failed"]


@dataclass
class _JobRecord:
    """Internal mutable record stored in the in-memory job store."""
    job_id: str
    status: JobStatus
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    progress_text: str = ""
    status_text: str = ""
    env: str = "development"
    progress: float = 0.0
    stage: str = "queued"
    updated_at: Optional[float] = None
    done_event: Optional[asyncio.Event] = None
    progress_queue: Optional[asyncio.Queue] = None


def _atomic_write_json(path: str, payload: Dict[str, Any]) -> None:
    """Write a JSON document atomically to reduce corruption risk."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=directory or None)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2)
            file_obj.flush()
            os.fsync(file_obj.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise


def _append_jsonl(path: str, record: Dict[str, Any]) -> None:
    """Append a single JSON record as one line in JSONL format."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as file_obj:
        file_obj.write(json.dumps(record, ensure_ascii=False) + "\n")


class _JobStore:
    """Thread-safe in-memory store for queued/running/completed jobs."""

    def __init__(self, max_age_seconds: int = 86400) -> None:
        """Initialize store state and completed-job retention policy."""
        self._lock = Lock()
        self._jobs: Dict[str, _JobRecord] = {}
        self._max_age = max_age_seconds

    def create(self) -> _JobRecord:
        """Create and register a queued job with a generated UUID."""
        job_id = str(uuid4())
        now = time.time()
        record = _JobRecord(
            job_id=job_id,
            status="queued",
            created_at=now,
            progress=0.0,
            stage="queued",
            updated_at=now,
        )
        with self._lock:
            self._jobs[job_id] = record
        return record

    def create_with_id(self, job_id: str, env: str = "development") -> _JobRecord:
        """Create and register a queued job using a caller-provided ID."""
        now = time.time()
        record = _JobRecord(
            job_id=job_id,
            status="queued",
            created_at=now,
            env=env,
            progress=0.0,
            stage="queued",
            updated_at=now,
        )
        with self._lock:
            self._jobs[job_id] = record
        return record

    def get(self, job_id: str) -> Optional[_JobRecord]:
        """Return a job record by ID if present."""
        with self._lock:
            return self._jobs.get(job_id)

    def mark_running(self, job_id: str) -> None:
        """Mark a queued job as running and set timestamps/progress."""
        with self._lock:
            record = self._jobs[job_id]
            record.status = "running"
            record.started_at = time.time()
            record.progress = max(record.progress, 0.01)
            record.stage = "running"
            record.updated_at = time.time()

    def mark_succeeded(self, job_id: str, result: Dict[str, Any]) -> None:
        """Mark a job as succeeded and attach its result payload."""
        with self._lock:
            record = self._jobs[job_id]
            record.status = "succeeded"
            record.finished_at = time.time()
            record.result = result
            record.error = None
            record.progress = 1.0
            record.stage = "succeeded"
            record.updated_at = time.time()

    def mark_failed(self, job_id: str, error: str) -> None:
        """Mark a job as failed and persist an error message."""
        with self._lock:
            record = self._jobs[job_id]
            record.status = "failed"
            record.finished_at = time.time()
            record.result = None
            record.error = error
            record.progress = record.progress if record.progress > 0 else 0.0
            record.stage = "failed"
            record.updated_at = time.time()

    def update_progress(self, job_id: str, progress: float, stage: Optional[str] = None) -> None:
        """Update progress and optional stage for an existing job."""
        with self._lock:
            record = self._jobs.get(job_id)
            if not record:
                return
            record.progress = max(0.0, min(1.0, float(progress)))
            if stage:
                record.stage = stage
            record.updated_at = time.time()

    def cleanup_old_jobs(self, max_age_seconds: Optional[int] = None) -> int:
        """Remove completed jobs older than retention threshold."""
        max_age = max_age_seconds if max_age_seconds is not None else self._max_age
        now = time.time()
        removed = 0

        with self._lock:
            to_remove = []
            for job_id, record in self._jobs.items():
                if record.status in ("succeeded", "failed"):
                    finish_time = record.finished_at or record.created_at
                    if now - finish_time > max_age:
                        to_remove.append(job_id)

            for job_id in to_remove:
                del self._jobs[job_id]
                removed += 1

        return removed

    def get_stats(self) -> Dict[str, int]:
        """Return aggregate counts for each job status."""
        with self._lock:
            stats = {
                "total": len(self._jobs),
                "queued": 0,
                "running": 0,
                "succeeded": 0,
                "failed": 0,
            }
            for record in self._jobs.values():
                if record.status in stats:
                    stats[record.status] += 1
            return stats

    def update_status_text(self, job_id: str, text: str) -> None:
        """Update human-readable status text for a job."""
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].status_text = text

    def update_progress_text(self, job_id: str, text: str) -> None:
        """Update human-readable progress text for a job."""
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].progress_text = text
