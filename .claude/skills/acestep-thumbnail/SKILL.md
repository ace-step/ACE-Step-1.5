---
name: acestep-thumbnail
description: Generate song cover/thumbnail images using Gemini API or the optional Atlas Cloud backend. Creates artistic images suitable for music video backgrounds. Use when users want to generate album art, song covers, thumbnails, or background images for MVs.
allowed-tools: Read, Write, Bash
---

# Thumbnail Generation Skill

Generate song cover/thumbnail images using Google Gemini's image generation API or Atlas Cloud. Gemini remains the default; Atlas is opt-in. Output images can be used directly as MV backgrounds with the acestep-simplemv skill.

## API Key Setup Guide

**Before generating, choose the provider and check only that provider's key.** Gemini is the
default. For Gemini, run:

```bash
cd "{project_root}/{.claude or .codex}/skills/acestep-thumbnail/" && bash ./scripts/acestep-thumbnail.sh config --check-key
```

For Atlas, check the environment without printing the key:

```bash
if [[ -n "${ATLASCLOUD_API_KEY:-${ATLAS_CLOUD_API_KEY:-}}" ]]; then
  echo "Atlas Cloud API key: configured"
else
  echo "Atlas Cloud API key: empty"
fi
```

These checks report only whether a key is set. **NEVER read or display the user's API key
content.** Do not use `config --get` on key fields or read `config.json` directly. The Gemini
`config --list` command is safe because it masks API keys as `***` in output.

**If the selected provider's check reports the key is empty**, stop and guide the user to
configure it before proceeding. Do not attempt generation without a valid key.

Use `AskUserQuestion` to ask the user to provide their API key, with the following guidance:

1. Tell the user which provider key is not configured.
2. Provide the matching setup instructions:
   - **Google AI Studio**: Get a API key at https://aistudio.google.com/apikey — requires a Google account.
   - **Atlas Cloud**: Create a key at https://www.atlascloud.ai/console/api-keys and export it as `ATLASCLOUD_API_KEY`.
3. Once the user provides the key, configure it using:
   ```bash
   cd "{project_root}/{.claude or .codex}/skills/acestep-thumbnail/" && bash ./scripts/acestep-thumbnail.sh config --set api_key <KEY>
   ```
4. After configuring Gemini, re-run `config --check-key`. For Atlas, repeat the safe environment check above.

**If the API key is already configured**, proceed directly to generation without asking.

## Quick Start

```bash
# 1. cd to this skill's directory
cd {project_root}/{.claude or .codex}/skills/acestep-thumbnail/

# 2. Configure API key
./scripts/acestep-thumbnail.sh config --set api_key <YOUR_GEMINI_KEY>

# 3. Generate thumbnail
./scripts/acestep-thumbnail.sh generate --prompt "Cherry blossoms at night with moonlight"

# 4. Output saved to: {project_root}/acestep_output/<timestamp>_thumbnail.png
```

### Atlas Cloud provider

Set an Atlas Cloud key in the environment and select the provider per call:

```bash
export ATLASCLOUD_API_KEY="your-key"
./scripts/acestep-thumbnail.sh generate \
  --provider atlas \
  --prompt "Cherry blossoms at night with moonlight" \
  --aspect-ratio 16:9 \
  --resolution 1k
```

Atlas uses `google/nano-banana-pro/text-to-image-developer` by default. Override it with
`--atlas-model` only after confirming the replacement is an enabled image model in the live
Atlas catalog. Atlas submission is made once; only prediction-status GET requests use bounded
transient retries.

## Prerequisites

- curl, jq, base64 (or python3)
- A Gemini API key (at https://aistudio.google.com/apikey), or `ATLASCLOUD_API_KEY` when using Atlas

## Script Usage

```bash
./scripts/acestep-thumbnail.sh generate [options]

Options:
  --prompt       Image description (required)
  --aspect-ratio 16:9, 1:1, or 9:16 (default: 16:9)
  --output       Output image path (default: acestep_output/<timestamp>_thumbnail.png)
  --provider     gemini or atlas (default: gemini)
  --resolution   Atlas output resolution: 1k, 2k, or 4k (default: 1k)
  --atlas-model  Optional Atlas image model override
```

## Prompt Guidelines

When crafting prompts for song thumbnails:

- **Be descriptive and atmospheric**: "Neon-lit rain-soaked Tokyo street at midnight" works better than "city at night"
- **Match the music mood**: A jazz song might need "Warm smoky lounge with dim golden lighting", while EDM might need "Abstract geometric patterns with vibrant electric colors"
- **Avoid text requests**: Image generation models often struggle with text. Add "No text or letters in the image" if needed
- **For MV backgrounds**: The image will be overlaid with visualizations, so avoid overly busy compositions. Atmospheric, gradient-rich scenes work best

## Configuration

Config file: `scripts/config.json`

```bash
# Set API key
./scripts/acestep-thumbnail.sh config --set api_key <YOUR_KEY>

# Change model
./scripts/acestep-thumbnail.sh config --set model gemini-3.1-flash-image-preview

# Change default aspect ratio
./scripts/acestep-thumbnail.sh config --set aspect_ratio 1:1

# View config (API key masked)
./scripts/acestep-thumbnail.sh config --list
```

| Option | Default | Description |
|--------|---------|-------------|
| `api_key` | `""` | Gemini API key |
| `api_url` | `https://generativelanguage.googleapis.com/v1beta` | Gemini API base URL |
| `model` | `gemini-3.1-flash-image-preview` | Gemini model with image generation |
| `aspect_ratio` | `16:9` | Default aspect ratio (16:9 for MV, 1:1 for album art) |

## Integration with MV Rendering

Generated thumbnails can be directly used as MV backgrounds:

```bash
# 1. Generate thumbnail
cd {project_root}/{.claude or .codex}/skills/acestep-thumbnail/
./scripts/acestep-thumbnail.sh generate --prompt "Energetic pop concert stage with colorful lights" --output /tmp/cover.png

# 2. Use as MV background
cd {project_root}/{.claude or .codex}/skills/acestep-simplemv/
./scripts/render-mv.sh --audio song.mp3 --lyrics song.lrc --title "Song Name" --background /tmp/cover.png
```

## Workflow: Full Song Pipeline

The complete workflow with all ACE-Step skills:

1. **acestep-songwriting** — Write lyrics and plan structure
2. **acestep** — Generate music from lyrics
3. **acestep-lyrics-transcription** — Transcribe audio to timestamped LRC
4. **acestep-thumbnail** — Generate cover art / MV background
5. **acestep-simplemv** — Render final music video with cover + audio + lyrics
