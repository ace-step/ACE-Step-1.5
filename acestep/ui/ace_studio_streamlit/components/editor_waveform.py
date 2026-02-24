"""
Waveform display and interactive region selector for the editor.

Provides ``show_waveform_and_player()`` and ``region_selector()``.
"""
import math
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import streamlit as st

# ---------- optional heavy imports ----------------------------------
try:
    import soundfile as sf
except ImportError:
    sf = None

try:
    import librosa
except ImportError:
    librosa = None


def show_waveform_and_player(audio_path: Path) -> float:
    """Render the audio player, metadata line, and waveform chart.

    Args:
        audio_path: Path to the audio file.

    Returns:
        Duration of the audio in seconds.
    """
    st.audio(str(audio_path))

    duration_sec = _get_duration(audio_path)
    size_kb = audio_path.stat().st_size / 1024
    st.caption(
        f"**{audio_path.name}** — "
        f"{duration_sec:.1f}s  |  "
        f"{size_kb:.0f} KB"
    )

    waveform = _load_waveform(audio_path)
    if waveform is not None:
        _draw_waveform(waveform, duration_sec)

    return duration_sec


def region_selector(
    duration_sec: float,
    prefix: str = "rp",
) -> Tuple[float, float]:
    """Two-slider region picker with a visual timeline bar.

    Args:
        duration_sec: Total audio duration in seconds.
        prefix: Unique key prefix (avoids widget-key conflicts).

    Returns:
        Tuple of (start_seconds, end_seconds).
    """
    dur_int = max(1, int(math.ceil(duration_sec)))

    st.markdown("**Select region on the timeline:**")
    col1, col2 = st.columns(2)
    with col1:
        start = st.slider(
            "Start (s)", 0, dur_int, 0, 1,
            key=f"{prefix}_start",
        )
    with col2:
        end = st.slider(
            "End (s)", 0, dur_int, min(30, dur_int), 1,
            key=f"{prefix}_end",
        )
    if end <= start:
        st.warning("End must be after start.")

    _draw_region_bar(start, end, duration_sec)
    return float(start), float(end)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _get_duration(audio_path: Path) -> float:
    """Return audio duration in seconds."""
    if sf is not None:
        try:
            return sf.info(str(audio_path)).duration
        except Exception:
            pass
    if librosa is not None:
        try:
            return librosa.get_duration(path=str(audio_path))
        except Exception:
            pass
    return 120.0  # fallback


def _load_waveform(
    audio_path: Path,
    target_sr: int = 8000,
) -> Optional[np.ndarray]:
    """Load a mono, downsampled waveform for visualisation."""
    if librosa is not None:
        try:
            y, _ = librosa.load(str(audio_path), sr=target_sr, mono=True)
            return y
        except Exception:
            pass
    if sf is not None:
        try:
            y, _ = sf.read(str(audio_path), always_2d=True)
            return y.mean(axis=1)
        except Exception:
            pass
    return None


def _draw_waveform(y: np.ndarray, duration_sec: float) -> None:
    """Render a lightweight waveform via ``st.line_chart``."""
    import pandas as pd

    n_points = min(len(y), 1000)
    step = max(1, len(y) // n_points)
    y_ds = y[::step]

    times = np.linspace(0, duration_sec, len(y_ds))
    df = pd.DataFrame({"time (s)": times, "amplitude": y_ds})
    df = df.set_index("time (s)")
    st.line_chart(df, height=120, use_container_width=True)


def _draw_region_bar(
    start: float,
    end: float,
    duration_sec: float,
) -> None:
    """Coloured HTML bar showing the selected region on the timeline."""
    pct_left = start / duration_sec * 100 if duration_sec else 0
    pct_width = (end - start) / duration_sec * 100 if duration_sec else 0
    st.markdown(
        f"""
<div style="position:relative;height:28px;background:#333;
            border-radius:6px;overflow:hidden;margin:4px 0 12px 0;">
  <div style="position:absolute;left:{pct_left:.1f}%;
              width:{pct_width:.1f}%;height:100%;
              background:rgba(255,100,100,0.55);
              border:2px solid #ff6464;border-radius:4px;"></div>
  <div style="position:absolute;width:100%;text-align:center;
              line-height:28px;color:#eee;font-size:0.8rem;">
    {start:.0f}s – {end:.0f}s &nbsp;(region)
  </div>
</div>""",
        unsafe_allow_html=True,
    )
