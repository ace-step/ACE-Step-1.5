---
date: 2026-03-08
topic: library-audio-player
---

# Phase 2: Library, Audio Player & Track Management

## What We're Building

A full-featured music library with project-based organization, pro waveform player,
A/B comparison workflow, and linked regeneration from any track's original params.
This replaces the placeholder "Library" section in the Phase 1 MVP with a real
track management and audio evaluation experience.

## Why This Approach

We considered four levels of library complexity:
- **History archive** — too passive, no organization
- **Curated collection** — limited without search/filter
- **Production workspace** — tags add complexity without clear project structure
- **Full-featured (chosen)** — projects/folders provide natural hierarchy, pro waveform
  enables serious audio evaluation, A/B comparison supports iterative refinement

Projects/folders chosen over flat+tags or smart collections because they match
the mental model of a creative workspace (like a DAW) rather than a media player.

## Key Decisions

- **Organization: Projects/folders** with drag-and-drop, hierarchical structure,
  default "Unsorted" project for new generations
- **Audio player: Pro waveform** with spectrogram toggle, A/B loop points, zoom,
  click-to-seek with playhead animation
- **Track management: A/B comparison** with side-by-side playback, synced or
  independent seek, winner/loser marking for iterative refinement
- **Generation link: Regenerate button** on any track pre-fills Generate tab with
  original params (prompt, BPM, key, duration, model settings)
- **Waveform tech: Canvas + Web Audio API** — decodeAudioData for waveform,
  FFT for spectrogram, no heavy dependencies
- **Storage: SQLite** — existing schema already has projects/tracks tables,
  store full GenerationParams JSON blob per track for regeneration

## Open Questions

- A/B comparison: dedicated view/modal vs. inline in Library?
- Audio file storage: app data folder vs. user-selected directory?

## Next Steps

Proceed to implementation planning.
