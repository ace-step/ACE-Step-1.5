#!/bin/bash
# render-mv.sh - Render a music video from audio + lyrics
#
# Usage:
#   ./render-mv.sh --audio <file> --lyrics <lrc_file> --title "Title" [options]
#
# Options:
#   --audio     Audio file path (absolute or relative)
#   --lyrics    LRC format lyrics file
#   --lyrics-json  JSON lyrics file [{start, end, text}]
#   --title     Video title (default: "Music Video")
#   --subtitle  Subtitle text
#   --credit    Bottom credit text
#   --offset    Lyric timing offset in seconds (default: -0.5)
#   --output    Output file path (default: acestep_output/<audio_basename>.mp4)
#   --codec     h264|h265|vp8|vp9 (default: h264)
#   --browser   Custom browser executable path (Chrome/Edge/Chromium)
#
# Environment variables:
#   BROWSER_EXECUTABLE  Path to browser executable (overrides auto-detection)
#
# Examples:
#   ./render-mv.sh --audio song.mp3 --lyrics song.lrc --title "My Song"
#   ./render-mv.sh --audio /path/to/abc123_1.mp3 --lyrics /path/to/abc123.lrc --title "夜桜"

set -euo pipefail

RENDER_DIR="$(cd "$(dirname "$0")" && pwd)"

# Ensure output directory exists
mkdir -p "${RENDER_DIR}/out"

# Cross-platform realpath alternative (works on macOS/Linux/Windows MSYS2)
resolve_path() {
  local dir base
  dir="$(cd "$(dirname "$1")" && pwd)"
  base="$(basename "$1")"
  echo "${dir}/${base}"
}

AUDIO=""
LYRICS=""
LYRICS_JSON=""
TITLE="Music Video"
SUBTITLE=""
CREDIT=""
OFFSET="-0.5"
OUTPUT=""
CODEC="h264"
BROWSER=""

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --audio)       AUDIO="$2"; shift 2 ;;
    --lyrics)      LYRICS="$2"; shift 2 ;;
    --lyrics-json) LYRICS_JSON="$2"; shift 2 ;;
    --title)       TITLE="$2"; shift 2 ;;
    --subtitle)    SUBTITLE="$2"; shift 2 ;;
    --credit)      CREDIT="$2"; shift 2 ;;
    --offset)      OFFSET="$2"; shift 2 ;;
    --output)      OUTPUT="$2"; shift 2 ;;
    --codec)       CODEC="$2"; shift 2 ;;
    --browser)     BROWSER="$2"; shift 2 ;;
    -h|--help)
      head -20 "$0" | tail -18
      exit 0
      ;;
    *)
      echo "Error: unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$AUDIO" ]]; then
  echo "Error: --audio is required" >&2
  exit 1
fi

if [[ ! -f "$AUDIO" ]]; then
  echo "Error: audio file not found: $AUDIO" >&2
  exit 1
fi

# Resolve absolute path for audio
AUDIO="$(resolve_path "$AUDIO")"

# Default output: acestep_output/<audio_basename>.mp4
if [[ -z "$OUTPUT" ]]; then
  BASENAME="$(basename "${AUDIO%.*}")"
  # Strip trailing _1, _2 etc from audio filename for cleaner video name
  OUTPUT="${RENDER_DIR}/out/${BASENAME}.mp4"
fi

# Ensure output directory exists
mkdir -p "$(dirname "$OUTPUT")"

# Build node args array (safe quoting, no eval)
NODE_ARGS=(render.mjs --audio "$AUDIO" --title "$TITLE" --offset "$OFFSET" --output "$OUTPUT" --codec "$CODEC")

if [[ -n "$LYRICS" ]]; then
  LYRICS="$(resolve_path "$LYRICS")"
  NODE_ARGS+=(--lyrics "$LYRICS")
elif [[ -n "$LYRICS_JSON" ]]; then
  LYRICS_JSON="$(resolve_path "$LYRICS_JSON")"
  NODE_ARGS+=(--lyrics-json "$LYRICS_JSON")
fi

[[ -n "$SUBTITLE" ]] && NODE_ARGS+=(--subtitle "$SUBTITLE")
[[ -n "$CREDIT" ]] && NODE_ARGS+=(--credit "$CREDIT")
[[ -n "$BROWSER" ]] && NODE_ARGS+=(--browser "$BROWSER")

echo "Rendering MV..."
echo "  Audio: $(basename "$AUDIO")"
echo "  Title: $TITLE"
echo "  Output: $OUTPUT"

cd "$RENDER_DIR"
node "${NODE_ARGS[@]}"

echo ""
echo "Output: $OUTPUT"
