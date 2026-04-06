"""Runtime progress relay helpers for generation execution."""

import queue
import threading
from typing import Callable, Optional

from loguru import logger


class RuntimeProgressRelay:
    """Bridge runtime step events onto monotonic UI progress updates."""

    def __init__(
        self,
        *,
        progress: Optional[Callable[[float], None]],
        start: float,
        end: float,
    ) -> None:
        self._progress = progress
        self._start = start
        self._end = end
        self._events: "queue.Queue[tuple[int, int, str] | None]" = queue.Queue()
        self._lock = threading.Lock()
        self._value = 0.0
        self._active = True

    def enqueue(self, current: int, total: int, desc: str) -> None:
        """Queue a runtime progress event while the relay is active."""
        with self._lock:
            if not self._active:
                return
        self._events.put((current, total, desc))

    def emit_progress(self, value: float, desc: Optional[str] = None) -> float:
        """Emit a monotonic progress update to the UI callback."""
        with self._lock:
            clamped = max(self._value, value)
            self._value = clamped
        if self._progress is not None:
            try:
                self._progress(clamped, desc=desc)
            except Exception as exc:
                logger.debug("[generate_music] Ignoring progress callback error: {}", exc)
        return clamped

    def drain(self) -> bool:
        """Drain queued runtime events and map them onto the configured UI range."""
        drained = False
        while True:
            try:
                item = self._events.get_nowait()
            except queue.Empty:
                return drained

            if item is None:
                return drained

            current, total, desc = item
            if total <= 0:
                continue
            frac = min(1.0, max(0.0, current / total))
            mapped = self._start + (self._end - self._start) * frac
            self.emit_progress(mapped, desc)
            drained = True

    def shutdown(self) -> None:
        """Disable future runtime event forwarding."""
        with self._lock:
            self._active = False
        self._events.put(None)

    @staticmethod
    def stop_estimator_if_finished(progress_thread):
        """Return the estimator thread handle only while it is still alive."""
        if progress_thread is None:
            return None
        progress_thread.join(timeout=1.0)
        if hasattr(progress_thread, "is_alive") and progress_thread.is_alive():
            return progress_thread
        return None
