"""
Generation Wizard component - create new songs.

Provides a single-page form for text-to-music generation
using the ACE-Step DiT + optional LLM pipeline.
"""
import sys
from pathlib import Path
from typing import Optional

import streamlit as st
from loguru import logger

from utils import (
    get_dit_handler,
    get_llm_handler,
    is_dit_ready,
    initialize_dit,
    ProjectManager,
)
from config import (
    ACESTEP_ROOT,
    PROJECTS_DIR,
    OUTPUT_DIR,
    GENRES,
    MOODS,
    DEFAULT_DURATION,
    DEFAULT_BPM,
)


def _quick_init_dit() -> None:
    """One-click DiT init from the Generate page."""
    import sys as _sys

    with st.spinner("Loading DiT model..."):
        _status, _ok = initialize_dit(
            config_path="acestep-v15-turbo",
            device="auto",
            offload_to_cpu=(_sys.platform != "darwin"),
        )
    if _ok:
        st.success("DiT model loaded!")
        st.rerun()
    else:
        st.error(f"Init failed: {_status}")


def show_generation_wizard() -> None:
    """Display the song generation form (all sections visible)."""
    st.markdown("## 🎵 Generate New Song")

    if not is_dit_ready():
        st.warning(
            "DiT model is **not loaded** yet.  "
            "Click below to load it, or go to "
            "**⚙️ Settings → Models**."
        )
        if st.button(
            "🚀 Load DiT Model Now",
            key="quick_init_dit",
            type="primary",
        ):
            _quick_init_dit()
            return

    # ------------------------------------------------------------------
    # Section 1 – Inspiration & Vibe
    # ------------------------------------------------------------------
    st.markdown("### 🎨 Inspiration & Vibe")

    col1, col2 = st.columns(2)
    with col1:
        quick_genre = st.selectbox(
            "Genre",
            GENRES,
            key="quick_genre",
        )
    with col2:
        quick_mood = st.selectbox(
            "Mood",
            MOODS,
            key="quick_mood",
        )

    caption = st.text_area(
        "Song Description (caption)",
        placeholder=(
            "E.g., 'Upbeat pop with electric guitars "
            "and catchy chorus, feels summery and energetic'"
        ),
        height=80,
        key="caption",
    )
    if not caption:
        caption = f"A {quick_mood.lower()} {quick_genre.lower()} song"

    st.divider()

    # ------------------------------------------------------------------
    # Section 2 – Song Structure
    # ------------------------------------------------------------------
    st.markdown("### 🎼 Song Structure")

    col1, col2, col3 = st.columns(3)

    with col1:
        duration = st.slider(
            "Duration (seconds)",
            min_value=10,
            max_value=600,
            value=DEFAULT_DURATION,
            step=10,
            key="duration",
        )
    with col2:
        bpm_opts = ["Auto", 60, 80, 90, 100, 110, 120, 140, 150, 160]
        bpm_input = st.selectbox(
            "BPM",
            options=bpm_opts,
            index=bpm_opts.index(DEFAULT_BPM),
            key="bpm",
        )
        bpm: Optional[int] = (
            None if bpm_input == "Auto" else int(bpm_input)
        )
    with col3:
        key_opts = [
            "Auto",
            "C Major", "C Minor",
            "D Major", "D Minor",
            "E Major", "E Minor",
            "F Major", "F Minor",
            "G Major", "G Minor",
            "A Major", "A Minor",
            "B Major", "B Minor",
        ]
        key_input = st.selectbox(
            "Key / Scale",
            options=key_opts,
            index=0,
            key="key",
        )
        key_opt: str = "" if key_input == "Auto" else key_input

    # Lyrics
    st.markdown("**Lyrics (optional)**")
    use_lyrics = st.checkbox(
        "Add lyrics", value=False, key="use_lyrics"
    )
    lyrics = ""
    if use_lyrics:
        lyrics = st.text_area(
            "Lyrics",
            placeholder=(
                "[Verse 1]\nLyrics here...\n\n"
                "[Chorus]\nCatchy chorus..."
            ),
            height=150,
            key="lyrics",
            label_visibility="collapsed",
        )

    st.divider()

    # ------------------------------------------------------------------
    # Section 3 – Advanced Options
    # ------------------------------------------------------------------
    with st.expander("🔧 Advanced Settings", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            inference_steps = st.slider(
                "Diffusion Steps",
                min_value=4,
                max_value=100,
                value=8,
                step=4,
                help="More steps = higher quality but slower",
                key="inference_steps",
            )
        with col2:
            guidance_scale = st.slider(
                "Guidance Scale",
                min_value=1.0,
                max_value=15.0,
                value=7.0,
                step=0.5,
                help="Higher = follows prompt more strictly",
                key="guidance_scale",
            )
        with col3:
            seed = st.number_input(
                "Seed (-1 = random)",
                value=-1,
                key="seed",
            )

        col4, col5 = st.columns(2)
        with col4:
            batch_size = st.number_input(
                "Batch Size",
                min_value=1,
                max_value=8,
                value=1,
                key="batch_size",
            )
        with col5:
            use_cot = st.checkbox(
                "LLM Chain-of-Thought reasoning",
                value=True,
                help="Let the LLM refine metadata + codes",
                key="use_cot",
            )

    st.divider()

    # ------------------------------------------------------------------
    # Generate button
    # ------------------------------------------------------------------
    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        if st.button(
            "🚀 Generate Song",
            use_container_width=True,
            type="primary",
            key="gen_btn",
        ):
            generate_song(
                caption=caption,
                duration=duration,
                bpm=bpm,
                key=key_opt,
                lyrics=lyrics if use_lyrics else "",
                inference_steps=inference_steps,
                guidance_scale=guidance_scale,
                seed=int(seed),
                batch_size=int(batch_size),
                use_cot=use_cot,
            )


# ------------------------------------------------------------------
# Actual generation logic
# ------------------------------------------------------------------

def generate_song(
    caption: str,
    duration: int,
    bpm: Optional[int] = None,
    key: str = "",
    lyrics: str = "",
    inference_steps: int = 8,
    guidance_scale: float = 7.0,
    seed: int = -1,
    batch_size: int = 1,
    use_cot: bool = True,
) -> None:
    """Run ACE-Step generation and persist outputs."""
    if not is_dit_ready():
        st.error(
            "DiT model not loaded. "
            "Please initialise it in **Settings → Models**."
        )
        return

    with st.spinner("🎹 Generating your music..."):
        try:
            dit_handler = get_dit_handler()
            llm_handler = get_llm_handler()

            progress_bar = st.progress(0)
            status_text = st.empty()

            status_text.text("⏳ Preparing generation...")
            progress_bar.progress(5)

            # Use the high-level inference API
            from acestep.inference import (
                GenerationParams,
                GenerationConfig,
                generate_music,
            )

            params = GenerationParams(
                task_type="text2music",
                caption=caption,
                lyrics=lyrics or "[Instrumental]",
                duration=float(duration),
                bpm=bpm,
                keyscale=key,
                inference_steps=inference_steps,
                guidance_scale=guidance_scale,
                seed=seed,
                thinking=use_cot,
                use_cot_metas=use_cot,
                use_cot_caption=use_cot,
                use_cot_language=use_cot,
            )

            config = GenerationConfig(
                batch_size=batch_size,
                use_random_seed=(seed < 0),
                seeds=[seed] if seed >= 0 else None,
            )

            status_text.text("🎨 Running ACE-Step pipeline...")
            progress_bar.progress(20)

            result = generate_music(
                dit_handler=dit_handler,
                llm_handler=llm_handler,
                params=params,
                config=config,
                save_dir=str(OUTPUT_DIR),
            )

            progress_bar.progress(100)

            if not result.success:
                st.error(f"Generation failed: {result.error}")
                return

            status_text.text("✅ Generation complete!")

            # Display generated audio files
            if result.audios:
                st.markdown("### 🎧 Results")
                for idx, audio_info in enumerate(result.audios):
                    audio_path = audio_info.get("path", "")
                    if audio_path and Path(audio_path).exists():
                        st.audio(audio_path)
                        st.caption(
                            f"Song {idx + 1} — "
                            f"{Path(audio_path).name}"
                        )

            # Save as project
            pm = ProjectManager(PROJECTS_DIR)
            safe_name = (
                caption[:30]
                .replace(" ", "_")
                .replace("/", "_")
            )
            project_path = pm.create_project(
                safe_name, description=caption
            )
            pm.save_metadata(
                project_path,
                genre=caption,
                mood="Generated",
                duration=duration,
                bpm=bpm,
            )

            # Copy audio files into project
            for audio_info in result.audios:
                src = Path(audio_info.get("path", ""))
                if src.exists():
                    import shutil
                    dst = project_path / src.name
                    shutil.copy2(str(src), str(dst))

            st.success(
                f"🎉 Saved as project '{safe_name}'"
            )

        except Exception as exc:
            logger.error(f"Generation error: {exc}")
            st.error(f"❌ Generation failed: {exc}")
