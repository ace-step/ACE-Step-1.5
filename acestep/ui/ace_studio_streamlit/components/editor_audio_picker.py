"""
Audio source picker for the editor – browses projects, outputs, uploads.

Provides ``pick_audio_source()`` which returns the selected path or None.
"""
import tempfile
from pathlib import Path
from typing import Optional, List

import streamlit as st

from utils import ProjectManager
from config import PROJECTS_DIR, OUTPUT_DIR, AUDIO_FORMATS


def pick_audio_source() -> Optional[Path]:
    """Let the user choose from projects, gradio_outputs, or upload.

    Returns:
        Path to the chosen audio file, or ``None`` if nothing selected.
    """
    tab_proj, tab_out, tab_upload = st.tabs(
        ["📁 Projects", "📂 All outputs", "⬆️ Upload file"]
    )

    audio_path: Optional[Path] = None

    with tab_proj:
        audio_path = _pick_from_projects(audio_path)

    with tab_out:
        audio_path = _pick_from_outputs(audio_path)

    with tab_upload:
        audio_path = _pick_from_upload(audio_path)

    return audio_path


# ------------------------------------------------------------------
# Tab helpers
# ------------------------------------------------------------------

def _pick_from_projects(fallback: Optional[Path]) -> Optional[Path]:
    """Project-file picker tab content."""
    pm = ProjectManager(PROJECTS_DIR)
    projects = pm.list_projects()
    if not projects:
        st.info("No projects yet – generate a song first.")
        return fallback

    proj_names = [p["name"] for p in projects]
    sel_proj = st.selectbox("Project", proj_names, key="ed_proj")
    proj_path = pm.get_project(sel_proj)
    if not proj_path:
        return fallback

    files = pm.get_audio_files(proj_path)
    if not files:
        st.info("No audio in this project.")
        return fallback

    sel_file = st.selectbox(
        "Audio file",
        [f.name for f in files],
        key="ed_proj_file",
    )
    return proj_path / sel_file


def _pick_from_outputs(fallback: Optional[Path]) -> Optional[Path]:
    """gradio_outputs browser tab content."""
    all_files = _scan_output_files()
    if not all_files:
        st.info("No output files found.")
        return fallback

    labels = [
        f"{f.parent.name}/{f.name}" if f.parent != OUTPUT_DIR else f.name
        for f in all_files
    ]
    sel_idx = st.selectbox(
        "Output file",
        range(len(labels)),
        format_func=lambda i: labels[i],
        key="ed_out_file",
    )
    return all_files[sel_idx]


def _pick_from_upload(fallback: Optional[Path]) -> Optional[Path]:
    """Upload tab content – persist to temp file."""
    uploaded = st.file_uploader(
        "Upload an audio file",
        type=["wav", "mp3", "flac", "m4a"],
        key="ed_upload",
    )
    if uploaded is None:
        return fallback
    tmp = Path(tempfile.gettempdir()) / uploaded.name
    tmp.write_bytes(uploaded.getvalue())
    return tmp


def _scan_output_files() -> List[Path]:
    """Return all audio files under gradio_outputs (flat + batch dirs)."""
    exts = set(AUDIO_FORMATS)
    out: List[Path] = []
    if not OUTPUT_DIR.exists():
        return out
    for p in sorted(OUTPUT_DIR.rglob("*"), reverse=True):
        if p.is_file() and p.suffix.lower() in exts:
            out.append(p)
        if len(out) >= 200:
            break
    return out
