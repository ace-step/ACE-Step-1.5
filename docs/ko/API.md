# ACE-Step API 클라이언트 문서

**언어 / Language / 语言 / 言語:** [English](../en/API.md) | [한국어](API.md) | [中文](../zh/API.md) | [日本語](../ja/API.md)

---

이 서비스는 HTTP 기반의 비동기 음악 생성 API를 제공합니다.

**기본 워크플로우**:
1. `POST /release_task`를 호출하여 작업을 제출하고 `task_id`를 획득합니다.
2. `POST /query_result`를 호출하여 작업 상태가 `1`(성공) 또는 `2`(실패)가 될 때까지 배치 쿼리를 수행합니다.
3. 결과에 반환된 `GET /v1/audio?path=...` URL을 통해 오디오 파일을 다운로드합니다.

---

## 목차

- [1. 인증](#1-인증)
- [2. 응답 형식](#2-응답-형식)
- [3. 작업 상태 설명](#3-작업-상태-설명)
- [4. 생성 작업 생성](#4-생성-작업-생성)
- [5. 작업 결과 배치 조회](#5-작업-결과-배치-조회)
- [6. 입력 포맷팅 (Format Input)](#6-입력-포맷팅-format-input)
- [7. 랜덤 샘플 가져오기](#7-랜덤-샘플-가져오기)
- [8. 사용 가능한 모델 목록](#8-사용-가능한-모델-목록)
- [9. 서버 통계](#9-서버-통계)
- [10. 오디오 파일 다운로드](#10-오디오-파일-다운로드)
- [11. 헬스 체크](#11-헬스-체크)
- [12. 환경 변수](#12-환경-변수)

---

## 1. 인증

API는 선택적으로 API 키 인증을 지원합니다. 활성화된 경우 요청 시 유효한 키를 제공해야 합니다.

### 인증 방법

두 가지 인증 방법을 지원합니다:

**방법 A: 요청 본문의 ai_token**

```json
{
  "ai_token": "your-api-key",
  "prompt": "upbeat pop song",
  ...
}
```

**방법 B: Authorization 헤더**

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Authorization: Bearer your-api-key' \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "upbeat pop song"}'
```

---

## 2. 응답 형식

모든 API 응답은 통합 래퍼 형식을 사용합니다:

```json
{
  "data": { ... },
  "code": 200,
  "error": null,
  "timestamp": 1700000000000,
  "extra": null
}
```

| 필드 | 타입 | 설명 |
| :--- | :--- | :--- |
| `data` | any | 실제 응답 데이터 |
| `code` | int | 상태 코드 (200=성공) |
| `error` | string | 에러 메시지 (성공 시 null) |
| `timestamp` | int | 응답 타임스탬프 (밀리초) |
| `extra` | any | 추가 정보 (보통 null) |

---

## 3. 작업 상태 설명

작업 상태(`status`)는 정수로 표현됩니다:

| 상태 코드 | 상태 이름 | 설명 |
| :--- | :--- | :--- |
| `0` | 대기 중/실행 중 | 작업이 대기열에 있거나 진행 중임 |
| `1` | 성공 | 생성이 성공적이며 결과가 준비됨 |
| `2` | 실패 | 생성 실패 |

---

## 4. 생성 작업 생성

### 4.1 API 정의

- **URL**: `/release_task`
- **Method**: `POST`
- **Content-Type**: `application/json`, `multipart/form-data`, 또는 `application/x-www-form-urlencoded`

### 4.2 요청 파라미터

#### 파라미터 명명 규칙

API는 대부분의 파라미터에 대해 **snake_case**와 **camelCase** 명명을 모두 지원합니다. 예:
- `audio_duration` / `duration` / `audioDuration`
- `key_scale` / `keyscale` / `keyScale`
- `time_signature` / `timesignature` / `timeSignature`
- `sample_query` / `sampleQuery` / `description` / `desc`
- `use_format` / `useFormat` / `format`

또한 메타데이터는 중첩된 객체(`metas`, `metadata`, 또는 `user_metadata`)로 전달할 수 있습니다.

#### 방법 A: JSON 요청 (application/json)

텍스트 파라미터만 전달하거나 서버에 이미 존재하는 오디오 파일 경로를 참조할 때 적합합니다.

**기본 파라미터**:

| 파라미터 명 | 타입 | 기본값 | 설명 |
| :--- | :--- | :--- | :--- |
| `prompt` | string | `""` | 음악 설명 프롬프트 (별칭: `caption`) |
| `lyrics` | string | `""` | 가사 내용 |
| `thinking` | bool | `false` | 5Hz LM을 사용하여 오디오 코드를 생성할지 여부 (lm-dit 동작) |
| `vocal_language` | string | `"en"` | 가사 언어 (en, zh, ja 등) |
| `audio_format` | string | `"mp3"` | 출력 형식 (mp3, wav, flac) |

**샘플/설명 모드 파라미터**:

| 파라미터 명 | 타입 | 기본값 | 설명 |
| :--- | :--- | :--- | :--- |
| `sample_mode` | bool | `false` | 랜덤 샘플 생성 모드 활성화 (LM을 통해 캡션/가사/메타데이터 자동 생성) |
| `sample_query` | string | `""` | 샘플 생성을 위한 자연어 설명 (예: "조용한 저녁을 위한 부드러운 벵골어 사랑 노래"). 별칭: `description`, `desc` |
| `use_format` | bool | `false` | LM을 사용하여 제공된 캡션과 가사를 개선/포맷팅합니다. 별칭: `format` |

**다중 모델 지원**:

| 파라미터 명 | 타입 | 기본값 | 설명 |
| :--- | :--- | :--- | :--- |
| `model` | string | null | 사용할 DiT 모델 선택 (예: `"acestep-v15-turbo"`, `"acestep-v15-turbo-shift3"`). `/v1/models`를 사용하여 가능한 모델 목록을 확인하세요. 지정하지 않으면 기본 모델을 사용합니다. |

**thinking 의미론 (중요)**:

- `thinking=false`:
  - 서버는 `audio_code_string`을 생성하기 위해 5Hz LM을 사용하지 **않습니다**.
  - DiT는 **text2music** 모드에서 실행되며 제공된 `audio_code_string`을 **무시**합니다.
- `thinking=true`:
  - 서버는 `audio_code_string`을 생성하기 위해 5Hz LM을 사용합니다 (lm-dit 동작).
  - DiT는 향상된 음악 품질을 위해 LM이 생성한 코드를 기반으로 실행됩니다.

**메타데이터 자동 완성 (조건부)**:

`use_cot_caption=true` 또는 `use_cot_language=true`이거나 메타데이터 필드가 누락된 경우, 서버는 `caption`/`lyrics`를 기반으로 누락된 필드를 채우기 위해 5Hz LM을 호출할 수 있습니다:

- `bpm`
- `key_scale`
- `time_signature`
- `audio_duration`

사용자가 제공한 값이 항상 우선하며, LM은 비어 있거나 누락된 필드만 채웁니다.

**음악 속성 파라미터**:

| 파라미터 명 | 타입 | 기본값 | 설명 |
| :--- | :--- | :--- | :--- |
| `bpm` | int | null | 템포(BPM) 지정, 범위 30-300 |
| `key_scale` | string | `""` | 키/스케일 (예: "C Major", "Am"). 별칭: `keyscale`, `keyScale` |
| `time_signature` | string | `""` | 박자 기호 (2/4, 3/4, 4/4, 6/8의 경우 2, 3, 4, 6). 별칭: `timesignature`, `timeSignature` |
| `audio_duration` | float | null | 생성 길이 (초), 범위 10-600. 별칭: `duration`, `target_duration` |

**오디오 코드 (선택 사항)**:

| 파라미터 명 | 타입 | 기본값 | 설명 |
| :--- | :--- | :--- | :--- |
| `audio_code_string` | string or string[] | `""` | `llm_dit`를 위한 오디오 시맨틱 토큰(5Hz) 문자열. 별칭: `audioCodeString` |

**생성 제어 파라미터**:

| 파라미터 명 | 타입 | 기본값 | 설명 |
| :--- | :--- | :--- | :--- |
| `inference_steps` | int | `8` | 추론 단계 수. Turbo 모델: 1-20 (권장 8). Base 모델: 1-200 (권장 32-64). |
| `guidance_scale` | float | `7.0` | 프롬프트 가이드 계수. Base 모델에서만 유효합니다. |
| `use_random_seed` | bool | `true` | 랜덤 시드 사용 여부 |
| `seed` | int | `-1` | 시드 지정 (use_random_seed=false일 때) |
| `batch_size` | int | `2` | 배치 생성 수 (최대 8) |

**고급 DiT 파라미터**:

| 파라미터 명 | 타입 | 기본값 | 설명 |
| :--- | :--- | :--- | :--- |
| `shift` | float | `3.0` | 타임스텝 시프트 계수 (범위 1.0-5.0). Turbo 모델이 아닌 Base 모델에서만 유효합니다. |
| `infer_method` | string | `"ode"` | 확산 추론 방법: `"ode"` (Euler, 더 빠름) 또는 `"sde"` (확률적). |
| `timesteps` | string | null | 쉼표로 구분된 커스텀 타임스텝 (예: `"0.97,0.76,0.615,0.5,0.395,0.28,0.18,0.085,0"`). `inference_steps`와 `shift`를 재정의합니다. |
| `use_adg` | bool | `false` | ADG (Adaptive Dual Guidance) 사용 (Base 모델 전용) |
| `cfg_interval_start` | float | `0.0` | CFG 적용 시작 비율 (0.0-1.0) |
| `cfg_interval_end` | float | `1.0` | CFG 적용 종료 비율 (0.0-1.0) |

**5Hz LM 파라미터 (선택 사항, 서버측)**:

이 파라미터들은 메타데이터 자동 완성 및 (thinking=true일 때) 코드 생성에 사용되는 5Hz LM 샘플링을 제어합니다.

| 파라미터 명 | 타입 | 기본값 | 설명 |
| :--- | :--- | :--- | :--- |
| `lm_model_path` | string | null | 5Hz LM 체크포인트 디렉토리 이름 (예: `acestep-5Hz-lm-0.6B`) |
| `lm_backend` | string | `"vllm"` | `vllm` 또는 `pt` |
| `lm_temperature` | float | `0.85` | 샘플링 온도 |
| `lm_cfg_scale` | float | `2.5` | CFG 스케일 (>1일 경우 CFG 활성화) |
| `lm_negative_prompt` | string | `"NO USER INPUT"` | CFG에 사용되는 네거티브 프롬프트 |
| `lm_top_k` | int | null | Top-k (0/null은 비활성) |
| `lm_top_p` | float | `0.9` | Top-p (>=1은 비활성) |
| `lm_repetition_penalty` | float | `1.0` | 반복 페널티 |

**LM CoT (Chain-of-Thought) 파라미터**:

| 파라미터 명 | 타입 | 기본값 | 설명 |
| :--- | :--- | :--- | :--- |
| `use_cot_caption` | bool | `true` | CoT 추론을 통해 LM이 입력된 캡션을 다시 쓰거나 개선하도록 합니다. 별칭: `cot_caption`, `cot-caption` |
| `use_cot_language` | bool | `true` | CoT를 통해 LM이 가창 언어를 감지하도록 합니다. 별칭: `cot_language`, `cot-language` |
| `constrained_decoding` | bool | `true` | 구조화된 LM 출력을 위해 FSM 기반 제약 디코딩을 활성화합니다. 별칭: `constrainedDecoding`, `constrained` |
| `constrained_decoding_debug` | bool | `false` | 제약 디코딩에 대한 디버그 로깅 활성화 |
| `allow_lm_batch` | bool | `true` | 효율성을 위해 LM 배치 처리 허용 |

**편집/참조 오디오 파라미터** (서버의 절대 경로 필요):

| 파라미터 명 | 타입 | 기본값 | 설명 |
| :--- | :--- | :--- | :--- |
| `reference_audio_path` | string | null | 참조 오디오 경로 (Style Transfer) |
| `src_audio_path` | string | null | 소스 오디오 경로 (Repainting/Cover) |
| `task_type` | string | `"text2music"` | 작업 유형: `text2music`, `cover`, `repaint`, `lego`, `extract`, `complete` |
| `instruction` | string | auto | 편집 지침 (제공되지 않으면 task_type에 따라 자동 생성됨) |
| `repainting_start` | float | `0.0` | 리페인팅 시작 시간 (초) |
| `repainting_end` | float | null | 리페인팅 종료 시간 (초), 오디오 끝까지의 경우 -1 |
| `audio_cover_strength` | float | `1.0` | 오디오 커버 강도 (0.0-1.0). 스타일 전송 작업의 경우 낮은 값(0.2)을 설정합니다. |

#### 방법 B: 파일 업로드 (multipart/form-data)

로컬 오디오 파일을 참조 또는 소스 오디오로 업로드해야 할 때 사용합니다.

위의 모든 필드를 폼 필드로 지원할 뿐만 아니라, 다음 파일 필드도 지원합니다:

- `reference_audio` 또는 `ref_audio`: (파일) 참조 오디오 파일 업로드
- `src_audio` 또는 `ctx_audio`: (파일) 소스 오디오 파일 업로드

> **참고**: 파일을 업로드하면 해당 `_path` 파라미터는 자동으로 무시되고 시스템은 업로드 후 생성된 임시 파일 경로를 사용합니다.

### 4.3 응답 예시

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

---

## 5. 작업 결과 배치 조회

### 5.1 API 정의

- **URL**: `/query_result`
- **Method**: `POST`
- **Content-Type**: `application/json` 또는 `application/x-www-form-urlencoded`

### 5.2 요청 파라미터

| 파라미터 명 | 타입 | 설명 |
| :--- | :--- | :--- |
| `task_id_list` | string (JSON array) or array | 조회할 작업 ID 목록 |

### 5.3 응답 예시

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

**Result 필드 설명** (result는 JSON 문자열이며, 파싱 후 다음을 포함):

| 필드 | 타입 | 설명 |
| :--- | :--- | :--- |
| `file` | string | 오디오 파일 URL (`/v1/audio` 엔드포인트와 함께 사용) |
| `wave` | string | 파형 데이터 (보통 비어 있음) |
| `status` | int | 상태 코드 (0=진행 중, 1=성공, 2=실패) |
| `create_time` | int | 생성 시간 (Unix 타임스탬프) |
| `env` | string | 환경 식별자 |
| `prompt` | string | 사용된 프롬프트 |
| `lyrics` | string | 사용된 가사 |
| `metas` | object | 메타데이터 (bpm, duration, genres, keyscale, timesignature) |
| `generation_info` | string | 생성 정보 요약 |
| `seed_value` | string | 사용된 시드 값 (쉼표로 구분) |
| `lm_model` | string | 사용된 LM 모델 명 |
| `dit_model` | string | 사용된 DiT 모델 명 |

---

## 6. 입력 포맷팅 (Format Input)

### 6.1 API 정의

- **URL**: `/format_input`
- **Method**: `POST`

이 엔드포인트는 LLM을 사용하여 사용자가 제공한 캡션과 가사를 개선하고 포맷팅합니다.

### 6.2 요청 파라미터

| 파라미터 명 | 타입 | 기본값 | 설명 |
| :--- | :--- | :--- | :--- |
| `prompt` | string | `""` | 음악 설명 프롬프트 |
| `lyrics` | string | `""` | 가사 내용 |
| `temperature` | float | `0.85` | LM 샘플링 온도 |
| `param_obj` | string (JSON) | `"{}"` | 메타데이터를 포함하는 JSON 객체 (duration, bpm, key, time_signature, language) |

### 6.3 응답 예시

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

---

## 7. 랜덤 샘플 가져오기

### 7.1 API 정의

- **URL**: `/create_random_sample`
- **Method**: `POST`

이 엔드포인트는 폼 채우기를 위해 사전 로드된 예제 데이터에서 임의의 샘플 파라미터를 반환합니다.

### 7.2 요청 파라미터

| 파라미터 명 | 타입 | 기본값 | 설명 |
| :--- | :--- | :--- | :--- |
| `sample_type` | string | `"simple_mode"` | 샘플 유형: `"simple_mode"` 또는 `"custom_mode"` |

---

## 8. 사용 가능한 모델 목록

### 8.1 API 정의

- **URL**: `/v1/models`
- **Method**: `GET`

서버에 로드된 사용 가능한 DiT 모델 목록을 반환합니다.

### 8.2 응답 예시

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

---

## 9. 서버 통계

### 9.1 API 정의

- **URL**: `/v1/stats`
- **Method**: `GET`

서버 런타임 통계를 반환합니다.

---

## 10. 오디오 파일 다운로드

### 10.1 API 정의

- **URL**: `/v1/audio`
- **Method**: `GET`

경로별로 생성된 오디오 파일을 다운로드합니다.

### 10.2 요청 파라미터

| 파라미터 명 | 타입 | 설명 |
| :--- | :--- | :--- |
| `path` | string | 오디오 파일의 URL 인코딩된 경로 |

---

## 11. 헬스 체크

### 11.1 API 정의

- **URL**: `/health`
- **Method**: `GET`

서비스 상태를 반환합니다.

---

## 12. 환경 변수

API 서버는 환경 변수를 사용하여 구성할 수 있습니다:

### 서버 구성

| 변수 | 기본값 | 설명 |
| :--- | :--- | :--- |
| `ACESTEP_API_HOST` | `127.0.0.1` | 서버 바인드 호스트 |
| `ACESTEP_API_PORT` | `8001` | 서버 바인드 포트 |
| `ACESTEP_API_KEY` | (비어 있음) | API 인증 키 (비어 있으면 인증 비활성화) |
| `ACESTEP_API_WORKERS` | `1` | API 워커 스레드 수 |

### 모델 구성

| 변수 | 기본값 | 설명 |
| :--- | :--- | :--- |
| `ACESTEP_CONFIG_PATH` | `acestep-v15-turbo` | 주 DiT 모델 경로 |
| `ACESTEP_DEVICE` | `auto` | 모델 로딩 장치 |
| `ACESTEP_OFFLOAD_TO_CPU` | `false` | 유휴 시 모델을 CPU로 오프로드 |

### LM 구성

| 변수 | 기본값 | 설명 |
| :--- | :--- | :--- |
| `ACESTEP_INIT_LLM` | auto | 시작 시 LM을 초기화할지 여부 (GPU에 따라 자동 결정) |
| `ACESTEP_LM_MODEL_PATH` | `acestep-5Hz-lm-0.6B` | 기본 5Hz LM 모델 |
| `ACESTEP_LM_BACKEND` | `vllm` | LM 백엔드 (vllm 또는 pt) |

---

## 에러 처리

**HTTP 상태 코드**:

- `200`: 성공
- `400`: 잘못된 요청 (잘못된 JSON, 누락된 필드)
- `401`: 미인증 (누락되었거나 잘못된 API 키)
- `429`: 서버 바쁨 (대기열이 가득 참)
- `500`: 내부 서버 오류

---

## 모범 사례

1.  **`thinking=true`를 사용**하여 LM이 향상된 생성 품질의 결과를 얻으세요.
2.  자연어 설명에서 빠른 생성을 위해 **`sample_query`/`description`을 사용**하세요.
3.  캡션/가사가 있지만 LM이 이를 개선하기를 원할 때 **`use_format=true`를 사용**하세요.
4.  `/query_result` 엔드포인트를 사용하여 여러 작업 상태를 **배치 조회**하세요.
5.  **/v1/stats를 확인**하여 서버 부하와 평균 작업 시간을 파악하세요.
6.  **보안을 위해** `ACESTEP_API_KEY`를 설정하여 인증을 활성화하세요.
