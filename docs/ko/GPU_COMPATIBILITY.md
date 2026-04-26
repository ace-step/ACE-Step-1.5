# GPU 호환성 가이드

ACE-Step 1.5는 GPU의 사용 가능한 VRAM에 자동으로 적응하여 생성 제한, LM 모델 가용성, 오프로드 전략 및 UI 기본 설정을 적절히 조정합니다. 시스템은 시작 시 GPU 메모리를 감지하고 최적의 설정을 구성합니다.

## GPU 티어 구성

| VRAM | 티어 | XL (4B) DiT | LM 모델 | 추천 LM | 백엔드 | 최대 길이 (LM 사용 / 미사용) | 최대 배치 (LM 사용 / 미사용) | 오프로드 | 양자화 |
|------|------|:-----------:|---------|---------|--------|------------------------------|------------------------------|----------|--------|
| ≤4GB | 티어 1 | ❌ | 없음 | — | pt | 4분 / 6분 | 1 / 1 | CPU + DiT | INT8 |
| 4-6GB | 티어 2 | ❌ | 없음 | — | pt | 8분 / 10분 | 1 / 1 | CPU + DiT | INT8 |
| 6-8GB | 티어 3 | ❌ | 0.6B | 0.6B | pt | 8분 / 10분 | 2 / 2 | CPU + DiT | INT8 |
| 8-12GB | 티어 4 | ❌ | 0.6B | 0.6B | vllm | 8분 / 10분 | 2 / 4 | CPU + DiT | INT8 |
| 12-16GB | 티어 5 | ⚠️ | 0.6B, 1.7B | 1.7B | vllm | 8분 / 10분 | 4 / 4 | CPU | INT8 |
| 16-20GB | 티어 6a | ✅ (오프로드) | 0.6B, 1.7B | 1.7B | vllm | 8분 / 10분 | 4 / 8 | CPU | INT8 |
| 20-24GB | 티어 6b | ✅ | 0.6B, 1.7B, 4B | 1.7B | vllm | 8분 / 8분 | 8 / 8 | 없음 | 없음 |
| ≥24GB | 제한 없음 | ✅ | 전체 (0.6B, 1.7B, 4B) | 4B | vllm | 10분 / 10분 | 8 / 8 | 없음 | 없음 |

> **XL (4B) DiT 열**: ❌ = 미지원, ⚠️ = 제한적 (오프로드 + 양자화 필요, 12-16GB에서 적극적 오프로드로 동작 가능), ✅ (오프로드) = CPU 오프로드로 지원, ✅ = 완전 지원. XL 모델 가중치 약 9GB (bf16), 2B는 약 4.7GB. 모든 LM 모델이 XL과 호환됩니다.

### 열 설명

- **LM 모델**: 해당 티어에서 로드할 수 있는 5Hz 언어 모델 크기
- **추천 LM**: UI에서 해당 티어에 기본 선택되는 LM 모델
- **백엔드**: LM 추론 백엔드 (`vllm`은 충분한 VRAM을 가진 NVIDIA GPU용, `pt`는 PyTorch 대체, `mlx`는 Apple Silicon용)
- **오프로드**:
  - **CPU + DiT**: 모든 모델(DiT, VAE, 텍스트 인코더)을 미사용 시 CPU로 오프로드; DiT도 단계 간 오프로드
  - **CPU**: VAE와 텍스트 인코더를 CPU로 오프로드; DiT는 GPU에 유지
  - **없음**: 모든 모델을 GPU에 유지
- **양자화**: VRAM 사용량을 줄이기 위해 기본적으로 INT8 가중치 양자화를 활성화할지 여부

## 적응형 UI 기본 설정

Gradio UI는 감지된 GPU 티어에 따라 자동으로 설정됩니다:

- **LM 초기화 체크박스**: LM을 지원하는 티어(티어 3+)에서 기본 체크, 티어 1-2에서는 체크 해제 및 비활성화
- **LM 모델 경로**: 티어의 추천 모델이 자동 입력; 드롭다운에는 호환 모델만 표시
- **백엔드 드롭다운**: 티어 1-3에서는 `pt`/`mlx`로 제한(vllm KV 캐시가 메모리를 과도하게 사용); 티어 4+에서는 모든 백엔드 사용 가능
- **CPU 오프로드 / DiT 오프로드**: 낮은 티어에서 기본 활성화, 높은 티어에서 비활성화
- **양자화**: 티어 1-6a에서 기본 활성화, 티어 6b+에서 비활성화(충분한 VRAM)
- **모델 컴파일**: 모든 티어에서 기본 활성화(양자화에 필요)

호환되지 않는 옵션을 수동으로 선택한 경우(예: 6GB GPU에서 vllm 사용 시도), 시스템이 경고를 표시하고 호환 가능한 설정으로 자동 대체합니다.

## 런타임 안전 기능

- **VRAM 가드**: 각 추론 전에 VRAM 요구 사항을 추정하고 필요 시 배치 크기를 자동 축소
- **적응형 VAE 디코딩**: 3단계 대체: GPU 타일 디코딩 → GPU 디코딩+CPU 오프로드 → 완전 CPU 디코딩
- **자동 청크 크기**: VAE 디코딩 청크 크기가 사용 가능한 여유 VRAM에 적응(64/128/256/512/1024/1536)
- **길이/배치 클램핑**: 티어 제한을 초과하는 값을 요청하면 경고와 함께 자동 조정

## 참고 사항

- **기본 설정**은 감지된 GPU 메모리에 따라 자동으로 구성됩니다
- **LM 모드**는 Chain-of-Thought 생성 및 오디오 이해에 사용되는 언어 모델을 의미합니다
- **Flash Attention**은 자동 감지되며 사용 가능할 때 활성화됩니다
- **제약 디코딩**: LM이 초기화되면 LM의 길이 생성도 GPU 티어의 최대 길이 제한으로 제약되어 CoT 생성 중 OOM 에러를 방지합니다
- VRAM이 6GB 이하인 GPU(티어 1-2)의 경우, DiT 모델의 메모리 확보를 위해 LM 초기화가 기본적으로 비활성화됩니다
- CLI 인자 또는 Gradio UI를 통해 설정을 수동으로 무시할 수 있습니다

> **커뮤니티 기여 환영**: 위의 GPU 티어 구성은 일반적인 하드웨어에서의 테스트를 바탕으로 합니다. 사용 중인 장치의 실제 성능이 이 파라미터와 다르다면, 더 철저한 테스트를 수행하고 `acestep/gpu_config.py`에서 구성을 최적화하기 위한 PR을 제출해 주시기 바랍니다.

## 메모리 최적화 팁

1. **초저 VRAM (≤6GB)**: LM 초기화 없이 DiT 전용 모드를 사용. INT8 양자화와 완전 CPU 오프로드가 필수. VAE 디코딩이 자동으로 CPU로 대체될 수 있습니다.
2. **저 VRAM (6-8GB)**: `pt` 백엔드로 0.6B LM 모델 사용 가능. 오프로드를 활성 상태로 유지하세요.
3. **중간 VRAM (8-16GB)**: 0.6B 또는 1.7B LM 모델을 사용. 티어 4+에서 `vllm` 백엔드가 잘 작동합니다.
4. **높은 VRAM (16-24GB)**: 더 큰 LM 모델(1.7B 추천)을 활성화. 20GB+에서는 양자화가 선택 사항이 됩니다.
5. **초고 VRAM (≥24GB)**: 모든 모델이 오프로드나 양자화 없이 작동. 최고 품질을 위해 4B LM을 사용하세요.

## 디버그 모드: 다른 GPU 구성 시뮬레이션

테스트 및 개발을 위해 `MAX_CUDA_VRAM` 환경 변수를 사용하여 다른 GPU 메모리 크기를 시뮬레이션할 수 있습니다:

```bash
# 4GB GPU 시뮬레이션 (티어 1)
MAX_CUDA_VRAM=4 uv run acestep

# 6GB GPU 시뮬레이션 (티어 2)
MAX_CUDA_VRAM=6 uv run acestep

# 8GB GPU 시뮬레이션 (티어 4)
MAX_CUDA_VRAM=8 uv run acestep

# 12GB GPU 시뮬레이션 (티어 5)
MAX_CUDA_VRAM=12 uv run acestep

# 16GB GPU 시뮬레이션 (티어 6a)
MAX_CUDA_VRAM=16 uv run acestep
```

`MAX_CUDA_VRAM`을 설정하면 시스템은 `torch.cuda.set_per_process_memory_fraction()`을 호출하여 VRAM 하드 캡을 강제하며, 고사양 GPU에서도 현실적인 시뮬레이션을 제공합니다.

### 자동 티어 테스트

UI에서 각 티어를 수동으로 테스트하는 대신, `profile_inference.py`의 `tier-test` 모드를 사용할 수 있습니다:

```bash
# 모든 티어 자동 테스트
python profile_inference.py --mode tier-test

# 특정 티어 테스트
python profile_inference.py --mode tier-test --tiers 6 8 16

# LM 활성화하여 테스트 (지원되는 티어에서)
python profile_inference.py --mode tier-test --tier-with-lm

# 빠른 테스트 (비양자화 티어에서 torch.compile 건너뛰기)
python profile_inference.py --mode tier-test --tier-skip-compile
```

프로파일링 도구의 전체 문서는 [BENCHMARK.md](BENCHMARK.md)를 참조하세요.

이는 다음과 같은 경우에 유용합니다:
- 고사양 하드웨어에서 GPU 티어 구성 테스트
- 각 티어에 대해 경고 및 제한이 올바르게 작동하는지 확인
- `acestep/gpu_config.py` 수정 후 자동 회귀 테스트
- CI/CD VRAM 호환성 검증

### 경계 테스트 (최소 티어 찾기)

`--tier-boundary`를 사용하면 INT8 양자화와 CPU 오프로드를 안전하게 비활성화할 수 있는 최소 VRAM 티어를 실험적으로 확인할 수 있습니다. 각 티어에 대해 최대 3가지 구성으로 테스트합니다:

1. **default** — 티어의 기본 설정 (양자화 + 오프로드를 구성대로 사용)
2. **no-quant** — 오프로드 설정은 유지하되 양자화 비활성화
3. **no-offload** — 양자화 없음, CPU 오프로드 없음 (모든 모델을 GPU에 유지)

```bash
# 모든 티어에서 경계 테스트 실행
python profile_inference.py --mode tier-test --tier-boundary

# 특정 티어의 경계 테스트
python profile_inference.py --mode tier-test --tier-boundary --tiers 8 12 16 20 24

# LM 활성화된 경계 테스트 (지원되는 티어에서)
python profile_inference.py --mode tier-test --tier-boundary --tier-with-lm

# 결과를 JSON으로 저장
python profile_inference.py --mode tier-test --tier-boundary --benchmark-output boundary_results.json
```

> **참고:** 경계 테스트 결과는 경험적이며, DiT 모델 변형 (turbo vs base), LM 활성화 여부, 생성 시간, flash attention 가용성에 따라 달라질 수 있습니다.

### 배치 크기 경계 테스트

`--tier-batch-boundary`를 사용하여 배치 크기 1, 2, 4, 8을 단계적으로 테스트하여 각 티어의 최대 안전 배치 크기를 찾습니다:

```bash
# LM 활성화 상태에서 배치 경계 테스트 실행
python profile_inference.py --mode tier-test --tier-batch-boundary --tier-with-lm

# 특정 티어 테스트
python profile_inference.py --mode tier-test --tier-batch-boundary --tier-with-lm --tiers 8 12 16 24
```

LM 사용/미사용 두 가지 구성을 모두 테스트하고 각 티어의 최대 성공 배치 크기를 보고합니다.
