# ACE-Step API Client Documentation

---

This service provides an HTTP-based asynchronous music generation API.

**Basic Workflow**:
1. Call `POST /release_task` to submit a task and obtain a `task_id`.
2. Call `POST /query_result` to batch query task status until `status` is `1` (succeeded) or `2` (failed).
3. Download audio files via `GET /v1/audio?path=...` URLs returned in the result.

---

## Table of Contents

- [Authentication](#1-authentication)
- [Response Format](#2-response-format)
- [Task Status Description](#3-task-status-description)
- [Create Generation Task](#4-create-generation-task)
- [Batch Query Task Results](#5-batch-query-task-results)
- [Format Input](#6-format-input)
- [Get Random Sample](#7-get-random-sample)
- [List Available Models](#8-list-available-models)
- [Server Statistics](#9-server-statistics)
- [Download Audio Files](#10-download-audio-files)
- [Health Check](#11-health-check)
- [Environment Variables](#12-environment-variables)

---

## 1. Authentication

The API supports optional API key authentication. When enabled, a valid key must be provided in requests.

### Authentication Methods

Two authentication methods are supported:

**Method A: ai_token in request body**

```json
{
  "ai_token": "your-api-key",
  "prompt": "upbeat pop song",
  ...
}
```

**Method B: Authorization header**

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Authorization: Bearer your-api-key' \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "upbeat pop song"}'
```

### Configuring API Key

Set via environment variable or command-line argument:

```bash
# Environment variable
export ACESTEP_API_KEY=your-secret-key

# Or command-line argument
python -m acestep.api_server --api-key your-secret-key
```

---

## 2. Response Format

All API responses use a unified wrapper format:

```json
{
  "data": { ... },
  "code": 200,
  "error": null,
  "timestamp": 1700000000000,
  "extra": null
}
```

| Field | Type | Description |
| :--- | :--- | :--- |
| `data` | any | Actual response data |
| `code` | int | Status code (200=success) |
| `error` | string | Error message (null on success) |
| `timestamp` | int | Response timestamp (milliseconds) |
| `extra` | any | Extra information (usually null) |

---

## 3. Task Status Description

Task status (`status`) is represented as integers:

| Status Code | Status Name | Description |
| :--- | :--- | :--- |
| `0` | queued/running | Task is queued or in progress |
| `1` | succeeded | Generation succeeded, result is ready |
| `2` | failed | Generation failed |

---

## 4. Create Generation Task

### 4.1 API Definition

- **URL**: `/release_task`
- **Method**: `POST`
- **Content-Type**: `application/json`, `multipart/form-data`, or `application/x-www-form-urlencoded`

### 4.2 Request Parameters

#### Parameter Naming Convention

The API supports both **snake_case** and **camelCase** naming for most parameters. For example:
- `audio_duration` / `duration` / `audioDuration`
- `key_scale` / `keyscale` / `keyScale`
- `time_signature` / `timesignature` / `timeSignature`
- `sample_query` / `sampleQuery` / `description` / `desc`
- `use_format` / `useFormat` / `format`

Additionally, metadata can be passed in a nested object (`metas`, `metadata`, or `user_metadata`).

#### Method A: JSON Request (application/json)

Suitable for passing only text parameters, or referencing audio file paths that already exist on the server.

**Basic Parameters**:

| Parameter Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `prompt` | string | `""` | Music description prompt (alias: `caption`) |
| `lyrics` | string | `""` | Lyrics content |
| `thinking` | bool | `false` | Whether to use 5Hz LM to generate audio codes (lm-dit behavior) |
| `vocal_language` | string | `"en"` | Lyrics language (en, zh, ja, etc.) |
| `audio_format` | string | `"mp3"` | Output format (mp3, wav, flac) |

**Sample/Description Mode Parameters**:

| Parameter Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `sample_mode` | bool | `false` | Enable random sample generation mode (auto-generates caption/lyrics/metas via LM) |
| `sample_query` | string | `""` | Natural language description for sample generation (e.g., "a soft Bengali love song"). Aliases: `description`, `desc` |
| `use_format` | bool | `false` | Use LM to enhance/format the provided caption and lyrics. Alias: `format` |

**Multi-Model Support**:

| Parameter Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `model` | string | null | Select which DiT model to use (e.g., `"acestep-v15-turbo"`, `"acestep-v15-turbo-shift3"`). Use `/v1/models` to list available models. If not specified, uses the default model. |

**thinking Semantics (Important)**:

- `thinking=false`:
  - The server will **NOT** use 5Hz LM to generate `audio_code_string`.
  - DiT runs in **text2music** mode and **ignores** any provided `audio_code_string`.
- `thinking=true`:
  - The server will use 5Hz LM to generate `audio_code_string` (lm-dit behavior).
  - DiT runs with LM-generated codes for enhanced music quality.

**Metadata Auto-Completion (Conditional)**:

When `use_cot_caption=true` or `use_cot_language=true` or metadata fields are missing, the server may call 5Hz LM to fill the missing fields based on `caption`/`lyrics`:

- `bpm`
- `key_scale`
- `time_signature`
- `audio_duration`

User-provided values always win; LM only fills the fields that are empty/missing.

**Music Attribute Parameters**:

| Parameter Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `bpm` | int | null | Specify tempo (BPM), range 30-300 |
| `key_scale` | string | `""` | Key/scale (e.g., "C Major", "Am"). Aliases: `keyscale`, `keyScale` |
| `time_signature` | string | `""` | Time signature (2, 3, 4, 6 for 2/4, 3/4, 4/4, 6/8). Aliases: `timesignature`, `timeSignature` |
| `audio_duration` | float | null | Generation duration (seconds), range 10-600. Aliases: `duration`, `target_duration` |

**Audio Codes (Optional)**:

| Parameter Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `audio_code_string` | string or string[] | `""` | Audio semantic tokens (5Hz) for `llm_dit`. Alias: `audioCodeString` |

**Generation Control Parameters**:

| Parameter Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `inference_steps` | int | `8` | Number of inference steps. Turbo model: 1-20 (recommended 8). Base model: 1-200 (recommended 32-64). |
| `guidance_scale` | float | `7.0` | Prompt guidance coefficient. Only effective for base model. |
| `use_random_seed` | bool | `true` | Whether to use random seed |
| `seed` | int | `-1` | Specify seed (when use_random_seed=false) |
| `batch_size` | int | `2` | Batch generation count (max 8) |

**Advanced DiT Parameters**:

| Parameter Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `shift` | float | `3.0` | Timestep shift factor (range 1.0-5.0). Only effective for base models, not turbo models. |
| `infer_method` | string | `"ode"` | Diffusion inference method: `"ode"` (Euler, faster) or `"sde"` (stochastic). |
| `timesteps` | string | null | Custom timesteps as comma-separated values (e.g., `"0.97,0.76,0.615,0.5,0.395,0.28,0.18,0.085,0"`). Overrides `inference_steps` and `shift`. |
| `use_adg` | bool | `false` | Use Adaptive Dual Guidance (base model only) |
| `cfg_interval_start` | float | `0.0` | CFG application start ratio (0.0-1.0) |
| `cfg_interval_end` | float | `1.0` | CFG application end ratio (0.0-1.0) |

**5Hz LM Parameters (Optional, server-side)**:

These parameters control 5Hz LM sampling, used for metadata auto-completion and (when `thinking=true`) codes generation.

| Parameter Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `lm_model_path` | string | null | 5Hz LM checkpoint dir name (e.g. `acestep-5Hz-lm-0.6B`) |
| `lm_backend` | string | `"vllm"` | `vllm` or `pt` |
| `lm_temperature` | float | `0.85` | Sampling temperature |
| `lm_cfg_scale` | float | `2.5` | CFG scale (>1 enables CFG) |
| `lm_negative_prompt` | string | `"NO USER INPUT"` | Negative prompt used by CFG |
| `lm_top_k` | int | null | Top-k (0/null disables) |
| `lm_top_p` | float | `0.9` | Top-p (>=1 will be treated as disabled) |
| `lm_repetition_penalty` | float | `1.0` | Repetition penalty |

**LM CoT (Chain-of-Thought) Parameters**:

| Parameter Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `use_cot_caption` | bool | `true` | Let LM rewrite/enhance the input caption via CoT reasoning. Aliases: `cot_caption`, `cot-caption` |
| `use_cot_language` | bool | `true` | Let LM detect vocal language via CoT. Aliases: `cot_language`, `cot-language` |
| `constrained_decoding` | bool | `true` | Enable FSM-based constrained decoding for structured LM output. Aliases: `constrainedDecoding`, `constrained` |
| `constrained_decoding_debug` | bool | `false` | Enable debug logging for constrained decoding |
| `allow_lm_batch` | bool | `true` | Allow LM batch processing for efficiency |

**Edit/Reference Audio Parameters** (requires absolute path on server):

| Parameter Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `reference_audio_path` | string | null | Reference audio path (Style Transfer) |
| `src_audio_path` | string | null | Source audio path (Repainting/Cover) |
| `task_type` | string | `"text2music"` | Task type: `text2music`, `cover`, `repaint`, `lego`, `extract`, `complete` |
| `instruction` | string | auto | Edit instruction (auto-generated based on task_type if not provided) |
| `repainting_start` | float | `0.0` | Repainting start time (seconds) |
| `repainting_end` | float | null | Repainting end time (seconds), -1 for end of audio |
| `audio_cover_strength` | float | `1.0` | Cover strength (0.0-1.0). Lower values (0.2) for style transfer. |

#### Method B: File Upload (multipart/form-data)

Use this when you need to upload local audio files as reference or source audio.

In addition to supporting all the above fields as Form Fields, the following file fields are also supported:

- `reference_audio` or `ref_audio`: (File) Upload reference audio file
- `src_audio` or `ctx_audio`: (File) Upload source audio file

> **Note**: After uploading files, the corresponding `_path` parameters will be automatically ignored, and the system will use the temporary file path after upload.

### 4.3 Response Example

```json
{
  "data": {
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "queued",
    "queue_position": 1
  },
  "code": 200,
  "error": null,
  "timestamp": 1700000000000,
  "extra": null
}
```

### 4.4 Usage Examples (cURL)

**Basic JSON Method**:

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "upbeat pop song",
    "lyrics": "Hello world",
    "inference_steps": 8
  }'
```

**With thinking=true (LM generates codes + fills missing metas)**:

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "upbeat pop song",
    "lyrics": "Hello world",
    "thinking": true,
    "lm_temperature": 0.85,
    "lm_cfg_scale": 2.5
  }'
```

**Description-driven generation (sample_query)**:

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "sample_query": "a soft Bengali love song for a quiet evening",
    "thinking": true
  }'
```

**With format enhancement (use_format=true)**:

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "pop rock",
    "lyrics": "[Verse 1]\nWalking down the street...",
    "use_format": true,
    "thinking": true
  }'
```

**Select specific model**:

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "electronic dance music",
    "model": "acestep-v15-turbo",
    "thinking": true
  }'
```

**With custom timesteps**:

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "jazz piano trio",
    "timesteps": "0.97,0.76,0.615,0.5,0.395,0.28,0.18,0.085,0",
    "thinking": true
  }'
```

**File Upload Method**:

```bash
curl -X POST http://localhost:8001/release_task \
  -F "prompt=remix this song" \
  -F "src_audio=@/path/to/local/song.mp3" \
  -F "task_type=repaint"
```

---

## 5. Batch Query Task Results

### 5.1 API Definition

- **URL**: `/query_result`
- **Method**: `POST`
- **Content-Type**: `application/json` or `application/x-www-form-urlencoded`

### 5.2 Request Parameters

| Parameter Name | Type | Description |
| :--- | :--- | :--- |
| `task_id_list` | string (JSON array) or array | List of task IDs to query |

### 5.3 Response Example

```json
{
  "data": [
    {
      "task_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": 1,
      "result": "[{\"file\": \"/v1/audio?path=...\", \"wave\": \"\", \"status\": 1, \"create_time\": 1700000000, \"env\": \"development\", \"prompt\": \"upbeat pop song\", \"lyrics\": \"Hello world\", \"metas\": {\"bpm\": 120, \"duration\": 30, \"genres\": \"\", \"keyscale\": \"C Major\", \"timesignature\": \"4\"}, \"generation_info\": \"...\", \"seed_value\": \"12345,67890\", \"lm_model\": \"acestep-5Hz-lm-0.6B\", \"dit_model\": \"acestep-v15-turbo\"}]"
    }
  ],
  "code": 200,
  "error": null,
  "timestamp": 1700000000000,
  "extra": null
}
```

**Result Field Description** (result is a JSON string, after parsing contains):

| Field | Type | Description |
| :--- | :--- | :--- |
| `file` | string | Audio file URL (use with `/v1/audio` endpoint) |
| `wave` | string | Waveform data (usually empty) |
| `status` | int | Status code (0=in progress, 1=success, 2=failed) |
| `create_time` | int | Creation time (Unix timestamp) |
| `env` | string | Environment identifier |
| `prompt` | string | Prompt used |
| `lyrics` | string | Lyrics used |
| `metas` | object | Metadata (bpm, duration, genres, keyscale, timesignature) |
| `generation_info` | string | Generation info summary |
| `seed_value` | string | Seed values used (comma-separated) |
| `lm_model` | string | LM model name used |
| `dit_model` | string | DiT model name used |

### 5.4 Usage Example

```bash
curl -X POST http://localhost:8001/query_result \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id_list": ["550e8400-e29b-41d4-a716-446655440000"]
  }'
```

---

## 6. Format Input

### 6.1 API Definition

- **URL**: `/format_input`
- **Method**: `POST`

This endpoint uses LLM to enhance and format user-provided caption and lyrics.

### 6.2 Request Parameters

| Parameter Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `prompt` | string | `""` | Music description prompt |
| `lyrics` | string | `""` | Lyrics content |
| `temperature` | float | `0.85` | LM sampling temperature |
| `param_obj` | string (JSON) | `"{}"` | JSON object containing metadata (duration, bpm, key, time_signature, language) |

### 6.3 Response Example

```json
{
  "data": {
    "caption": "Enhanced music description",
    "lyrics": "Formatted lyrics...",
    "bpm": 120,
    "key_scale": "C Major",
    "time_signature": "4",
    "duration": 180,
    "vocal_language": "en"
  },
  "code": 200,
  "error": null,
  "timestamp": 1700000000000,
  "extra": null
}
```

### 6.4 Usage Example

```bash
curl -X POST http://localhost:8001/format_input \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "pop rock",
    "lyrics": "Walking down the street",
    "param_obj": "{\"duration\": 180, \"language\": \"en\"}"
  }'
```

---

## 7. Get Random Sample

### 7.1 API Definition

- **URL**: `/create_random_sample`
- **Method**: `POST`

This endpoint returns random sample parameters from pre-loaded example data for form filling.

### 7.2 Request Parameters

| Parameter Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `sample_type` | string | `"simple_mode"` | Sample type: `"simple_mode"` or `"custom_mode"` |

### 7.3 Response Example

```json
{
  "data": {
    "caption": "Upbeat pop song with guitar accompaniment",
    "lyrics": "[Verse 1]\nSunshine on my face...",
    "bpm": 120,
    "key_scale": "G Major",
    "time_signature": "4",
    "duration": 180,
    "vocal_language": "en"
  },
  "code": 200,
  "error": null,
  "timestamp": 1700000000000,
  "extra": null
}
```

### 7.4 Usage Example

```bash
curl -X POST http://localhost:8001/create_random_sample \
  -H 'Content-Type: application/json' \
  -d '{"sample_type": "simple_mode"}'
```

---

## 8. List Available Models

### 8.1 API Definition

- **URL**: `/v1/models`
- **Method**: `GET`

Returns a list of available DiT models loaded on the server.

### 8.2 Response Example

```json
{
  "data": {
    "models": [
      {
        "name": "acestep-v15-turbo",
        "is_default": true
      },
      {
        "name": "acestep-v15-turbo-shift3",
        "is_default": false
      }
    ],
    "default_model": "acestep-v15-turbo"
  },
  "code": 200,
  "error": null,
  "timestamp": 1700000000000,
  "extra": null
}
```

### 8.3 Usage Example

```bash
curl http://localhost:8001/v1/models
```

---

## 9. Server Statistics

### 9.1 API Definition

- **URL**: `/v1/stats`
- **Method**: `GET`

Returns server runtime statistics.

### 9.2 Response Example

```json
{
  "data": {
    "jobs": {
      "total": 100,
      "queued": 5,
      "running": 1,
      "succeeded": 90,
      "failed": 4
    },
    "queue_size": 5,
    "queue_maxsize": 200,
    "avg_job_seconds": 8.5
  },
  "code": 200,
  "error": null,
  "timestamp": 1700000000000,
  "extra": null
}
```

### 9.3 Usage Example

```bash
curl http://localhost:8001/v1/stats
```

---

## 10. Download Audio Files

### 10.1 API Definition

- **URL**: `/v1/audio`
- **Method**: `GET`

Download generated audio files by path.

### 10.2 Request Parameters

| Parameter Name | Type | Description |
| :--- | :--- | :--- |
| `path` | string | URL-encoded path to the audio file |

### 10.3 Usage Example

```bash
# Download using the URL from task result
curl "http://localhost:8001/v1/audio?path=%2Ftmp%2Fapi_audio%2Fabc123.mp3" -o output.mp3
```

---

## 11. Health Check

### 11.1 API Definition

- **URL**: `/health`
- **Method**: `GET`

Returns service health status.

### 11.2 Response Example

```json
{
  "data": {
    "status": "ok",
    "service": "ACE-Step API",
    "version": "1.0"
  },
  "code": 200,
  "error": null,
  "timestamp": 1700000000000,
  "extra": null
}
```

---

## 12. Environment Variables

The API server can be configured using environment variables:

### Server Configuration

| Variable | Default | Description |
| :--- | :--- | :--- |
| `ACESTEP_API_HOST` | `127.0.0.1` | Server bind host |
| `ACESTEP_API_PORT` | `8001` | Server bind port |
| `ACESTEP_API_KEY` | (empty) | API authentication key (empty disables auth) |
| `ACESTEP_API_WORKERS` | `1` | API worker thread count |

### Model Configuration

| Variable | Default | Description |
| :--- | :--- | :--- |
| `ACESTEP_CONFIG_PATH` | `acestep-v15-turbo` | Primary DiT model path |
| `ACESTEP_CONFIG_PATH2` | (empty) | Secondary DiT model path (optional) |
| `ACESTEP_CONFIG_PATH3` | (empty) | Third DiT model path (optional) |
| `ACESTEP_DEVICE` | `auto` | Device for model loading |
| `ACESTEP_USE_FLASH_ATTENTION` | `true` | Enable flash attention |
| `ACESTEP_OFFLOAD_TO_CPU` | `false` | Offload models to CPU when idle |
| `ACESTEP_OFFLOAD_DIT_TO_CPU` | `false` | Offload DiT specifically to CPU |

### LM Configuration

| Variable | Default | Description |
| :--- | :--- | :--- |
| `ACESTEP_INIT_LLM` | auto | Whether to initialize LM at startup (auto determines based on GPU) |
| `ACESTEP_LM_MODEL_PATH` | `acestep-5Hz-lm-0.6B` | Default 5Hz LM model |
| `ACESTEP_LM_BACKEND` | `vllm` | LM backend (vllm or pt) |
| `ACESTEP_LM_DEVICE` | (same as ACESTEP_DEVICE) | Device for LM |
| `ACESTEP_LM_OFFLOAD_TO_CPU` | `false` | Offload LM to CPU |

### Queue Configuration

| Variable | Default | Description |
| :--- | :--- | :--- |
| `ACESTEP_QUEUE_MAXSIZE` | `200` | Maximum queue size |
| `ACESTEP_QUEUE_WORKERS` | `1` | Number of queue workers |
| `ACESTEP_AVG_JOB_SECONDS` | `5.0` | Initial average job duration estimate |
| `ACESTEP_AVG_WINDOW` | `50` | Window for averaging job duration |

### Cache Configuration

| Variable | Default | Description |
| :--- | :--- | :--- |
| `ACESTEP_TMPDIR` | `.cache/acestep/tmp` | Temporary file directory |
| `TRITON_CACHE_DIR` | `.cache/acestep/triton` | Triton cache directory |
| `TORCHINDUCTOR_CACHE_DIR` | `.cache/acestep/torchinductor` | TorchInductor cache directory |

---

## Error Handling

**HTTP Status Codes**:

- `200`: Success
- `400`: Invalid request (bad JSON, missing fields)
- `401`: Unauthorized (missing or invalid API key)
- `404`: Resource not found
- `415`: Unsupported Content-Type
- `429`: Server busy (queue is full)
- `500`: Internal server error

**Error Response Format**:

```json
{
  "detail": "Error message describing the issue"
}
```

---

## Best Practices

1. **Use `thinking=true`** for best quality results with LM-enhanced generation.

2. **Use `sample_query`/`description`** for quick generation from natural language descriptions.

3. **Use `use_format=true`** when you have caption/lyrics but want LM to enhance them.

4. **Batch query task status** using the `/query_result` endpoint to query multiple tasks at once.

5. **Check `/v1/stats`** to understand server load and average job time.

6. **Use multi-model support** by setting `ACESTEP_CONFIG_PATH2` and `ACESTEP_CONFIG_PATH3` environment variables, then select with the `model` parameter.

7. **For production**, set `ACESTEP_API_KEY` to enable authentication and secure your API.

8. **For low VRAM environments**, enable `ACESTEP_OFFLOAD_TO_CPU=true` to support longer audio generation.
