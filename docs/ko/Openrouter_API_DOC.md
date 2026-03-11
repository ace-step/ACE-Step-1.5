# ACE-Step OpenRouter API 문서

> AI 음악 생성을 위한 OpenAI Chat Completions 호환 API

**Base URL:** `http://{host}:{port}` (기본값 `http://127.0.0.1:8002`)

---

## 목차

- [인증](#인증)
- [엔드포인트](#엔드포인트)
  - [POST /v1/chat/completions - 음악 생성](#1-음악-생성)
  - [GET /v1/models - 모델 목록](#2-모델-목록)
  - [GET /health - 헬스 체크](#3-헬스-체크)
- [입력 모드](#입력-모드)
- [오디오 입력](#오디오-입력)
- [스트리밍 응답](#스트리밍-응답)
- [예제](#예제)
- [에러 코드](#에러-코드)

---

## 인증

서버에 API 키가 설정된 경우(환경 변수 `OPENROUTER_API_KEY` 또는 `--api-key` 플래그 사용), 모든 요청은 다음 헤더를 포함해야 합니다:

```
Authorization: Bearer <your-api-key>
```

API 키가 설정되지 않은 경우 인증이 필요하지 않습니다.

---

## 엔드포인트

### 1. 음악 생성

**POST** `/v1/chat/completions`

채팅 메시지로부터 음악을 생성하고 오디오 데이터와 LM이 생성한 메타데이터를 반환합니다.

#### 요청 파라미터

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|
| `model` | string | 아니요 | 자동 | 모델 ID (`/v1/models`에서 확인) |
| `messages` | array | **예** | - | 채팅 메시지 리스트. [입력 모드](#입력-모드) 참조 |
| `stream` | boolean | 아니요 | `false` | 스트리밍 응답 활성화. [스트리밍 응답](#스트리밍-응답) 참조 |
| `audio_config` | object | 아니요 | `null` | 오디오 생성 설정. 아래 참조 |
| `temperature` | float | 아니요 | `0.85` | LM 샘플링 온도 |
| `top_p` | float | 아니요 | `0.9` | LM nucleus sampling 파라미터 |
| `seed` | int \| string | 아니요 | `null` | 랜덤 시드. `batch_size > 1`일 때 쉼표로 구분하여 여러 개 지정 가능 (예: `"42,123,456"`) |
| `lyrics` | string | 아니요 | `""` | 직접 전달되는 가사 (메시지에서 파싱된 가사보다 우선). 설정 시 messages 텍스트는 prompt로 사용 |
| `sample_mode` | boolean | 아니요 | `false` | LLM sample 모드 활성화. messages 텍스트가 sample_query로 LLM에 전달되어 prompt/lyrics 자동 생성 |
| `thinking` | boolean | 아니요 | `false` | 더 깊은 추론을 위한 LLM thinking 모드 활성화 |
| `use_format` | boolean | 아니요 | `false` | 사용자가 prompt/lyrics를 제공할 때 LLM 포맷팅으로 개선 |
| `use_cot_caption` | boolean | 아니요 | `true` | CoT를 통해 음악 설명을 재작성/개선 |
| `use_cot_language` | boolean | 아니요 | `true` | CoT를 통해 보컬 언어를 자동 감지 |
| `guidance_scale` | float | 아니요 | `7.0` | Classifier-free guidance scale |
| `batch_size` | int | 아니요 | `1` | 생성할 오디오 수 |
| `task_type` | string | 아니요 | `"text2music"` | 작업 유형. [오디오 입력](#오디오-입력) 참조 |
| `repainting_start` | float | 아니요 | `0.0` | repaint 영역 시작 위치(초) |
| `repainting_end` | float | 아니요 | `null` | repaint 영역 종료 위치(초) |
| `audio_cover_strength` | float | 아니요 | `1.0` | 커버 강도 (0.0~1.0) |

#### audio_config 객체

| 필드 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `duration` | float | `null` | 오디오 길이(초). 생략 시 LM이 자동 결정 |
| `bpm` | integer | `null` | 분당 비트수(BPM). 생략 시 LM이 자동 결정 |
| `vocal_language` | string | `"en"` | 보컬 언어 코드 (예: `"ko"`, `"en"`, `"ja"`) |
| `instrumental` | boolean | `null` | 보컬 없는 연주곡 여부. 생략 시 가사에 따라 자동 판단 |
| `format` | string | `"mp3"` | 출력 오디오 포맷 |
| `key_scale` | string | `null` | 조성 (예: `"C major"`) |
| `time_signature` | string | `null` | 박자 (예: `"4/4"`) |

> **messages 텍스트의 의미는 모드에 따라 다릅니다:**
> - `lyrics` 설정 시 → messages 텍스트 = caption
> - `sample_mode: true` 설정 시 → messages 텍스트 = sample_query (LLM에게 모든 것을 생성하도록 함)
> - 둘 다 미설정 → 자동 감지: 태그가 있으면 태그 모드, 가사처럼 보이면 가사 모드, 그 외 caption 로 직접 생성에 사용

#### messages 형식

일반 텍스트와 멀티모달(텍스트 + 오디오) 두 가지 형식을 지원합니다:

**일반 텍스트:**

```json
{
  "messages": [
    {"role": "user", "content": "입력 내용"}
  ]
}
```

**멀티모달 (오디오 입력 포함):**

```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "이 노래를 커버해줘"},
        {
          "type": "input_audio",
          "input_audio": {
            "data": "<base64 오디오 데이터>",
            "format": "mp3"
          }
        }
      ]
    }
  ]
}
```

---

#### 비스트리밍 응답 (`stream: false`)

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

**응답 필드 설명:**

| 필드 | 설명 |
|---|---|
| `choices[0].message.content` | LM이 생성한 텍스트 정보. Metadata(Caption/BPM/Duration/Key/Time Signature/Language)와 Lyrics를 포함. LM이 관여하지 않은 경우 `"Music generated successfully."` 반환 |
| `choices[0].message.audio` | 오디오 데이터 배열. 각 항목에 `type` (`"audio_url"`)과 `audio_url.url` (Base64 Data URL, 형식: `data:audio/mpeg;base64,...`)을 포함 |
| `choices[0].finish_reason` | `"stop"`은 정상 완료를 나타냄 |

**오디오 디코딩 형식:**

`audio_url.url` 값은 Data URL 형식: `data:audio/mpeg;base64,<base64_data>`

쉼표 이후의 base64 데이터 부분을 추출하여 디코딩하면 MP3 파일을 얻을 수 있습니다:

```python
import base64

url = response["choices"][0]["message"]["audio"][0]["audio_url"]["url"]
# "data:audio/mpeg;base64," 접두사 제거
b64_data = url.split(",", 1)[1]
audio_bytes = base64.b64decode(b64_data)

with open("output.mp3", "wb") as f:
    f.write(audio_bytes)
```

```javascript
const url = response.choices[0].message.audio[0].audio_url.url;
const b64Data = url.split(",")[1];
const audioBytes = atob(b64Data);
// Data URL을 <audio> 태그에 직접 사용 가능
const audio = new Audio(url);
audio.play();
```

---

### 2. 모델 목록

**GET** `/v1/models`

사용 가능한 모델 정보를 반환합니다.

#### 응답

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

### 3. 헬스 체크

**GET** `/health`

#### 응답

```json
{
  "status": "ok",
  "service": "ACE-Step OpenRouter API",
  "version": "1.0"
}
```

---

## 입력 모드

시스템은 마지막 `user` 메시지의 내용에 따라 입력 모드를 자동으로 선택합니다. `lyrics` 또는 `sample_mode` 필드로 명시적으로 지정할 수도 있습니다.

### 모드 1: 태그 모드 (권장)

`<prompt>`와 `<lyrics>` 태그를 사용하여 음악 설명과 가사를 명시적으로 지정합니다:

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

- `<prompt>...</prompt>` — 음악 스타일/장면 설명 (caption)
- `<lyrics>...</lyrics>` — 가사 내용
- 하나의 태그만 사용할 수도 있음
- `use_format: true`일 때 LLM이 prompt와 lyrics를 자동으로 개선

### 모드 2: 자연어 모드 (샘플 모드)

원하는 음악을 자연어로 설명합니다. 시스템이 LLM을 사용하여 prompt와 lyrics를 자동으로 생성합니다:

```json
{
  "messages": [
    {"role": "user", "content": "여름과 여행에 관한 신나는 팝송을 만들어줘"}
  ],
  "sample_mode": true,
  "audio_config": {
    "vocal_language": "ko"
  }
}
```

트리거 조건: `sample_mode: true`, 또는 메시지에 태그가 없고 가사처럼 보이지 않을 때 자동 트리거.

### 모드 3: 가사 전용 모드

구조 마커가 있는 가사를 직접 전달하면 시스템이 자동으로 인식합니다:

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

트리거 조건: 메시지에 `[Verse]`, `[Chorus]` 등의 마커가 포함되거나 여러 줄의 짧은 텍스트 구조를 가진 경우.

### 모드 4: 가사 + Prompt 분리

`lyrics` 필드로 가사를 직접 전달하고, messages 텍스트는 자동으로 prompt로 사용됩니다:

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

### 연주곡 모드

`audio_config.instrumental: true` 설정:

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

## 오디오 입력

멀티모달 messages를 통해 오디오 파일(base64 인코딩)을 전달하여 cover, repaint 등의 작업에 사용할 수 있습니다.

### task_type 유형

| task_type | 설명 | 오디오 입력 필요 |
|---|---|---|
| `text2music` | 텍스트에서 음악 생성 (기본값) | 선택 (reference로) |
| `cover` | 커버/스타일 전환 | src_audio 필요 |
| `repaint` | 부분 리페인팅 | src_audio 필요 |
| `lego` | 오디오 접합 | src_audio 필요 |
| `extract` | 오디오 추출 | src_audio 필요 |
| `complete` | 오디오 이어쓰기 | src_audio 필요 |

### 오디오 라우팅 규칙

여러 `input_audio` 블록은 순서대로 다른 파라미터에 라우팅됩니다 (다중 이미지 업로드와 유사):

| task_type | audio[0] | audio[1] |
|---|---|---|
| `text2music` | reference_audio (스타일 참조) | - |
| `cover/repaint/lego/extract/complete` | src_audio (편집 대상 오디오) | reference_audio (선택적 스타일 참조) |

### 오디오 입력 예제

**Cover 작업 (커버):**

```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "<prompt>Jazz style cover with saxophone</prompt>"},
        {
          "type": "input_audio",
          "input_audio": {"data": "<base64 원본 오디오>", "format": "mp3"}
        }
      ]
    }
  ],
  "task_type": "cover",
  "audio_cover_strength": 0.8,
  "audio_config": {"duration": 30}
}
```

**Repaint 작업 (부분 리페인팅):**

```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "<prompt>Replace with guitar solo</prompt>"},
        {
          "type": "input_audio",
          "input_audio": {"data": "<base64 원본 오디오>", "format": "mp3"}
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

## 스트리밍 응답

`"stream": true`로 설정하면 SSE(Server-Sent Events) 스트리밍이 활성화됩니다.

### 이벤트 형식

각 이벤트는 `data: `로 시작하고 JSON이 뒤따르며 이중 줄바꿈 `\n\n`으로 끝납니다:

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{...},"finish_reason":null}]}

```

### 스트리밍 이벤트 순서

| 단계 | delta 내용 | 설명 |
|---|---|---|
| 1. 초기화 | `{"role":"assistant","content":""}` | 연결 수립 |
| 2. LM 콘텐츠 | `{"content":"\n\n## Metadata\n..."}` | LM 사용 시 metadata와 lyrics 전송 |
| 3. 하트비트 | `{"content":"."}` | 오디오 생성 중 2초마다 전송, 연결 유지 |
| 4. 오디오 데이터 | `{"audio":[{"type":"audio_url","audio_url":{"url":"data:..."}}]}` | 오디오 base64 데이터 |
| 5. 완료 | `finish_reason: "stop"` | 생성 완료 |
| 6. 종료 | `data: [DONE]` | 스트림 종료 마커 |

### 스트리밍 응답 예시

```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{"content":"\n\n## Metadata\n**Caption:** Upbeat pop\n**BPM:** 120"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{"content":"."},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{"audio":[{"type":"audio_url","audio_url":{"url":"data:audio/mpeg;base64,..."}}]},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]

```

### 클라이언트 측 스트리밍 처리

```python
import json
import httpx

with httpx.stream("POST", "http://127.0.0.1:8002/v1/chat/completions", json={
    "messages": [{"role": "user", "content": "경쾌한 기타 곡을 생성해줘"}],
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
            print("생성 완료!")

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
    messages: [{ role: "user", content: "경쾌한 기타 곡을 생성해줘" }],
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

// audioUrl은 <audio src="...">에 직접 사용 가능
```

---

## 예제

### 예제 1: 자연어 생성 (가장 간단한 사용법)

```bash
curl -X POST http://127.0.0.1:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "고향과 추억에 관한 부드러운 포크 송"}
    ],
    "sample_mode": true,
    "audio_config": {"vocal_language": "ko"}
  }'
```

### 예제 2: 태그 모드 + 파라미터 지정

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

### 예제 3: 연주곡 + LM 개선 비활성화

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

### 예제 4: 스트리밍 요청

```bash
curl -X POST http://127.0.0.1:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -N \
  -d '{
    "messages": [
      {"role": "user", "content": "생일 축하 노래를 만들어줘"}
    ],
    "sample_mode": true,
    "stream": true
  }'
```

### 예제 5: 멀티 시드 배치 생성

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

## 에러 코드

| HTTP 상태 코드 | 설명 |
|---|---|
| 400 | 잘못된 요청 형식 또는 유효한 입력 누락 |
| 401 | API 키 누락 또는 유효하지 않음 |
| 429 | 서비스 과부하, 큐 가득 참 |
| 500 | 음악 생성 중 내부 오류 발생 |
| 503 | 모델이 아직 초기화되지 않음 |
| 504 | 생성 타임아웃 |

에러 응답 형식:

```json
{
  "detail": "에러 설명 메시지"
}
```

---

## 서버 설정 (환경 변수)

다음 환경 변수로 서버를 설정할 수 있습니다 (운영 참고용):

| 변수명 | 기본값 | 설명 |
|---|---|---|
| `OPENROUTER_API_KEY` | 없음 | API 인증 키 |
| `OPENROUTER_HOST` | `127.0.0.1` | 리슨 주소 |
| `OPENROUTER_PORT` | `8002` | 리슨 포트 |
| `ACESTEP_CONFIG_PATH` | `acestep-v15-turbo` | DiT 모델 설정 경로 |
| `ACESTEP_DEVICE` | `auto` | 추론 디바이스 |
| `ACESTEP_LM_MODEL_PATH` | `acestep-5Hz-lm-0.6B` | LLM 모델 경로 |
| `ACESTEP_LM_BACKEND` | `vllm` | LLM 추론 백엔드 |
| `ACESTEP_QUEUE_MAXSIZE` | `200` | 작업 큐 최대 용량 |
| `ACESTEP_GENERATION_TIMEOUT` | `600` | 비스트리밍 요청 타임아웃(초) |
