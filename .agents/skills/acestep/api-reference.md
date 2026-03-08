# ACE-Step API Reference

> For debugging and advanced usage only. Normal operations should use `scripts/acestep.sh`.

## Native Mode Endpoints

All responses wrapped: `{"data": <payload>, "code": 200, "error": null, "timestamp": ...}`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/release_task` | POST | Create generation task |
| `/query_result` | POST | Query task status, body: `{"task_id_list": ["id"]}` |
| `/v1/models` | GET | List available models |
| `/v1/audio?path={path}` | GET | Download audio file |

## Completion Mode Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | Generate music (OpenRouter-compatible) |
| `/v1/models` | GET | List available models (OpenRouter format) |

## Query Result Response

```json
{
  "data": [{
    "task_id": "xxx",
    "status": 1,
    "result": "[{\"file\":\"/v1/audio?path=...\",\"metas\":{\"bpm\":120,\"duration\":60,\"keyscale\":\"C Major\"}}]"
  }]
}
```

Status codes: `0` = processing, `1` = success, `2` = failed

## Completion Mode Request (`/v1/chat/completions`)

**Caption mode** — prompt and lyrics wrapped in XML tags inside message content:
```json
{
  "model": "acestep/ACE-Step-v1.5",
  "messages": [{"role": "user", "content": "<prompt>Jazz with saxophone</prompt><lyrics>[Verse] Hello...</lyrics>"}],
  "stream": false,
  "thinking": true,
  "use_format": false,
  "audio_config": {"duration": 90, "bpm": 110, "format": "mp3", "vocal_language": "en"}
}
```

**Simple mode** — plain text message, set `sample_mode: true`:
```json
{
  "model": "acestep/ACE-Step-v1.5",
  "messages": [{"role": "user", "content": "A cheerful pop song about spring"}],
  "stream": false,
  "sample_mode": true,
  "thinking": true
}
```

## Completion Mode Response

```json
{
  "id": "chatcmpl-abc123",
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "## Metadata\n**Caption:** ...\n**BPM:** 128\n\n## Lyrics\n...",
      "audio": [{"type": "audio_url", "audio_url": {"url": "data:audio/mpeg;base64,..."}}]
    },
    "finish_reason": "stop"
  }]
}
```

Audio is base64-encoded inline — the script auto-decodes and saves to `acestep_output/`.

## Request Parameters (`/release_task`)

Parameters can be placed in `param_obj` object.

### Generation Modes

| Mode | Usage | When to Use |
|------|-------|-------------|
| **Caption** (Recommended) | `generate -c "style" -l "lyrics"` | For vocal songs - write lyrics yourself first |
| **Simple** | `generate -d "description"` | Quick exploration, LM generates everything |
| **Random** | `random` | Random generation for inspiration |

### Core Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | string | "" | Music style description (Caption mode) |
| `lyrics` | string | "" | **Full lyrics content** - Pass ALL lyrics without omission. Use `[inst]` for instrumental. Partial/truncated lyrics = incomplete songs |
| `sample_mode` | bool | false | Enable Simple/Random mode |
| `sample_query` | string | "" | Description for Simple mode |
| `thinking` | bool | false | Enable 5Hz LM for audio code generation |
| `use_format` | bool | false | Use LM to enhance caption/lyrics |
| `model` | string | - | DiT model name |
| `batch_size` | int | 1 | Number of audio files to generate |

### Music Attributes

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `audio_duration` | float | - | Duration in seconds |
| `bpm` | int | - | Tempo (beats per minute) |
| `key_scale` | string | "" | Key (e.g. "C Major") |
| `time_signature` | string | "" | Time signature (e.g. "4/4") |
| `vocal_language` | string | "en" | Language code (en, zh, ja, etc.) |
| `audio_format` | string | "mp3" | Output format (mp3/wav/flac) |

### Generation Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `inference_steps` | int | 8 | Diffusion steps |
| `guidance_scale` | float | 7.0 | CFG scale |
| `seed` | int | -1 | Random seed (-1 for random) |
| `infer_method` | string | "ode" | Diffusion method (ode/sde) |

### Audio Task Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task_type` | string | "text2music" | text2music / continuation / repainting |
| `src_audio_path` | string | - | Source audio for continuation |
| `repainting_start` | float | 0.0 | Repainting start position (seconds) |
| `repainting_end` | float | - | Repainting end position (seconds) |

### Example Request (Simple Mode)

```json
{
  "sample_mode": true,
  "sample_query": "A cheerful pop song about spring",
  "thinking": true,
  "param_obj": {
    "duration": 60,
    "bpm": 120,
    "language": "en"
  },
  "batch_size": 2
}
```
