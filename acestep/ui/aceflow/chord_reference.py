"""Compatibility facade for AceFlow chord-reference helpers.

The original public API remains here for callers such as ``app.py``, while the
implementation is split by responsibility into parsing, voicing, synthesis, and
file-output modules.
"""

from .chord_file import render_reference_wav_file
from .chord_parser import ParsedChord, parse_chord_symbol
from .chord_synth import MAX_RENDER_DURATION_SEC, midi_to_freq, synthesize_reference_wav_bytes
from .chord_voicing import choose_voicing

__all__ = [
    'MAX_RENDER_DURATION_SEC',
    'ParsedChord',
    'choose_voicing',
    'midi_to_freq',
    'parse_chord_symbol',
    'render_reference_wav_file',
    'synthesize_reference_wav_bytes',
]
