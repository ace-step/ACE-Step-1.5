"""Log capture utilities for API progress/status endpoints."""

from __future__ import annotations

from typing import Any


class LogBuffer:
    """Minimal write buffer storing the latest non-empty log line."""

    def __init__(self):
        """Initialize buffer with default waiting status."""

        self.last_message = "Waiting"

    def write(self, message: str) -> None:
        """Capture latest non-empty stripped message."""

        msg = message.strip()
        if msg:
            self.last_message = msg

    def flush(self) -> None:
        """No-op flush to satisfy file-like API expectations."""

        return None


class StderrLogger:
    """Stderr proxy forwarding writes to original stderr and log buffer."""

    def __init__(self, original_stderr: Any, buffer: LogBuffer):
        """Initialize stderr proxy references."""

        self.original_stderr = original_stderr
        self.buffer = buffer

    def write(self, message: str) -> None:
        """Write to terminal stderr and update in-memory buffer."""

        self.original_stderr.write(message)
        self.buffer.write(message)

    def flush(self) -> None:
        """Flush original stderr stream."""

        self.original_stderr.flush()


def install_log_capture(logger_obj: Any, stderr_obj: Any) -> tuple[LogBuffer, StderrLogger]:
    """Install log sink and stderr proxy for API status polling.

    Args:
        logger_obj: Logger exposing ``add`` method (for example loguru logger).
        stderr_obj: Existing stderr stream object.

    Returns:
        Tuple of ``(log_buffer, stderr_proxy)``.
    """

    log_buffer = LogBuffer()
    logger_obj.add(
        lambda msg: log_buffer.write(str(msg)),
        format="{time:HH:mm:ss} | {level} | {message}",
    )
    stderr_proxy = StderrLogger(stderr_obj, log_buffer)
    return log_buffer, stderr_proxy
