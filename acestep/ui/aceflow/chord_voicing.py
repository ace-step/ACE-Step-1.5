"""Voicing selection helpers for AceFlow chord references."""

from __future__ import annotations

from itertools import product
from typing import Optional

from .chord_parser import ParsedChord

_PAD_LOW = 50
_PAD_HIGH = 79
_PAD_CENTER = 64.0


def _pitch_candidates(pc: int, lo: int, hi: int) -> list[int]:
    """Return all MIDI notes with a given pitch class inside a range."""
    return [midi for midi in range(lo, hi + 1) if midi % 12 == pc]


def _best_bass_midi(pc: int, previous: Optional[int]) -> int:
    """Pick a bass note one octave deeper while preserving smooth movement."""
    candidates = _pitch_candidates(pc, 24, 43)
    target = previous if previous is not None else 31
    return min(candidates, key=lambda midi: (abs(midi - target), abs(midi - 31)))


def _descriptor_targets(chord: ParsedChord) -> tuple[int, int, float, bool]:
    """Return target voice count, target spread, top-register lift, and root preference."""
    desc = chord.descriptor
    if desc in {'maj7', 'min7', 'dom7', 'dim7', '9', 'maj9', 'min9', '7#5'}:
        return 4, 15, 4.0, False
    if desc in {'6', 'min6', 'add9'}:
        return 4, 14, 3.0, True
    if desc in {'sus2', 'sus4', 'aug'}:
        return 3, 13, 2.0, True
    return 3, 12, 2.0, True


def _build_interval_patterns(chord: ParsedChord) -> list[list[int]]:
    """Build candidate interval layouts for a chord before octave placement."""
    intervals = sorted({(pc - chord.root_pc) % 12 for pc in chord.chord_pcs})
    target_len, _, _, prefer_root_low = _descriptor_targets(chord)
    patterns: list[list[int]] = []
    seen = set()

    def add_pattern(values: list[int]) -> None:
        key = tuple(values)
        if len(values) >= 3 and key not in seen:
            seen.add(key)
            patterns.append(values)

    if len(intervals) >= target_len:
        for inversion in range(len(intervals)):
            rotated = intervals[inversion:] + [value + 12 for value in intervals[:inversion]]
            add_pattern(rotated[:target_len])
    else:
        base = list(intervals)
        extension_pool = [0, 7, 3, 4, 10, 11, 2, 5, 8, 9, 6]
        extras: list[int] = []
        for interval in extension_pool:
            normalized = interval % 12
            if normalized in intervals:
                extras.append(normalized)
            if len(base) + len(extras) >= target_len:
                break
        merged = base + extras
        while len(merged) < target_len:
            merged.append(0)
        for inversion in range(len(base)):
            rotated = merged[inversion:] + [value + 12 for value in merged[:inversion]]
            add_pattern(rotated[:target_len])

    if prefer_root_low and intervals:
        compact = list(intervals[:target_len])
        if compact and compact[0] != 0:
            compact = [0] + compact
        add_pattern(sorted(compact[:target_len]))

    upper_pool = [value + 12 for value in intervals if value != 0]
    for pattern in list(patterns):
        if len(pattern) == 3 and upper_pool:
            for extra in upper_pool:
                add_pattern(sorted(pattern + [extra]))
                break

    return patterns or [[0, 4, 7]]


def _place_pattern(root_midi: int, pattern: list[int]) -> list[int]:
    """Place interval pattern on a root MIDI note and keep it ascending."""
    notes: list[int] = []
    for interval in pattern:
        midi = root_midi + interval
        while notes and midi <= notes[-1]:
            midi += 12
        notes.append(midi)
    return notes


def _fit_voicing_range(notes: list[int]) -> list[int]:
    """Shift a voiced chord into the preferred pad register while preserving order."""
    voiced = list(notes)
    if not voiced:
        return [60, 64, 67]
    center = sum(voiced) / len(voiced)
    while center < _PAD_CENTER - 3.0:
        voiced = [m + 12 for m in voiced]
        center = sum(voiced) / len(voiced)
    while center > _PAD_CENTER + 3.0:
        voiced = [m - 12 for m in voiced]
        center = sum(voiced) / len(voiced)
    while voiced[0] < _PAD_LOW:
        voiced = [m + 12 for m in voiced]
    while voiced[-1] > _PAD_HIGH:
        voiced = [m - 12 for m in voiced]
    if voiced[0] < _PAD_LOW:
        shift = _PAD_LOW - voiced[0]
        voiced = [m + shift for m in voiced]
    if voiced[-1] > _PAD_HIGH:
        shift = voiced[-1] - _PAD_HIGH
        voiced = [m - shift for m in voiced]
    fixed = [voiced[0]]
    for midi in voiced[1:]:
        while midi <= fixed[-1]:
            midi += 12
        fixed.append(midi)
    return [max(_PAD_LOW, min(_PAD_HIGH, midi)) for midi in fixed]


def _drop2_variant(notes: list[int]) -> Optional[list[int]]:
    """Return a drop-2 style variant when it fits the register safely."""
    if len(notes) < 4:
        return None
    variant = list(notes)
    variant[-2] -= 12
    variant = sorted(variant)
    if variant[0] < _PAD_LOW:
        return None
    for idx in range(1, len(variant)):
        if variant[idx] - variant[idx - 1] < 2:
            return None
    return variant


def _respell_for_previous(notes: list[int], previous_pad: Optional[list[int]]) -> list[int]:
    """Move notes by octaves near previous voices to encourage smooth voice leading."""
    if not previous_pad:
        return notes
    targets = _resample_previous(previous_pad, len(notes))
    adjusted = sorted(notes)
    for idx, target in enumerate(targets):
        midi = adjusted[idx]
        best = min((midi + 12 * k for k in range(-2, 3)), key=lambda value: abs(value - target))
        adjusted[idx] = best
    adjusted.sort()
    for idx in range(1, len(adjusted)):
        while adjusted[idx] <= adjusted[idx - 1]:
            adjusted[idx] += 12
    return _fit_voicing_range(adjusted)


def _resample_previous(previous_pad: list[int], voice_count: int) -> list[int]:
    """Map a previous voicing to a new voice count for movement scoring."""
    if not previous_pad:
        return [60, 64, 67][:voice_count] or [60]
    if len(previous_pad) == voice_count:
        return list(previous_pad)
    if voice_count == 1:
        return [round(sum(previous_pad) / len(previous_pad))]
    out: list[int] = []
    max_idx = len(previous_pad) - 1
    for idx in range(voice_count):
        pos = (idx / max(1, voice_count - 1)) * max_idx
        low = int(pos)
        high = min(max_idx, low + 1)
        frac = pos - low
        value = previous_pad[low] * (1.0 - frac) + previous_pad[high] * frac
        out.append(int(round(value)))
    return out


def _voice_leading_score(notes: list[int], chord: ParsedChord, previous_pad: Optional[list[int]]) -> float:
    """Score a voiced chord for smooth movement and healthy spacing."""
    target_len, target_spread, target_lift, prefer_root_low = _descriptor_targets(chord)
    prev = _resample_previous(previous_pad or [60, 64, 67], len(notes))
    center = sum(notes) / len(notes)
    spread = notes[-1] - notes[0]
    movement = sum(abs(notes[idx] - prev[idx]) for idx in range(len(notes)))
    max_leap = max(abs(notes[idx] - prev[idx]) for idx in range(len(notes)))
    lowest_gap = notes[1] - notes[0] if len(notes) >= 2 else 7
    upper_gap_penalty = sum(max(0, 3 - (notes[idx] - notes[idx - 1])) for idx in range(2, len(notes)))
    common_tones = sum(1 for note in notes if any(abs(note - old) <= 1 and note % 12 == old % 12 for old in prev))
    top_lift = notes[-1] - center
    root_pc_present = chord.root_pc in {note % 12 for note in notes}

    score = 0.0
    score += abs(center - _PAD_CENTER) * 0.65
    score += abs(spread - target_spread) * 0.35
    score += movement * 0.9
    score += max(0.0, max_leap - 5.0) * 1.8
    score += max(0.0, 4.0 - lowest_gap) * 1.6
    score += upper_gap_penalty * 1.4
    score += abs(top_lift - target_lift) * 0.7
    score -= common_tones * 1.35
    if prefer_root_low and not root_pc_present:
        score += 5.0
    if not prefer_root_low and len(notes) >= 4 and notes[0] % 12 == chord.root_pc:
        score += 1.25
    if notes[0] < 53 and lowest_gap < 5:
        score += 2.0
    if notes[-1] > 77:
        score += (notes[-1] - 77) * 0.8
    return score + abs(len(notes) - target_len) * 2.0


def _generate_candidate_voicings(chord: ParsedChord, previous_pad: Optional[list[int]]) -> list[list[int]]:
    """Generate candidate pad voicings for a chord."""
    patterns = _build_interval_patterns(chord)
    candidate_roots = _pitch_candidates(chord.root_pc, 48, 65) or [60]
    prev_center = sum(previous_pad) / len(previous_pad) if previous_pad else _PAD_CENTER
    roots_ranked = sorted(candidate_roots, key=lambda midi: abs(midi - max(52.0, min(62.0, prev_center - 3.0))))
    candidates: list[list[int]] = []
    seen = set()
    for root_midi in roots_ranked[:6]:
        for pattern in patterns:
            base = _fit_voicing_range(_place_pattern(root_midi, pattern))
            variants = [base]
            drop2 = _drop2_variant(base)
            if drop2 is not None:
                variants.append(drop2)
            for variant in variants:
                voiced = _respell_for_previous(variant, previous_pad)
                key = tuple(voiced)
                if key not in seen:
                    seen.add(key)
                    candidates.append(voiced)
    return candidates or [[60, 64, 67]]


def choose_voicing(
    chord: ParsedChord,
    previous_pad: Optional[list[int]],
    previous_bass: Optional[int],
) -> tuple[int, list[int]]:
    """Choose a bass note and voiced pad for a parsed chord with smoother movement."""
    bass_midi = _best_bass_midi(chord.bass_pc, previous_bass)
    candidates = _generate_candidate_voicings(chord, previous_pad)
    best_pad = min(candidates, key=lambda notes: _voice_leading_score(notes, chord, previous_pad))
    return bass_midi, best_pad
