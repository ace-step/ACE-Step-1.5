# ACE-Step OpenRouter API Documentation

> OpenAI Chat Completions-compatible API for AI music generation

**Base URL:** `http://{host}:{port}` (default `http://127.0.0.1:8002`)

---

## Table of Contents

- [Authentication](#authentication)
- [Endpoints](#endpoints)
  - [POST /v1/chat/completions - Generate Music](#1-generate-music)
  - [GET /v1/models - List Models](#2-list-models)
  - [GET /health - Health Check](#3-health-check)
- [Input Modes](#input-modes)
- [Audio Input](#audio-input)
- [Streaming Responses](#streaming-responses)
- [Examples](#examples)
- [Error Codes](#error-codes)

---

## Authentication

If the server is configured with an API key (via the `OPENROUTER_API_KEY` environment variable or `--api-key` CLI flag), all requests must include the following header:

```
Authorization: Bearer <your-api-key>
```

No authentication is required when no API key is configured.

---

## Endpoints

### 1. Generate Music

**POST** `/v1/chat/completions`

Generates music from chat messages and returns audio data along with LM-generated metadata.

#### Request Parameters

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `model` | string | No | auto | Model ID (obtain from `/v1/models`) |
| `messages` | array | **Yes** | - | Chat message list. See [Input Modes](#input-modes) |
| `stream` | boolean | No | `false` | Enable streaming response. See [Streaming Responses](#streaming-responses) |
| `audio_config` | object | No | `null` | Audio generation configuration. See below |
| `temperature` | float | No | `0.85` | LM sampling temperature |
| `top_p` | float | No | `0.9` | LM nucleus sampling parameter |
| `seed` | int \| string | No | `null` | Random seed. When `batch_size > 1`, use comma-separated values, e.g. `"42,123,456"` |
| `lyrics` | string | No | `""` | Lyrics passed directly (takes priority over lyrics parsed from messages). When set, messages text becomes the prompt |
| `sample_mode` | boolean | No | `false` | Enable LLM sample mode. Messages text becomes sample_query for LLM to auto-generate prompt/lyrics |
| `thinking` | boolean | No | `false` | Enable LLM thinking mode for deeper reasoning |
| `use_format` | boolean | No | `false` | When user provides prompt/lyrics, enhance them via LLM formatting |
| `use_cot_caption` | boolean | No | `true` | Rewrite/enhance the music description via Chain-of-Thought |
| `use_cot_language` | boolean | No | `true` | Auto-detect vocal language via Chain-of-Thought |
| `guidance_scale` | float | No | `7.0` | Classifier-free guidance scale |
| `batch_size` | int | No | `1` | Number of audio samples to generate |
| `task_type` | string | No | `"text2music"` | Task type. See [Audio Input](#audio-input) |
| `repainting_start` | float | No | `0.0` | Repaint region start position (seconds) |
| `repainting_end` | float | No | `null` | Repaint region end position (seconds) |
| `audio_cover_strength` | float | No | `1.0` | Cover strength (0.0~1.0) |

#### audio_config Object

| Field | Type | Default | Description |
|---|---|---|---|
| `duration` | float | `null` | Audio duration in seconds. If omitted, determined automatically by the LM |
| `bpm` | integer | `null` | Beats per minute. If omitted, determined automatically by the LM |
| `vocal_language` | string | `"en"` | Vocal language code (e.g. `"zh"`, `"en"`, `"ja"`) |
| `instrumental` | boolean | `null` | Whether to generate instrumental-only (no vocals). If omitted, auto-determined from lyrics |
| `format` | string | `"mp3"` | Output audio format |
| `key_scale` | string | `null` | Musical key (e.g. `"C major"`) |
| `time_signature` | string | `null` | Time signature (e.g. `"4/4"`) |

> **Messages text meaning depends on the mode:**
> - If `lyrics` is set → messages text = caption
> - If `sample_mode: true` is set → messages text = sample_query (let LLM generate everything)
> - Neither set → auto-detect: tags → tag mode, lyrics-like → lyrics mode, otherwise used as caption directly for generation

#### messages Format

Supports both plain text and multimodal (text + audio) formats:

**Plain text:**

```json
{
  "messages": [
    {"role": "user", "content": "Your input content"}
  ]
}
```

**Multimodal (with audio input):**

```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "Cover this song"},
        {
          "type": "input_audio",
          "input_audio": {
            "data": "<base64 audio data>",
            "format": "mp3"
          }
        }
      ]
    }
  ]
}
```

---

#### Non-Streaming Response (`stream: false`)

```json
{
  "id": "chatcmpl-a1b2c3d4e5f6g7h8",
  "object": "chat.completion",
  "created": 1706688000,
  "model": "acemusic/acestep-v15-turbo",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "## Metadata\n**Caption:** Upbeat pop song...\n**BPM:** 120\n**Duration:** 30s\n**Key:** C major\n\n## Lyrics\n[Verse 1]\nHello world...",
        "audio": [
          {
            "type": "audio_url",
            "audio_url": {
              "url": "data:audio/mpeg;base64,SUQzBAAAAAAAI1RTU0UAAAA..."
            }
          }
        ]
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 100,
    "total_tokens": 110
  }
}
```

**Response Fields:**

| Field | Description |
|---|---|
| `choices[0].message.content` | Text information generated by the LM, including Metadata (Caption/BPM/Duration/Key/Time Signature/Language) and Lyrics. Returns `"Music generated successfully."` if LM was not involved |
| `choices[0].message.audio` | Audio data array. Each item contains `type` (`"audio_url"`) and `audio_url.url` (Base64 Data URL in format `data:audio/mpeg;base64,...`) |
| `choices[0].finish_reason` | `"stop"` indicates normal completion |

**Decoding Audio:**

The `audio_url.url` value is a Data URL: `data:audio/mpeg;base64,<base64_data>`

Extract the base64 portion after the comma and decode it to get the MP3 file:

```python
import base64

url = response["choices"][0]["message"]["audio"][0]["audio_url"]["url"]
# Strip the "data:audio/mpeg;base64," prefix
b64_data = url.split(",", 1)[1]
audio_bytes = base64.b64decode(b64_data)

with open("output.mp3", "wb") as f:
    f.write(audio_bytes)
```

```javascript
const url = response.choices[0].message.audio[0].audio_url.url;
const b64Data = url.split(",")[1];
const audioBytes = atob(b64Data);
// Or use the Data URL directly in an <audio> element
const audio = new Audio(url);
audio.play();
```

---

### 2. List Models

**GET** `/v1/models`

Returns available model information.

#### Response

```json
{
  "data": [
    {
      "id": "acemusic/acestep-v15-turbo",
      "name": "ACE-Step",
      "created": 1706688000,
      "description": "High-performance text-to-music generation model. Supports multiple styles, lyrics input, and various audio durations.",
      "input_modalities": ["text", "audio"],
      "output_modalities": ["audio", "text"],
      "context_length": 4096,
      "pricing": {"prompt": "0", "completion": "0", "request": "0"},
      "supported_sampling_parameters": ["temperature", "top_p"]
    }
  ]
}
```

---

### 3. Health Check

**GET** `/health`

#### Response

```json
{
  "status": "ok",
  "service": "ACE-Step OpenRouter API",
  "version": "1.0"
}
```

---

## Input Modes

The system automatically selects the input mode based on the content of the last `user` message. You can also explicitly specify via the `lyrics` or `sample_mode` fields.

### Mode 1: Tagged Mode (Recommended)

Use `<prompt>` and `<lyrics>` tags to explicitly specify the music description and lyrics:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "<prompt>A gentle acoustic ballad in C major, female vocal</prompt>\n<lyrics>[Verse 1]\nSunlight through the window\nA brand new day begins\n\n[Chorus]\nWe are the dreamers\nWe are the light</lyrics>"
    }
  ],
  "audio_config": {
    "duration": 30,
    "vocal_language": "en"
  }
}
```

- `<prompt>...</prompt>` — Music style/scene description (caption)
- `<lyrics>...</lyrics>` — Lyrics content
- Either tag can be used alone
- When `use_format: true`, the LLM automatically enhances both prompt and lyrics

### Mode 2: Natural Language Mode (Sample Mode)

Describe the desired music in natural language. The system uses LLM to generate the prompt and lyrics automatically:

```json
{
  "messages": [
    {"role": "user", "content": "Generate an upbeat pop song about summer and travel"}
  ],
  "sample_mode": true,
  "audio_config": {
    "vocal_language": "en"
  }
}
```

Trigger condition: `sample_mode: true`, or message content contains no tags and does not resemble lyrics.

### Mode 3: Lyrics-Only Mode

Pass in lyrics with structural markers directly. The system identifies them automatically:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "[Verse 1]\nWalking down the street\nFeeling the beat\n\n[Chorus]\nDance with me tonight\nUnder the moonlight"
    }
  ],
  "audio_config": {"duration": 30}
}
```

Trigger condition: Message content contains `[Verse]`, `[Chorus]`, or similar markers, or has a multi-line short-text structure.

### Mode 4: Lyrics + Prompt Separation

Use the `lyrics` field to pass lyrics directly, and messages text automatically becomes the prompt:

```json
{
  "messages": [
    {"role": "user", "content": "Energetic EDM with heavy bass drops"}
  ],
  "lyrics": "[Verse 1]\nFeel the rhythm in your soul\nLet the music take control\n\n[Drop]\n(instrumental break)",
  "audio_config": {
    "bpm": 128,
    "duration": 60
  }
}
```

### Instrumental Mode

Set `audio_config.instrumental: true`:

```json
{
  "messages": [
    {"role": "user", "content": "<prompt>Epic orchestral cinematic score, dramatic and powerful</prompt>"}
  ],
  "audio_config": {
    "instrumental": true,
    "duration": 30
  }
}
```

---

## Audio Input

Audio files can be passed via multimodal messages (base64 encoded) for cover, repaint, and other tasks.

### task_type Types

| task_type | Description | Audio Input Required |
|---|---|---|
| `text2music` | Text to music (default) | Optional (as reference) |
| `cover` | Cover/style transfer | Requires src_audio |
| `repaint` | Partial repaint | Requires src_audio |
| `lego` | Audio splicing | Requires src_audio |
| `extract` | Audio extraction | Requires src_audio |
| `complete` | Audio continuation | Requires src_audio |

### Audio Routing Rules

Multiple `input_audio` blocks are routed to different parameters in order (similar to multi-image upload):

| task_type | audio[0] | audio[1] |
|---|---|---|
| `text2music` | reference_audio (style reference) | - |
| `cover/repaint/lego/extract/complete` | src_audio (audio to edit) | reference_audio (optional style reference) |

### Audio Input Examples

**Cover Task:**

```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "<prompt>Jazz style cover with saxophone</prompt>"},
        {
          "type": "input_audio",
          "input_audio": {"data": "<base64 source audio>", "format": "mp3"}
        }
      ]
    }
  ],
  "task_type": "cover",
  "audio_cover_strength": 0.8,
  "audio_config": {"duration": 30}
}
```

**Repaint Task:**

```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "<prompt>Replace with guitar solo</prompt>"},
        {
          "type": "input_audio",
          "input_audio": {"data": "<base64 source audio>", "format": "mp3"}
        }
      ]
    }
  ],
  "task_type": "repaint",
  "repainting_start": 10.0,
  "repainting_end": 20.0,
  "audio_config": {"duration": 30}
}
```

---

## Streaming Responses

Set `"stream": true` to enable SSE (Server-Sent Events) streaming.

### Event Format

Each event starts with `data: `, followed by JSON, ending with a double newline `\n\n`:

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{...},"finish_reason":null}]}

```

### Streaming Event Sequence

| Phase | Delta Content | Description |
|---|---|---|
| 1. Initialization | `{"role":"assistant","content":""}` | Establishes the connection |
| 2. LM Content | `{"content":"\n\n## Metadata\n..."}` | Metadata and lyrics pushed after LM generation (if LM was used) |
| 3. Heartbeat | `{"content":"."}` | Sent every 2 seconds during audio generation to keep the connection alive |
| 4. Audio Data | `{"audio":[{"type":"audio_url","audio_url":{"url":"data:..."}}]}` | Audio base64 data |
| 5. Finish | `finish_reason: "stop"` | Generation complete |
| 6. Termination | `data: [DONE]` | End-of-stream marker |

### Streaming Response Example

```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{"content":"\n\n## Metadata\n**Caption:** Upbeat pop\n**BPM:** 120"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{"content":"."},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{"audio":[{"type":"audio_url","audio_url":{"url":"data:audio/mpeg;base64,..."}}]},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]

```

### Client-Side Streaming Handling

```python
import json
import httpx

with httpx.stream("POST", "http://127.0.0.1:8002/v1/chat/completions", json={
    "messages": [{"role": "user", "content": "Generate a cheerful guitar piece"}],
    "sample_mode": True,
    "stream": True,
    "audio_config": {"instrumental": True}
}) as response:
    content_parts = []
    audio_url = None

    for line in response.iter_lines():
        if not line or not line.startswith("data: "):
            continue
        if line == "data: [DONE]":
            break

        chunk = json.loads(line[6:])
        delta = chunk["choices"][0]["delta"]

        if "content" in delta and delta["content"]:
            content_parts.append(delta["content"])

        if "audio" in delta and delta["audio"]:
            audio_url = delta["audio"][0]["audio_url"]["url"]

        if chunk["choices"][0].get("finish_reason") == "stop":
            print("Generation complete!")

    print("Content:", "".join(content_parts))
    if audio_url:
        import base64
        b64_data = audio_url.split(",", 1)[1]
        with open("output.mp3", "wb") as f:
            f.write(base64.b64decode(b64_data))
```

```javascript
const response = await fetch("http://127.0.0.1:8002/v1/chat/completions", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    messages: [{ role: "user", content: "Generate a cheerful guitar piece" }],
    sample_mode: true,
    stream: true,
    audio_config: { instrumental: true }
  })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let audioUrl = null;
let content = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  const text = decoder.decode(value);
  for (const line of text.split("\n")) {
    if (!line.startsWith("data: ") || line === "data: [DONE]") continue;

    const chunk = JSON.parse(line.slice(6));
    const delta = chunk.choices[0].delta;

    if (delta.content) content += delta.content;
    if (delta.audio) audioUrl = delta.audio[0].audio_url.url;
  }
}

// audioUrl can be used directly as <audio src="...">
```

---

## Examples

### Example 1: Natural Language Generation (Simplest Usage)

```bash
curl -X POST http://127.0.0.1:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "A soft folk song about hometown and memories"}
    ],
    "sample_mode": true,
    "audio_config": {"vocal_language": "en"}
  }'
```

### Example 2: Tagged Mode with Specific Parameters

```bash
curl -X POST http://127.0.0.1:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": "<prompt>Energetic EDM track with heavy bass drops and synth leads</prompt><lyrics>[Verse 1]\nFeel the rhythm in your soul\nLet the music take control\n\n[Drop]\n(instrumental break)</lyrics>"
      }
    ],
    "audio_config": {
      "bpm": 128,
      "duration": 60,
      "vocal_language": "en"
    }
  }'
```

### Example 3: Instrumental with LM Enhancement Disabled

```bash
curl -X POST http://127.0.0.1:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": "<prompt>Peaceful piano solo, slow tempo, jazz harmony</prompt>"
      }
    ],
    "use_cot_caption": false,
    "audio_config": {
      "instrumental": true,
      "duration": 45
    }
  }'
```

### Example 4: Streaming Request

```bash
curl -X POST http://127.0.0.1:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -N \
  -d '{
    "messages": [
      {"role": "user", "content": "Generate a happy birthday song"}
    ],
    "sample_mode": true,
    "stream": true
  }'
```

### Example 5: Multi-Seed Batch Generation

```bash
curl -X POST http://127.0.0.1:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "<prompt>Lo-fi hip hop beat</prompt>"}
    ],
    "batch_size": 3,
    "seed": "42,123,456",
    "audio_config": {
      "instrumental": true,
      "duration": 30
    }
  }'
```

---

## Error Codes

| HTTP Status | Description |
|---|---|
| 400 | Invalid request format or missing valid input |
| 401 | Missing or invalid API key |
| 429 | Service busy, queue full |
| 500 | Internal error during music generation |
| 503 | Model not yet initialized |
| 504 | Generation timeout |

Error response format:

```json
{
  "detail": "Error description message"
}
```

---

## Server Configuration (Environment Variables)

The following environment variables can be used to configure the server (for operations reference):

| Variable | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | None | API authentication key |
| `OPENROUTER_HOST` | `127.0.0.1` | Listen address |
| `OPENROUTER_PORT` | `8002` | Listen port |
| `ACESTEP_CONFIG_PATH` | `acestep-v15-turbo` | DiT model configuration path |
| `ACESTEP_DEVICE` | `auto` | Inference device |
| `ACESTEP_LM_MODEL_PATH` | `acestep-5Hz-lm-0.6B` | LLM model path |
| `ACESTEP_LM_BACKEND` | `vllm` | LLM inference backend |
| `ACESTEP_QUEUE_MAXSIZE` | `200` | Task queue max capacity |
| `ACESTEP_GENERATION_TIMEOUT` | `600` | Non-streaming request timeout (seconds) |
