"""Job models for API queue state and response payloads."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "running", "succeeded", "failed"]


class CreateJobResponse(BaseModel):
    """Response payload returned immediately after job creation."""

    task_id: str
    status: JobStatus
    queue_position: int = 0
    progress_text: Optional[str] = ""


class JobResult(BaseModel):
    """Result payload for completed music generation jobs."""

    first_audio_path: Optional[str] = None
    second_audio_path: Optional[str] = None
    audio_paths: list[str] = Field(default_factory=list)
    generation_info: str = ""
    status_message: str = ""
    seed_value: str = ""
    metas: Dict[str, Any] = Field(default_factory=dict)
    bpm: Optional[int] = None
    duration: Optional[float] = None
    genres: Optional[str] = None
    keyscale: Optional[str] = None
    timesignature: Optional[str] = None
    lm_model: Optional[str] = None
    dit_model: Optional[str] = None


class JobResponse(BaseModel):
    """Response payload for querying a job's current status."""

    job_id: str
    status: JobStatus
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    queue_position: int = 0
    eta_seconds: Optional[float] = None
    avg_job_seconds: Optional[float] = None
    result: Optional[JobResult] = None
    error: Optional[str] = None
