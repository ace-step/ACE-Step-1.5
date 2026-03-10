"""Voicing selection helpers for AceFlow chord references."""

from __future__ import annotations

from typing import Optional

from .chord_parser import ParsedChord

_BASS_LOW = 31
_BASS_HIGH = 43
_CHORD_LOW = 55
_CHORD_HIGH = 76
_CHORD_CENTER = 64.0


_DESCRIPTOR_INTERVALS = {
    "maj": [0, 4, 7, 12],
    "min": [0, 3, 7, 12],
    "maj7": [0, 4, 7, 11],
    "min7": [0, 3, 7, 10],
    "dom7": [0, 4, 7, 10],
    "dim": [0, 3, 6, 12],
    "dim7": [0, 3, 6, 9],
    "aug": [0, 4, 8, 12],
    "sus2": [0, 2, 7, 12],
    "sus4": [0, 5, 7, 12],
    "add9": [0, 4, 7, 14],
    "6": [0, 4, 7, 9],
    "min6": [0, 3, 7, 9],
    "9": [0, 4, 10, 14],
    "maj9": [0, 4, 11, 14],
    "min9": [0, 3, 10, 14],
    "7#5": [0, 4, 8, 10],
}


def _pitch_candidates(pc: int, lo: int, hi: int) -> list[int]:
    return [midi for midi in range(lo, hi + 1) if midi % 12 == pc]


def _nearest_pitch_class(pc: int, target: float, lo: int, hi: int) -> int:
    candidates = _pitch_candidates(pc, lo, hi)
    if not candidates:
        base = int(round(target))
        while base < lo:
            base += 12
        while base > hi:
            base -= 12
        return max(lo, min(hi, base))
    return min(candidates, key=lambda midi: (abs(midi - target), abs(midi - int(target))))


def _choose_bass_midi(chord: ParsedChord, previous: Optional[int]) -> int:
    target = previous if previous is not None else 36.0
    if chord.bass_pc != chord.root_pc:
        target = min(target, 38.0)
    return _nearest_pitch_class(chord.bass_pc, target, _BASS_LOW, _BASS_HIGH)


def _descriptor_shell(chord: ParsedChord) -> list[int]:
    base = list(_DESCRIPTOR_INTERVALS.get(chord.descriptor, [0, 4, 7, 12]))
    # Keep the harmonic identity obvious. Fifths are optional for dense colors.
    if chord.descriptor in {"9", "maj9", "min9"}:
        essential = [base[0], base[1], base[2], base[3] if len(base) > 3 else 10]
        if len(base) > 4:
            essential.append(base[4])
        return essential
    if chord.descriptor in {"maj7", "min7", "dom7", "7#5"}:
        return [base[0], base[1], base[2], base[3]]
    if chord.descriptor in {"add9", "6", "min6"}:
        return [base[0], base[1], base[2], base[3]]
    return base[:4]


def _normalize_strictly_ascending(notes: list[int]) -> list[int]:
    if not notes:
        return []
    out = [int(notes[0])]
    for midi in notes[1:]:
        value = int(midi)
        while value <= out[-1]:
            value += 12
        out.append(value)
    return out


def _fit_range(notes: list[int], lo: int, hi: int, center: float) -> list[int]:
    voiced = _normalize_strictly_ascending(notes)
    if not voiced:
        return [60, 64, 67]
    best = None
    best_score = None
    for shift in range(-3, 4):
        shifted = _normalize_strictly_ascending([m + 12 * shift for m in voiced])
        low_penalty = max(0, lo - shifted[0]) * 8.0
        high_penalty = max(0, shifted[-1] - hi) * 8.0
        center_penalty = abs((sum(shifted) / len(shifted)) - center)
        score = low_penalty + high_penalty + center_penalty
        if best is None or score < best_score:
            best = shifted
            best_score = score
    voiced = list(best)
    for idx in range(len(voiced)):
        while voiced[idx] < lo and voiced[idx] + 12 <= hi:
            voiced[idx] += 12
        while voiced[idx] > hi and voiced[idx] - 12 >= lo:
            voiced[idx] -= 12
    voiced = _normalize_strictly_ascending(voiced)
    while voiced and voiced[0] < lo:
        voiced = [m + 12 for m in voiced]
        voiced = _normalize_strictly_ascending(voiced)
        if voiced[-1] > hi:
            break
    while voiced and voiced[-1] > hi:
        voiced = [m - 12 for m in voiced]
        voiced = _normalize_strictly_ascending(voiced)
        if voiced[0] < lo:
            break
    return _normalize_strictly_ascending(voiced)


def _match_previous(candidate: list[int], previous_pad: Optional[list[int]]) -> list[int]:
    if not previous_pad:
        return _fit_range(candidate, _CHORD_LOW, _CHORD_HIGH, _CHORD_CENTER)
    prev = list(previous_pad)
    out: list[int] = []
    for idx, midi in enumerate(candidate):
        target = prev[min(idx, len(prev) - 1)]
        choices = [midi + 12 * shift for shift in range(-2, 3)]
        value = min(choices, key=lambda v: abs(v - target))
        if out and value <= out[-1]:
            while value <= out[-1]:
                value += 12
        out.append(value)
    return _fit_range(out, _CHORD_LOW, _CHORD_HIGH, _CHORD_CENTER)


def _candidate_roots(chord: ParsedChord, previous_pad: Optional[list[int]]) -> list[int]:
    target = previous_pad[0] if previous_pad else 60.0
    roots = _pitch_candidates(chord.root_pc, 48, 64)
    if not roots:
        roots = [60]
    return sorted(roots, key=lambda midi: (abs(midi - max(54.0, min(62.0, target))), abs(midi - 60)))


def _build_candidates(chord: ParsedChord, previous_pad: Optional[list[int]], bass_midi: int) -> list[list[int]]:
    shell = _descriptor_shell(chord)
    roots = _candidate_roots(chord, previous_pad)
    candidates: list[list[int]] = []
    seen = set()
    for root in roots[:4]:
        base = [root + interval for interval in shell]
        variants = [base]
        if len(base) >= 4:
            # More open but still root-anchored.
            variants.append([base[0], base[1] + 12, base[2], base[3]])
            variants.append([base[0], base[1], base[2] + 12, base[3]])
        if chord.descriptor in {"maj", "min", "sus2", "sus4", "dim", "aug"}:
            variants.append([base[0], base[1], base[2], base[0] + 12])
        for variant in variants:
            voiced = _match_previous(variant, previous_pad)
            if voiced[0] - bass_midi < 12:
                voiced = [m + 12 for m in voiced]
                voiced = _fit_range(voiced, _CHORD_LOW, _CHORD_HIGH, _CHORD_CENTER)
            key = tuple(voiced)
            if key not in seen:
                seen.add(key)
                candidates.append(voiced)
    return candidates or [[60, 64, 67, 72]]


def _voicing_score(notes: list[int], chord: ParsedChord, previous_pad: Optional[list[int]], bass_midi: int) -> float:
    score = 0.0
    pcs = {n % 12 for n in notes}
    required = set(chord.chord_pcs)
    third_pc = None
    if chord.descriptor.startswith("min"):
        third_pc = (chord.root_pc + 3) % 12
    elif chord.descriptor.startswith("sus2"):
        third_pc = (chord.root_pc + 2) % 12
    elif chord.descriptor.startswith("sus4"):
        third_pc = (chord.root_pc + 5) % 12
    elif chord.descriptor != "dim":
        third_pc = (chord.root_pc + 4) % 12

    missing = required - pcs
    score += len(missing) * 7.0
    if chord.root_pc not in pcs:
        score += 10.0
    if third_pc is not None and third_pc not in pcs:
        score += 8.0

    center = sum(notes) / len(notes)
    spread = notes[-1] - notes[0]
    score += abs(center - _CHORD_CENTER) * 0.45
    score += abs(spread - 14.0) * 0.35

    if notes[0] < 57:
        score += (57 - notes[0]) * 1.5

    low_gap = notes[0] - bass_midi
    if low_gap < 12:
        score += (12 - low_gap) * 3.0
    if low_gap > 24:
        score += (low_gap - 24) * 0.6

    for idx in range(1, len(notes)):
        gap = notes[idx] - notes[idx - 1]
        if gap < 3:
            score += (3 - gap) * 3.0
        if gap > 8:
            score += (gap - 8) * 1.1

    if previous_pad:
        movement = 0.0
        for idx, midi in enumerate(notes):
            target = previous_pad[min(idx, len(previous_pad) - 1)]
            movement += abs(midi - target)
        score += movement * 0.6
    return score


def choose_voicing(
    chord: ParsedChord,
    previous_pad: Optional[list[int]],
    previous_bass: Optional[int],
) -> tuple[int, list[int]]:
    bass_midi = _choose_bass_midi(chord, previous_bass)
    candidates = _build_candidates(chord, previous_pad, bass_midi)
    best_pad = min(candidates, key=lambda notes: _voicing_score(notes, chord, previous_pad, bass_midi))
    return bass_midi, best_pad
