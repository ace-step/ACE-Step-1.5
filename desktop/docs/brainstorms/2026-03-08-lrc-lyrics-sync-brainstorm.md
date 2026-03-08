---
date: 2026-03-08
topic: lrc-lyrics-sync
---

# LRC / Lyrics Sync

## What We're Building

A lyrics synchronization system integrated into the Library's track detail view. When a user clicks a track, a detail panel opens showing the full waveform with a lyrics timeline lane below it. AI generates initial timestamps via Whisper-based forced alignment on the backend, then users can manually refine timing by dragging lyric markers on the waveform.

## Why This Approach

- **AI + manual refine**: Whisper gives accurate initial alignment; manual editor handles edge cases
- **Library-integrated**: Keeps workflow in context — no separate tab needed
- **Line-level default + word-level optional**: Simple for most users, powerful for perfectionists
- **Standard .lrc format**: Widely compatible for export to other tools/players

## Key Decisions

- **Location**: Track detail view in Library (click track → expand detail panel)
- **AI engine**: Backend Whisper-based forced alignment endpoint
- **Edit precision**: Line-level by default, word-level toggle for power users
- **Storage**: `lyrics_lrc` text column in tracks table + separate lrc_lines table
- **Export**: Standard .lrc (line-level) and enhanced .lrc (word-level with tags)
- **Preview**: Karaoke-style real-time highlighting during playback

## Core Features

1. Track Detail View — expandable panel in Library with full waveform + lyrics lane
2. AI Alignment — "Sync Lyrics" button sends audio + text to backend Whisper endpoint
3. Lyrics Timeline — draggable markers on the waveform for each line/word
4. Karaoke Preview — real-time highlighted lyrics during playback
5. Import/Export — .lrc file import/export

## Open Questions

- Whisper endpoint: does ACE-Step backend already expose a transcription endpoint, or do we need to add one?
- Word-level alignment: does Whisper return word-level timestamps natively or do we need forced alignment (e.g., whisperX)?

## Next Steps

→ Plan implementation details
