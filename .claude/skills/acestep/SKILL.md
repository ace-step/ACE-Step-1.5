---
name: acestep
description: Use ACE-Step API to generate music, edit songs, and remix music. Supports text-to-music, lyrics generation, audio continuation, and audio repainting. Use this skill when users mention generating music, creating songs, music production, remix, or audio continuation.
allowed-tools: Read, Write, Bash, Skill
---

# ACE-Step Music Generation Skill

Use ACE-Step V1.5 API for music generation. **Always use `scripts/acestep.sh` script** — do NOT call API endpoints directly.

## Quick Start

```bash
# 1. cd to this skill's directory
cd {project_root}/{.claude or .codex}/skills/acestep/

# 2. Check API service health
./scripts/acestep.sh health

# 3. Generate with lyrics (recommended)
./scripts/acestep.sh generate -c "pop, female vocal, piano" -l "[Verse] Your lyrics here..." --duration 120 --language zh

# 4. Output saved to: {project_root}/acestep_output/
```

## Workflow

For user requests requiring vocals:
1. Use the **acestep-songwriting** skill for lyrics writing, caption creation, duration/BPM/key selection
2. Write complete, well-structured lyrics yourself based on the songwriting guide
3. Generate using Caption mode with `-c` and `-l` parameters

Only use Simple/Random mode (`-d` or `random`) for quick inspiration or instrumental exploration.

If the user needs a simple music video, use the **acestep-simplemv** skill to render one with waveform visualization and synced lyrics.

**MV Production Requirements**: Making a simple MV requires three additional skills to be installed:
- **acestep-songwriting** — for writing lyrics and planning song structure
- **acestep-lyrics-transcription** — for transcribing audio to timestamped lyrics (LRC)
- **acestep-simplemv** — for rendering the final music video
- **acestep-thumbnail** (optional) — for generating cover art / MV background images via Gemini API

**MV Background Image**: When the user requests MV production, ask whether they want a background image for the video:
1. **Generate via Gemini** — use the **acestep-thumbnail** skill (requires Gemini API key configuration)
2. **Provide an existing image** — user supplies a local image path
3. **Skip** — use the default animated gradient background (no image needed)

Use `AskUserQuestion` to let the user choose before proceeding with MV rendering.

**Parallel Processing**: Lyrics transcription and thumbnail generation are independent tasks. When the user chooses to generate a background image, run **acestep-lyrics-transcription** and **acestep-thumbnail** in parallel (e.g. via two concurrent Agent calls) to save time, then use both outputs for the final MV render.

## Script Commands

**CRITICAL - Complete Lyrics Input**: When providing lyrics via the `-l` parameter, you MUST pass ALL lyrics content WITHOUT any omission:
- If user provides lyrics, pass the ENTIRE text they give you
- If you generate lyrics yourself, pass the COMPLETE lyrics you created
- NEVER truncate, shorten, or pass only partial lyrics
- Missing lyrics will result in incomplete or incoherent songs

**Music Parameters**: Use the **acestep-songwriting** skill for guidance on duration, BPM, key scale, and time signature.

```bash
# need to cd to this skill's directory first
cd {project_root}/{.claude or .codex}/skills/acestep/

# Caption mode - RECOMMENDED: Write lyrics first, then generate
./scripts/acestep.sh generate -c "Electronic pop, energetic synths" -l "[Verse] Your complete lyrics
[Chorus] Full chorus here..." --duration 120 --bpm 128

# Instrumental only
./scripts/acestep.sh generate "Jazz with saxophone"

# Quick exploration (Simple/Random mode)
./scripts/acestep.sh generate -d "A cheerful song about spring"
./scripts/acestep.sh random

# Cover / Repainting from source audio
./scripts/acestep.sh cover song.mp3 -c "Rock cover style" -l "[Verse] Lyrics..." --duration 120 --bpm 128
./scripts/acestep.sh generate --src-audio song.mp3 --task-type repaint -c "Pop" --repaint-start 30 --repaint-end 60

# Music attribute options
./scripts/acestep.sh generate "Rock" --duration 60 --bpm 120 --key-scale "C major" --time-sig "4/4"
./scripts/acestep.sh generate "Rock" --duration 60 --batch 2
./scripts/acestep.sh generate "EDM" --no-thinking    # Faster

# Other commands
./scripts/acestep.sh status <job_id>
./scripts/acestep.sh health
./scripts/acestep.sh models
```

### Cover / Audio Repainting

The `cover` command generates music based on a source audio file. The audio is base64-encoded and sent to the API.

```bash
# Cover: regenerate with new style/lyrics, preserving melody structure
./scripts/acestep.sh cover input.mp3 -c "Jazz cover" -l "[Verse] New lyrics..." --duration 120

# Repainting: modify a specific region of the audio
./scripts/acestep.sh generate --src-audio input.mp3 --task-type repaint -c "Pop ballad" --repaint-start 30 --repaint-end 90

# Cover options
#   --src-audio         Source audio file path
#   --task-type         cover (default with --src-audio), repaint, text2music
#   --cover-strength    0.0-1.0 (default: 1.0, higher = closer to source)
#   --repaint-start     Repainting start position (seconds)
#   --repaint-end       Repainting end position (seconds)
#   --key-scale         Musical key (e.g. "E minor")
#   --time-signature    Time signature (e.g. "4/4")
```

**Note**: For cloud API usage, large audio files may be rejected by Cloudflare. Compress audio before uploading if needed (e.g. using ffmpeg: `ffmpeg -i input.mp3 -b:a 64k -ar 24000 -ac 1 compressed.mp3`).

## Output Files

After generation, the script automatically saves results to the `acestep_output` folder in the project root (same level as `.claude`):

```
project_root/
├── .claude/
│   └── skills/acestep/...
├── acestep_output/          # Output directory
│   ├── <job_id>.json         # Complete task result (JSON)
│   ├── <job_id>_1.mp3        # First audio file
│   ├── <job_id>_2.mp3        # Second audio file (if batch_size > 1)
│   └── ...
└── ...
```

### JSON Result Structure

**Important**: When LM enhancement is enabled (`use_format=true`), the final synthesized content may differ from your input. Check the JSON file for actual values:

| Field | Description |
|-------|-------------|
| `prompt` | **Actual caption** used for synthesis (may be LM-enhanced) |
| `lyrics` | **Actual lyrics** used for synthesis (may be LM-enhanced) |
| `metas.prompt` | Original input caption |
| `metas.lyrics` | Original input lyrics |
| `metas.bpm` | BPM used |
| `metas.keyscale` | Key scale used |
| `metas.duration` | Duration in seconds |
| `generation_info` | Detailed timing and model info |
| `seed_value` | Seeds used (for reproducibility) |
| `lm_model` | LM model name |
| `dit_model` | DiT model name |

To get the actual synthesized lyrics, parse the JSON and read the top-level `lyrics` field, not `metas.lyrics`.

## Configuration

**Important**: Configuration follows this priority (high to low):

1. **Command line arguments** > **config.json defaults**
2. User-specified parameters **temporarily override** defaults but **do not modify** config.json
3. Only `config --set` command **permanently modifies** config.json

### Default Config File (`scripts/config.json`)

```json
{
  "api_url": "http://127.0.0.1:8001",
  "api_key": "",
  "api_mode": "completion",
  "generation": {
    "thinking": true,
    "use_format": false,
    "use_cot_caption": true,
    "use_cot_language": false,
    "batch_size": 1,
    "audio_format": "mp3",
    "vocal_language": "en"
  }
}
```

| Option | Default | Description |
|--------|---------|-------------|
| `api_url` | `http://127.0.0.1:8001` | API server address |
| `api_key` | `""` | API authentication key (optional) |
| `api_mode` | `completion` | API mode: `completion` (OpenRouter, default) or `native` (polling) |
| `generation.thinking` | `true` | Enable 5Hz LM (higher quality, slower) |
| `generation.audio_format` | `mp3` | Output format (mp3/wav/flac) |
| `generation.vocal_language` | `en` | Vocal language |

## Prerequisites - ACE-Step API Service

**IMPORTANT**: This skill requires the ACE-Step API server to be running.

### Required Dependencies

The `scripts/acestep.sh` script requires: **curl** and **jq**.

```bash
# Check dependencies
curl --version
jq --version
```

If jq is not installed, the script will attempt to install it automatically. If automatic installation fails:
- **Windows**: `choco install jq` or download from https://jqlang.github.io/jq/download/
- **macOS**: `brew install jq`
- **Linux**: `sudo apt-get install jq` (Debian/Ubuntu) or `sudo dnf install jq` (Fedora)

### Before First Use

**You MUST check the API key and URL status before proceeding.** Run:

```bash
cd "{project_root}/{.claude or .codex}/skills/acestep/" && bash ./scripts/acestep.sh config --check-key
cd "{project_root}/{.claude or .codex}/skills/acestep/" && bash ./scripts/acestep.sh config --get api_url
```

#### Case 1: Using Official Cloud API (`https://api.acemusic.ai`) without API key

If `api_url` is `https://api.acemusic.ai` and `api_key` is `empty`, you MUST stop and guide the user to configure their key:

1. Tell the user: "You're using the ACE-Step official cloud API, but no API key is configured. An API key is required to use this service."
2. Explain how to get a key: API keys are currently available through [acemusic.ai](https://acemusic.ai/api-key) for free.
3. Use `AskUserQuestion` to ask the user to provide their API key.
4. Once provided, configure it:
   ```bash
   cd "{project_root}/{.claude or .codex}/skills/acestep/" && bash ./scripts/acestep.sh config --set api_key <KEY>
   ```
5. Additionally, inform the user: "If you also want to render music videos (MV), it's recommended to configure a lyrics transcription API key as well (OpenAI Whisper or ElevenLabs Scribe), so that lyrics can be automatically transcribed with accurate timestamps. You can configure it later via the `acestep-lyrics-transcription` skill."

#### Case 2: API key is configured

Verify the API endpoint: `./scripts/acestep.sh health` and proceed with music generation.

#### Case 3: Using local/custom API without key

Local services (`http://127.0.0.1:*`) typically don't require a key. Verify with `./scripts/acestep.sh health` and proceed.

If health check fails:
- Ask: "Do you have ACE-Step installed?"
- **If installed but not running**: Use the acestep-docs skill to help them start the service
- **If not installed**: Use acestep-docs skill to guide through installation

### Service Configuration

**Official Cloud API:** ACE-Step provides an official API endpoint at `https://api.acemusic.ai`. To use it:
```bash
./scripts/acestep.sh config --set api_url "https://api.acemusic.ai"
./scripts/acestep.sh config --set api_key "your-key"
./scripts/acestep.sh config --set api_mode completion
```
API keys are currently available through [acemusic.ai](https://acemusic.ai/api-key) for free. 

**Local Service (Default):** No configuration needed — connects to `http://127.0.0.1:8001`.

**Custom Remote Service:** Update `scripts/config.json` or use:
```bash
./scripts/acestep.sh config --set api_url "http://remote-server:8001"
./scripts/acestep.sh config --set api_key "your-key"
```

**API Key Handling**: When checking whether an API key is configured, use `config --check-key` which only reports `configured` or `empty` without printing the actual key. **NEVER use `config --get api_key`** or read `config.json` directly — these would expose the user's API key. The `config --list` command is safe — it automatically masks API keys as `***` in output.

### API Mode

The skill supports two API modes. Switch via `api_mode` in `scripts/config.json`:

| Mode | Endpoint | Description |
|------|----------|-------------|
| `completion` (default) | `/v1/chat/completions` | OpenRouter-compatible, sync request, audio returned as base64 |
| `native` | `/release_task` + `/query_result` | Async polling mode, supports all parameters |

**Switch mode:**
```bash
./scripts/acestep.sh config --set api_mode completion
./scripts/acestep.sh config --set api_mode native
```

**Completion mode notes:**
- No polling needed — single request returns result directly
- Audio is base64-encoded inline in the response (auto-decoded and saved)
- `inference_steps`, `infer_method`, `shift` are not configurable (server defaults)
- `--no-wait` and `status` commands are not applicable in completion mode
- Requires `model` field — auto-detected from `/v1/models` if not specified

### Using acestep-docs Skill for Setup Help

**IMPORTANT**: For installation and startup, always use the acestep-docs skill to get complete and accurate guidance.

**DO NOT provide simplified startup commands** - each user's environment may be different. Always guide them to use acestep-docs for proper setup.

---

For API debugging, see [API Reference](./api-reference.md).
