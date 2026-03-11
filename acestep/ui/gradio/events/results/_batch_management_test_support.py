"""Shared test utilities for ``batch_management`` unit tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
from typing import Any, Dict, Tuple
from unittest.mock import patch


_MISSING = object()


def build_progress_result(*, length: int = 48, all_audio_paths: Any = _MISSING) -> tuple:
    """Build a minimally valid ``generate_with_progress`` result tuple."""
    result = [None] * length
    for idx in range(8):
        result[idx] = {"value": f"audio_{idx}.flac", "playback_position": 0}
    result[8] = ["audio_0.flac", "audio_0.json"] if all_audio_paths is _MISSING else all_audio_paths
    result[9] = "generation info"
    result[10] = "Generation Complete"
    result[11] = "42"
    result[44] = {"bpm": 120}
    result[45] = False
    if length > 46:
        result[46] = {"lrcs": ["lrc"] * 8, "subtitles": ["sub"] * 8}
    if length > 47:
        result[47] = ["codes"] * 8
    if length > 48:
        result[48] = {"future_tail_field": True}
    return tuple(result)


def load_batch_management_module(*, is_windows: bool = False) -> Tuple[Any, Dict[str, Any]]:
    """Load ``batch_management.py`` with dependency stubs and trackers."""
    state: Dict[str, Any] = {
        "store_calls": [],
        "info_messages": [],
        "warning_messages": [],
        "log_info": [],
        "log_warning": [],
    }

    def _gr_update(**kwargs):
        """Return a deterministic Gradio-like update payload."""
        return {"kind": "update", **kwargs}

    def _gr_skip():
        """Return a deterministic Gradio-like skip payload."""
        return {"kind": "skip"}

    def _gr_info(message):
        """Capture ``gr.Info`` messages for assertions."""
        state["info_messages"].append(message)

    def _gr_warning(message):
        """Capture ``gr.Warning`` messages for assertions."""
        state["warning_messages"].append(message)

    def _logger_info(message):
        """Capture logger info messages for assertions."""
        state["log_info"].append(str(message))

    def _logger_warning(message):
        """Capture logger warning messages for assertions."""
        state["log_warning"].append(str(message))

    def _default_generate_with_progress(*_args, **_kwargs):
        """Default empty generator placeholder patched per test."""
        if False:
            yield None

    def _store_batch_in_queue(batch_queue, batch_idx, all_audio_paths, generation_info, seed_value_for_ui, **kwargs):
        """Store synthetic batch data and keep call history for assertions."""
        call = {
            "batch_queue": dict(batch_queue),
            "batch_idx": batch_idx,
            "all_audio_paths": all_audio_paths,
            "generation_info": generation_info,
            "seed_value_for_ui": seed_value_for_ui,
            **kwargs,
        }
        state["store_calls"].append(call)
        next_queue = dict(batch_queue)
        next_queue[batch_idx] = {"status": "completed", **call}
        return next_queue

    def _translate(key, **kwargs):
        """Return predictable translation output with formatted kwargs."""
        return f"{key}|{kwargs}" if kwargs else key

    acestep_pkg = types.ModuleType("acestep")
    ui_pkg = types.ModuleType("acestep.ui")
    gradio_pkg = types.ModuleType("acestep.ui.gradio")
    events_pkg = types.ModuleType("acestep.ui.gradio.events")
    results_pkg = types.ModuleType("acestep.ui.gradio.events.results")

    results_dir = Path(__file__).resolve().parent
    events_dir = results_dir.parent
    gradio_dir = events_dir.parent
    ui_dir = gradio_dir.parent
    acestep_dir = ui_dir.parent

    acestep_pkg.__path__ = [str(acestep_dir)]
    ui_pkg.__path__ = [str(ui_dir)]
    gradio_pkg.__path__ = [str(gradio_dir)]
    events_pkg.__path__ = [str(events_dir)]
    results_pkg.__path__ = [str(results_dir)]

    fake_gradio = types.ModuleType("gradio")
    fake_gradio.update = _gr_update
    fake_gradio.skip = _gr_skip
    fake_gradio.Progress = lambda track_tqdm=True: None
    fake_gradio.Info = _gr_info
    fake_gradio.Warning = _gr_warning

    fake_logger = types.SimpleNamespace(
        info=_logger_info,
        warning=_logger_warning,
        error=lambda _msg: None,
    )

    modules = {
        "gradio": fake_gradio,
        "loguru": types.SimpleNamespace(logger=fake_logger),
        "acestep": acestep_pkg,
        "acestep.ui": ui_pkg,
        "acestep.ui.gradio": gradio_pkg,
        "acestep.ui.gradio.i18n": types.SimpleNamespace(t=_translate),
        "acestep.ui.gradio.events": events_pkg,
        "acestep.ui.gradio.events.results": results_pkg,
        "acestep.ui.gradio.events.results.generation_info": types.SimpleNamespace(IS_WINDOWS=is_windows),
        "acestep.ui.gradio.events.results.generation_progress": types.SimpleNamespace(
            generate_with_progress=_default_generate_with_progress
        ),
        "acestep.ui.gradio.events.results.batch_queue": types.SimpleNamespace(
            store_batch_in_queue=_store_batch_in_queue,
            update_batch_indicator=lambda current, total: f"Batch {current + 1}/{total}",
            update_navigation_buttons=lambda current, total: (current > 0, current < total - 1),
        ),
    }

    acestep_pkg.ui = ui_pkg
    ui_pkg.gradio = gradio_pkg
    gradio_pkg.events = events_pkg
    events_pkg.results = results_pkg

    for module_name in list(sys.modules):
        if module_name.startswith("acestep.ui.gradio.events.results.batch_management"):
            sys.modules.pop(module_name, None)

    module_path = Path(__file__).with_name("batch_management.py")
    spec = importlib.util.spec_from_file_location("batch_management", module_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict("sys.modules", modules):
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module, state
