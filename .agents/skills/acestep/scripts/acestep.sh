#!/bin/bash
#
# ACE-Step Music Generation CLI (Bash + Curl + jq)
#
# Requirements: curl, jq
#
# Usage:
#   ./acestep.sh generate "Music description" [options]
#   ./acestep.sh random [--no-thinking]
#   ./acestep.sh status <job_id>
#   ./acestep.sh models
#   ./acestep.sh health
#   ./acestep.sh config [--get|--set|--reset]
#
# Output:
#   - Results saved to output/<job_id>.json
#   - Audio files downloaded to output/<job_id>_1.mp3, output/<job_id>_2.mp3, ...

set -e

# Ensure UTF-8 encoding for non-ASCII characters (Japanese, Chinese, etc.)
export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config.json"
# Output dir at same level as .claude (go up 4 levels from scripts/)
OUTPUT_DIR="$(cd "${SCRIPT_DIR}/../../../.." && pwd)/acestep_output"
DEFAULT_API_URL="http://127.0.0.1:8001"
STAR_MARKER_FILE="${SCRIPT_DIR}/.first_gen_done"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# Show GitHub star prompt on first successful generation
show_star_prompt() {
    if [ ! -f "$STAR_MARKER_FILE" ]; then
        touch "$STAR_MARKER_FILE"
        echo ""
        echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${BOLD}  ACE-Step is free and open-source.${NC}"
        echo -e "  If you enjoyed this, a ${YELLOW}★ Star${NC} on GitHub means a lot to us!"
        echo -e "  ${CYAN}→ https://github.com/ace-step/ACE-Step-1.5${NC}"
        echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    fi
}

# Check dependencies
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

# JSON value extractor using jq
# Usage: json_get "$json" ".key" or json_get "$json" ".nested.key"
json_get() {
    local json="$1"
    local path="$2"
    echo "$json" | jq -r "$path // empty" 2>/dev/null
}

# Extract array values using jq
json_get_array() {
    local json="$1"
    local path="$2"
    echo "$json" | jq -r "$path[]? // empty" 2>/dev/null
}

# Ensure output directory exists
ensure_output_dir() {
    mkdir -p "$OUTPUT_DIR"
}

# Default config
DEFAULT_CONFIG='{
  "api_url": "http://127.0.0.1:8001",
  "api_key": "",
  "api_mode": "native",
  "generation": {
    "thinking": true,
    "use_format": true,
    "use_cot_caption": true,
    "use_cot_language": true,
    "audio_format": "mp3",
    "vocal_language": "en"
  }
}'

# Ensure config file exists
ensure_config() {
    if [ ! -f "$CONFIG_FILE" ]; then
        local example="${SCRIPT_DIR}/config.example.json"
        if [ -f "$example" ]; then
            cp "$example" "$CONFIG_FILE"
            echo -e "${YELLOW}Config file created from config.example.json. Please configure your settings:${NC}"
            echo -e "  ${CYAN}./scripts/acestep.sh config --set api_url <url>${NC}"
            echo -e "  ${CYAN}./scripts/acestep.sh config --set api_key <key>${NC}"
        else
            echo "$DEFAULT_CONFIG" > "$CONFIG_FILE"
        fi
    fi
}

# Get config value using jq
get_config() {
    local key="$1"
    ensure_config
    # Convert dot notation to jq path: "generation.thinking" -> ".generation.thinking"
    local jq_path=".${key}"
    local value
    # Don't use // operator as it treats boolean false as falsy
    value=$(jq -r "$jq_path" "$CONFIG_FILE" 2>/dev/null)
    # Remove any trailing whitespace/newlines (Windows compatibility)
    # Return empty string if value is "null" (key doesn't exist)
    if [ "$value" = "null" ]; then
        echo ""
    else
        echo "$value" | tr -d '\r\n'
    fi
}

# Normalize boolean value for jq --argjson
normalize_bool() {
    local val="$1"
    local default="${2:-false}"
    case "$val" in
        true|True|TRUE|1) echo "true" ;;
        false|False|FALSE|0) echo "false" ;;
        *) echo "$default" ;;
    esac
}

# Set config value using jq
set_config() {
    local key="$1"
    local value="$2"
    ensure_config

    local tmp_file="${CONFIG_FILE}.tmp"
    local jq_path=".${key}"

    # Determine value type and set accordingly
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

# Load API URL
load_api_url() {
    local url=$(get_config "api_url")
    echo "${url:-$DEFAULT_API_URL}"
}

# Load API Key
load_api_key() {
    local key=$(get_config "api_key")
    echo "${key:-}"
}

# Check API health
check_health() {
    local url="$1"
    local status
    status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "${url}/health" 2>/dev/null) || true
    [ "$status" = "200" ]
}

# Build auth header
build_auth_header() {
    local api_key=$(load_api_key)
    if [ -n "$api_key" ]; then
        echo "-H \"Authorization: Bearer ${api_key}\""
    fi
}

# Prompt for URL
prompt_for_url() {
    echo ""
    echo -e "${YELLOW}API server is not responding.${NC}"
    echo "Please enter the API URL (or press Enter for default):"
    read -p "API URL [$DEFAULT_API_URL]: " user_input
    echo "${user_input:-$DEFAULT_API_URL}"
}

# Ensure API connection
ensure_connection() {
    ensure_config
    local api_url=$(load_api_url)

    if check_health "$api_url"; then
        echo "$api_url"
        return 0
    fi

    echo -e "${YELLOW}Cannot connect to: $api_url${NC}" >&2
    local new_url=$(prompt_for_url)

    if check_health "$new_url"; then
        set_config "api_url" "$new_url" > /dev/null
        echo -e "${GREEN}Saved API URL: $new_url${NC}" >&2
        echo "$new_url"
        return 0
    fi

    echo -e "${RED}Error: Cannot connect to $new_url${NC}" >&2
    exit 1
}

# Save result to JSON file
save_result() {
    local job_id="$1"
    local result_json="$2"

    ensure_output_dir
    local output_file="${OUTPUT_DIR}/${job_id}.json"
    echo "$result_json" > "$output_file"
    echo -e "${GREEN}Result saved: $output_file${NC}"
}

# Health command
cmd_health() {
    check_deps
    ensure_config
    local api_url=$(load_api_url)

    echo "Checking API at: $api_url"
    if check_health "$api_url"; then
        echo -e "${GREEN}Status: OK${NC}"
        curl -s "${api_url}/health"
        echo ""
    else
        echo -e "${RED}Status: FAILED${NC}"
        exit 1
    fi
}

# Config command
cmd_config() {
    check_deps
    ensure_config

    local action=""
    local key=""
    local value=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --get) action="get"; key="$2"; shift 2 ;;
            --set) action="set"; key="$2"; value="$3"; shift 3 ;;
            --reset) action="reset"; shift ;;
            --list) action="list"; shift ;;
            --check-key) action="check-key"; shift ;;
            *) shift ;;
        esac
    done

    case "$action" in
        "check-key")
            local api_key=$(get_config "api_key")
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
            echo "Output dir: $OUTPUT_DIR"
            echo "----------------------------------------"
            cat "$CONFIG_FILE"
            echo "----------------------------------------"
            echo ""
            echo "Usage:"
            echo "  config --list              Show config"
            echo "  config --get <key>         Get value"
            echo "  config --set <key> <val>   Set value"
            echo "  config --reset             Reset to defaults"
            ;;
    esac
}

# Models command
cmd_models() {
    check_deps
    local api_url=$(ensure_connection)
    local api_key=$(load_api_key)

    echo "Available Models:"
    echo "----------------------------------------"
    if [ -n "$api_key" ]; then
        curl -s -H "Authorization: Bearer ${api_key}" "${api_url}/v1/models"
    else
        curl -s "${api_url}/v1/models"
    fi
    echo ""
}

# Query job result via /query_result endpoint
query_job_result() {
    local api_url="$1"
    local job_id="$2"
    local api_key=$(load_api_key)

    local payload=$(jq -n --arg id "$job_id" '{"task_id_list": [$id]}')

    if [ -n "$api_key" ]; then
        curl -s -X POST "${api_url}/query_result" \
            -H "Content-Type: application/json; charset=utf-8" \
            -H "Authorization: Bearer ${api_key}" \
            -d "$payload"
    else
        curl -s -X POST "${api_url}/query_result" \
            -H "Content-Type: application/json; charset=utf-8" \
            -d "$payload"
    fi
}

# Parse query_result response to extract status (0=processing, 1=success, 2=failed)
# Response is wrapped: {"data": [...], "code": 200, ...}
# Uses temp file to avoid jq pipe issues with special characters on Windows
parse_query_status() {
    local response="$1"
    local tmp_file=$(mktemp)
    printf '%s' "$response" > "$tmp_file"
    jq -r '.data[0].status // .[0].status // 0' "$tmp_file"
    rm -f "$tmp_file"
}

# Parse result JSON string from query_result response
# The result field is a JSON string that needs to be parsed
# Uses temp file to avoid jq pipe issues with special characters on Windows
parse_query_result() {
    local response="$1"
    local tmp_file=$(mktemp)
    printf '%s' "$response" > "$tmp_file"
    jq -r '.data[0].result // .[0].result // "[]"' "$tmp_file"
    rm -f "$tmp_file"
}

# Extract audio file paths from result (returns newline-separated paths)
# Uses temp file to avoid jq pipe issues with special characters on Windows
parse_audio_files() {
    local result="$1"
    local tmp_file=$(mktemp)
    printf '%s' "$result" > "$tmp_file"
    jq -r '.[].file // empty' "$tmp_file" 2>/dev/null
    rm -f "$tmp_file"
}

# Extract metas value from result
# Uses temp file to avoid jq pipe issues with special characters on Windows
parse_metas_value() {
    local result="$1"
    local key="$2"
    local tmp_file=$(mktemp)
    printf '%s' "$result" > "$tmp_file"
    jq -r ".[0].metas.$key // .[0].$key // empty" "$tmp_file" 2>/dev/null
    rm -f "$tmp_file"
}

# Status command
cmd_status() {
    check_deps
    local job_id="$1"

    [ -z "$job_id" ] && { echo -e "${RED}Error: job_id required${NC}"; echo "Usage: $0 status <job_id>"; exit 1; }

    local api_url=$(ensure_connection)
    local response=$(query_job_result "$api_url" "$job_id")

    local status=$(parse_query_status "$response")
    echo "Job ID: $job_id"

    case "$status" in
        0)
            echo "Status: processing"
            ;;
        1)
            echo "Status: succeeded"
            echo ""
            local result_file=$(mktemp)
            parse_query_result "$response" > "$result_file"

            local bpm=$(jq -r '.[0].metas.bpm // .[0].bpm // empty' "$result_file" 2>/dev/null)
            local keyscale=$(jq -r '.[0].metas.keyscale // .[0].keyscale // empty' "$result_file" 2>/dev/null)
            local duration=$(jq -r '.[0].metas.duration // .[0].duration // empty' "$result_file" 2>/dev/null)

            echo "Result:"
            [ -n "$bpm" ] && echo "  BPM: $bpm"
            [ -n "$keyscale" ] && echo "  Key: $keyscale"
            [ -n "$duration" ] && echo "  Duration: ${duration}s"

            # Save and download
            save_result "$job_id" "$response"
            download_audios "$api_url" "$job_id" "$result_file"
            rm -f "$result_file"
            ;;
        2)
            echo "Status: failed"
            echo ""
            echo -e "${RED}Task failed${NC}"
            ;;
        *)
            echo "Status: unknown ($status)"
            ;;
    esac
}

# Download audio files from result file
# Usage: download_audios <api_url> <job_id> <result_file>
download_audios() {
    local api_url="$1"
    local job_id="$2"
    local result_file="$3"
    local api_key=$(load_api_key)

    ensure_output_dir

    local audio_format=$(get_config "generation.audio_format")
    [ -z "$audio_format" ] && audio_format="mp3"

    # Read result file content and extract audio paths using pipe (avoid temp file path issues on Windows)
    local result_content
    result_content=$(cat "$result_file" 2>/dev/null)

    if [ -z "$result_content" ]; then
        echo -e "  ${RED}Error: Result file is empty or cannot be read${NC}"
        return 1
    fi

    # Extract audio paths using pipe instead of file (better Windows compatibility)
    local audio_paths
    audio_paths=$(echo "$result_content" | jq -r '.[].file // empty' 2>&1)
    local jq_exit_code=$?

    if [ $jq_exit_code -ne 0 ]; then
        echo -e "  ${RED}Error: Failed to parse result JSON${NC}"
        echo -e "  ${RED}jq error: $audio_paths${NC}"
        return 1
    fi

    if [ -z "$audio_paths" ]; then
        echo -e "  ${YELLOW}No audio files found in result${NC}"
        return 0
    fi

    local count=1
    while IFS= read -r audio_path; do
        # Skip empty lines and remove potential Windows carriage return
        audio_path=$(echo "$audio_path" | tr -d '\r')
        if [ -n "$audio_path" ]; then
            local output_file="${OUTPUT_DIR}/${job_id}_${count}.${audio_format}"
            local download_url="${api_url}${audio_path}"

            echo -e "  ${CYAN}Downloading audio $count...${NC}"
            local curl_output
            local curl_exit_code
            if [ -n "$api_key" ]; then
                curl_output=$(curl -s --connect-timeout 10 --max-time 300 \
                    -w "%{http_code}" \
                    -o "$output_file" \
                    -H "Authorization: Bearer ${api_key}" \
                    "$download_url" 2>&1)
                curl_exit_code=$?
            else
                curl_output=$(curl -s --connect-timeout 10 --max-time 300 \
                    -w "%{http_code}" \
                    -o "$output_file" \
                    "$download_url" 2>&1)
                curl_exit_code=$?
            fi

            if [ $curl_exit_code -ne 0 ]; then
                echo -e "  ${RED}Failed to download (curl error $curl_exit_code): $download_url${NC}"
                rm -f "$output_file" 2>/dev/null
            elif [ -f "$output_file" ] && [ -s "$output_file" ]; then
                echo -e "  ${GREEN}Saved: $output_file${NC}"
            else
                echo -e "  ${RED}Failed to download (HTTP $curl_output): $download_url${NC}"
                rm -f "$output_file" 2>/dev/null
            fi
            count=$((count + 1))
        fi
    done <<< "$audio_paths"
}

# =============================================================================
# Completion Mode (OpenRouter /v1/chat/completions)
# =============================================================================

# Load api_mode from config (default: native)
load_api_mode() {
    local mode=$(get_config "api_mode")
    echo "${mode:-native}"
}

# Get model ID from /v1/models endpoint for completion mode
get_completion_model() {
    local api_url="$1"
    local user_model="$2"
    local api_key=$(load_api_key)

    # If user specified a model, prefix with acemusic/ if needed
    if [ -n "$user_model" ]; then
        if [[ "$user_model" == */* ]]; then
            echo "$user_model"
        else
            echo "acemusic/${user_model}"
        fi
        return
    fi

    # Query /v1/models for the first available model
    local response
    if [ -n "$api_key" ]; then
        response=$(curl -s -H "Authorization: Bearer ${api_key}" "${api_url}/v1/models" 2>/dev/null)
    else
        response=$(curl -s "${api_url}/v1/models" 2>/dev/null)
    fi

    local model_id
    model_id=$(echo "$response" | jq -r '.data[0].id // empty' 2>/dev/null)
    echo "${model_id:-acemusic/acestep-v15-turbo}"
}

# Decode base64 audio data URL and save to file
# Handles cross-platform compatibility (Linux/macOS/Windows MSYS)
decode_base64_audio() {
    local data_url="$1"
    local output_file="$2"

    # Strip data URL prefix: data:audio/mpeg;base64,...
    local b64_data="${data_url#data:*;base64,}"

    local tmp_b64=$(mktemp)
    printf '%s' "$b64_data" > "$tmp_b64"

    if command -v base64 &> /dev/null; then
        # Linux / macOS / MSYS2
        base64 -d < "$tmp_b64" > "$output_file" 2>/dev/null || \
        base64 -D < "$tmp_b64" > "$output_file" 2>/dev/null || \
        python3 -c "import base64,sys; sys.stdout.buffer.write(base64.b64decode(sys.stdin.read()))" < "$tmp_b64" > "$output_file" 2>/dev/null || \
        python -c "import base64,sys; sys.stdout.buffer.write(base64.b64decode(sys.stdin.read()))" < "$tmp_b64" > "$output_file" 2>/dev/null
    else
        # Fallback to python
        python3 -c "import base64,sys; sys.stdout.buffer.write(base64.b64decode(sys.stdin.read()))" < "$tmp_b64" > "$output_file" 2>/dev/null || \
        python -c "import base64,sys; sys.stdout.buffer.write(base64.b64decode(sys.stdin.read()))" < "$tmp_b64" > "$output_file" 2>/dev/null
    fi

    local decode_ok=$?
    rm -f "$tmp_b64"
    return $decode_ok
}

# Parse completion response: extract metadata, save audio files
# Usage: parse_completion_response <response_file> <job_id>
parse_completion_response() {
    local resp_file="$1"
    local job_id="$2"

    ensure_output_dir

    local audio_format=$(get_config "generation.audio_format")
    [ -z "$audio_format" ] && audio_format="mp3"

    # Check for error
    local finish_reason
    finish_reason=$(jq -r '.choices[0].finish_reason // "stop"' "$resp_file" 2>/dev/null)
    if [ "$finish_reason" = "error" ]; then
        local err_content
        err_content=$(jq -r '.choices[0].message.content // "Unknown error"' "$resp_file" 2>/dev/null)
        echo -e "${RED}Generation failed: $err_content${NC}"
        return 1
    fi

    # Extract and display text content (metadata + lyrics)
    local content
    content=$(jq -r '.choices[0].message.content // empty' "$resp_file" 2>/dev/null)
    if [ -n "$content" ]; then
        echo "$content"
        echo ""
    fi

    # Extract and save audio files
    local audio_count
    audio_count=$(jq -r '.choices[0].message.audio | length // 0' "$resp_file" 2>/dev/null)

    if [ "$audio_count" -gt 0 ] 2>/dev/null; then
        local i=0
        while [ "$i" -lt "$audio_count" ]; do
            local audio_url
            audio_url=$(jq -r ".choices[0].message.audio[$i].audio_url.url // empty" "$resp_file" 2>/dev/null)

            if [ -n "$audio_url" ]; then
                local output_file="${OUTPUT_DIR}/${job_id}_$((i+1)).${audio_format}"
                echo -e "  ${CYAN}Decoding audio $((i+1))...${NC}"

                if decode_base64_audio "$audio_url" "$output_file"; then
                    if [ -f "$output_file" ] && [ -s "$output_file" ]; then
                        echo -e "  ${GREEN}Saved: $output_file${NC}"
                    else
                        echo -e "  ${RED}Failed to decode audio $((i+1))${NC}"
                        rm -f "$output_file" 2>/dev/null
                    fi
                else
                    echo -e "  ${RED}Failed to decode audio $((i+1))${NC}"
                    rm -f "$output_file" 2>/dev/null
                fi
            fi
            i=$((i+1))
        done
    else
        echo -e "  ${YELLOW}No audio files in response${NC}"
    fi

    # Save full response JSON (strip base64 audio to keep file small)
    local clean_resp
    clean_resp=$(jq 'del(.choices[].message.audio[].audio_url.url)' "$resp_file" 2>/dev/null)
    if [ -n "$clean_resp" ]; then
        save_result "$job_id" "$clean_resp"
    else
        save_result "$job_id" "$(cat "$resp_file")"
    fi
}

# Send request to /v1/chat/completions and handle response
# Usage: send_completion_request <api_url> <payload_file> <job_id_var>
send_completion_request() {
    local api_url="$1"
    local payload_file="$2"
    local api_key=$(load_api_key)

    local resp_file=$(mktemp)

    local http_code
    if [ -n "$api_key" ]; then
        http_code=$(curl -s -w "%{http_code}" --connect-timeout 10 --max-time 660 \
            -o "$resp_file" \
            -X POST "${api_url}/v1/chat/completions" \
            -H "Content-Type: application/json; charset=utf-8" \
            -H "Authorization: Bearer ${api_key}" \
            -A "curl/8.7.1" \
            --data-binary "@${payload_file}")
    else
        http_code=$(curl -s -w "%{http_code}" --connect-timeout 10 --max-time 660 \
            -o "$resp_file" \
            -X POST "${api_url}/v1/chat/completions" \
            -H "Content-Type: application/json; charset=utf-8" \
            -A "curl/8.7.1" \
            --data-binary "@${payload_file}")
    fi

    rm -f "$payload_file"

    if [ "$http_code" != "200" ]; then
        local err_detail
        err_detail=$(jq -r '.detail // .error.message // empty' "$resp_file" 2>/dev/null)
        echo -e "${RED}Error: HTTP $http_code${NC}"
        [ -n "$err_detail" ] && echo -e "${RED}$err_detail${NC}"
        rm -f "$resp_file"
        return 1
    fi

    # Generate a job_id from the completion id
    local job_id
    job_id=$(jq -r '.id // empty' "$resp_file" 2>/dev/null)
    [ -z "$job_id" ] && job_id="completion-$(date +%s)"

    echo ""
    echo -e "${GREEN}Generation completed!${NC}"
    echo ""

    parse_completion_response "$resp_file" "$job_id"
    rm -f "$resp_file"

    echo ""
    echo -e "${GREEN}Done! Files saved to: $OUTPUT_DIR${NC}"
    show_star_prompt
}

# Wait for job and download results
wait_for_job() {
    local api_url="$1"
    local job_id="$2"

    echo "Job created: $job_id"
    echo "Output: $OUTPUT_DIR"
    echo ""

    while true; do
        local response=$(query_job_result "$api_url" "$job_id")
        local status=$(parse_query_status "$response")

        case "$status" in
            1)
                echo ""
                echo -e "${GREEN}Generation completed!${NC}"
                echo ""

                local result_file=$(mktemp)
                parse_query_result "$response" > "$result_file"

                local bpm=$(jq -r '.[0].metas.bpm // .[0].bpm // empty' "$result_file" 2>/dev/null)
                local keyscale=$(jq -r '.[0].metas.keyscale // .[0].keyscale // empty' "$result_file" 2>/dev/null)
                local duration=$(jq -r '.[0].metas.duration // .[0].duration // empty' "$result_file" 2>/dev/null)

                echo "Metadata:"
                [ -n "$bpm" ] && echo "  BPM: $bpm"
                [ -n "$keyscale" ] && echo "  Key: $keyscale"
                [ -n "$duration" ] && echo "  Duration: ${duration}s"
                echo ""

                # Save result JSON
                save_result "$job_id" "$response"

                # Download audio files
                echo "Downloading audio files..."
                download_audios "$api_url" "$job_id" "$result_file"
                rm -f "$result_file"

                echo ""
                echo -e "${GREEN}Done! Files saved to: $OUTPUT_DIR${NC}"
                show_star_prompt
                return 0
                ;;
            2)
                echo ""
                echo -e "${RED}Generation failed!${NC}"

                # Save error result
                save_result "$job_id" "$response"
                return 1
                ;;
            0)
                printf "\rProcessing...              "
                ;;
            *)
                printf "\rWaiting...                 "
                ;;
        esac
        sleep 5
    done
}

# Generate command
cmd_generate() {
    check_deps
    ensure_config

    local caption="" lyrics="" description="" thinking="" use_format=""
    local no_thinking=false no_format=false no_wait=false
    local model="" language="" steps="" guidance="" seed="" duration="" bpm="" batch=""
    local task_type="" src_audio="" cover_strength="" repaint_start="" repaint_end=""
    local key_scale="" time_signature=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --caption|-c) caption="$2"; shift 2 ;;
            --lyrics|-l) lyrics="$2"; shift 2 ;;
            --description|-d) description="$2"; shift 2 ;;
            --thinking|-t) thinking="true"; shift ;;
            --no-thinking) no_thinking=true; shift ;;
            --use-format) use_format="true"; shift ;;
            --no-format) no_format=true; shift ;;
            --model|-m) model="$2"; shift 2 ;;
            --language|--vocal-language) language="$2"; shift 2 ;;
            --steps) steps="$2"; shift 2 ;;
            --guidance) guidance="$2"; shift 2 ;;
            --seed) seed="$2"; shift 2 ;;
            --duration) duration="$2"; shift 2 ;;
            --bpm) bpm="$2"; shift 2 ;;
            --batch) batch="$2"; shift 2 ;;
            --no-wait) no_wait=true; shift ;;
            --task-type) task_type="$2"; shift 2 ;;
            --src-audio) src_audio="$2"; shift 2 ;;
            --cover-strength) cover_strength="$2"; shift 2 ;;
            --repaint-start) repaint_start="$2"; shift 2 ;;
            --repaint-end) repaint_end="$2"; shift 2 ;;
            --key-scale|--key) key_scale="$2"; shift 2 ;;
            --time-signature|--time-sig) time_signature="$2"; shift 2 ;;
            *) [ -z "$caption" ] && caption="$1"; shift ;;
        esac
    done

    # If no caption but has description, use simple mode
    if [ -z "$caption" ] && [ -z "$description" ]; then
        echo -e "${RED}Error: caption or description required${NC}"
        echo "Usage: $0 generate \"Music description\" [options]"
        echo "       $0 generate -d \"Simple description\" [options]"
        exit 1
    fi

    local api_url=$(ensure_connection)

    # Get defaults
    local def_thinking=$(get_config "generation.thinking")
    local def_format=$(get_config "generation.use_format")
    local def_cot_caption=$(get_config "generation.use_cot_caption")
    local def_cot_language=$(get_config "generation.use_cot_language")
    local def_language=$(get_config "generation.vocal_language")
    local def_audio_format=$(get_config "generation.audio_format")

    [ -z "$thinking" ] && thinking="${def_thinking:-true}"
    [ -z "$use_format" ] && use_format="${def_format:-true}"
    [ -z "$language" ] && language="${def_language:-en}"

    [ "$no_thinking" = true ] && thinking="false"
    [ "$no_format" = true ] && use_format="false"

    # Normalize boolean values for jq --argjson
    thinking=$(normalize_bool "$thinking" "true")
    use_format=$(normalize_bool "$use_format" "true")
    local cot_caption=$(normalize_bool "$def_cot_caption" "true")
    local cot_language=$(normalize_bool "$def_cot_language" "true")

    # Build payload using jq for proper escaping
    local payload=$(jq -n \
        --arg prompt "$caption" \
        --arg lyrics "${lyrics:-}" \
        --arg sample_query "${description:-}" \
        --argjson thinking "$thinking" \
        --argjson use_format "$use_format" \
        --argjson use_cot_caption "$cot_caption" \
        --argjson use_cot_language "$cot_language" \
        --arg vocal_language "$language" \
        --arg audio_format "${def_audio_format:-mp3}" \
        '{
            prompt: $prompt,
            lyrics: $lyrics,
            sample_query: $sample_query,
            thinking: $thinking,
            use_format: $use_format,
            use_cot_caption: $use_cot_caption,
            use_cot_language: $use_cot_language,
            vocal_language: $vocal_language,
            audio_format: $audio_format,
            use_random_seed: true
        }')

    # Validate src_audio file exists if provided
    if [ -n "$src_audio" ]; then
        if [ ! -f "$src_audio" ]; then
            echo -e "${RED}Error: Source audio file not found: $src_audio${NC}"
            exit 1
        fi
        # Default task_type to "cover" when src_audio is provided
        [ -z "$task_type" ] && task_type="cover"
    fi

    # Add optional parameters
    [ -n "$model" ] && payload=$(echo "$payload" | jq --arg v "$model" '. + {model: $v}')
    [ -n "$steps" ] && payload=$(echo "$payload" | jq --argjson v "$steps" '. + {inference_steps: $v}')
    [ -n "$guidance" ] && payload=$(echo "$payload" | jq --argjson v "$guidance" '. + {guidance_scale: $v}')
    [ -n "$seed" ] && payload=$(echo "$payload" | jq --argjson v "$seed" '. + {seed: $v, use_random_seed: false}')
    [ -n "$duration" ] && payload=$(echo "$payload" | jq --argjson v "$duration" '. + {audio_duration: $v}')
    [ -n "$bpm" ] && payload=$(echo "$payload" | jq --argjson v "$bpm" '. + {bpm: $v}')
    [ -n "$batch" ] && payload=$(echo "$payload" | jq --argjson v "$batch" '. + {batch_size: $v}')
    [ -n "$task_type" ] && payload=$(echo "$payload" | jq --arg v "$task_type" '. + {task_type: $v}')
    [ -n "$src_audio" ] && payload=$(echo "$payload" | jq --arg v "$src_audio" '. + {src_audio_path: $v}')
    [ -n "$cover_strength" ] && payload=$(echo "$payload" | jq --argjson v "$cover_strength" '. + {audio_cover_strength: $v}')
    [ -n "$repaint_start" ] && payload=$(echo "$payload" | jq --argjson v "$repaint_start" '. + {repainting_start: $v}')
    [ -n "$repaint_end" ] && payload=$(echo "$payload" | jq --argjson v "$repaint_end" '. + {repainting_end: $v}')
    [ -n "$key_scale" ] && payload=$(echo "$payload" | jq --arg v "$key_scale" '. + {key_scale: $v}')
    [ -n "$time_signature" ] && payload=$(echo "$payload" | jq --arg v "$time_signature" '. + {time_signature: $v}')

    local api_mode=$(load_api_mode)

    echo "Generating music..."
    if [ -n "$task_type" ] && [ "$task_type" != "text2music" ]; then
        echo "  Mode: $(echo "$task_type" | awk '{print toupper(substr($0,1,1)) substr($0,2)}') (${task_type})"
        [ -n "$src_audio" ] && echo "  Source audio: $src_audio"
    elif [ -n "$description" ]; then
        echo "  Mode: Simple (description)"
        echo "  Description: ${description:0:50}..."
    else
        echo "  Mode: Caption"
        echo "  Caption: ${caption:0:50}..."
    fi
    echo "  Thinking: $thinking, Format: $use_format"
    echo "  API: $api_mode"
    echo "  Output: $OUTPUT_DIR"
    echo ""

    if [ "$api_mode" = "completion" ]; then
        # --- Completion mode: /v1/chat/completions ---
        local model_id=$(get_completion_model "$api_url" "$model")

        # Build message content parts
        local message_content=""
        local sample_mode=false
        if [ -n "$description" ]; then
            message_content="$description"
            sample_mode=true
        else
            message_content="<prompt>${caption}</prompt>"
            [ -n "$lyrics" ] && message_content="${message_content}<lyrics>${lyrics}</lyrics>"
        fi

        # Build completion payload
        local payload_c
        if [ -n "$src_audio" ]; then
            # Audio input mode: use multipart content array with text + input_audio
            # Encode audio to base64 using python to avoid shell argument limits
            local audio_b64_file=$(mktemp)
            python3 -c "
import base64, sys
with open(sys.argv[1], 'rb') as f:
    sys.stdout.write(base64.b64encode(f.read()).decode('ascii'))
" "$src_audio" > "$audio_b64_file"

            local audio_ext="${src_audio##*.}"
            [ -z "$audio_ext" ] && audio_ext="mp3"

            # Build payload with audio using jq --rawfile to read base64 from file
            payload_c=$(jq -n \
                --arg model "$model_id" \
                --arg text_content "$message_content" \
                --rawfile audio_b64 "$audio_b64_file" \
                --arg audio_format "$audio_ext" \
                --argjson thinking "$thinking" \
                --argjson use_format "$use_format" \
                --argjson sample_mode "$sample_mode" \
                --argjson use_cot_caption "$cot_caption" \
                --argjson use_cot_language "$cot_language" \
                --arg vocal_language "$language" \
                --arg format "${def_audio_format:-mp3}" \
                --arg task_type "${task_type:-text2music}" \
                '{
                    model: $model,
                    messages: [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": $text_content},
                            {"type": "input_audio", "input_audio": {"data": $audio_b64, "format": $audio_format}}
                        ]
                    }],
                    stream: false,
                    thinking: $thinking,
                    use_format: $use_format,
                    sample_mode: $sample_mode,
                    use_cot_caption: $use_cot_caption,
                    use_cot_language: $use_cot_language,
                    task_type: $task_type,
                    audio_config: {
                        format: $format,
                        vocal_language: $vocal_language
                    }
                }')

            rm -f "$audio_b64_file"

            # Add cover/repainting parameters
            [ -n "$cover_strength" ] && payload_c=$(echo "$payload_c" | jq --argjson v "$cover_strength" '. + {audio_cover_strength: $v}')
            [ -n "$repaint_start" ] && payload_c=$(echo "$payload_c" | jq --argjson v "$repaint_start" '. + {repainting_start: $v}')
            [ -n "$repaint_end" ] && payload_c=$(echo "$payload_c" | jq --argjson v "$repaint_end" '. + {repainting_end: $v}')
        else
            # Text-only mode: use string content
            payload_c=$(jq -n \
                --arg model "$model_id" \
                --arg content "$message_content" \
                --argjson thinking "$thinking" \
                --argjson use_format "$use_format" \
                --argjson sample_mode "$sample_mode" \
                --argjson use_cot_caption "$cot_caption" \
                --argjson use_cot_language "$cot_language" \
                --arg vocal_language "$language" \
                --arg format "${def_audio_format:-mp3}" \
                '{
                    model: $model,
                    messages: [{"role": "user", "content": $content}],
                    stream: false,
                    thinking: $thinking,
                    use_format: $use_format,
                    sample_mode: $sample_mode,
                    use_cot_caption: $use_cot_caption,
                    use_cot_language: $use_cot_language,
                    audio_config: {
                        format: $format,
                        vocal_language: $vocal_language
                    }
                }')
        fi

        # Add optional parameters to completion payload
        [ -n "$guidance" ] && payload_c=$(echo "$payload_c" | jq --argjson v "$guidance" '. + {guidance_scale: $v}')
        [ -n "$seed" ] && payload_c=$(echo "$payload_c" | jq --argjson v "$seed" '. + {seed: $v}')
        [ -n "$batch" ] && payload_c=$(echo "$payload_c" | jq --argjson v "$batch" '. + {batch_size: $v}')
        [ -n "$duration" ] && payload_c=$(echo "$payload_c" | jq --argjson v "$duration" '.audio_config.duration = $v')
        [ -n "$bpm" ] && payload_c=$(echo "$payload_c" | jq --argjson v "$bpm" '.audio_config.bpm = $v')
        [ -n "$key_scale" ] && payload_c=$(echo "$payload_c" | jq --arg v "$key_scale" '.audio_config.key_scale = $v')
        [ -n "$time_signature" ] && payload_c=$(echo "$payload_c" | jq --arg v "$time_signature" '.audio_config.time_signature = $v')

        local temp_payload=$(mktemp)
        printf '%s' "$payload_c" > "$temp_payload"

        send_completion_request "$api_url" "$temp_payload"
    else
        # --- Native mode: /release_task + polling ---
        local temp_payload=$(mktemp)
        printf '%s' "$payload" > "$temp_payload"

        local api_key=$(load_api_key)
        local response
        if [ -n "$api_key" ]; then
            response=$(curl -s -X POST "${api_url}/release_task" \
                -H "Content-Type: application/json; charset=utf-8" \
                -H "Authorization: Bearer ${api_key}" \
                --data-binary "@${temp_payload}")
        else
            response=$(curl -s -X POST "${api_url}/release_task" \
                -H "Content-Type: application/json; charset=utf-8" \
                --data-binary "@${temp_payload}")
        fi

        rm -f "$temp_payload"

        local job_id=$(echo "$response" | jq -r '.data.task_id // .task_id // empty')
        [ -z "$job_id" ] && { echo -e "${RED}Error: Failed to create job${NC}"; echo "$response"; exit 1; }

        if [ "$no_wait" = true ]; then
            echo "Job ID: $job_id"
            echo "Use '$0 status $job_id' to check progress and download"
        else
            wait_for_job "$api_url" "$job_id"
        fi
    fi
}

# Random command
cmd_random() {
    check_deps
    ensure_config

    local thinking="" no_thinking=false no_wait=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --thinking|-t) thinking="true"; shift ;;
            --no-thinking) no_thinking=true; shift ;;
            --no-wait) no_wait=true; shift ;;
            *) shift ;;
        esac
    done

    local api_url=$(ensure_connection)

    local def_thinking=$(get_config "generation.thinking")
    [ -z "$thinking" ] && thinking="${def_thinking:-true}"
    [ "$no_thinking" = true ] && thinking="false"

    # Normalize boolean for jq --argjson
    thinking=$(normalize_bool "$thinking" "true")

    local api_mode=$(load_api_mode)

    echo "Generating random music..."
    echo "  Thinking: $thinking"
    echo "  API: $api_mode"
    echo "  Output: $OUTPUT_DIR"
    echo ""

    if [ "$api_mode" = "completion" ]; then
        # --- Completion mode ---
        local model_id=$(get_completion_model "$api_url" "")
        local def_audio_format=$(get_config "generation.audio_format")

        local payload_c=$(jq -n \
            --arg model "$model_id" \
            --argjson thinking "$thinking" \
            --arg format "${def_audio_format:-mp3}" \
            '{
                model: $model,
                messages: [{"role": "user", "content": "Generate a random song"}],
                stream: false,
                sample_mode: true,
                thinking: $thinking,
                audio_config: { format: $format }
            }')

        local temp_payload=$(mktemp)
        printf '%s' "$payload_c" > "$temp_payload"

        send_completion_request "$api_url" "$temp_payload"
    else
        # --- Native mode ---
        local payload=$(jq -n --argjson thinking "$thinking" '{sample_mode: true, thinking: $thinking}')

        local temp_payload=$(mktemp)
        printf '%s' "$payload" > "$temp_payload"

        local api_key=$(load_api_key)
        local response
        if [ -n "$api_key" ]; then
            response=$(curl -s -X POST "${api_url}/release_task" \
                -H "Content-Type: application/json; charset=utf-8" \
                -H "Authorization: Bearer ${api_key}" \
                --data-binary "@${temp_payload}")
        else
            response=$(curl -s -X POST "${api_url}/release_task" \
                -H "Content-Type: application/json; charset=utf-8" \
                --data-binary "@${temp_payload}")
        fi

        rm -f "$temp_payload"

        local job_id=$(echo "$response" | jq -r '.data.task_id // .task_id // empty')
        [ -z "$job_id" ] && { echo -e "${RED}Error: Failed to create job${NC}"; echo "$response"; exit 1; }

        if [ "$no_wait" = true ]; then
            echo "Job ID: $job_id"
            echo "Use '$0 status $job_id' to check progress and download"
        else
            wait_for_job "$api_url" "$job_id"
        fi
    fi
}

# Cover command (shortcut for generate --task-type cover --src-audio)
cmd_cover() {
    check_deps
    ensure_config

    local src_audio=""
    local args=()

    # Extract src_audio as first positional arg, pass rest to generate
    while [[ $# -gt 0 ]]; do
        case $1 in
            --src-audio) src_audio="$2"; shift 2 ;;
            -*) args+=("$1"); shift ;;
            *)
                if [ -z "$src_audio" ]; then
                    src_audio="$1"; shift
                else
                    args+=("$1"); shift
                fi
                ;;
        esac
    done

    if [ -z "$src_audio" ]; then
        echo -e "${RED}Error: source audio file required${NC}"
        echo "Usage: $0 cover <audio_file> -c \"caption\" -l \"lyrics\" [options]"
        exit 1
    fi

    cmd_generate --src-audio "$src_audio" --task-type cover "${args[@]}"
}

# Help
show_help() {
    echo "ACE-Step Music Generation CLI"
    echo ""
    echo "Requirements: curl, jq"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  generate    Generate music from text"
    echo "  cover       Cover/repainting from source audio"
    echo "  random      Generate random music"
    echo "  status      Check job status and download results"
    echo "  models      List available models"
    echo "  health      Check API health"
    echo "  config      Manage configuration"
    echo ""
    echo "Output:"
    echo "  Results saved to: $OUTPUT_DIR/<job_id>.json"
    echo "  Audio files: $OUTPUT_DIR/<job_id>_1.mp3, ..."
    echo ""
    echo "Generate Options:"
    echo "  -c, --caption       Music style/genre description (caption mode)"
    echo "  -d, --description   Simple description, LM auto-generates caption/lyrics"
    echo "  -l, --lyrics        Lyrics text"
    echo "  -t, --thinking      Enable thinking mode (default: true)"
    echo "  --no-thinking       Disable thinking mode"
    echo "  --no-format         Disable format enhancement"
    echo "  --duration          Duration in seconds"
    echo "  --bpm               Beats per minute"
    echo "  --key-scale         Musical key (e.g. \"E minor\")"
    echo "  --time-signature    Time signature (e.g. \"4/4\")"
    echo ""
    echo "Cover/Repainting Options:"
    echo "  --src-audio         Source audio file path"
    echo "  --task-type         Task type: cover, repaint, text2music (default: auto)"
    echo "  --cover-strength    Cover strength 0.0-1.0 (default: 1.0)"
    echo "  --repaint-start     Repainting start position in seconds"
    echo "  --repaint-end       Repainting end position in seconds"
    echo ""
    echo "Examples:"
    echo "  $0 generate \"Pop music with guitar\"           # Caption mode"
    echo "  $0 generate -d \"A February love song\"         # Simple mode (LM generates)"
    echo "  $0 generate -c \"Jazz\" -l \"[Verse] Hello\"      # With lyrics"
    echo "  $0 cover song.mp3 -c \"Rock cover\" -l \"[Verse] ...\" --duration 120"
    echo "  $0 generate --src-audio song.mp3 --task-type repaint -c \"Pop\" --repaint-start 30 --repaint-end 60"
    echo "  $0 random"
    echo "  $0 status <job_id>"
    echo "  $0 config --set generation.thinking false"
}

# Main
case "$1" in
    generate) shift; cmd_generate "$@" ;;
    cover) shift; cmd_cover "$@" ;;
    random) shift; cmd_random "$@" ;;
    status) shift; cmd_status "$@" ;;
    models) cmd_models ;;
    health) cmd_health ;;
    config) shift; cmd_config "$@" ;;
    help|--help|-h) show_help ;;
    *) show_help; exit 1 ;;
esac
