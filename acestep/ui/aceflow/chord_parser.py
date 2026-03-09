"""Chord symbol normalization and parsing helpers for AceFlow."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

NOTE_INDEX = {
    'C': 0, 'B#': 0,
    'C#': 1, 'Db': 1,
    'D': 2,
    'D#': 3, 'Eb': 3,
    'E': 4, 'Fb': 4,
    'F': 5, 'E#': 5,
    'F#': 6, 'Gb': 6,
    'G': 7,
    'G#': 8, 'Ab': 8,
    'A': 9,
    'A#': 10, 'Bb': 10,
    'B': 11, 'Cb': 11,
}

_DESCRIPTOR_ALIASES = {
    '': 'maj', 'maj': 'maj', 'major': 'maj',
    'm': 'min', 'min': 'min', 'minor': 'min',
    'maj7': 'maj7', 'm7': 'min7', 'min7': 'min7',
    '7': 'dom7', 'dom7': 'dom7',
    'dim': 'dim', 'dim7': 'dim7',
    'aug': 'aug', '+': 'aug',
    'sus': 'sus4', 'sus4': 'sus4', 'sus2': 'sus2',
    'add9': 'add9', '6': '6', 'm6': 'min6',
    '9': '9', 'maj9': 'maj9', 'm9': 'min9', '7#5': '7#5',
}

_BASE_INTERVALS = {
    'maj': [0, 4, 7], 'min': [0, 3, 7],
    'maj7': [0, 4, 7, 11], 'min7': [0, 3, 7, 10], 'dom7': [0, 4, 7, 10],
    'dim': [0, 3, 6], 'dim7': [0, 3, 6, 9], 'aug': [0, 4, 8],
    'sus2': [0, 2, 7], 'sus4': [0, 5, 7],
    'add9': [0, 4, 7, 14], '6': [0, 4, 7, 9], 'min6': [0, 3, 7, 9],
    '9': [0, 4, 7, 10, 14], 'maj9': [0, 4, 7, 11, 14], 'min9': [0, 3, 7, 10, 14],
    '7#5': [0, 4, 8, 10],
}

_UPPERCASE_MAJOR_ALIASES = {
    'M': 'maj', 'M6': '6', 'M7': 'maj7', 'M9': 'maj9', 'M11': 'maj9', 'M13': 'maj9',
}


@dataclass
class ParsedChord:
    """Normalized representation of a chord symbol used by the preview renderer."""

    original: str
    normalized: str
    root_pc: int
    chord_pcs: list[int]
    bass_pc: int
    descriptor: str
    warning: Optional[str] = None


def _normalize_symbol(symbol: str) -> str:
    """Normalize spacing and accidental aliases in a chord symbol."""
    text = str(symbol or '').strip()
    text = text.replace('♯', '#').replace('♭', 'b').replace('Δ', 'maj')
    return re.sub(r'\s+', '', text)


def _resolve_descriptor(desc: str) -> tuple[str, Optional[str]]:
    """Resolve a raw descriptor string into a canonical internal alias."""
    descriptor = _DESCRIPTOR_ALIASES.get(desc)
    warning = None
    uppercase_major_descriptor = _UPPERCASE_MAJOR_ALIASES.get(desc)
    if descriptor is None and uppercase_major_descriptor is not None:
        return uppercase_major_descriptor, 'descriptor_fallback'
    if descriptor is not None:
        return descriptor, warning
    lc = desc.lower()
    if 'maj9' in lc:
        return 'maj9', warning
    if 'maj7' in lc:
        return 'maj7', 'descriptor_fallback' if lc != 'maj7' else None
    if lc in {'m7b5', 'ø', 'ø7'}:
        return 'dim', 'descriptor_fallback'
    if 'm9' in lc or 'min9' in lc:
        return 'min9', 'descriptor_fallback' if lc not in {'m9', 'min9'} else None
    if '13' in lc or '11' in lc:
        if 'maj' in lc:
            return 'maj9', 'descriptor_fallback'
        if lc.startswith('m') or 'min' in lc:
            return 'min9', 'descriptor_fallback'
        return '9', 'descriptor_fallback'
    if lc == '9' or lc.startswith('9'):
        return '9', 'descriptor_fallback' if lc != '9' else None
    if 'm7' in lc or 'min7' in lc:
        return 'min7', 'descriptor_fallback' if lc not in {'m7', 'min7'} else None
    if 'add9' in lc:
        return 'add9', 'descriptor_fallback' if lc != 'add9' else None
    if 'sus2' in lc:
        return 'sus2', 'descriptor_fallback' if lc != 'sus2' else None
    if 'sus' in lc:
        return 'sus4', 'descriptor_fallback' if lc not in {'sus', 'sus4'} else None
    if 'dim7' in lc:
        return 'dim7', 'descriptor_fallback' if lc != 'dim7' else None
    if 'dim' in lc:
        return 'dim', 'descriptor_fallback' if lc != 'dim' else None
    if '7#5' in lc:
        return '7#5', 'descriptor_fallback' if lc != '7#5' else None
    if 'aug' in lc or lc == '+':
        return 'aug', 'descriptor_fallback' if lc not in {'aug', '+'} else None
    if lc == '7' or lc.startswith('7'):
        return 'dom7', 'descriptor_fallback' if lc != '7' else None
    if lc.startswith('m') or lc.startswith('min'):
        return 'min', 'descriptor_fallback' if lc not in {'m', 'min', 'minor'} else None
    return 'maj', 'descriptor_fallback' if lc else None


def parse_chord_symbol(symbol: str) -> Optional[ParsedChord]:
    """Parse a chord symbol into a normalized structure for voicing and rendering."""
    normalized = _normalize_symbol(symbol)
    if not normalized:
        return None
    match = re.match(r'^([A-G](?:#|b)?)([^/]*)?(?:/([A-G](?:#|b)?))?$', normalized)
    if not match:
        return None
    root_name = match.group(1)
    raw_desc = (match.group(2) or '').strip()
    bass_name = (match.group(3) or '').strip()
    root_pc = NOTE_INDEX.get(root_name)
    if root_pc is None:
        return None
    descriptor, warning = _resolve_descriptor(raw_desc)
    bass_pc = NOTE_INDEX.get(bass_name, root_pc) if bass_name else root_pc
    chord_pcs = sorted({(root_pc + interval) % 12 for interval in _BASE_INTERVALS[descriptor]})
    return ParsedChord(
        original=str(symbol or ''),
        normalized=normalized,
        root_pc=root_pc,
        chord_pcs=chord_pcs,
        bass_pc=bass_pc,
        descriptor=descriptor,
        warning=warning,
    )
