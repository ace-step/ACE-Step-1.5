"""
Debug helpers (global).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Callable, Union

from acestep.constants import (
    TENSOR_DEBUG_MODE,
    DEBUG_API_SERVER,
    DEBUG_INFERENCE,
    DEBUG_TRAINING,
    DEBUG_DATASET,
    DEBUG_AUDIO,
    DEBUG_LLM,
    DEBUG_UI,
    DEBUG_MODEL_LOADING,
    DEBUG_GPU,
)


def _normalize_mode(mode: str) -> str:
    return (mode or "").strip().upper()


def is_debug_enabled(mode: str) -> bool:
    return _normalize_mode(mode) != "OFF"


def is_debug_verbose(mode: str) -> bool:
    return _normalize_mode(mode) == "VERBOSE"


def debug_log(message: Union[str, Callable[[], str]], *, mode: str = TENSOR_DEBUG_MODE, prefix: str = "debug") -> None:
    """Emit a timestamped debug log line if the mode is enabled."""
    if not is_debug_enabled(mode):
        return
    if callable(message):
        message = message()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{prefix}] {ts} {message}", flush=True)


# Placeholder debug switches registry (for centralized access)
DEBUG_SWITCHES = {
    "tensor": TENSOR_DEBUG_MODE,
    "api_server": DEBUG_API_SERVER,
    "inference": DEBUG_INFERENCE,
    "training": DEBUG_TRAINING,
    "dataset": DEBUG_DATASET,
    "audio": DEBUG_AUDIO,
    "llm": DEBUG_LLM,
    "ui": DEBUG_UI,
    "model_loading": DEBUG_MODEL_LOADING,
    "gpu": DEBUG_GPU,
}


def get_debug_mode(name: str, default: str = "OFF") -> str:
    """Fetch a placeholder debug mode by name."""
    return DEBUG_SWITCHES.get((name or "").strip().lower(), default)


def debug_log_for(name: str, message: Union[str, Callable[[], str]], *, prefix: str | None = None) -> None:
    """Emit a timestamped debug log for a named subsystem."""
    mode = get_debug_mode(name)
    debug_log(message, mode=mode, prefix=prefix or name)


def debug_start_for(name: str, label: str) -> Optional[float]:
    """Start timing for a named subsystem."""
    mode = get_debug_mode(name)
    return debug_start(label, mode=mode, prefix=name)


def debug_end_for(name: str, label: str, start_ts: Optional[float]) -> None:
    """End timing for a named subsystem."""
    mode = get_debug_mode(name)
    debug_end(label, start_ts, mode=mode, prefix=name)


def debug_log_verbose_for(name: str, message: Union[str, Callable[[], str]], *, prefix: str | None = None) -> None:
    """Emit a timestamped debug log only in VERBOSE mode for a named subsystem."""
    mode = get_debug_mode(name)
    if not is_debug_verbose(mode):
        return
    debug_log(message, mode=mode, prefix=prefix or name)


def debug_start_verbose_for(name: str, label: str) -> Optional[float]:
    """Start timing only in VERBOSE mode for a named subsystem."""
    mode = get_debug_mode(name)
    if not is_debug_verbose(mode):
        return None
    return debug_start(label, mode=mode, prefix=name)


def debug_end_verbose_for(name: str, label: str, start_ts: Optional[float]) -> None:
    """End timing only in VERBOSE mode for a named subsystem."""
    mode = get_debug_mode(name)
    if not is_debug_verbose(mode):
        return
    debug_end(label, start_ts, mode=mode, prefix=name)


def debug_start(name: str, *, mode: str = TENSOR_DEBUG_MODE, prefix: str = "debug") -> Optional[float]:
    """Return a start timestamp (perf counter) if enabled, otherwise None."""
    if not is_debug_enabled(mode):
        return None
    debug_log(f"START {name}", mode=mode, prefix=prefix)
    from time import perf_counter
    return perf_counter()


def debug_end(name: str, start_ts: Optional[float], *, mode: str = TENSOR_DEBUG_MODE, prefix: str = "debug") -> None:
    """Emit an END log with elapsed ms if enabled and start_ts is present."""
    if start_ts is None or not is_debug_enabled(mode):
        return
    from time import perf_counter
    elapsed_ms = (perf_counter() - start_ts) * 1000.0
    debug_log(f"END {name} ({elapsed_ms:.1f} ms)", mode=mode, prefix=prefix)
