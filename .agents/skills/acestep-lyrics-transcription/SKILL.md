---
name: acestep-lyrics-transcription
description: Transcribe audio to timestamped lyrics using OpenAI Whisper or ElevenLabs Scribe API. Outputs LRC, SRT, or JSON with word-level timestamps. Use when users want to transcribe songs, generate LRC files, or extract lyrics with timestamps from audio.
allowed-tools: Read, Write, Bash
---

# Lyrics Transcription Skill

Transcribe audio files to timestamped lyrics (LRC/SRT/JSON) via OpenAI Whisper or ElevenLabs Scribe API.

## API Key Setup Guide

**Before transcribing, you MUST check whether the user's API key is configured.** Run the following command to check:

```bash
cd "{project_root}/{.Codex or .codex}/skills/acestep-lyrics-transcription/" && bash ./scripts/acestep-lyrics-transcription.sh config --check-key
```

This command only reports whether the active provider's API key is set or empty — it does NOT print the actual key value. **NEVER read or display the user's API key content.** Do not use `config --get` on key fields or read `config.json` directly. The `config --list` command is safe — it automatically masks API keys as `***` in output.

**If the command reports the key is empty**, you MUST stop and guide the user to configure it before proceeding. Do NOT attempt transcription without a valid key — it will fail.

Use `AskUserQuestion` to ask the user to provide their API key, with the following options and guidance:

1. Tell the user which provider is currently active (openai or elevenlabs) and that its API key is not configured. Explain that transcription cannot proceed without it.
2. Provide clear instructions on where to obtain a key:
   - **OpenAI**: Get an API key at https://platform.openai.com/api-keys — requires an OpenAI account with billing enabled. The Whisper API costs ~$0.006/min.
   - **ElevenLabs**: Get an API key at https://elevenlabs.io/app/settings/api-keys — requires an ElevenLabs account. Free tier includes limited credits.
3. Also offer the option to switch to the other provider if they already have a key for it.
4. Once the user provides the key, configure it using:
   ```bash
   cd "{project_root}/{.Codex or .codex}/skills/acestep-lyrics-transcription/" && bash ./scripts/acestep-lyrics-transcription.sh config --set <provider>.api_key <KEY>
   ```
5. If the user wants to switch providers, also run:
   ```bash
   cd "{project_root}/{.Codex or .codex}/skills/acestep-lyrics-transcription/" && bash ./scripts/acestep-lyrics-transcription.sh config --set provider <provider_name>
   ```
6. After configuring, re-run `config --check-key` to verify the key is set before proceeding.

**If the API key is already configured**, proceed directly to transcription without asking.

## Quick Start

```bash
# 1. cd to this skill's directory
cd {project_root}/{.Codex or .codex}/skills/acestep-lyrics-transcription/

# 2. Configure API key (choose one)
./scripts/acestep-lyrics-transcription.sh config --set openai.api_key sk-...
# or
./scripts/acestep-lyrics-transcription.sh config --set elevenlabs.api_key ...
./scripts/acestep-lyrics-transcription.sh config --set provider elevenlabs

# 3. Transcribe
./scripts/acestep-lyrics-transcription.sh transcribe --audio /path/to/song.mp3 --language zh

# 4. Output saved to: {project_root}/acestep_output/<filename>.lrc
```

## Prerequisites

- curl, jq, python3 (or python)
- An API key for OpenAI or ElevenLabs

## Script Usage

```bash
./scripts/acestep-lyrics-transcription.sh transcribe --audio <file> [options]

Options:
  -a, --audio      Audio file path (required)
  -l, --language   Language code (zh, en, ja, etc.)
  -f, --format     Output format: lrc, srt, json (default: lrc)
  -p, --provider   API provider: openai, elevenlabs (overrides config)
  -o, --output     Output file path (default: acestep_output/<filename>.lrc)
```

## Post-Transcription Lyrics Correction (MANDATORY)

**CRITICAL**: After transcription, you MUST manually correct the LRC file before using it for MV rendering. Transcription models frequently produce errors on sung lyrics:

- Proper nouns: "ACE-Step" → "AC step", "Spotify" → "spot a fly"
- Similar-sounding words: "arrives" → "eyes", "open source" → "open sores"
- Merged/split words: "lighting up" → "lightin' nup"

### Correction Workflow

1. **Read the transcribed LRC file** using the Read tool
2. **Read the original lyrics** from the ACE-Step output JSON file
3. **Use original lyrics as a whole reference**: Do NOT attempt line-by-line alignment — transcription often splits, merges, or reorders lines differently from the original. Instead, read the original lyrics in full to understand the correct wording, then scan each LRC line and fix any misrecognized words based on your knowledge of what the original lyrics say.
4. **Fix transcription errors**: Replace misrecognized words with the correct original words, keeping the timestamps intact
5. **Write the corrected LRC** back using the Write tool

### What to Correct

- Replace misrecognized words with their correct original versions
- Keep all `[MM:SS.cc]` timestamps exactly as-is (timestamps from transcription are accurate)
- Do NOT add structure tags like `[Verse]` or `[Chorus]` — the LRC should only have timestamped text lines

### Example

**Transcribed (wrong):**
```
[00:46.96]AC step alive,
[00:50.80]one point five eyes.
```

**Original lyrics reference:**
```
ACE-Step alive
One point five arrives
```

**Corrected (right):**
```
[00:46.96]ACE-Step alive,
[00:50.80]One point five arrives.
```

## Configuration

Config file: `scripts/config.json`

```bash
# Switch provider
./scripts/acestep-lyrics-transcription.sh config --set provider openai
./scripts/acestep-lyrics-transcription.sh config --set provider elevenlabs

# Set API keys
./scripts/acestep-lyrics-transcription.sh config --set openai.api_key sk-...
./scripts/acestep-lyrics-transcription.sh config --set elevenlabs.api_key ...

# View config
./scripts/acestep-lyrics-transcription.sh config --list
```

| Option | Default | Description |
|--------|---------|-------------|
| `provider` | `openai` | Active provider: `openai` or `elevenlabs` |
| `output_format` | `lrc` | Default output: `lrc`, `srt`, or `json` |
| `openai.api_key` | `""` | OpenAI API key |
| `openai.api_url` | `https://api.openai.com/v1` | OpenAI API base URL |
| `openai.model` | `whisper-1` | OpenAI model (whisper-1 for word timestamps) |
| `elevenlabs.api_key` | `""` | ElevenLabs API key |
| `elevenlabs.api_url` | `https://api.elevenlabs.io/v1` | ElevenLabs API base URL |
| `elevenlabs.model` | `scribe_v2` | ElevenLabs model |

## Provider Notes

| Provider | Model | Word Timestamps | Pricing |
|----------|-------|-----------------|---------|
| OpenAI | whisper-1 | Yes (segment + word) | $0.006/min |
| ElevenLabs | scribe_v2 | Yes (word-level) | Varies by plan |

- OpenAI `whisper-1` is the only OpenAI model supporting word-level timestamps
- ElevenLabs `scribe_v2` returns word-level timestamps with type filtering
- Both support multilingual transcription

## Examples

```bash
# Basic transcription (uses config defaults)
./scripts/acestep-lyrics-transcription.sh transcribe --audio song.mp3

# Chinese song to LRC
./scripts/acestep-lyrics-transcription.sh transcribe --audio song.mp3 --language zh

# Use ElevenLabs, output SRT
./scripts/acestep-lyrics-transcription.sh transcribe --audio song.mp3 --provider elevenlabs --format srt

# Custom output path
./scripts/acestep-lyrics-transcription.sh transcribe --audio song.mp3 --output ./my_lyrics.lrc
```
