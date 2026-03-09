"""Waveform synthesis helpers for AceFlow chord references."""

from __future__ import annotations

import io
import math
import wave
from typing import Optional

import numpy as np

from .chord_parser import ParsedChord, parse_chord_symbol
from .chord_voicing import choose_voicing

MAX_RENDER_DURATION_SEC = 600.0


def midi_to_freq(midi: float) -> float:
    """Convert a MIDI note number to frequency in hertz."""
    return 440.0 * (2.0 ** ((float(midi) - 69.0) / 12.0))


def _warning_debug_entry(symbol: str, parsed: Optional[ParsedChord], reason: str, fallback: str) -> dict:
    """Create debug metadata for a fallback or warning event."""
    entry = {'symbol': str(symbol or ''), 'reason': str(reason or ''), 'fallback': str(fallback or '')}
    if parsed is not None:
        entry['normalized_input'] = parsed.normalized
        entry['resolved_descriptor'] = parsed.descriptor
    return entry


def _envelope(length: int, sr: int, attack: float, decay: float, sustain: float, release: float) -> np.ndarray:
    """Generate a simple ADSR envelope."""
    if length <= 1:
        return np.ones(max(length, 1), dtype=np.float32)
    attack_n = max(1, int(sr * max(0.001, attack)))
    decay_n = max(1, int(sr * max(0.001, decay)))
    release_n = max(1, int(sr * max(0.001, release)))
    sustain_n = max(0, length - attack_n - decay_n - release_n)
    env = np.concatenate([
        np.linspace(0.0, 1.0, attack_n, endpoint=False, dtype=np.float32),
        np.linspace(1.0, sustain, decay_n, endpoint=False, dtype=np.float32),
        np.full(sustain_n, sustain, dtype=np.float32),
        np.linspace(sustain, 0.0, release_n, endpoint=True, dtype=np.float32),
    ])
    if env.size < length:
        env = np.pad(env, (0, length - env.size), mode='constant')
    return env[:length]


def _bass_tone(freq: float, t: np.ndarray) -> np.ndarray:
    """Generate the bass oscillator blend."""
    return (
        np.sin(2 * np.pi * freq * t)
        + 0.22 * np.sin(2 * np.pi * freq * 2.0 * t)
        + 0.08 * np.sin(2 * np.pi * freq * 3.0 * t)
    ) / 1.3


def _chord_tone(freq: float, t: np.ndarray) -> np.ndarray:
    """Generate the pad oscillator blend."""
    tri = (2.0 / np.pi) * np.arcsin(np.sin(2 * np.pi * freq * t))
    sine = np.sin(2 * np.pi * freq * t)
    return (0.68 * tri + 0.32 * sine + 0.12 * np.sin(2 * np.pi * freq * 2.0 * t) + 0.04 * np.sin(2 * np.pi * freq * 3.0 * t)) / 1.16


def _add_signal(buffer: np.ndarray, signal: np.ndarray, start: int) -> None:
    """Mix a signal into the output buffer starting at a given sample offset."""
    if start >= buffer.size or signal.size <= 0:
        return
    end = min(buffer.size, start + signal.size)
    buffer[start:end] += signal[: end - start]


def synthesize_reference_wav_bytes(
    chords: list[str],
    bpm: float = 120.0,
    beats_per_chord: int = 4,
    target_duration_sec: Optional[float] = None,
) -> tuple[bytes, dict]:
    """Render a mono chord-reference WAV in memory and return debug metadata."""
    sample_rate = 44100
    safe_bpm = max(48.0, min(220.0, float(bpm or 120.0)))
    beat_sec = 60.0 / safe_bpm
    chord_sec = max(beat_sec * 2.0, beat_sec * max(1, int(beats_per_chord or 4)))
    requested = [str(item or '').strip() for item in (chords or []) if str(item or '').strip()]
    parsed_sequence: list[ParsedChord] = []
    warnings = []
    warning_debug = []
    for symbol in (requested or ['Cmaj7', 'Am7', 'Fmaj7', 'G']):
        parsed = parse_chord_symbol(symbol)
        if parsed is None:
            fallback_parsed = parse_chord_symbol('C')
            warnings.append({'symbol': symbol, 'reason': 'unparsed', 'fallback': 'C'})
            warning_debug.append(_warning_debug_entry(symbol, fallback_parsed, 'unparsed', 'C'))
            parsed = fallback_parsed
        elif parsed.warning:
            warnings.append({'symbol': symbol, 'reason': parsed.warning, 'fallback': parsed.descriptor})
            warning_debug.append(_warning_debug_entry(symbol, parsed, parsed.warning, parsed.descriptor))
        parsed_sequence.append(parsed)
    return _render_progression(parsed_sequence, requested, safe_bpm, beats_per_chord, beat_sec, chord_sec, target_duration_sec, sample_rate, warnings, warning_debug)


def _render_progression(
    parsed_sequence: list[ParsedChord],
    requested: list[str],
    safe_bpm: float,
    beats_per_chord: int,
    beat_sec: float,
    chord_sec: float,
    target_duration_sec: Optional[float],
    sample_rate: int,
    warnings: list[dict],
    warning_debug: list[dict],
) -> tuple[bytes, dict]:
    """Render parsed chord events into a PCM WAV payload and metadata."""
    base_duration = len(parsed_sequence) * chord_sec
    requested_duration = max(base_duration, float(target_duration_sec or 0.0))
    capped_duration = min(requested_duration, MAX_RENDER_DURATION_SEC)
    if requested_duration > capped_duration:
        warnings.append({'symbol': '', 'reason': 'duration_truncated', 'fallback': str(MAX_RENDER_DURATION_SEC)})
        warning_debug.append({'symbol': '', 'reason': 'duration_truncated', 'fallback': str(MAX_RENDER_DURATION_SEC), 'requested_duration_sec': round(requested_duration, 4), 'capped_duration_sec': round(capped_duration, 4)})
    loop_count = max(1, math.ceil(capped_duration / max(base_duration, 0.001)))
    expanded = parsed_sequence * loop_count
    total_duration = max(base_duration, capped_duration)
    total_samples = max(1, int(sample_rate * total_duration))
    pcm = np.zeros(total_samples, dtype=np.float32)
    events = _render_events(pcm, expanded, total_duration, chord_sec, beat_sec, sample_rate)
    _apply_output_gain(pcm, sample_rate, total_samples)
    pcm16 = np.clip(np.round(pcm * 32767.0), -32768, 32767).astype(np.int16)
    bio = io.BytesIO()
    with wave.open(bio, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())
    return bio.getvalue(), {'sample_rate': sample_rate, 'bpm': safe_bpm, 'beats_per_chord': int(max(1, beats_per_chord or 4)), 'input_chords': requested, 'warnings': warnings, 'warning_count': len(warning_debug), 'warning_debug': warning_debug, 'rendered_events': events, 'total_duration_sec': round(total_duration, 4), 'loop_count': loop_count}


def _render_events(pcm: np.ndarray, expanded: list[ParsedChord], total_duration: float, chord_sec: float, beat_sec: float, sample_rate: int) -> list[dict]:
    """Render each chord event into the output PCM buffer."""
    prev_pad = None
    prev_bass = None
    events = []
    for idx, chord in enumerate(expanded):
        start_sec = idx * chord_sec
        if start_sec >= total_duration:
            break
        dur_sec = min(chord_sec, total_duration - start_sec)
        start = int(start_sec * sample_rate)
        bass_midi, pad_midis = choose_voicing(chord, prev_pad, prev_bass)
        prev_pad = pad_midis
        prev_bass = bass_midi
        _render_bass(pcm, start, dur_sec, sample_rate, bass_midi)
        _render_pad(pcm, start, dur_sec, beat_sec, sample_rate, pad_midis)
        events.append({'index': idx, 'symbol': chord.original, 'normalized': chord.normalized, 'start_sec': round(start_sec, 4), 'dur_sec': round(dur_sec, 4), 'bass_midi': bass_midi, 'pad_midis': pad_midis})
    return events


def _render_bass(pcm: np.ndarray, start: int, dur_sec: float, sample_rate: int, bass_midi: int) -> None:
    """Render the bass layer for one chord event."""
    bass_len = max(1, int(sample_rate * max(0.18, dur_sec - 0.06)))
    bass_t = np.arange(bass_len, dtype=np.float32) / sample_rate
    bass_env = _envelope(bass_len, sample_rate, 0.012, 0.09, 0.82, 0.12)
    bass_sig = 0.23 * _bass_tone(midi_to_freq(bass_midi), bass_t) * bass_env
    _add_signal(pcm, bass_sig.astype(np.float32), start)


def _render_pad(pcm: np.ndarray, start: int, dur_sec: float, beat_sec: float, sample_rate: int, pad_midis: list[int]) -> None:
    """Render the sustained pad and refresh accents for one chord event."""
    chord_len = max(1, int(sample_rate * max(0.22, dur_sec - 0.04)))
    chord_t = np.arange(chord_len, dtype=np.float32) / sample_rate
    chord_env = _envelope(chord_len, sample_rate, 0.02, 0.12, 0.88, 0.16)
    for note_idx, midi in enumerate(pad_midis):
        stagger = int(sample_rate * 0.004 * note_idx)
        amp = 0.105 if note_idx == 0 else 0.12
        sig = amp * _chord_tone(midi_to_freq(midi), chord_t) * chord_env
        _add_signal(pcm, sig.astype(np.float32), start + stagger)
    if dur_sec < beat_sec * 3.25:
        return
    refresh_start = start + int(sample_rate * beat_sec * 2.5)
    refresh_len = max(1, int(sample_rate * min(beat_sec * 0.8, max(0.15, dur_sec - beat_sec * 2.5))))
    refresh_t = np.arange(refresh_len, dtype=np.float32) / sample_rate
    refresh_env = _envelope(refresh_len, sample_rate, 0.01, 0.06, 0.72, 0.10)
    for note_idx, midi in enumerate(pad_midis[:3]):
        sig = 0.045 * _chord_tone(midi_to_freq(midi), refresh_t) * refresh_env
        _add_signal(pcm, sig.astype(np.float32), refresh_start + int(sample_rate * 0.005 * note_idx))


def _apply_output_gain(pcm: np.ndarray, sample_rate: int, total_samples: int) -> None:
    """Apply fade-in, fade-out, and peak normalization to the PCM buffer."""
    fade = min(int(sample_rate * 0.02), max(1, total_samples // 12))
    if fade > 1:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        pcm[:fade] *= ramp
        pcm[-fade:] *= ramp[::-1]
    peak = float(np.max(np.abs(pcm))) if pcm.size else 0.0
    if peak > 0:
        pcm *= min(0.92 / peak, 1.0)
