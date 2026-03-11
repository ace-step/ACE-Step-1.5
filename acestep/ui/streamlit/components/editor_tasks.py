"""Edit-task UI panels – repaint, cover, and complete.

Delegates generation to ``editor_runner.run_edit_task()``.
"""
from pathlib import Path

import streamlit as st

from .editor_waveform import region_selector
from .editor_runner import run_edit_task


def repaint_ui(audio_path: Path, duration_sec: float) -> None:
    """Interactive repaint: mark a region and regenerate it."""
    st.markdown("### 🎨 Repaint Region")
    st.caption(
        "Select a time region and describe what should replace it. "
        "The rest of the song stays untouched."
    )

    start, end = region_selector(duration_sec, prefix="rp")

    prompt = st.text_area(
        "What should this section sound like?",
        placeholder=(
            "e.g. 'Energetic drum fill with rising synth' "
            "or 'Soft piano interlude'"
        ),
        key="rp_prompt",
    )
    lyrics = st.text_area(
        "Lyrics for this section (optional)",
        placeholder="[Chorus]\nNew lyrics...",
        height=80,
        key="rp_lyrics",
    )

    with st.expander("Advanced", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            steps = st.slider(
                "Diffusion steps", 4, 100, 8, 4, key="rp_steps"
            )
        with col2:
            seed = st.number_input(
                "Seed (-1 random)", value=-1, key="rp_seed"
            )

    if st.button(
        "🎨 Repaint", type="primary",
        use_container_width=True, key="rp_go",
    ):
        if end <= start:
            st.error("Invalid region — end must be after start.")
            return
        run_edit_task(
            task_type="repaint",
            src_audio=str(audio_path),
            caption=prompt or "Repaint section",
            lyrics=lyrics,
            repainting_start=start,
            repainting_end=end,
            inference_steps=steps,
            seed=int(seed),
        )


def cover_ui(audio_path: Path, duration_sec: float) -> None:
    """Create a cover or restyle from source audio."""
    st.markdown("### 🎤 Cover / Restyle")
    st.caption(
        "Generate a new version of this audio in a different style."
    )

    prompt = st.text_area(
        "Describe the target style",
        placeholder=(
            "e.g. 'Acoustic folk version with female vocals' "
            "or 'Lo-fi hip-hop remix'"
        ),
        key="cv_prompt",
    )
    lyrics = st.text_area(
        "Lyrics (optional)", placeholder="[Verse]\n...",
        height=80, key="cv_lyrics",
    )

    col1, col2 = st.columns(2)
    with col1:
        strength = st.slider(
            "Cover strength", 0.0, 1.0, 0.7, 0.05,
            help="1.0 = very close to original; lower = more creative",
            key="cv_strength",
        )
    with col2:
        noise = st.slider(
            "Noise strength", 0.0, 1.0, 0.0, 0.05,
            help="0 = pure noise (new); 1 = closest to source",
            key="cv_noise",
        )

    with st.expander("Advanced", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            steps = st.slider(
                "Diffusion steps", 4, 100, 8, 4, key="cv_steps"
            )
        with col2:
            seed = st.number_input(
                "Seed (-1 random)", value=-1, key="cv_seed"
            )

    if st.button(
        "🎤 Create Cover", type="primary",
        use_container_width=True, key="cv_go",
    ):
        run_edit_task(
            task_type="cover",
            src_audio=str(audio_path),
            caption=prompt or "Cover version",
            lyrics=lyrics,
            audio_cover_strength=strength,
            cover_noise_strength=noise,
            inference_steps=steps,
            seed=int(seed),
        )


def complete_ui(audio_path: Path, duration_sec: float) -> None:
    """Fill a gap or extend a song."""
    st.markdown("### 🎼 Complete / Extend")
    st.caption(
        "Select a region to fill, or set end = duration to extend."
    )

    start, end = region_selector(duration_sec, prefix="cp")

    prompt = st.text_area(
        "Describe the section to generate",
        placeholder="e.g. 'Guitar solo bridge' or "
                    "'Outro with fading strings'",
        key="cp_prompt",
    )
    lyrics = st.text_area(
        "Lyrics (optional)", height=80, key="cp_lyrics",
    )

    with st.expander("Advanced", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            steps = st.slider(
                "Diffusion steps", 4, 100, 8, 4, key="cp_steps"
            )
        with col2:
            seed = st.number_input(
                "Seed (-1 random)", value=-1, key="cp_seed"
            )

    if st.button(
        "🎼 Complete", type="primary",
        use_container_width=True, key="cp_go",
    ):
        if end <= start:
            st.error("Invalid region.")
            return
        run_edit_task(
            task_type="complete",
            src_audio=str(audio_path),
            caption=prompt or "Complete section",
            lyrics=lyrics,
            repainting_start=start,
            repainting_end=end,
            inference_steps=steps,
            seed=int(seed),
        )
