"""Optional SoundFont-based renderer for AceFlow chord references.

This module is intentionally isolated so the existing internal renderer remains
available as a zero-regression fallback when no compatible .sf2 file is found
or if SoundFont rendering fails for any reason.
"""

from __future__ import annotations

import io
import time
import wave
from pathlib import Path
from typing import Optional

import numpy as np
from loguru import logger

from .chord_parser import ParsedChord
from .chord_voicing import choose_voicing
from .vendor import meltysynth as ms

_SOUND_FONT_EXTENSIONS = (".sf2",)
_DEFAULT_SAMPLE_RATE = 24000
_CHORD_CHANNEL_PIANO = 0
_BASS_CHANNEL = 1
_PATCH_ACOUSTIC_GRAND_PIANO = 0
_PATCH_ACOUSTIC_BASS = 32


def find_first_soundfont() -> Optional[Path]:
    """Return the first optional SoundFont file found in standard folders."""
    module_root = Path(__file__).resolve().parent
    for folder_name in ("soundfonts", "soundfont"):
        folder = module_root / folder_name
        if not folder.is_dir():
            logger.debug("[chord-sf2] folder missing: {}", folder)
            continue
        matches = []
        for ext in _SOUND_FONT_EXTENSIONS:
            matches.extend(sorted(folder.glob(f"*{ext}")))
            matches.extend(sorted(folder.glob(f"*{ext.upper()}")))
        deduped = []
        seen = set()
        for match in matches:
            key = str(match.resolve()) if match.exists() else str(match)
            if key in seen:
                continue
            deduped.append(match)
            seen.add(key)
        if not deduped:
            logger.debug("[chord-sf2] no soundfont found in {}", folder)
            continue
        if len(deduped) > 1:
            logger.warning(
                "[chord-sf2] multiple soundfonts found in {} -> using first alphabetically: {} | others: {}",
                folder,
                deduped[0].name,
                ", ".join(p.name for p in deduped[1:]),
            )
        else:
            logger.info("[chord-sf2] using soundfont: {}", deduped[0])
        return deduped[0]
    logger.info("[chord-sf2] no optional soundfont found under package root")
    return None


def render_soundfont_reference_wav_bytes(
    parsed_sequence: list[ParsedChord],
    requested: list[str],
    safe_bpm: float,
    beats_per_chord: int,
    beat_sec: float,
    chord_sec: float,
    total_duration: float,
) -> tuple[bytes, dict]:
    """Render the chord progression with an optional SoundFont, if available."""
    soundfont_path = find_first_soundfont()
    if soundfont_path is None:
        raise FileNotFoundError("No optional .sf2 file found in soundfonts/ or soundfont/.")

    started_at = time.perf_counter()
    logger.info(
        "[chord-sf2] render start file={} chords={} bpm={} beats_per_chord={} total_duration_sec={}",
        soundfont_path,
        len(parsed_sequence),
        round(float(safe_bpm), 3),
        int(max(1, beats_per_chord or 4)),
        round(float(total_duration), 3),
    )

    sample_rate = _DEFAULT_SAMPLE_RATE
    settings = ms.SynthesizerSettings(sample_rate)
    settings.maximum_polyphony = 12
    settings.enable_reverb_and_chorus = False
    sound_font = ms.SoundFont.from_file(str(soundfont_path))
    synth = ms.Synthesizer(sound_font, settings)

    preset_debug = {
        'piano': _describe_preset(sound_font, 0, _PATCH_ACOUSTIC_GRAND_PIANO),
        'bass': _describe_preset(sound_font, 0, _PATCH_ACOUSTIC_BASS),
    }
    logger.info(
        "[chord-sf2] preset resolution piano={} bass={} total_presets={}",
        preset_debug['piano'],
        preset_debug['bass'],
        len(sound_font.presets),
    )

    synth.process_midi_message(_CHORD_CHANNEL_PIANO, 0xC0, _PATCH_ACOUSTIC_GRAND_PIANO, 0)
    synth.process_midi_message(_BASS_CHANNEL, 0xC0, _PATCH_ACOUSTIC_BASS, 0)

    total_samples = max(1, int(round(sample_rate * total_duration)))
    left = ms.create_buffer(total_samples)
    right = ms.create_buffer(total_samples)

    prev_pad: Optional[list[int]] = None
    prev_bass: Optional[int] = None
    active_notes = {_CHORD_CHANNEL_PIANO: [], _BASS_CHANNEL: []}
    events = []
    write_index = 0

    for idx, chord in enumerate(parsed_sequence):
        start_sec = idx * chord_sec
        if start_sec >= total_duration:
            break
        dur_sec = min(chord_sec, total_duration - start_sec)
        if dur_sec <= 0:
            continue

        chord_start = max(0, min(total_samples, int(round(start_sec * sample_rate))))
        chord_end = max(chord_start, min(total_samples, int(round((start_sec + dur_sec) * sample_rate))))
        if chord_end <= chord_start:
            logger.debug(
                "[chord-sf2] skip zero-length chord index={} start={} end={} total_samples={}",
                idx,
                chord_start,
                chord_end,
                total_samples,
            )
            continue

        if write_index < chord_start:
            gap = chord_start - write_index
            synth.render(left, right, write_index, gap)
            write_index += gap
        elif write_index > chord_end:
            logger.warning(
                "[chord-sf2] write index already past chord window index={} write_index={} chord_end={} total_samples={}",
                idx,
                write_index,
                chord_end,
                total_samples,
            )
            continue

        bass_midi, pad_midis = choose_voicing(chord, prev_pad, prev_bass)
        prev_pad = pad_midis
        prev_bass = bass_midi

        for channel, notes in active_notes.items():
            for midi in notes:
                synth.note_off(channel, midi)
            active_notes[channel] = []

        bass_note = _fit_bass_range(bass_midi)
        piano_notes = [_fit_chord_range(m) for m in pad_midis]

        chord_write_index = write_index
        chord_remaining = max(0, chord_end - chord_write_index)

        bass_velocity = 58
        piano_velocities = [86, 80, 74, 70, 66]

        synth.note_on(_BASS_CHANNEL, bass_note, bass_velocity)
        active_notes[_BASS_CHANNEL].append(bass_note)
        for note_idx, midi in enumerate(piano_notes):
            velocity = piano_velocities[min(note_idx, len(piano_velocities) - 1)]
            synth.note_on(_CHORD_CHANNEL_PIANO, midi, velocity)
            active_notes[_CHORD_CHANNEL_PIANO].append(midi)

        if chord_remaining > 0:
            synth.render(left, right, chord_write_index, chord_remaining)
            chord_write_index += chord_remaining
            chord_remaining = 0

        write_index = chord_write_index
        events.append({
            'index': idx,
            'symbol': chord.original,
            'normalized': chord.normalized,
            'start_sec': round(start_sec, 4),
            'dur_sec': round(dur_sec, 4),
            'bass_midi': bass_midi,
            'pad_midis': pad_midis,
            'renderer': 'soundfont',
            'soundfont_bass_midi': bass_note,
            'soundfont_piano_midis': piano_notes,
            'soundfont_layers': ['bass', 'piano'],
            'write_index': int(write_index),
            'chord_start_sample': int(chord_start),
            'chord_end_sample': int(chord_end),
        })

    if write_index < total_samples:
        synth.render(left, right, write_index, total_samples - write_index)

    pcm = ((np.asarray(left, dtype=np.float32) + np.asarray(right, dtype=np.float32)) * 0.5).astype(np.float32)
    _post_process_pcm(pcm, sample_rate)
    pcm16 = np.clip(np.round(pcm * 32767.0), -32768, 32767).astype(np.int16)
    bio = io.BytesIO()
    with wave.open(bio, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())
    sf_info = sound_font.info
    elapsed = time.perf_counter() - started_at
    logger.info(
        "[chord-sf2] render done file={} samples={} written_samples={} sample_rate={} elapsed_sec={}",
        soundfont_path,
        total_samples,
        write_index,
        sample_rate,
        round(elapsed, 3),
    )
    return bio.getvalue(), {
        'sample_rate': sample_rate,
        'bpm': safe_bpm,
        'beats_per_chord': int(max(1, beats_per_chord or 4)),
        'input_chords': requested,
        'rendered_events': events,
        'total_duration_sec': round(total_duration, 4),
        'renderer': 'soundfont',
        'render_elapsed_sec': round(elapsed, 4),
        'soundfont_path': str(soundfont_path),
        'soundfont_bank_name': getattr(sf_info, 'bank_name', '') or '',
        'soundfont_author': getattr(sf_info, 'author', '') or '',
        'soundfont_presets': preset_debug,
        'soundfont_layers': ['bass', 'piano'],
        'soundfont_strategy': 'mirror_internal_voicing_minimal_layers',
        'loop_count': 1,
    }


def _describe_preset(sound_font: ms.SoundFont, bank: int, patch: int) -> dict:
    resolved = None
    gm_fallback = False
    default_fallback = False
    for preset in sound_font.presets:
        if preset.bank_number == bank and preset.patch_number == patch:
            resolved = preset
            break
    if resolved is None and bank != 0:
        for preset in sound_font.presets:
            if preset.bank_number == 0 and preset.patch_number == patch:
                resolved = preset
                gm_fallback = True
                break
    if resolved is None and sound_font.presets:
        resolved = sound_font.presets[0]
        default_fallback = True
    info = {
        'requested_bank': int(bank),
        'requested_patch_zero_based': int(patch),
        'requested_patch_gm_1_based': int(patch) + 1,
        'resolved': bool(resolved is not None),
        'gm_bank_fallback': bool(gm_fallback),
        'default_preset_fallback': bool(default_fallback),
    }
    if resolved is not None:
        info.update({
            'resolved_name': getattr(resolved, 'name', '') or '',
            'resolved_bank': int(getattr(resolved, 'bank_number', 0) or 0),
            'resolved_patch_zero_based': int(getattr(resolved, 'patch_number', 0) or 0),
            'resolved_patch_gm_1_based': int(getattr(resolved, 'patch_number', 0) or 0) + 1,
        })
    return info


def _render_note_step(synth, left, right, write_index: int, remaining: int, channel: int, midi: int, velocity: int, step_samples: int) -> int:
    if remaining <= 0:
        return write_index
    synth.note_on(channel, midi, max(1, min(int(velocity), 127)))
    chunk = min(step_samples, remaining)
    synth.render(left, right, write_index, chunk)
    return write_index + chunk


def _fit_bass_range(midi: int) -> int:
    return int(max(31, min(43, midi)))


def _fit_chord_range(midi: int) -> int:
    return int(max(58, min(82, midi)))


def _fit_pad_range(midi: int) -> int:
    return int(max(70, min(91, midi)))


def _post_process_pcm(pcm: np.ndarray, sample_rate: int) -> None:
    if pcm.size <= 0:
        return
    fade = min(int(sample_rate * 0.02), max(1, pcm.size // 12))
    if fade > 1:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        pcm[:fade] *= ramp
        pcm[-fade:] *= ramp[::-1]
    peak = float(np.max(np.abs(pcm))) if pcm.size else 0.0
    if peak > 0:
        pcm *= min(0.92 / peak, 1.0)


def _guide_bar_beats(beats_per_chord: int) -> int:
    beats = max(1, int(beats_per_chord or 4))
    if beats >= 4:
        return 4
    return beats


def _choose_guitar_notes(pad_midis: list[int]) -> list[int]:
    if not pad_midis:
        return [64, 67, 71]
    core = list(pad_midis[:3])
    while len(core) < 3:
        core.append(core[-1] + 3)
    voiced = []
    for idx, midi in enumerate(core[:3]):
        bump = 2 if idx == 0 else (5 if idx == 1 else 9)
        voiced.append(_fit_guitar_range(midi + bump))
    return voiced


def _basic_drum_pattern(bar_beats: int, beat_in_bar: int) -> list[tuple[int, int]]:
    kick = 36
    snare = 38
    closed_hat = 42
    open_hat = 46
    hits: list[tuple[int, int]] = []
    if bar_beats >= 4:
        if beat_in_bar == 0:
            hits.append((kick, 88))
            hits.append((closed_hat, 54))
        elif beat_in_bar == 1:
            hits.append((snare, 78))
            hits.append((closed_hat, 50))
        elif beat_in_bar == 2:
            hits.append((kick, 76))
            hits.append((closed_hat, 52))
        else:
            hits.append((snare, 82))
            hits.append((open_hat, 48))
    elif bar_beats == 3:
        if beat_in_bar == 0:
            hits.append((kick, 86))
            hits.append((closed_hat, 52))
        elif beat_in_bar == 1:
            hits.append((closed_hat, 48))
        else:
            hits.append((snare, 78))
            hits.append((open_hat, 44))
    elif bar_beats == 2:
        if beat_in_bar == 0:
            hits.append((kick, 86))
            hits.append((closed_hat, 52))
        else:
            hits.append((snare, 80))
            hits.append((open_hat, 44))
    else:
        if beat_in_bar == 0:
            hits.append((kick, 84))
            hits.append((closed_hat, 48))
    return hits


def _fit_guitar_range(midi: int) -> int:
    return int(max(62, min(81, midi)))
