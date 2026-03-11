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
#   --background Background image file path (if omitted, uses animated gradient)
#   --browser   Custom browser executable path (Chrome/Edge/Chromium)
#   --max-size  Max output file size in MB (e.g. 24). Compresses video if exceeded.
#              Use for IM platforms (WhatsApp/Discord/Telegram) with upload limits.
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
BACKGROUND=""
BROWSER=""
MAX_SIZE=""

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
    --background)  BACKGROUND="$2"; shift 2 ;;
    --browser)     BROWSER="$2"; shift 2 ;;
    --max-size)    MAX_SIZE="$2"; shift 2 ;;
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
if [[ -n "$BACKGROUND" ]]; then
  BACKGROUND="$(resolve_path "$BACKGROUND")"
  NODE_ARGS+=(--background "$BACKGROUND")
fi
[[ -n "$BROWSER" ]] && NODE_ARGS+=(--browser "$BROWSER")

# --- Font check for container environments ---
check_and_install_cjk_fonts() {
  # Only run on Linux (containers are typically Linux)
  [[ "$(uname -s)" != "Linux" ]] && return 0

  # Check if any CJK font is available via fc-list
  if command -v fc-list &>/dev/null; then
    if fc-list :lang=zh 2>/dev/null | head -1 | grep -q .; then
      return 0  # CJK fonts found
    fi
    if fc-list :lang=ja 2>/dev/null | head -1 | grep -q .; then
      return 0  # Japanese fonts found
    fi
  fi

  echo "⚠️  No CJK fonts detected. Non-ASCII lyrics may render as □ boxes."

  # Attempt to install fonts-noto-cjk (works on Debian/Ubuntu containers)
  if command -v apt-get &>/dev/null; then
    echo "   Attempting to install fonts-noto-cjk..."
    if apt-get update -qq &>/dev/null && apt-get install -y -qq fonts-noto-cjk &>/dev/null; then
      # Refresh font cache
      command -v fc-cache &>/dev/null && fc-cache -f &>/dev/null
      echo "   ✅ CJK fonts installed successfully."
      return 0
    else
      echo "   ⚠️  Failed to install fonts (may need root/sudo). Trying sudo..."
      if sudo apt-get update -qq &>/dev/null && sudo apt-get install -y -qq fonts-noto-cjk &>/dev/null; then
        command -v fc-cache &>/dev/null && fc-cache -f &>/dev/null
        echo "   ✅ CJK fonts installed successfully."
        return 0
      fi
    fi
  elif command -v apk &>/dev/null; then
    # Alpine Linux containers
    echo "   Attempting to install font-noto-cjk (Alpine)..."
    if apk add --no-cache font-noto-cjk &>/dev/null; then
      command -v fc-cache &>/dev/null && fc-cache -f &>/dev/null
      echo "   ✅ CJK fonts installed successfully."
      return 0
    fi
  elif command -v dnf &>/dev/null; then
    echo "   Attempting to install google-noto-sans-cjk-fonts (dnf)..."
    if dnf install -y -q google-noto-sans-cjk-fonts &>/dev/null; then
      command -v fc-cache &>/dev/null && fc-cache -f &>/dev/null
      echo "   ✅ CJK fonts installed successfully."
      return 0
    fi
  fi

  echo "   ⚠️  Could not auto-install CJK fonts. Please install manually:"
  echo "      Debian/Ubuntu: apt-get install fonts-noto-cjk"
  echo "      Alpine: apk add font-noto-cjk"
  echo "      Fedora/RHEL: dnf install google-noto-sans-cjk-fonts"
  return 1
}

check_and_install_cjk_fonts

# --- Render ---
echo "Rendering MV..."
echo "  Audio: $(basename "$AUDIO")"
echo "  Title: $TITLE"
echo "  Output: $OUTPUT"

cd "$RENDER_DIR"
node "${NODE_ARGS[@]}"

# --- Post-render: compress if --max-size is set ---
if [[ -n "$MAX_SIZE" && -f "$OUTPUT" ]]; then
  FILE_SIZE_BYTES=$(stat -f%z "$OUTPUT" 2>/dev/null || stat -c%s "$OUTPUT" 2>/dev/null || echo 0)
  MAX_SIZE_BYTES=$((MAX_SIZE * 1024 * 1024))

  if [[ "$FILE_SIZE_BYTES" -gt "$MAX_SIZE_BYTES" ]]; then
    echo ""
    echo "Video size $(( FILE_SIZE_BYTES / 1024 / 1024 ))MB exceeds ${MAX_SIZE}MB limit. Compressing..."

    COMPRESSED="${OUTPUT%.mp4}_compressed.mp4"

    # Calculate target total bitrate (bits/s) from max size and duration
    DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUTPUT" 2>/dev/null)
    if [[ -z "$DURATION" || "$DURATION" == "N/A" ]]; then
      echo "Error: Cannot determine video duration for compression." >&2
      exit 1
    fi

    # Target bitrate = (max_size_bytes * 8) / duration * 0.95 safety margin
    # Use bc for floating point, fallback to awk
    TARGET_BITRATE=$(awk "BEGIN { printf \"%d\", ($MAX_SIZE_BYTES * 8 / $DURATION) * 0.95 }")
    AUDIO_BITRATE=96000  # 96k audio
    VIDEO_BITRATE=$((TARGET_BITRATE - AUDIO_BITRATE))

    if [[ "$VIDEO_BITRATE" -lt 100000 ]]; then
      echo "Error: Target size too small for this video duration." >&2
      exit 1
    fi

    echo "  Target video bitrate: $((VIDEO_BITRATE / 1000))kbps"

    # Two-pass encoding for best quality at target size
    ffmpeg -y -i "$OUTPUT" \
      -c:v libx264 -b:v "${VIDEO_BITRATE}" -pass 1 \
      -preset medium -an -f null /dev/null 2>/dev/null

    ffmpeg -y -i "$OUTPUT" \
      -c:v libx264 -b:v "${VIDEO_BITRATE}" -pass 2 \
      -preset medium -c:a aac -b:a 96k \
      -movflags +faststart \
      "$COMPRESSED" 2>/dev/null

    # Clean up two-pass log files
    rm -f ffmpeg2pass-0.log ffmpeg2pass-0.log.mbtree

    if [[ -f "$COMPRESSED" ]]; then
      COMP_SIZE=$(stat -f%z "$COMPRESSED" 2>/dev/null || stat -c%s "$COMPRESSED" 2>/dev/null || echo 0)
      echo "  Compressed: $(( COMP_SIZE / 1024 / 1024 ))MB (was $(( FILE_SIZE_BYTES / 1024 / 1024 ))MB)"

      # Replace original with compressed
      mv "$COMPRESSED" "$OUTPUT"
      echo "  ✅ Compressed video saved to: $OUTPUT"
    else
      echo "  ⚠️  Compression failed, keeping original file."
    fi
  else
    echo "Video size $(( FILE_SIZE_BYTES / 1024 / 1024 ))MB is within ${MAX_SIZE}MB limit. No compression needed."
  fi
fi

echo ""
echo "Output: $OUTPUT"
