# ACE-Step 推理 API 文档

**Language / 语言 / 言語:** [English](../en/INFERENCE.md) | [中文](INFERENCE.md) | [日本語](../ja/INFERENCE.md)

---

本文档提供 ACE-Step 推理 API 的综合文档，包括所有支持任务类型的参数规范。

## 目录

- [快速开始](#快速开始)
- [API 概述](#api-概述)
- [GenerationParams 参数](#generationparams-参数)
- [GenerationConfig 参数](#generationconfig-参数)
- [任务类型](#任务类型)
- [辅助函数](#辅助函数)
- [完整示例](#完整示例)
- [最佳实践](#最佳实践)

---

## 快速开始

### 基本用法

```python
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.inference import GenerationParams, GenerationConfig, generate_music

# 初始化处理器
dit_handler = AceStepHandler()
llm_handler = LLMHandler()

# 初始化服务
dit_handler.initialize_service(
    project_root="/path/to/project",
    config_path="acestep-v15-turbo",
    device="auto"
)

llm_handler.initialize(
    checkpoint_dir="/path/to/checkpoints",
    lm_model_path="acestep-5Hz-lm-0.6B",
    backend="vllm",
    device="auto"
)

# 配置生成参数
params = GenerationParams(
    caption="欢快的电子舞曲，重低音",
    bpm=128,
    duration=30,
)

# 配置生成设置
config = GenerationConfig(
    batch_size=2,
    audio_format="flac",
)

# 生成音乐
result = generate_music(dit_handler, llm_handler, params, config, save_dir="/path/to/output")

# 访问结果
if result.success:
    for audio in result.audios:
        print(f"已生成：{audio['path']}")
        print(f"Key：{audio['key']}")
        print(f"Seed：{audio['params']['seed']}")
else:
    print(f"错误：{result.error}")
```

---

## API 概述

### 主要函数

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

使用 ACE-Step 模型生成音乐的主函数。

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

分析音频语义代码并提取元数据（caption、lyrics、BPM、调性等）。

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

从自然语言描述生成完整的音乐样本（caption、lyrics、元数据）。

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

格式化和增强用户提供的 caption 和 lyrics，生成结构化元数据。

### 配置对象

API 使用两个配置数据类：

**GenerationParams** - 包含所有音乐生成参数：

```python
@dataclass
class GenerationParams:
    # 任务和指令
    task_type: str = "text2music"
    instruction: str = "Fill the audio semantic mask based on the given conditions:"
    
    # 音频上传
    reference_audio: Optional[str] = None
    src_audio: Optional[str] = None
    
    # LM 代码提示
    audio_codes: str = ""
    
    # 文本输入
    caption: str = ""
    lyrics: str = ""
    instrumental: bool = False
    
    # 元数据
    vocal_language: str = "unknown"
    bpm: Optional[int] = None
    keyscale: str = ""
    timesignature: str = ""
    duration: float = -1.0
    
    # 高级设置
    inference_steps: int = 8
    seed: int = -1
    guidance_scale: float = 7.0
    use_adg: bool = False
    cfg_interval_start: float = 0.0
    cfg_interval_end: float = 1.0
    shift: float = 1.0                    # 新增：时间步偏移因子
    infer_method: str = "ode"             # 新增：扩散推理方法
    timesteps: Optional[List[float]] = None  # 新增：自定义时间步
    
    repainting_start: float = 0.0
    repainting_end: float = -1
    audio_cover_strength: float = 1.0
    
    # 5Hz 语言模型参数
    thinking: bool = True
    lm_temperature: float = 0.85
    lm_cfg_scale: float = 2.0
    lm_top_k: int = 0
    lm_top_p: float = 0.9
    lm_negative_prompt: str = "NO USER INPUT"
    use_cot_metas: bool = True
    use_cot_caption: bool = True
    use_cot_lyrics: bool = False
    use_cot_language: bool = True
    use_constrained_decoding: bool = True
    
    # CoT 生成的值（由 LM 自动填充）
    cot_bpm: Optional[int] = None
    cot_keyscale: str = ""
    cot_timesignature: str = ""
    cot_duration: Optional[float] = None
    cot_vocal_language: str = "unknown"
    cot_caption: str = ""
    cot_lyrics: str = ""
```

**GenerationConfig** - 包含批处理和输出配置：

```python
@dataclass
class GenerationConfig:
    batch_size: int = 2
    allow_lm_batch: bool = False
    use_random_seed: bool = True
    seeds: Optional[List[int]] = None
    lm_batch_chunk_size: int = 8
    constrained_decoding_debug: bool = False
    audio_format: str = "flac"
```

### 结果对象

**GenerationResult** - 音乐生成结果：

```python
@dataclass
class GenerationResult:
    # 音频输出
    audios: List[Dict[str, Any]]  # 音频字典列表
    
    # 生成信息
    status_message: str           # 生成状态消息
    extra_outputs: Dict[str, Any] # 额外输出（latents、masks、lm_metadata、time_costs）
    
    # 成功状态
    success: bool                 # 生成是否成功
    error: Optional[str]          # 失败时的错误消息
```

**音频字典结构：**

`audios` 列表中的每个项目包含：

```python
{
    "path": str,           # 保存的音频文件路径
    "tensor": Tensor,      # 音频张量 [channels, samples]，CPU，float32
    "key": str,            # 唯一音频键（基于参数的 UUID）
    "sample_rate": int,    # 采样率（默认：48000）
    "params": Dict,        # 此音频的生成参数（包括 seed、audio_codes 等）
}
```

**UnderstandResult** - 音乐理解结果：

```python
@dataclass
class UnderstandResult:
    # 元数据字段
    caption: str = ""
    lyrics: str = ""
    bpm: Optional[int] = None
    duration: Optional[float] = None
    keyscale: str = ""
    language: str = ""
    timesignature: str = ""
    
    # 状态
    status_message: str = ""
    success: bool = True
    error: Optional[str] = None
```

**CreateSampleResult** - 样本创建结果：

```python
@dataclass
class CreateSampleResult:
    # 元数据字段
    caption: str = ""
    lyrics: str = ""
    bpm: Optional[int] = None
    duration: Optional[float] = None
    keyscale: str = ""
    language: str = ""
    timesignature: str = ""
    instrumental: bool = False
    
    # 状态
    status_message: str = ""
    success: bool = True
    error: Optional[str] = None
```

**FormatSampleResult** - 样本格式化结果：

```python
@dataclass
class FormatSampleResult:
    # 元数据字段
    caption: str = ""
    lyrics: str = ""
    bpm: Optional[int] = None
    duration: Optional[float] = None
    keyscale: str = ""
    language: str = ""
    timesignature: str = ""
    
    # 状态
    status_message: str = ""
    success: bool = True
    error: Optional[str] = None
```

---

## GenerationParams 参数

### 文本输入

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|-------------|
| `caption` | `str` | `""` | 期望音乐的文本描述。可以是简单提示如"放松的钢琴音乐"，或包含风格、情绪、乐器等的详细描述。最多 512 字符。|
| `lyrics` | `str` | `""` | 人声音乐的歌词文本。纯音乐使用 `"[Instrumental]"`。支持多种语言。最多 4096 字符。|
| `instrumental` | `bool` | `False` | 如果为 True，无论歌词如何都生成纯音乐。|

### 音乐元数据

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|-------------|
| `bpm` | `Optional[int]` | `None` | 每分钟节拍数（30-300）。`None` 启用通过 LM 自动检测。|
| `keyscale` | `str` | `""` | 音乐调性（例如"C Major"、"Am"、"F# minor"）。空字符串启用自动检测。|
| `timesignature` | `str` | `""` | 拍号（2 表示 '2/4'，3 表示 '3/4'，4 表示 '4/4'，6 表示 '6/8'）。空字符串启用自动检测。|
| `vocal_language` | `str` | `"unknown"` | 人声语言代码（ISO 639-1）。支持：`"en"`、`"zh"`、`"ja"`、`"es"`、`"fr"` 等。使用 `"unknown"` 自动检测。|
| `duration` | `float` | `-1.0` | 目标音频长度（秒）（10-600）。如果 <= 0 或 None，模型根据歌词长度自动选择。|

### 生成参数

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|-------------|
| `inference_steps` | `int` | `8` | 去噪步数。Turbo 模型：1-20（推荐 8）。Base 模型：1-200（推荐 32-64）。越高 = 质量越好但更慢。|
| `guidance_scale` | `float` | `7.0` | 无分类器引导比例（1.0-15.0）。较高的值增加对文本提示的遵循度。仅支持非 turbo 模型。典型范围：5.0-9.0。|
| `seed` | `int` | `-1` | 用于可重复性的随机种子。使用 `-1` 表示随机种子，或任何正整数表示固定种子。|

### 高级 DiT 参数

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|-------------|
| `use_adg` | `bool` | `False` | 使用自适应双引导（仅 base 模型）。以速度为代价提高质量。|
| `cfg_interval_start` | `float` | `0.0` | CFG 应用起始比例（0.0-1.0）。控制何时开始应用无分类器引导。|
| `cfg_interval_end` | `float` | `1.0` | CFG 应用结束比例（0.0-1.0）。控制何时停止应用无分类器引导。|
| `shift` | `float` | `1.0` | 时间步偏移因子（范围 1.0-5.0，默认 1.0）。当 != 1.0 时，对时间步应用 `t = shift * t / (1 + (shift - 1) * t)`。turbo 模型推荐 3.0。|
| `infer_method` | `str` | `"ode"` | 扩散推理方法。`"ode"`（Euler）更快且确定性。`"sde"`（随机）可能产生不同的带方差结果。|
| `timesteps` | `Optional[List[float]]` | `None` | 自定义时间步，从 1.0 到 0.0 的浮点数列表（例如 `[0.97, 0.76, 0.615, 0.5, 0.395, 0.28, 0.18, 0.085, 0]`）。如果提供，覆盖 `inference_steps` 和 `shift`。|

### 任务特定参数

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|-------------|
| `task_type` | `str` | `"text2music"` | 生成任务类型。详见[任务类型](#任务类型)部分。|
| `instruction` | `str` | `"Fill the audio semantic mask based on the given conditions:"` | 任务特定指令提示。|
| `reference_audio` | `Optional[str]` | `None` | 用于风格迁移或续写任务的参考音频文件路径。|
| `src_audio` | `Optional[str]` | `None` | 用于音频到音频任务（cover、repaint 等）的源音频文件路径。|
| `audio_codes` | `str` | `""` | 预提取的 5Hz 音频语义代码字符串。仅供高级使用。|
| `repainting_start` | `float` | `0.0` | 重绘开始时间（秒）（用于 repaint/lego 任务）。|
| `repainting_end` | `float` | `-1` | 重绘结束时间（秒）。使用 `-1` 表示音频末尾。|
| `audio_cover_strength` | `float` | `1.0` | 音频 cover/代码影响强度（0.0-1.0）。风格迁移任务设置较小值（0.2）。|

### 5Hz 语言模型参数

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|-------------|
| `thinking` | `bool` | `True` | 启用 5Hz 语言模型"思维链"推理用于语义/音乐元数据和代码。|
| `lm_temperature` | `float` | `0.85` | LM 采样温度（0.0-2.0）。越高 = 更有创意/多样，越低 = 更保守。|
| `lm_cfg_scale` | `float` | `2.0` | LM 无分类器引导比例。越高 = 更强的提示遵循度。|
| `lm_top_k` | `int` | `0` | LM top-k 采样。`0` 禁用 top-k 过滤。典型值：40-100。|
| `lm_top_p` | `float` | `0.9` | LM 核采样（0.0-1.0）。`1.0` 禁用核采样。典型值：0.9-0.95。|
| `lm_negative_prompt` | `str` | `"NO USER INPUT"` | LM 引导的负面提示。帮助避免不想要的特征。|
| `use_cot_metas` | `bool` | `True` | 使用 LM CoT 推理生成元数据（BPM、调性、时长等）。|
| `use_cot_caption` | `bool` | `True` | 使用 LM CoT 推理优化用户 caption。|
| `use_cot_language` | `bool` | `True` | 使用 LM CoT 推理检测人声语言。|
| `use_cot_lyrics` | `bool` | `False` | （保留供将来使用）使用 LM CoT 生成/优化歌词。|
| `use_constrained_decoding` | `bool` | `True` | 启用结构化 LM 输出的约束解码。|

### CoT 生成的值

这些字段在启用 CoT 推理时由 LM 自动填充：

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|-------------|
| `cot_bpm` | `Optional[int]` | `None` | LM 生成的 BPM 值。|
| `cot_keyscale` | `str` | `""` | LM 生成的调性。|
| `cot_timesignature` | `str` | `""` | LM 生成的拍号。|
| `cot_duration` | `Optional[float]` | `None` | LM 生成的时长。|
| `cot_vocal_language` | `str` | `"unknown"` | LM 检测的人声语言。|
| `cot_caption` | `str` | `""` | LM 优化的 caption。|
| `cot_lyrics` | `str` | `""` | LM 生成/优化的歌词。|

---

## GenerationConfig 参数

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|-------------|
| `batch_size` | `int` | `2` | 并行生成的样本数量（1-8）。较高的值需要更多 GPU 内存。|
| `allow_lm_batch` | `bool` | `False` | 允许 LM 批处理。当 `batch_size >= 2` 且 `thinking=True` 时更快。|
| `use_random_seed` | `bool` | `True` | 是否使用随机种子。`True` 每次不同结果，`False` 可重复结果。|
| `seeds` | `Optional[List[int]]` | `None` | 批量生成的种子列表。如果提供的种子少于 batch_size，将用随机种子填充。也可以是单个 int。|
| `lm_batch_chunk_size` | `int` | `8` | 每个 LM 推理块的最大批处理大小（GPU 内存限制）。|
| `constrained_decoding_debug` | `bool` | `False` | 启用约束解码的调试日志。|
| `audio_format` | `str` | `"flac"` | 输出音频格式。选项：`"mp3"`、`"wav"`、`"flac"`。默认 FLAC 以快速保存。|

---

## 任务类型

ACE-Step 支持 6 种不同的生成任务类型，每种都针对特定用例进行了优化。

### 1. Text2Music（默认）

**目的**：从文本描述和可选元数据生成音乐。

**关键参数**：
```python
params = GenerationParams(
    task_type="text2music",
    caption="充满活力的摇滚音乐，电吉他",
    lyrics="[Instrumental]",  # 或实际歌词
    bpm=140,
    duration=30,
)
```

**必需**：
- `caption` 或 `lyrics`（至少一个）

**可选但推荐**：
- `bpm`：控制节奏
- `keyscale`：控制音乐调性
- `timesignature`：控制节拍结构
- `duration`：控制长度
- `vocal_language`：控制人声特征

**用例**：
- 从文本描述生成音乐
- 从提示创建伴奏
- 生成带歌词的歌曲

---

### 2. Cover

**目的**：转换现有音频，保持结构但改变风格/音色。

**关键参数**：
```python
params = GenerationParams(
    task_type="cover",
    src_audio="original_song.mp3",
    caption="爵士钢琴版本",
    audio_cover_strength=0.8,  # 0.0-1.0
)
```

**必需**：
- `src_audio`：源音频文件路径
- `caption`：期望风格/转换的描述

**可选**：
- `audio_cover_strength`：控制原始音频的影响
  - `1.0`：强烈保持原始结构
  - `0.5`：平衡转换
  - `0.1`：宽松解读
- `lyrics`：新歌词（如果要更改人声）

**用例**：
- 创建不同风格的翻唱
- 在保持旋律的同时更改乐器
- 风格转换

---

### 3. Repaint

**目的**：重新生成音频的特定时间段，保持其余部分不变。

**关键参数**：
```python
params = GenerationParams(
    task_type="repaint",
    src_audio="original.mp3",
    repainting_start=10.0,  # 秒
    repainting_end=20.0,    # 秒
    caption="带钢琴独奏的平滑过渡",
)
```

**必需**：
- `src_audio`：源音频文件路径
- `repainting_start`：开始时间（秒）
- `repainting_end`：结束时间（秒）（使用 `-1` 表示文件末尾）
- `caption`：重绘部分期望内容的描述

**用例**：
- 修复生成音乐的特定部分
- 为歌曲的某些部分添加变化
- 创建平滑过渡
- 替换有问题的片段

---

### 4. Lego（仅 Base 模型）

**目的**：在现有音频的上下文中生成特定乐器轨道。

**关键参数**：
```python
params = GenerationParams(
    task_type="lego",
    src_audio="backing_track.mp3",
    instruction="Generate the guitar track based on the audio context:",
    caption="带有蓝调感觉的主音吉他旋律",
    repainting_start=0.0,
    repainting_end=-1,
)
```

**必需**：
- `src_audio`：源/伴奏音频路径
- `instruction`：必须指定轨道类型（例如"Generate the {TRACK_NAME} track..."）
- `caption`：期望轨道特征的描述

**可用轨道**：
- `"vocals"`、`"backing_vocals"`、`"drums"`、`"bass"`、`"guitar"`、`"keyboard"`、
- `"percussion"`、`"strings"`、`"synth"`、`"fx"`、`"brass"`、`"woodwinds"`

**用例**：
- 添加特定乐器轨道
- 在伴奏轨道上叠加额外乐器
- 迭代创建多轨作品

---

### 5. Extract（仅 Base 模型）

**目的**：从混音音频中提取/分离特定乐器轨道。

**关键参数**：
```python
params = GenerationParams(
    task_type="extract",
    src_audio="full_mix.mp3",
    instruction="Extract the vocals track from the audio:",
)
```

**必需**：
- `src_audio`：混音音频文件路径
- `instruction`：必须指定要提取的轨道

**可用轨道**：与 Lego 任务相同

**用例**：
- 音轨分离
- 分离特定乐器
- 创建混音
- 分析单独轨道

---

### 6. Complete（仅 Base 模型）

**目的**：用指定的乐器完成/扩展部分轨道。

**关键参数**：
```python
params = GenerationParams(
    task_type="complete",
    src_audio="incomplete_track.mp3",
    instruction="Complete the input track with drums, bass, guitar:",
    caption="摇滚风格完成",
)
```

**必需**：
- `src_audio`：不完整/部分轨道的路径
- `instruction`：必须指定要添加的轨道
- `caption`：期望风格的描述

**用例**：
- 编排不完整的作品
- 添加伴奏轨道
- 自动完成音乐想法

---

## 辅助函数

### understand_music

分析音频代码以提取音乐元数据。

```python
from acestep.inference import understand_music

result = understand_music(
    llm_handler=llm_handler,
    audio_codes="<|audio_code_123|><|audio_code_456|>...",
    temperature=0.85,
    use_constrained_decoding=True,
)

if result.success:
    print(f"Caption：{result.caption}")
    print(f"歌词：{result.lyrics}")
    print(f"BPM：{result.bpm}")
    print(f"调性：{result.keyscale}")
    print(f"时长：{result.duration}s")
    print(f"语言：{result.language}")
else:
    print(f"错误：{result.error}")
```

**用例**：
- 分析现有音乐
- 从音频代码提取元数据
- 逆向工程生成参数

---

### create_sample

从自然语言描述生成完整的音乐样本。这是"简单模式"/"灵感模式"功能。

```python
from acestep.inference import create_sample

result = create_sample(
    llm_handler=llm_handler,
    query="一首适合安静夜晚的柔和孟加拉情歌",
    instrumental=False,
    vocal_language="bn",  # 可选：限制为孟加拉语
    temperature=0.85,
)

if result.success:
    print(f"Caption：{result.caption}")
    print(f"歌词：{result.lyrics}")
    print(f"BPM：{result.bpm}")
    print(f"时长：{result.duration}s")
    print(f"调性：{result.keyscale}")
    print(f"是否纯音乐：{result.instrumental}")
    
    # 与 generate_music 一起使用
    params = GenerationParams(
        caption=result.caption,
        lyrics=result.lyrics,
        bpm=result.bpm,
        duration=result.duration,
        keyscale=result.keyscale,
        vocal_language=result.language,
    )
else:
    print(f"错误：{result.error}")
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|-------------|
| `query` | `str` | 必需 | 期望音乐的自然语言描述 |
| `instrumental` | `bool` | `False` | 是否生成纯音乐 |
| `vocal_language` | `Optional[str]` | `None` | 将歌词限制为特定语言（例如"en"、"zh"、"bn"）|
| `temperature` | `float` | `0.85` | 采样温度 |
| `top_k` | `Optional[int]` | `None` | Top-k 采样（None 禁用）|
| `top_p` | `Optional[float]` | `None` | Top-p 采样（None 禁用）|
| `repetition_penalty` | `float` | `1.0` | 重复惩罚 |
| `use_constrained_decoding` | `bool` | `True` | 使用基于 FSM 的约束解码 |

---

### format_sample

格式化和增强用户提供的 caption 和 lyrics，生成结构化元数据。

```python
from acestep.inference import format_sample

result = format_sample(
    llm_handler=llm_handler,
    caption="拉丁流行，雷鬼音",
    lyrics="[Verse 1]\nBailando en la noche...",
    user_metadata={"bpm": 95},  # 可选：约束特定值
    temperature=0.85,
)

if result.success:
    print(f"增强后的 Caption：{result.caption}")
    print(f"格式化后的歌词：{result.lyrics}")
    print(f"BPM：{result.bpm}")
    print(f"时长：{result.duration}s")
    print(f"调性：{result.keyscale}")
    print(f"检测到的语言：{result.language}")
else:
    print(f"错误：{result.error}")
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|-------------|
| `caption` | `str` | 必需 | 用户的 caption/描述 |
| `lyrics` | `str` | 必需 | 用户的带结构标签的歌词 |
| `user_metadata` | `Optional[Dict]` | `None` | 约束特定元数据值（bpm、duration、keyscale、timesignature、language）|
| `temperature` | `float` | `0.85` | 采样温度 |
| `top_k` | `Optional[int]` | `None` | Top-k 采样（None 禁用）|
| `top_p` | `Optional[float]` | `None` | Top-p 采样（None 禁用）|
| `repetition_penalty` | `float` | `1.0` | 重复惩罚 |
| `use_constrained_decoding` | `bool` | `True` | 使用基于 FSM 的约束解码 |

---

## 完整示例

### 示例 1：简单文本到音乐生成

```python
from acestep.inference import GenerationParams, GenerationConfig, generate_music

params = GenerationParams(
    task_type="text2music",
    caption="宁静的氛围音乐，柔和的钢琴和弦乐",
    duration=60,
    bpm=80,
    keyscale="C Major",
)

config = GenerationConfig(
    batch_size=2,  # 生成 2 个变体
    audio_format="flac",
)

result = generate_music(dit_handler, llm_handler, params, config, save_dir="/output")

if result.success:
    for i, audio in enumerate(result.audios, 1):
        print(f"变体 {i}：{audio['path']}")
```

### 示例 2：带歌词的歌曲生成

```python
params = GenerationParams(
    task_type="text2music",
    caption="流行民谣，情感人声",
    lyrics="""Verse 1:
今天走在街上
想着你曾说过的话
一切都变得不同了
但我会找到自己的路

Chorus:
我在前进，我很坚强
这就是我属于的地方
""",
    vocal_language="zh",
    bpm=72,
    duration=45,
)

config = GenerationConfig(batch_size=1)

result = generate_music(dit_handler, llm_handler, params, config, save_dir="/output")
```

### 示例 3：使用自定义时间步

```python
params = GenerationParams(
    task_type="text2music",
    caption="复杂和声的爵士融合",
    # 自定义 9 步调度
    timesteps=[0.97, 0.76, 0.615, 0.5, 0.395, 0.28, 0.18, 0.085, 0],
    thinking=True,
)

config = GenerationConfig(batch_size=1)

result = generate_music(dit_handler, llm_handler, params, config, save_dir="/output")
```

### 示例 4：使用 Shift 参数（Turbo 模型）

```python
params = GenerationParams(
    task_type="text2music",
    caption="欢快的电子舞曲",
    inference_steps=8,
    shift=3.0,  # Turbo 模型推荐
    infer_method="ode",
)

config = GenerationConfig(batch_size=2)

result = generate_music(dit_handler, llm_handler, params, config, save_dir="/output")
```

### 示例 5：使用 create_sample 的简单模式

```python
from acestep.inference import create_sample, GenerationParams, GenerationConfig, generate_music

# 步骤 1：从描述创建样本
sample = create_sample(
    llm_handler=llm_handler,
    query="充满活力的韩国流行舞曲，带有朗朗上口的 Hook",
    vocal_language="ko",
)

if sample.success:
    # 步骤 2：使用样本生成音乐
    params = GenerationParams(
        caption=sample.caption,
        lyrics=sample.lyrics,
        bpm=sample.bpm,
        duration=sample.duration,
        keyscale=sample.keyscale,
        vocal_language=sample.language,
        thinking=True,
    )
    
    config = GenerationConfig(batch_size=2)
    result = generate_music(dit_handler, llm_handler, params, config, save_dir="/output")
```

### 示例 6：格式化和增强用户输入

```python
from acestep.inference import format_sample, GenerationParams, GenerationConfig, generate_music

# 步骤 1：格式化用户输入
formatted = format_sample(
    llm_handler=llm_handler,
    caption="摇滚民谣",
    lyrics="[Verse]\n在黑暗中我找到了自己的路...",
)

if formatted.success:
    # 步骤 2：使用增强后的输入生成
    params = GenerationParams(
        caption=formatted.caption,
        lyrics=formatted.lyrics,
        bpm=formatted.bpm,
        duration=formatted.duration,
        keyscale=formatted.keyscale,
        thinking=True,
        use_cot_metas=False,  # 已格式化，跳过元数据 CoT
    )
    
    config = GenerationConfig(batch_size=2)
    result = generate_music(dit_handler, llm_handler, params, config, save_dir="/output")
```

---

## 最佳实践

### 1. Caption 写作

**好的 Caption**：
```python
# 具体且描述性强
caption="欢快的电子舞曲，重低音和合成器主旋律"

# 包含情绪和风格
caption="忧郁的独立民谣，原声吉他和柔和的人声"

# 指定乐器
caption="爵士三重奏，钢琴、立式贝斯和刷子鼓"
```

**避免**：
```python
# 太模糊
caption="好音乐"

# 矛盾
caption="快慢音乐"  # 节奏冲突
```

### 2. 参数调优

**最佳质量**：
- 使用 base 模型，`inference_steps=64` 或更高
- 启用 `use_adg=True`
- 设置 `guidance_scale=7.0-9.0`
- 设置 `shift=3.0` 以获得更好的时间步分布
- 使用无损音频格式（`audio_format="wav"`）

**追求速度**：
- 使用 turbo 模型，`inference_steps=8`
- 禁用 ADG（`use_adg=False`）
- 使用 `infer_method="ode"`（默认）
- 使用压缩格式（`audio_format="mp3"`）或默认 FLAC

**一致性**：
- 在 config 中设置 `use_random_seed=False`
- 使用固定的 `seeds` 列表或在 params 中使用单个 `seed`
- 保持较低的 `lm_temperature`（0.7-0.85）

**多样性**：
- 在 config 中设置 `use_random_seed=True`
- 增加 `lm_temperature`（0.9-1.1）
- 使用 `batch_size > 1` 获得变体

### 3. 时长指南

- **纯音乐**：30-180 秒效果良好
- **带歌词**：推荐自动检测（设置 `duration=-1` 或保持默认）
- **短片段**：最少 10-20 秒
- **长格式**：最多 600 秒（10 分钟）

### 4. LM 使用

**何时启用 LM（`thinking=True`）**：
- 需要自动元数据检测
- 想要 caption 优化
- 从最少输入生成
- 需要多样化输出

**何时禁用 LM（`thinking=False`）**：
- 已有精确的元数据
- 需要更快的生成
- 想要完全控制参数

### 5. 批处理

```python
# 高效批量生成
config = GenerationConfig(
    batch_size=8,           # 支持的最大值
    allow_lm_batch=True,    # 启用以提速（当 thinking=True 时）
    lm_batch_chunk_size=4,  # 根据 GPU 内存调整
)
```

### 6. 错误处理

```python
result = generate_music(dit_handler, llm_handler, params, config, save_dir="/output")

if not result.success:
    print(f"生成失败：{result.error}")
    print(f"状态：{result.status_message}")
else:
    # 处理成功结果
    for audio in result.audios:
        path = audio['path']
        key = audio['key']
        seed = audio['params']['seed']
        # ... 处理音频文件
```

### 7. 内存管理

对于大批量大小或长时长：
- 监控 GPU 内存使用
- 如果出现 OOM 错误，减少 `batch_size`
- 减少 `lm_batch_chunk_size` 用于 LM 操作
- 考虑在初始化期间使用 `offload_to_cpu=True`

---

## 故障排除

### 常见问题

**问题**：内存不足错误
- **解决方案**：减少 `batch_size`、`inference_steps`，或启用 CPU 卸载

**问题**：结果质量差
- **解决方案**：增加 `inference_steps`，调整 `guidance_scale`，使用 base 模型

**问题**：结果与提示不匹配
- **解决方案**：使 caption 更具体，增加 `guidance_scale`，启用 LM 优化（`thinking=True`）

**问题**：生成缓慢
- **解决方案**：使用 turbo 模型，减少 `inference_steps`，禁用 ADG

**问题**：LM 不生成代码
- **解决方案**：验证 `llm_handler` 已初始化，检查 `thinking=True` 和 `use_cot_metas=True`

**问题**：种子不被尊重
- **解决方案**：在 config 中设置 `use_random_seed=False` 并提供 `seeds` 列表或在 params 中提供 `seed`

**问题**：自定义时间步不工作
- **解决方案**：确保时间步是从 1.0 到 0.0 的浮点数列表，正确排序

---

## 版本历史

- **v1.5.2**：当前版本
  - 添加了 `shift` 参数用于时间步偏移
  - 添加了 `infer_method` 参数用于 ODE/SDE 选择
  - 添加了 `timesteps` 参数用于自定义时间步调度
  - 添加了 `understand_music()` 函数用于音频分析
  - 添加了 `create_sample()` 函数用于简单模式生成
  - 添加了 `format_sample()` 函数用于输入增强
  - 添加了 `UnderstandResult`、`CreateSampleResult`、`FormatSampleResult` 数据类

- **v1.5.1**：上一版本
  - 将 `GenerationConfig` 拆分为 `GenerationParams` 和 `GenerationConfig`
  - 重命名参数以保持一致性（`key_scale` → `keyscale`、`time_signature` → `timesignature`、`audio_duration` → `duration`、`use_llm_thinking` → `thinking`、`audio_code_string` → `audio_codes`）
  - 添加了 `instrumental` 参数
  - 添加了 `use_constrained_decoding` 参数
  - 添加了 CoT 自动填充字段（`cot_*`）
  - 将默认 `audio_format` 更改为 "flac"
  - 将默认 `batch_size` 更改为 2
  - 将默认 `thinking` 更改为 True
  - 简化了 `GenerationResult` 结构，统一 `audios` 列表
  - 在 `extra_outputs` 中添加了统一的 `time_costs`

- **v1.5**：初始版本
  - 引入了 `GenerationConfig` 和 `GenerationResult` 数据类
  - 简化了参数传递
  - 添加了综合文档

---

更多信息，请参阅：
- 主 README：[`../../README.md`](../../README.md)
- REST API 文档：[`API.md`](API.md)
- Gradio 演示指南：[`GRADIO_GUIDE.md`](GRADIO_GUIDE.md)
- 项目仓库：[ACE-Step-1.5](https://github.com/yourusername/ACE-Step-1.5)
