"""
Editor component – thin orchestrator for interactive audio editing.

Delegates to:
- ``editor_audio_picker`` – file selection from projects / outputs / upload
- ``editor_waveform`` – waveform display and region selector
- ``editor_tasks`` – repaint, cover, and complete UIs
- ``editor_runner`` – shared generation call
"""
import streamlit as st

from utils import is_dit_ready
from .editor_audio_picker import pick_audio_source
from .editor_waveform import show_waveform_and_player
from .editor_tasks import repaint_ui, cover_ui, complete_ui

_TASK_LABELS = {
    "repaint": "🎨 Repaint a section",
    "cover": "🎤 Create a cover / restyle",
    "complete": "🎼 Extend / fill section",
}


def show_editor() -> None:
    """Top-level editor page."""
    st.markdown("## 🎛️ Audio Editor")

    if not is_dit_ready():
        st.warning(
            "DiT model is **not loaded**.  "
            "Load it in **⚙️ Settings → Models** first."
        )

    # 1. Pick source audio
    audio_path = pick_audio_source()
    if audio_path is None:
        return

    # 2. Waveform + metadata
    duration_sec = show_waveform_and_player(audio_path)

    st.divider()

    # 3. Task selector → delegate to task-specific UI
    task = st.selectbox(
        "Edit task",
        options=list(_TASK_LABELS),
        format_func=_TASK_LABELS.get,
        key="edit_task",
    )

    if task == "repaint":
        repaint_ui(audio_path, duration_sec)
    elif task in ("cover", "cover-nofsq"):
        cover_ui(audio_path, duration_sec)
    elif task == "complete":
        complete_ui(audio_path, duration_sec)

