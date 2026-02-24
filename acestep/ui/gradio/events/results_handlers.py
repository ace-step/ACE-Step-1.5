"""
Results Handlers Facade

Thin re-export layer that preserves the original ``results_handlers`` public
interface while delegating to focused sub-modules under ``results/``.

All symbols that were previously importable from this module are still
available here so that existing callers (e.g. ``events/__init__.py``,
``api_server.py``) continue to work without changes.
"""

# --- constants ----------------------------------------------------------
from acestep.ui.gradio.events.results.generation_info import (
    DEFAULT_RESULTS_DIR,
    PROJECT_ROOT,
)

# --- generation info & audio clearing -----------------------------------
from acestep.ui.gradio.events.results.generation_info import (
    clear_audio_outputs_for_new_generation,
    _build_generation_info,
)

# --- LRC / VTT utilities -----------------------------------------------
from acestep.ui.gradio.events.results.lrc_utils import (
    parse_lrc_to_subtitles,
    _format_vtt_timestamp,
    lrc_to_vtt_file,
    update_audio_subtitles_from_lrc,
    save_lrc_to_file,
    generate_lrc_handler,
)

# --- batch queue management ---------------------------------------------
from acestep.ui.gradio.events.results.batch_queue import (
    store_batch_in_queue,
    update_batch_indicator,
    update_navigation_buttons,
    capture_current_params,
    restore_batch_parameters,
)

# --- scoring ------------------------------------------------------------
from acestep.ui.gradio.events.results.scoring import (
    calculate_score_handler,
    calculate_score_handler_with_selection,
)

# --- audio transfer (remix / repaint / codes) ---------------------------
from acestep.ui.gradio.events.results.audio_transfer import (
    send_audio_to_src_with_metadata,
    _extract_metadata_for_editing,
    send_audio_to_remix,
    send_audio_to_repaint,
    convert_result_audio_to_codes,
)

# --- generation progress ------------------------------------------------
from acestep.ui.gradio.events.results.generation_progress import (
    generate_with_progress,
)

# --- batch management & AutoGen -----------------------------------------
from acestep.ui.gradio.events.results.batch_management import (
    generate_with_batch_management,
    generate_next_batch_background,
)

# --- batch navigation ---------------------------------------------------
from acestep.ui.gradio.events.results.batch_navigation import (
    navigate_to_previous_batch,
    navigate_to_next_batch,
)

__all__ = [
    # constants
    "DEFAULT_RESULTS_DIR",
    "PROJECT_ROOT",
    # generation info
    "clear_audio_outputs_for_new_generation",
    "_build_generation_info",
    # LRC / VTT
    "parse_lrc_to_subtitles",
    "_format_vtt_timestamp",
    "lrc_to_vtt_file",
    "update_audio_subtitles_from_lrc",
    "save_lrc_to_file",
    "generate_lrc_handler",
    # batch queue
    "store_batch_in_queue",
    "update_batch_indicator",
    "update_navigation_buttons",
    "capture_current_params",
    "restore_batch_parameters",
    # scoring
    "calculate_score_handler",
    "calculate_score_handler_with_selection",
    # audio transfer
    "send_audio_to_src_with_metadata",
    "_extract_metadata_for_editing",
    "send_audio_to_remix",
    "send_audio_to_repaint",
    "convert_result_audio_to_codes",
    # generation
    "generate_with_progress",
    "generate_with_batch_management",
    "generate_next_batch_background",
    # navigation
    "navigate_to_previous_batch",
    "navigate_to_next_batch",
]
