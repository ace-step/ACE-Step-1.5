# ACE-Step OpenRouter API 문서

> AI 음악 생성을 위한 OpenAI Chat Completions 호환 API

**Base URL:** `http://{host}:{port}` (기본값 `http://127.0.0.1:8002`)

---

## 목차

- [인증](#인증)
- [엔드포인트](#엔드포인트)
  - [POST /v1/chat/completions - 음악 생성](#1-음악-생성)
  - [GET /api/v1/models - 모델 목록](#2-모델-목록)
  - [GET /health - 헬스 체크](#3-헬스-체크)
- [입력 모드](#입력-모드)
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
| `model` | string | 아니요 | `"acemusic/acestep-v1.5-turbo"` | 모델 ID |
| `messages` | array | **예** | - | 채팅 메시지 리스트. [입력 모드](#입력-모드) 참조 |
| `stream` | boolean | 아니요 | `false` | 스트리밍 응답 활성화 여부 |
| `temperature` | float | 아니요 | `0.85` | LM 샘플링 온도 |
| `top_p` | float | 아니요 | `0.9` | LM nucleus sampling 파라미터 |
| `lyrics` | string | 아니요 | `""` | 직접 전달되는 가사 (메시지에서 파싱된 가사보다 우선함) |
| `duration` | float | 아니요 | `null` | 오디오 길이(초). 생략 시 LM이 자동 결정 |
| `bpm` | integer | 아니요 | `null` | 분당 비트수(BPM). 생략 시 LM이 자동 결정 |
| `vocal_language` | string | 아니요 | `"en"` | 보컬 언어 코드 (예: `"ko"`, `"en"`, `"ja"`) |
| `instrumental` | boolean | 아니요 | `false` | 보컬 없는 연주곡 생성 여부 |
| `thinking` | boolean | 아니요 | `false` | 더 깊은 추론을 위한 LLM thinking 모드 활성화 |
| `use_cot_metas` | boolean | 아니요 | `true` | CoT를 통해 BPM, 길이, 키 등을 자동 생성 |
| `use_cot_caption` | boolean | 아니요 | `true` | CoT를 통해 음악 설명을 재작성/개선 |
| `use_cot_language` | boolean | 아니요 | `true` | CoT를 통해 보컬 언어를 자동 감지 |
| `use_format` | boolean | 아니요 | `true` | 프롬프트/가사가 직접 제공될 때 LLM 포맷팅을 통해 개선 |

#### 비스트리밍 응답 예시 (`stream: false`)

```json
{
  "id": "chatcmpl-a1b2c3d4e5f6g7h8",
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "## Metadata\n**Caption:** 신나는 팝 곡...\n**BPM:** 120\n**Duration:** 30s\n**Key:** C major\n\n## Lyrics\n[Verse 1]\nHello world...",
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
  ]
}
```

---

## 입력 모드

시스템은 마지막 `user` 메시지의 내용에 따라 입력 모드를 자동으로 선택합니다:

### 모드 1: 태그 모드 (권장)

`<prompt>`와 `<lyrics>` 태그를 사용하여 음악 설명과 가사를 명시적으로 지정합니다:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "<prompt>C Major, 80 BPM, 여성 보컬의 잔잔한 어쿠스틱 발라드</prompt>\n<lyrics>[Verse 1]\n창가에 비치는 햇살\n새로운 하루가 시작돼</lyrics>"
    }
  ]
}
```

### 모드 2: 자연어 모드 (샘플 모드)

원하는 음악을 자연어로 설명합니다. 시스템이 LLM을 사용하여 프롬프트와 가사를 자동으로 생성합니다:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "여름과 여행에 관한 신나는 팝송을 만들어줘"
    }
  ]
}
```

---

## 스트리밍 응답

`"stream": true`로 설정하면 SSE(Server-Sent Events) 스트리밍이 활성화됩니다. 오디오 생성 중에도 하트비트(`.`)를 보내 연결을 유지하며, 마지막에 오디오 데이터를 보냅니다.

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
    "vocal_language": "ko"
  }'
```

### 예제 2: 스트리밍 요청

```bash
curl -X POST http://127.0.0.1:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -N \
  -d '{
    "messages": [
      {"role": "user", "content": "생일 축하 노래를 만들어줘"}
    ],
    "stream": true
  }'
```
