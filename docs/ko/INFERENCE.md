# ACE-Step 추론 API 문서

**언어 / Language / 语言 / 言語:** [English](INFERENCE.md) | [한국어](INFERENCE.md) | [中文](../zh/INFERENCE.md) | [日本語](../ja/INFERENCE.md)

---

이 문서는 모든 지원되는 작업 유형에 대한 파라미터 사양을 포함하여 ACE-Step 추론 API에 대한 포괄적인 문서를 제공합니다.

## 목차

- [빠른 시작](#빠른-시작)
- [API 개요](#api-개요)
- [GenerationParams 파라미터](#generationparams-파라미터)
- [GenerationConfig 파라미터](#generationconfig-파라미터)
- [작업 유형 (Task Types)](#작업-유형-task-types)
- [도우미 함수](#도우미-함수)
- [전체 예제](#전체-예제)
- [모범 사례](#모범-사례)

---

## 빠른 시작

### 기본 사용법

```python
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.inference import GenerationParams, GenerationConfig, generate_music

# 핸들러 초기화
dit_handler = AceStepHandler()
llm_handler = LLMHandler()

# 서비스 초기화
dit_handler.initialize_service(
    project_root="/path/to/project",
    config_path="acestep-v15-turbo",
    device="cuda"
)

llm_handler.initialize(
    checkpoint_dir="/path/to/checkpoints",
    lm_model_path="acestep-5Hz-lm-0.6B",
    backend="vllm",
    device="cuda"
)

# 생성 파라미터 설정
params = GenerationParams(
    caption="upbeat electronic dance music with heavy bass",
    bpm=128,
    duration=30,
)

# 생성 설정 구성
config = GenerationConfig(
    batch_size=2,
    audio_format="flac",
)

# 음악 생성
result = generate_music(dit_handler, llm_handler, params, config, save_dir="/path/to/output")

# 결과 확인
if result.success:
    for audio in result.audios:
        print(f"Generated: {audio['path']}")
        print(f"Key: {audio['key']}")
        print(f"Seed: {audio['params']['seed']}")
else:
    print(f"Error: {result.error}")
```

---

## API 개요

### 주요 함수

#### generate_music

```python
def generate_music(
    dit_handler,
    llm_handler,
    params: GenerationParams,
    config: GenerationConfig,
    save_dir: Optional[str] = None,
    progress=None,
) -> GenerationResult
```

ACE-Step 모델을 사용하여 음악을 생성하는 메인 함수입니다.

#### understand_music

```python
def understand_music(
    llm_handler,
    audio_codes: str,
    temperature: float = 0.85,
    top_k: Optional[int] = None,
    top_p: Optional[float] = None,
    repetition_penalty: float = 1.0,
    use_constrained_decoding: bool = True,
    constrained_decoding_debug: bool = False,
) -> UnderstandResult
```

오디오 시맨틱 코드를 분석하고 메타데이터(캡션, 가사, BPM, 키 등)를 추출합니다.

#### create_sample

```python
def create_sample(
    llm_handler,
    query: str,
    instrumental: bool = False,
    vocal_language: Optional[str] = None,
    temperature: float = 0.85,
    top_k: Optional[int] = None,
    top_p: Optional[float] = None,
    repetition_penalty: float = 1.0,
    use_constrained_decoding: bool = True,
    constrained_decoding_debug: bool = False,
) -> CreateSampleResult
```

자연어 설명으로부터 완전한 음악 샘플(캡션, 가사, 메타데이터)을 생성합니다.

#### format_sample

```python
def format_sample(
    llm_handler,
    caption: str,
    lyrics: str,
    user_metadata: Optional[Dict[str, Any]] = None,
    temperature: float = 0.85,
    top_k: Optional[int] = None,
    top_p: Optional[float] = None,
    repetition_penalty: float = 1.0,
    use_constrained_decoding: bool = True,
    constrained_decoding_debug: bool = False,
) -> FormatSampleResult
```

사용자가 제공한 캡션과 가사를 개선/포맷팅하고 구조화된 메타데이터를 생성합니다.

---

## GenerationParams 파라미터

### 텍스트 입력

| 파라미터 | 타입 | 기본값 | 설명 |
|-----------|------|---------|-------------|
| `caption` | `str` | `""` | 원하는 음악에 대한 텍스트 설명. 간단한 프롬프트나 장르, 분위기, 악기 등이 포함된 상세 설명이 가능합니다. 최대 512자. |
| `lyrics` | `str` | `""` | 보컬 음악을 위한 가사. 연주곡의 경우 `"[Instrumental]"`을 사용하세요. 다국어를 지원합니다. 최대 4096자. |
| `instrumental` | `bool` | `False` | True일 경우 가사에 상관없이 연주곡을 생성합니다. |

### 음악 메타데이터

| 파라미터 | 타입 | 기본값 | 설명 |
|-----------|------|---------|-------------|
| `bpm` | `Optional[int]` | `None` | 분당 비트수(30-300). `None`으로 설정하면 LM을 통한 자동 감지를 활성화합니다. |
| `keyscale` | `str` | `""` | 음악 키 (예: "C Major", "Am", "F# minor"). 빈 문자열은 자동 감지를 활성화합니다. |
| `timesignature` | `str` | `""` | 박자 기호 ('2/4'는 2, '3/4'는 3, '4/4'는 4, '6/8'은 6). 빈 문자열은 자동 감지를 활성화합니다. |
| `vocal_language` | `str` | `"unknown"` | 보컬 언어 코드 (ISO 639-1). 지원: `"en"`, `"zh"`, `"ja"`, `"ko"`, `"es"`, `"fr"` 등. 자동 감지는 `"unknown"` 사용. |
| `duration` | `float` | `-1.0` | 대상 오디오 길이(초, 10-600). 0 이하이거나 None인 경우 가사 길이에 따라 모델이 자동으로 선택합니다. |

### 생성 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|-----------|------|---------|-------------|
| `inference_steps` | `int` | `8` | 노이즈 제거 단계 수. Turbo 모델: 1-20 (8 권장). Base 모델: 1-200 (32-64 권장). 높을수록 품질은 좋아지지만 속도는 느려집니다. |
| `guidance_scale` | `float` | `7.0` | Classifier-free guidance 스케일 (1.0-15.0). 높을수록 텍스트 프롬프트에 더 가깝게 생성됩니다. 비-Turbo 모델에서만 지원됩니다. |
| `seed` | `int` | `-1` | 재현성을 위한 랜덤 시드. 랜덤은 `-1`, 고정된 결과는 양의 정수를 사용하세요. |

### 고급 DiT 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|-----------|------|---------|-------------|
| `use_adg` | `bool` | `False` | Adaptive Dual Guidance 사용 (Base 모델 전용). 속도는 느려지지만 품질이 향상됩니다. |
| `cfg_interval_start` | `float` | `0.0` | CFG 적용 시작 비율 (0.0-1.0). |
| `cfg_interval_end` | `float` | `1.0` | CFG 적용 종료 비율 (0.0-1.0). |
| `shift` | `float` | `1.0` | 타임스텝 시프트 계수 (범위 1.0-5.0). Turbo 모델의 경우 3.0을 권장합니다. |
| `infer_method` | `str` | `"ode"` | 확산 추론 방법. `"ode"`(Euler)는 빠르고 결정론적입니다. `"sde"`는 결과에 분산이 발생할 수 있습니다. |

### 작업별 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|-----------|------|---------|-------------|
| `task_type` | `str` | `"text2music"` | 생성 작업 유형. [작업 유형](#작업-유형-task-types) 섹션을 참조하세요. |
| `reference_audio` | `Optional[str]` | `None` | 스타일 전송 또는 연속 생성 작업을 위한 참조 오디오 파일 경로. |
| `src_audio` | `Optional[str]` | `None` | 오디오-투-오디오 작업(cover, repaint 등)을 위한 소스 오디오 파일 경로. |
| `repainting_start` | `float` | `0.0` | 리페인팅 시작 시간 (초). |
| `repainting_end` | `float` | `-1` | 리페인팅 종료 시간 (초). -1은 오디오 끝을 의미합니다. |
| `audio_cover_strength` | `float` | `1.0` | 오디오 커버/코드 영향력 강도 (0.0-1.0). 스타일 전송의 경우 낮게(0.2) 설정하세요. |

### 5Hz 언어 모델 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|-----------|------|---------|-------------|
| `thinking` | `bool` | `True` | 시맨틱/음악 메타데이터 및 코드를 위한 5Hz LM "추론(Chain-of-Thought)" 활성화. |
| `lm_temperature` | `float` | `0.85` | LM 샘플링 온도. 높을수록 창의적/다양함, 낮을수록 보수적임. |
| `lm_cfg_scale` | `float` | `2.0` | LM classifier-free guidance 스케일. |
| `use_cot_metas` | `bool` | `True` | LM CoT 추론을 사용하여 메타데이터(BPM, 키 등) 생성. |
| `use_cot_caption` | `bool` | `True` | LM CoT 추론을 사용하여 사용자 캡션 개선. |
| `use_constrained_decoding` | `bool` | `True` | 구조화된 LM 출력을 위한 제약 디코딩 활성화. |

---

## 작업 유형 (Task Types)

### 1. Text2Music (기본)
텍스트 설명과 선택적 메타데이터로부터 음악을 생성합니다.

### 2. Cover
원본의 구조는 유지하면서 스타일이나 음색을 변형합니다. `src_audio`와 `caption`이 필요합니다.

### 3. Repaint
오디오의 특정 시간 구간만 다시 생성합니다. `repainting_start`와 `repainting_end`를 사용합니다.

### 4. Lego (Base 모델 전용)
기존 오디오 컨텍스트 내에서 특정 악기 트랙(보컬, 드럼 등)을 생성합니다.

### 5. Extract (Base 모델 전용)
믹스된 오디오에서 특정 악기 트랙을 분리/추출합니다.

### 6. Complete (Base 모델 전용)
부분적인 트랙에 지정된 악기를 추가하여 완성합니다.

---

## 예제: 가사가 포함된 노래 생성

```python
params = GenerationParams(
    task_type="text2music",
    caption="pop ballad with emotional vocals",
    lyrics="""Verse 1:
Walking down the street today
Thinking of the words you used to say
Everything feels different now
But I'll find my way somehow

Chorus:
I'm moving on, I'm staying strong
This is where I belong
""",
    vocal_language="en",
    bpm=72,
    duration=45,
)

config = GenerationConfig(batch_size=1)
result = generate_music(dit_handler, llm_handler, params, config, save_dir="/output")
```

---

## 모범 사례

1. **상세한 프롬프트**: "슬픈 노래"보다는 "피아노와 보컬이 어우러진 잔잔하고 애절한 발라드"가 더 나은 결과를 얻습니다.
2. **Turbo 모델 활용**: 빠른 반복 작업에는 `turbo` 모델을 사용하는 것이 효율적입니다.
3. **Thinking 모드**: 더 논리적인 음악 구조가 필요할 때 `thinking=True`를 사용하되, 메모리가 부족하면 끌 수 있습니다.
4. **결과 반복**: 배치 크기를 2-4로 설정하여 여러 버전을 한 번에 듣고 최적의 결과를 고르는 것이 좋습니다.
