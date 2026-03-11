---
name: acestep-thumbnail
description: Generate song cover/thumbnail images using Gemini API. Creates artistic images suitable for music video backgrounds. Use when users want to generate album art, song covers, thumbnails, or background images for MVs.
allowed-tools: Read, Write, Bash
---

# Thumbnail Generation Skill

Generate song cover/thumbnail images using Google Gemini's image generation API. Output images can be used directly as MV backgrounds with the acestep-simplemv skill.

## API Key Setup Guide

**Before generating, you MUST check whether the user's API key is configured.** Run the following command to check:

```bash
cd "{project_root}/{.claude or .codex}/skills/acestep-thumbnail/" && bash ./scripts/acestep-thumbnail.sh config --check-key
```

This command only reports whether the API key is set or empty — it does NOT print the actual key value. **NEVER read or display the user's API key content.** Do not use `config --get` on key fields or read `config.json` directly. The `config --list` command is safe — it automatically masks API keys as `***` in output.

**If the command reports the key is empty**, you MUST stop and guide the user to configure it before proceeding. Do NOT attempt generation without a valid key — it will fail.

Use `AskUserQuestion` to ask the user to provide their API key, with the following guidance:

1. Tell the user the Gemini API key is not configured and image generation cannot proceed without it.
2. Provide instructions on where to get a key:
   - **Google AI Studio**: Get a API key at https://aistudio.google.com/apikey — requires a Google account.
3. Once the user provides the key, configure it using:
   ```bash
   cd "{project_root}/{.claude or .codex}/skills/acestep-thumbnail/" && bash ./scripts/acestep-thumbnail.sh config --set api_key <KEY>
   ```
4. After configuring, re-run `config --check-key` to verify the key is set before proceeding.

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

## Prerequisites

- curl, jq, base64 (or python3)
- A Gemini API key (at https://aistudio.google.com/apikey)

## Script Usage

```bash
./scripts/acestep-thumbnail.sh generate [options]

Options:
  --prompt       Image description (required)
  --aspect-ratio 16:9, 1:1, or 9:16 (default: 16:9)
  --output       Output image path (default: acestep_output/<timestamp>_thumbnail.png)
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
