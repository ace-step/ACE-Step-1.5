#!/bin/bash
#
# acestep-lyrics-transcription.sh - Transcribe audio to timestamped lyrics (LRC/SRT/JSON)
#
# Requirements: curl, jq
#
# Usage:
#   ./acestep-lyrics-transcription.sh transcribe --audio <file> [options]
#   ./acestep-lyrics-transcription.sh config [--get|--set|--reset]
#
# Output:
#   - LRC/SRT/JSON files saved to output directory

set -e

export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config.json"
OUTPUT_DIR="$(cd "${SCRIPT_DIR}/../../../.." && pwd)/acestep_output"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Convert MSYS2/Cygwin paths to Windows-native paths for Python
to_python_path() {
    if command -v cygpath &> /dev/null; then
        cygpath -m "$1"
    else
        echo "$1"
    fi
}

# Detect python executable (python3 or python)
PYTHON_CMD=""
find_python() {
    if [ -n "$PYTHON_CMD" ]; then return; fi
    # Test actual execution, not just existence (Windows Store python3 shim returns exit 49)
    if python3 -c "pass" &> /dev/null; then
        PYTHON_CMD="python3"
    elif python -c "pass" &> /dev/null; then
        PYTHON_CMD="python"
    else
        echo -e "${RED}Error: python3 or python is required but not found.${NC}"
        exit 1
    fi
}

# ─── Dependencies ───

check_deps() {
    if ! command -v curl &> /dev/null; then
        echo -e "${RED}Error: curl is required but not installed.${NC}"
        exit 1
    fi
    if ! command -v jq &> /dev/null; then
        echo -e "${RED}Error: jq is required but not installed.${NC}"
        echo "Install: apt install jq / brew install jq / choco install jq"
        exit 1
    fi
}

# ─── Config ───

DEFAULT_CONFIG='{
  "provider": "openai",
  "output_format": "lrc",
  "openai": {
    "api_key": "",
    "api_url": "https://api.openai.com/v1",
    "model": "whisper-1"
  },
  "elevenlabs": {
    "api_key": "",
    "api_url": "https://api.elevenlabs.io/v1",
    "model": "scribe_v2"
  }
}'

ensure_config() {
    if [ ! -f "$CONFIG_FILE" ]; then
        local example="${SCRIPT_DIR}/config.example.json"
        if [ -f "$example" ]; then
            cp "$example" "$CONFIG_FILE"
            echo -e "${YELLOW}Config file created from config.example.json. Please configure your settings:${NC}"
            echo -e "  ${CYAN}./scripts/acestep-lyrics-transcription.sh config --set provider <openai|elevenlabs>${NC}"
            echo -e "  ${CYAN}./scripts/acestep-lyrics-transcription.sh config --set <provider>.api_key <key>${NC}"
        else
            echo "$DEFAULT_CONFIG" > "$CONFIG_FILE"
        fi
    fi
}

get_config() {
    local key="$1"
    ensure_config
    local jq_path=".${key}"
    local value
    value=$(jq -r "$jq_path" "$CONFIG_FILE" 2>/dev/null)
    if [ "$value" = "null" ]; then
        echo ""
    else
        echo "$value" | tr -d '\r\n'
    fi
}

set_config() {
    local key="$1"
    local value="$2"
    ensure_config
    local tmp_file="${CONFIG_FILE}.tmp"
    local jq_path=".${key}"

    if [ "$value" = "true" ] || [ "$value" = "false" ]; then
        jq "$jq_path = $value" "$CONFIG_FILE" > "$tmp_file"
    elif [[ "$value" =~ ^-?[0-9]+$ ]] || [[ "$value" =~ ^-?[0-9]+\.[0-9]+$ ]]; then
        jq "$jq_path = $value" "$CONFIG_FILE" > "$tmp_file"
    else
        jq "$jq_path = \"$value\"" "$CONFIG_FILE" > "$tmp_file"
    fi

    mv "$tmp_file" "$CONFIG_FILE"
    echo "Set $key = $value"
}

ensure_output_dir() {
    mkdir -p "$OUTPUT_DIR"
}

# ─── Format Conversion ───

# Convert word-level timestamps to LRC format
# Input: JSON array of {word, start, end} on stdin
# Output: LRC text
words_to_lrc() {
    local json_file="$(to_python_path "$1")"
    local output_file="$(to_python_path "$2")"
    local line_gap="${3:-1.5}"
    find_python

    $PYTHON_CMD -c "
import json, sys, unicodedata

def is_cjk(ch):
    cp = ord(ch)
    return (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
            0x20000 <= cp <= 0x2A6DF or 0x2A700 <= cp <= 0x2B73F or
            0x2B740 <= cp <= 0x2B81F or 0x2B820 <= cp <= 0x2CEAF or
            0xF900 <= cp <= 0xFAFF or 0x2F800 <= cp <= 0x2FA1F or
            0x3000 <= cp <= 0x303F or 0x3040 <= cp <= 0x309F or
            0x30A0 <= cp <= 0x30FF or 0xFF00 <= cp <= 0xFFEF)

def smart_join(word_list):
    if not word_list:
        return ''
    result = word_list[0]
    for j in range(1, len(word_list)):
        prev_w = word_list[j-1]
        curr_w = word_list[j]
        prev_last = prev_w[-1] if prev_w else ''
        curr_first = curr_w[0] if curr_w else ''
        if is_cjk(prev_last) or is_cjk(curr_first):
            result += curr_w
        else:
            result += ' ' + curr_w
    return result.strip()

with open('$json_file', 'r', encoding='utf-8') as f:
    words = json.load(f)

if not words:
    sys.exit(0)

lines = []
current_line = []
current_start = words[0]['start']

for i, w in enumerate(words):
    current_line.append(w['word'])
    is_last = (i == len(words) - 1)
    has_punct = w['word'].rstrip().endswith(('.', '!', '?', '。', '！', '？', '，', ','))
    has_gap = (not is_last and words[i+1]['start'] - w['end'] > $line_gap)

    if is_last or has_punct or has_gap:
        text = smart_join(current_line)
        text = text.rstrip('，。,.')
        if text:
            mins = int(current_start) // 60
            secs = current_start - mins * 60
            lines.append(f'[{mins:02d}:{secs:05.2f}]{text}')
        current_line = []
        if not is_last:
            current_start = words[i+1]['start']

with open('$output_file', 'w', encoding='utf-8') as f:
    for line in lines:
        f.write(line + '\n')
"
}

# Convert word-level timestamps to SRT format
words_to_srt() {
    local json_file="$(to_python_path "$1")"
    local output_file="$(to_python_path "$2")"
    local line_gap="${3:-1.5}"
    find_python

    $PYTHON_CMD -c "
import json, sys

def is_cjk(ch):
    cp = ord(ch)
    return (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
            0x20000 <= cp <= 0x2A6DF or 0x2A700 <= cp <= 0x2B73F or
            0x2B740 <= cp <= 0x2B81F or 0x2B820 <= cp <= 0x2CEAF or
            0xF900 <= cp <= 0xFAFF or 0x2F800 <= cp <= 0x2FA1F or
            0x3000 <= cp <= 0x303F or 0x3040 <= cp <= 0x309F or
            0x30A0 <= cp <= 0x30FF or 0xFF00 <= cp <= 0xFFEF)

def smart_join(word_list):
    if not word_list:
        return ''
    result = word_list[0]
    for j in range(1, len(word_list)):
        prev_w = word_list[j-1]
        curr_w = word_list[j]
        prev_last = prev_w[-1] if prev_w else ''
        curr_first = curr_w[0] if curr_w else ''
        if is_cjk(prev_last) or is_cjk(curr_first):
            result += curr_w
        else:
            result += ' ' + curr_w
    return result.strip()

with open('$json_file', 'r', encoding='utf-8') as f:
    words = json.load(f)

if not words:
    sys.exit(0)

def fmt(t):
    h = int(t) // 3600
    m = (int(t) % 3600) // 60
    s = t - h*3600 - m*60
    return f'{h:02d}:{m:02d}:{s:06.3f}'.replace('.', ',')

lines = []
current_line = []
current_start = words[0]['start']
current_end = words[0]['end']

for i, w in enumerate(words):
    current_line.append(w['word'])
    current_end = w['end']
    is_last = (i == len(words) - 1)
    has_punct = w['word'].rstrip().endswith(('.', '!', '?', '。', '！', '？', '，', ','))
    has_gap = (not is_last and words[i+1]['start'] - w['end'] > $line_gap)

    if is_last or has_punct or has_gap:
        text = smart_join(current_line)
        text = text.rstrip('，。,.')
        if text:
            lines.append((current_start, current_end, text))
        current_line = []
        if not is_last:
            current_start = words[i+1]['start']

with open('$output_file', 'w', encoding='utf-8') as f:
    for idx, (s, e, text) in enumerate(lines, 1):
        f.write(f'{idx}\n')
        f.write(f'{fmt(s)} --> {fmt(e)}\n')
        f.write(f'{text}\n')
        f.write('\n')
"
}

# ─── OpenAI Whisper ───

transcribe_openai() {
    local audio_file="$1"
    local language="$2"
    local words_file="$3"

    local api_key=$(get_config "openai.api_key")
    local api_url=$(get_config "openai.api_url")
    local model=$(get_config "openai.model")

    [ -z "$api_key" ] && { echo -e "${RED}Error: OpenAI API key not configured.${NC}"; echo "Run: ./acestep-lyrics-transcription.sh config --set openai.api_key YOUR_KEY"; exit 1; }
    [ -z "$api_url" ] && api_url="https://api.openai.com/v1"
    [ -z "$model" ] && model="whisper-1"

    echo -e "  Provider: OpenAI (${model})"

    local resp_file=$(mktemp)

    # Build curl command
    local curl_args=(
        -s -w "%{http_code}"
        -o "$resp_file"
        -X POST "${api_url}/audio/transcriptions"
        -H "Authorization: Bearer ${api_key}"
        -F "file=@${audio_file}"
        -F "model=${model}"
        -F "response_format=verbose_json"
        -F "timestamp_granularities[]=word"
        -F "timestamp_granularities[]=segment"
    )

    [ -n "$language" ] && curl_args+=(-F "language=${language}")

    local http_code
    http_code=$(curl "${curl_args[@]}")

    if [ "$http_code" != "200" ]; then
        local err
        err=$(jq -r '.error.message // .detail // "Unknown error"' "$resp_file" 2>/dev/null)
        echo -e "${RED}Error: HTTP $http_code - $err${NC}"
        rm -f "$resp_file"
        return 1
    fi

    # Extract word-level timestamps into normalized format [{word, start, end}]
    jq '[.words[] | {word: .word, start: .start, end: .end}]' "$resp_file" > "$words_file" 2>/dev/null

    # Show transcription text
    local text
    text=$(jq -r '.text // empty' "$resp_file" 2>/dev/null)
    echo -e "  ${GREEN}Transcription complete${NC}"
    echo ""
    echo "$text"

    rm -f "$resp_file"
}

# ─── ElevenLabs Scribe ───

transcribe_elevenlabs() {
    local audio_file="$1"
    local language="$2"
    local words_file="$3"

    local api_key=$(get_config "elevenlabs.api_key")
    local api_url=$(get_config "elevenlabs.api_url")
    local model=$(get_config "elevenlabs.model")

    [ -z "$api_key" ] && { echo -e "${RED}Error: ElevenLabs API key not configured.${NC}"; echo "Run: ./acestep-lyrics-transcription.sh config --set elevenlabs.api_key YOUR_KEY"; exit 1; }
    [ -z "$api_url" ] && api_url="https://api.elevenlabs.io/v1"
    [ -z "$model" ] && model="scribe_v2"

    echo -e "  Provider: ElevenLabs (${model})"

    local resp_file=$(mktemp)

    local curl_args=(
        -s -w "%{http_code}"
        -o "$resp_file"
        -X POST "${api_url}/speech-to-text"
        -H "xi-api-key: ${api_key}"
        -F "file=@${audio_file}"
        -F "model_id=${model}"
    )

    [ -n "$language" ] && curl_args+=(-F "language_code=${language}")

    local http_code
    http_code=$(curl "${curl_args[@]}")

    if [ "$http_code" != "200" ]; then
        local err
        err=$(jq -r '.detail.message // .detail // "Unknown error"' "$resp_file" 2>/dev/null)
        echo -e "${RED}Error: HTTP $http_code - $err${NC}"
        rm -f "$resp_file"
        return 1
    fi

    # ElevenLabs response: { text, words: [{text, start, end, type}...] }
    # Normalize to [{word, start, end}], timestamps already in seconds, filter only "word" type
    jq '[.words[] | select(.type == "word") | {word: .text, start: .start, end: .end}]' "$resp_file" > "$words_file" 2>/dev/null

    local text
    text=$(jq -r '.text // empty' "$resp_file" 2>/dev/null)
    echo -e "  ${GREEN}Transcription complete${NC}"
    echo ""
    echo "$text"

    rm -f "$resp_file"
}

# ─── Commands ───

cmd_transcribe() {
    check_deps
    ensure_config

    local audio="" language="" output="" format="" provider=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --audio|-a)    audio="$2"; shift 2 ;;
            --language|-l) language="$2"; shift 2 ;;
            --output|-o)   output="$2"; shift 2 ;;
            --format|-f)   format="$2"; shift 2 ;;
            --provider|-p) provider="$2"; shift 2 ;;
            *) [ -z "$audio" ] && audio="$1"; shift ;;
        esac
    done

    [ -z "$audio" ] && { echo -e "${RED}Error: --audio is required${NC}"; echo "Usage: $0 transcribe --audio <file> [options]"; exit 1; }
    [ ! -f "$audio" ] && { echo -e "${RED}Error: audio file not found: $audio${NC}"; exit 1; }

    # Resolve absolute path
    audio="$(cd "$(dirname "$audio")" && pwd)/$(basename "$audio")"

    [ -z "$provider" ] && provider=$(get_config "provider")
    [ -z "$provider" ] && provider="openai"

    [ -z "$format" ] && format=$(get_config "output_format")
    [ -z "$format" ] && format="lrc"

    # Default output path
    if [ -z "$output" ]; then
        ensure_output_dir
        local basename="$(basename "${audio%.*}")"
        output="${OUTPUT_DIR}/${basename}.${format}"
    fi

    echo "Transcribing..."
    echo "  Audio: $(basename "$audio")"
    echo "  Format: $format"

    # Transcribe to normalized word timestamps
    local words_file=$(mktemp)

    case "$provider" in
        openai)   transcribe_openai "$audio" "$language" "$words_file" ;;
        elevenlabs) transcribe_elevenlabs "$audio" "$language" "$words_file" ;;
        *) echo -e "${RED}Error: unknown provider: $provider${NC}"; echo "Supported: openai, elevenlabs"; rm -f "$words_file"; exit 1 ;;
    esac

    # Check if we got words
    local word_count
    word_count=$(jq 'length' "$words_file" 2>/dev/null)
    if [ -z "$word_count" ] || [ "$word_count" = "0" ]; then
        echo -e "${YELLOW}Warning: no word-level timestamps returned${NC}"
        rm -f "$words_file"
        return 1
    fi

    echo ""
    echo "  Words detected: $word_count"

    # Convert to output format
    mkdir -p "$(dirname "$output")"

    case "$format" in
        lrc)
            words_to_lrc "$words_file" "$output"
            ;;
        srt)
            words_to_srt "$words_file" "$output"
            ;;
        json)
            cp "$words_file" "$output"
            ;;
        *)
            echo -e "${RED}Error: unknown format: $format (supported: lrc, srt, json)${NC}"
            rm -f "$words_file"
            exit 1
            ;;
    esac

    rm -f "$words_file"

    echo -e "  ${GREEN}Saved: $output${NC}"
    echo ""
    echo -e "${GREEN}Done!${NC}"
}

cmd_config() {
    check_deps
    ensure_config

    local action="" key="" value=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --get)       action="get"; key="$2"; shift 2 ;;
            --set)       action="set"; key="$2"; value="$3"; shift 3 ;;
            --reset)     action="reset"; shift ;;
            --list)      action="list"; shift ;;
            --check-key) action="check-key"; shift ;;
            *) shift ;;
        esac
    done

    case "$action" in
        "check-key")
            local provider=$(get_config "provider")
            [ -z "$provider" ] && provider="openai"
            local api_key=$(get_config "${provider}.api_key")
            echo "provider: $provider"
            if [ -n "$api_key" ]; then
                echo "api_key: configured"
            else
                echo "api_key: empty"
            fi
            ;;
        "get")
            [ -z "$key" ] && { echo -e "${RED}Error: --get requires KEY${NC}"; exit 1; }
            local result=$(get_config "$key")
            [ -n "$result" ] && echo "$key = $result" || echo "Key not found: $key"
            ;;
        "set")
            [ -z "$key" ] || [ -z "$value" ] && { echo -e "${RED}Error: --set requires KEY VALUE${NC}"; exit 1; }
            set_config "$key" "$value"
            ;;
        "reset")
            echo "$DEFAULT_CONFIG" > "$CONFIG_FILE"
            echo -e "${GREEN}Configuration reset to defaults.${NC}"
            jq 'walk(if type == "object" and has("api_key") and (.api_key | length) > 0 then .api_key = "***" else . end)' "$CONFIG_FILE"
            ;;
        "list")
            echo "Current configuration:"
            jq 'walk(if type == "object" and has("api_key") and (.api_key | length) > 0 then .api_key = "***" else . end)' "$CONFIG_FILE"
            ;;
        *)
            echo "Config file: $CONFIG_FILE"
            echo "----------------------------------------"
            jq 'walk(if type == "object" and has("api_key") and (.api_key | length) > 0 then .api_key = "***" else . end)' "$CONFIG_FILE"
            echo ""
            echo "----------------------------------------"
            echo ""
            echo "Usage:"
            echo "  config --list              Show config"
            echo "  config --get <key>         Get value"
            echo "  config --set <key> <val>   Set value"
            echo "  config --reset             Reset to defaults"
            echo ""
            echo "Examples:"
            echo "  config --set provider elevenlabs"
            echo "  config --set openai.api_key sk-..."
            echo "  config --set elevenlabs.api_key ..."
            echo "  config --set output_format srt"
            ;;
    esac
}

show_help() {
    echo "Lyrics Transcription CLI"
    echo ""
    echo "Requirements: curl, jq, python3"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  transcribe   Transcribe audio to timestamped lyrics"
    echo "  config       Manage configuration"
    echo ""
    echo "Transcribe Options:"
    echo "  -a, --audio      Audio file path (required)"
    echo "  -l, --language   Language code (e.g. zh, en, ja)"
    echo "  -f, --format     Output format: lrc, srt, json (default: lrc)"
    echo "  -p, --provider   API provider: openai, elevenlabs"
    echo "  -o, --output     Output file path"
    echo ""
    echo "Examples:"
    echo "  $0 transcribe --audio song.mp3"
    echo "  $0 transcribe --audio song.mp3 --language zh --format lrc"
    echo "  $0 config --set provider openai"
}

# ─── Main ───

case "$1" in
    transcribe) shift; cmd_transcribe "$@" ;;
    config)     shift; cmd_config "$@" ;;
    help|--help|-h) show_help ;;
    *) show_help; exit 1 ;;
esac
