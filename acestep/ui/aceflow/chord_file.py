"""File output helpers for AceFlow chord-reference rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .chord_synth import synthesize_reference_wav_bytes


def render_reference_wav_file(
    chords: list[str],
    output_path: str | Path,
    bpm: float = 120.0,
    beats_per_chord: int = 4,
    target_duration_sec: Optional[float] = None,
) -> dict:
    """Render a chord-reference WAV to disk and return the render metadata."""
    wav_bytes, meta = synthesize_reference_wav_bytes(
        chords=chords,
        bpm=bpm,
        beats_per_chord=beats_per_chord,
        target_duration_sec=target_duration_sec,
    )
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(wav_bytes)
    meta['output_path'] = str(out)
    meta['size_bytes'] = out.stat().st_size
    return meta
