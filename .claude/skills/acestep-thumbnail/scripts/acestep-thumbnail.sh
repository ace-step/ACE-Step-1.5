#!/bin/bash
# acestep-thumbnail.sh - Generate song cover/thumbnail images using Gemini API
#
# Usage:
#   ./acestep-thumbnail.sh generate --prompt "description" [options]
#   ./acestep-thumbnail.sh config --set <key> <value>
#   ./acestep-thumbnail.sh config --get <key>
#   ./acestep-thumbnail.sh config --list
#   ./acestep-thumbnail.sh config --check-key
#
# Generate options:
#   --prompt       Image description prompt (required)
#   --aspect-ratio Aspect ratio: 16:9, 1:1, 9:16 (default: from config, typically 16:9)
#   --output       Output image path (default: acestep_output/<timestamp>_thumbnail.png)
#
# Examples:
#   ./acestep-thumbnail.sh generate --prompt "Cyberpunk city skyline at night with neon lights"
#   ./acestep-thumbnail.sh generate --prompt "Cherry blossoms" --output /tmp/cover.png

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config.json"
CONFIG_EXAMPLE="${SCRIPT_DIR}/config.example.json"

# ── Helpers ──────────────────────────────────────────────────────────

ensure_config() {
  if [[ ! -f "$CONFIG_FILE" ]]; then
    if [[ -f "$CONFIG_EXAMPLE" ]]; then
      cp "$CONFIG_EXAMPLE" "$CONFIG_FILE"
      echo "Created config.json from config.example.json"
    else
      echo '{"api_key":"","api_url":"https://generativelanguage.googleapis.com/v1beta","model":"gemini-3.1-flash-image-preview","aspect_ratio":"16:9"}' > "$CONFIG_FILE"
      echo "Created default config.json"
    fi
  fi
}

get_config() {
  local key="$1"
  ensure_config
  jq -r ".$key // empty" "$CONFIG_FILE"
}

set_config() {
  local key="$1" value="$2"
  ensure_config
  local tmp="${CONFIG_FILE}.tmp"
  jq --arg v "$value" ".$key = \$v" "$CONFIG_FILE" > "$tmp" && mv "$tmp" "$CONFIG_FILE"
  echo "Set $key"
}

check_api_key() {
  ensure_config
  local key
  key=$(get_config "api_key")
  if [[ -n "$key" ]]; then
    echo "Gemini API key: configured"
  else
    echo "Gemini API key: empty"
    echo ""
    echo "Get a free API key at: https://aistudio.google.com/apikey"
    echo "Then run: ./scripts/acestep-thumbnail.sh config --set api_key <YOUR_KEY>"
  fi
}

list_config() {
  ensure_config
  # Mask API key in output
  jq 'if .api_key and (.api_key | length) > 0 then .api_key = "***" else . end' "$CONFIG_FILE"
}

# ── Config command ───────────────────────────────────────────────────

handle_config() {
  local action="${1:-}" key="${2:-}" value="${3:-}"
  case "$action" in
    --set)
      [[ -z "$key" || -z "$value" ]] && { echo "Usage: config --set <key> <value>" >&2; exit 1; }
      set_config "$key" "$value"
      ;;
    --get)
      [[ -z "$key" ]] && { echo "Usage: config --get <key>" >&2; exit 1; }
      # Safety: refuse to print API key directly
      if [[ "$key" == "api_key" ]]; then
        echo "Error: Use 'config --check-key' to check API key status. Direct key access is not allowed." >&2
        exit 1
      fi
      get_config "$key"
      ;;
    --list)
      list_config
      ;;
    --check-key)
      check_api_key
      ;;
    *)
      echo "Usage: config [--set <key> <value> | --get <key> | --list | --check-key]" >&2
      exit 1
      ;;
  esac
}

# ── Generate command ─────────────────────────────────────────────────

handle_generate() {
  ensure_config

  local prompt="" aspect_ratio="" output=""

  # Parse args
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --prompt)       prompt="$2"; shift 2 ;;
      --aspect-ratio) aspect_ratio="$2"; shift 2 ;;
      --output)       output="$2"; shift 2 ;;
      *)
        echo "Error: unknown argument: $1" >&2
        exit 1
        ;;
    esac
  done

  # Load config
  local api_key api_url model
  api_key=$(get_config "api_key")
  api_url=$(get_config "api_url")
  model=$(get_config "model")

  if [[ -z "$api_key" ]]; then
    echo "Error: Gemini API key not configured." >&2
    echo "Get a free key at: https://aistudio.google.com/apikey" >&2
    echo "Then run: ./scripts/acestep-thumbnail.sh config --set api_key <YOUR_KEY>" >&2
    exit 1
  fi

  [[ -z "$api_url" ]] && api_url="https://generativelanguage.googleapis.com/v1beta"
  [[ -z "$model" ]] && model="gemini-3.1-flash-image-preview"
  local generate_api="generateContent"

  # Aspect ratio: CLI arg > config > default
  if [[ -z "$aspect_ratio" ]]; then
    aspect_ratio=$(get_config "aspect_ratio")
    [[ -z "$aspect_ratio" ]] && aspect_ratio="16:9"
  fi

  if [[ -z "$prompt" ]]; then
    echo "Error: --prompt is required" >&2
    exit 1
  fi

  # Default output path
  if [[ -z "$output" ]]; then
    # Find project root (walk up to find acestep_output or use skill's parent)
    local project_root
    project_root="$(cd "$SKILL_DIR/../.." && pwd)"
    # Go up one more level if we're inside .claude/skills or .codex/skills
    if [[ "$(basename "$(dirname "$SKILL_DIR")")" == "skills" ]]; then
      local skills_parent
      skills_parent="$(dirname "$(dirname "$SKILL_DIR")")"
      local skills_grandparent
      skills_grandparent="$(dirname "$skills_parent")"
      project_root="$skills_grandparent"
    fi
    local out_dir="${project_root}/acestep_output"
    mkdir -p "$out_dir"
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    output="${out_dir}/${timestamp}_thumbnail.png"
  fi

  # Ensure output directory exists
  mkdir -p "$(dirname "$output")"

  echo "Generating thumbnail..."
  echo "  Prompt: ${prompt:0:100}$([ ${#prompt} -gt 100 ] && echo '...')"
  echo "  Model: $model"
  echo "  Aspect ratio: $aspect_ratio"
  echo "  Output: $output"
  echo ""

  # Build request payload
  local payload
  payload=$(jq -n \
    --arg prompt "$prompt" \
    --arg aspect_ratio "$aspect_ratio" \
    '{
      contents: [{
        role: "user",
        parts: [{ text: $prompt }]
      }],
      generationConfig: {
        responseModalities: ["IMAGE"],
        thinkingConfig: { thinkingLevel: "MINIMAL" },
        imageConfig: { aspectRatio: $aspect_ratio, imageSize: "1K" }
      }
    }')

  # Call Gemini API
  local endpoint="${api_url}/models/${model}:${generate_api}?key=${api_key}"

  local response http_code
  local tmp_response
  tmp_response=$(mktemp)

  http_code=$(curl -s -w "%{http_code}" -o "$tmp_response" \
    -X POST "$endpoint" \
    -H "Content-Type: application/json" \
    -d "$payload")

  if [[ "$http_code" -ne 200 ]]; then
    echo "Error: API request failed with HTTP $http_code" >&2
    # Show error message but mask the API key
    local err_body
    err_body=$(cat "$tmp_response")
    echo "$err_body" | jq -r '.error.message // .error // .' 2>/dev/null || echo "$err_body" >&2
    rm -f "$tmp_response"
    exit 1
  fi

  response=$(cat "$tmp_response")
  rm -f "$tmp_response"

  # Extract base64 image data from response (generateContent returns plain JSON)
  local image_data mime_type
  image_data=$(echo "$response" | jq -r '
    .candidates[0].content.parts[]
    | select(.inlineData != null)
    | .inlineData.data' 2>/dev/null | head -1)

  mime_type=$(echo "$response" | jq -r '
    .candidates[0].content.parts[]
    | select(.inlineData != null)
    | .inlineData.mimeType' 2>/dev/null | head -1)

  if [[ -z "$image_data" || "$image_data" == "null" ]]; then
    echo "Error: No image data in API response" >&2
    local text_part
    text_part=$(echo "$response" | jq -r '.candidates[0].content.parts[] | select(.text != null) | .text' 2>/dev/null | head -3)
    [[ -n "$text_part" ]] && echo "Response text: $text_part" >&2
    echo "Raw response (first 500 chars): ${response:0:500}" >&2
    exit 1
  fi

  # Determine file extension from mime type
  local ext="png"
  case "$mime_type" in
    image/jpeg) ext="jpg" ;;
    image/png)  ext="png" ;;
    image/webp) ext="webp" ;;
  esac

  # Adjust output extension if needed
  local output_ext="${output##*.}"
  if [[ "$output_ext" != "$ext" && "$output_ext" == "png" ]]; then
    output="${output%.*}.${ext}"
  fi

  # Decode base64 and save
  echo "$image_data" | base64 -d > "$output" 2>/dev/null || \
  echo "$image_data" | python3 -c "import sys,base64; sys.stdout.buffer.write(base64.b64decode(sys.stdin.read().strip()))" > "$output" 2>/dev/null || \
  echo "$image_data" | python -c "import sys,base64; sys.stdout.buffer.write(base64.b64decode(sys.stdin.read().strip()))" > "$output"

  local file_size
  if [[ -f "$output" ]]; then
    file_size=$(wc -c < "$output" | tr -d ' ')
    echo "Thumbnail saved: $output (${file_size} bytes)"
    echo ""
    echo "Use as MV background:"
    echo "  ./scripts/render-mv.sh --audio song.mp3 --lyrics song.lrc --title \"Title\" --background \"$output\""
  else
    echo "Error: Failed to save image" >&2
    exit 1
  fi
}

# ── Main ─────────────────────────────────────────────────────────────

main() {
  local command="${1:-}"
  shift || true

  case "$command" in
    generate)
      handle_generate "$@"
      ;;
    config)
      handle_config "$@"
      ;;
    -h|--help|help)
      head -16 "$0" | tail -14
      ;;
    *)
      echo "Usage: acestep-thumbnail.sh <command> [options]" >&2
      echo "" >&2
      echo "Commands:" >&2
      echo "  generate   Generate a thumbnail image" >&2
      echo "  config     Manage configuration" >&2
      echo "  help       Show usage" >&2
      exit 1
      ;;
  esac
}

main "$@"
