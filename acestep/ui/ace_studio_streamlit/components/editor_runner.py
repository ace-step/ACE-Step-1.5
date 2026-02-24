"""
Shared generation runner for editor edit tasks.

Calls ``acestep.inference.generate_music()`` and displays results.
"""
import shutil
from pathlib import Path

import streamlit as st
from loguru import logger

from utils import (
    get_dit_handler,
    get_llm_handler,
    is_dit_ready,
    ProjectManager,
)
from config import OUTPUT_DIR, PROJECTS_DIR


def run_edit_task(
    task_type: str,
    src_audio: str,
    caption: str,
    lyrics: str = "",
    repainting_start: float = 0.0,
    repainting_end: float = -1.0,
    audio_cover_strength: float = 1.0,
    cover_noise_strength: float = 0.0,
    inference_steps: int = 8,
    seed: int = -1,
) -> None:
    """Run an ACE-Step edit task and display results.

    Args:
        task_type: One of ``repaint``, ``cover``, ``complete``.
        src_audio: Path to the source audio file.
        caption: Text prompt describing the edit.
        lyrics: Optional lyrics for the edited section.
        repainting_start: Region start in seconds (repaint/complete).
        repainting_end: Region end in seconds (repaint/complete).
        audio_cover_strength: Cover similarity (cover task).
        cover_noise_strength: Noise level (cover task).
        inference_steps: DiT diffusion steps.
        seed: Random seed (-1 for random).
    """
    if not is_dit_ready():
        st.error("DiT model not loaded.")
        return

    with st.spinner(f"Running {task_type}…"):
        try:
            result = _generate(
                task_type=task_type,
                src_audio=src_audio,
                caption=caption,
                lyrics=lyrics,
                repainting_start=repainting_start,
                repainting_end=repainting_end,
                audio_cover_strength=audio_cover_strength,
                cover_noise_strength=cover_noise_strength,
                inference_steps=inference_steps,
                seed=seed,
            )
        except Exception as exc:
            logger.error(f"{task_type} error: {exc}")
            st.error(f"❌ {task_type} failed: {exc}")
            return

    if not result.success:
        st.error(f"Failed: {result.error}")
        return

    st.success(f"✅ {task_type.title()} complete!")
    _show_results(result, task_type, caption)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _generate(
    task_type: str,
    src_audio: str,
    caption: str,
    lyrics: str,
    repainting_start: float,
    repainting_end: float,
    audio_cover_strength: float,
    cover_noise_strength: float,
    inference_steps: int,
    seed: int,
):
    """Build params, invoke generate_music, return GenerationResult."""
    from acestep.inference import (
        GenerationParams,
        GenerationConfig,
        generate_music,
    )

    params = GenerationParams(
        task_type=task_type,
        caption=caption,
        lyrics=lyrics or "[Instrumental]",
        src_audio=src_audio,
        repainting_start=repainting_start,
        repainting_end=repainting_end,
        audio_cover_strength=audio_cover_strength,
        cover_noise_strength=cover_noise_strength,
        inference_steps=inference_steps,
        seed=seed,
        thinking=False,
    )
    config = GenerationConfig(
        batch_size=1,
        use_random_seed=(seed < 0),
        seeds=[seed] if seed >= 0 else None,
    )

    return generate_music(
        dit_handler=get_dit_handler(),
        llm_handler=get_llm_handler(),
        params=params,
        config=config,
        save_dir=str(OUTPUT_DIR),
    )


def _show_results(result, task_type: str, caption: str) -> None:
    """Display audio outputs and offer project-save buttons."""
    for idx, audio_info in enumerate(result.audios):
        out_path = audio_info.get("path", "")
        if not out_path or not Path(out_path).exists():
            continue
        st.audio(out_path)
        st.caption(Path(out_path).name)

        if st.button(
            "💾 Save to project",
            key=f"save_{task_type}_{idx}",
        ):
            pm = ProjectManager(PROJECTS_DIR)
            safe = caption[:25].replace(" ", "_").replace("/", "_")
            proj = pm.create_project(
                f"{task_type}_{safe}",
                description=caption,
            )
            dst = proj / Path(out_path).name
            shutil.copy2(out_path, str(dst))
            st.success("Saved to project")
