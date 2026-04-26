"""Shared types for external AI request and parse flows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


class ExternalAIClientError(RuntimeError):
    """Raised when external API calls or response parsing fail."""


@dataclass
class ExternalAIPlan:
    """Structured external text-task result for generation inputs."""

    caption: str
    lyrics: str
    bpm: int | None
    duration: float | None
    key_scale: str
    time_signature: str
    vocal_language: str
    instrumental: bool

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable plan view with both canonical and runtime metadata keys."""

        payload = asdict(self)
        payload["keyscale"] = payload["key_scale"]
        payload["timesignature"] = payload["time_signature"]
        return payload
