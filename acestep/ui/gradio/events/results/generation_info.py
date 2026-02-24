"""Generation info formatting and shared constants.

Provides timing summary construction and module-level constants shared
across the results sub-package.
"""
import os
import sys
from typing import Dict, Any, Optional

from acestep.ui.gradio.i18n import t

# Platform detection for Windows-specific fixes
IS_WINDOWS = sys.platform == "win32"

# Global results directory inside project root
# This file is in acestep/ui/gradio/events/results/, need 6 levels up to project root
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))))
)
DEFAULT_RESULTS_DIR = os.path.join(PROJECT_ROOT, "gradio_outputs").replace("\\", "/")
os.makedirs(DEFAULT_RESULTS_DIR, exist_ok=True)


def clear_audio_outputs_for_new_generation():
    """Return None for all 9 audio outputs so Gradio clears them and stops playback."""
    return (None,) * 9


def _build_generation_info(
    lm_metadata: Optional[Dict[str, Any]],
    time_costs: Dict[str, float],
    seed_value: str,
    inference_steps: int,
    num_audios: int,
    audio_format: str = "flac",
) -> str:
    """Build a compact generation timing summary.

    Args:
        lm_metadata: LM-generated metadata dictionary (unused, kept for API compat).
        time_costs: Unified time costs dictionary.
        seed_value: Seed value string (unused, kept for API compat).
        inference_steps: Number of inference steps (unused, kept for API compat).
        num_audios: Number of generated audios.
        audio_format: Output audio format name (e.g. "flac", "mp3", "wav32").

    Returns:
        Formatted generation info string.
    """
    if not time_costs or num_audios <= 0:
        return ""

    songs_label = f"({num_audios} song{'s' if num_audios > 1 else ''})"
    info_parts = []

    # --- Block 1: Generation time (LM + DiT) ---
    lm_total = time_costs.get('lm_total_time', 0.0)
    dit_total = time_costs.get('dit_total_time_cost', 0.0)
    gen_total = lm_total + dit_total

    if gen_total > 0:
        avg = gen_total / num_audios
        lines = [f"**🎵 Total generation time {songs_label}: {gen_total:.2f}s**"]
        lines.append(f"- {avg:.2f}s per song")
        if lm_total > 0:
            lines.append(f"- LM phase {songs_label}: {lm_total:.2f}s")
        if dit_total > 0:
            lines.append(f"- DiT phase {songs_label}: {dit_total:.2f}s")
        info_parts.append("\n".join(lines))

    # --- Block 2: Processing time (conversion + scoring + LRC) ---
    audio_conversion_time = time_costs.get('audio_conversion_time', 0.0)
    auto_score_time = time_costs.get('auto_score_time', 0.0)
    auto_lrc_time = time_costs.get('auto_lrc_time', 0.0)
    proc_total = audio_conversion_time + auto_score_time + auto_lrc_time

    if proc_total > 0:
        fmt_label = audio_format.upper() if audio_format != "wav32" else "WAV 32-bit"
        lines = [f"**🔧 Total processing time {songs_label}: {proc_total:.2f}s**"]
        if audio_conversion_time > 0:
            lines.append(f"- to {fmt_label} {songs_label}: {audio_conversion_time:.2f}s")
        if auto_score_time > 0:
            lines.append(f"- scoring {songs_label}: {auto_score_time:.2f}s")
        if auto_lrc_time > 0:
            lines.append(f"- LRC detection {songs_label}: {auto_lrc_time:.2f}s")
        info_parts.append("\n".join(lines))

    return "\n\n".join(info_parts)
