# ACE-Step API 客户端文档

**Language / 语言 / 言語:** [English](../en/API.md) | [中文](API.md) | [日本語](../ja/API.md)

---

本服务提供基于 HTTP 的异步音乐生成 API。

**基本工作流程**：
1. 调用 `POST /release_task` 提交任务并获取 `task_id`。
2. 调用 `POST /query_result` 批量查询任务状态，直到 `status` 为 `1`（成功）或 `2`（失败）。
3. 通过结果中返回的 `GET /v1/audio?path=...` URL 下载音频文件。

---

## 目录

- [认证](#1-认证)
- [响应格式](#2-响应格式)
- [任务状态说明](#3-任务状态说明)
- [创建生成任务](#4-创建生成任务)
- [批量查询任务结果](#5-批量查询任务结果)
- [格式化输入](#6-格式化输入)
- [获取随机样本](#7-获取随机样本)
- [列出可用模型](#8-列出可用模型)
- [服务器统计](#9-服务器统计)
- [下载音频文件](#10-下载音频文件)
- [健康检查](#11-健康检查)
- [环境变量](#12-环境变量)

---

## 1. 认证

API 支持可选的 API Key 认证。启用后，必须在请求中提供有效的密钥。

### 认证方式

支持两种认证方式：

**方式 A：请求体中的 ai_token**

```json
{
  "ai_token": "your-api-key",
  "prompt": "欢快的流行歌曲",
  ...
}
```

**方式 B：Authorization 头**

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Authorization: Bearer your-api-key' \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "欢快的流行歌曲"}'
```

### 配置 API Key

通过环境变量或命令行参数设置：

```bash
# 环境变量
export ACESTEP_API_KEY=your-secret-key

# 或命令行参数
python -m acestep.api_server --api-key your-secret-key
```

---

## 2. 响应格式

所有 API 响应使用统一的包装格式：

```json
{
  "data": { ... },
  "code": 200,
  "error": null,
  "timestamp": 1700000000000,
  "extra": null
}
```

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `data` | any | 实际响应数据 |
| `code` | int | 状态码（200=成功）|
| `error` | string | 错误信息（成功时为 null）|
| `timestamp` | int | 响应时间戳（毫秒）|
| `extra` | any | 额外信息（通常为 null）|

---

## 3. 任务状态说明

任务状态（`status`）使用整数表示：

| 状态码 | 状态名 | 说明 |
| :--- | :--- | :--- |
| `0` | queued/running | 任务排队中或执行中 |
| `1` | succeeded | 生成成功，结果已就绪 |
| `2` | failed | 生成失败 |

---

## 4. 创建生成任务

### 4.1 API 定义

- **URL**：`/release_task`
- **方法**：`POST`
- **Content-Type**：`application/json`、`multipart/form-data` 或 `application/x-www-form-urlencoded`

### 4.2 请求参数

#### 参数命名约定

API 支持大多数参数的 **snake_case** 和 **camelCase** 命名。例如：
- `audio_duration` / `duration` / `audioDuration`
- `key_scale` / `keyscale` / `keyScale`
- `time_signature` / `timesignature` / `timeSignature`
- `sample_query` / `sampleQuery` / `description` / `desc`
- `use_format` / `useFormat` / `format`

此外，元数据可以通过嵌套对象传递（`metas`、`metadata` 或 `user_metadata`）。

#### 方法 A：JSON 请求（application/json）

适用于仅传递文本参数，或引用服务器上已存在的音频文件路径。

**基本参数**：

| 参数名 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `prompt` | string | `""` | 音乐描述提示词（别名：`caption`）|
| `lyrics` | string | `""` | 歌词内容 |
| `thinking` | bool | `false` | 是否使用 5Hz LM 生成音频代码（lm-dit 行为）|
| `vocal_language` | string | `"en"` | 歌词语言（en、zh、ja 等）|
| `audio_format` | string | `"mp3"` | 输出格式（mp3、wav、flac）|

**样本/描述模式参数**：

| 参数名 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `sample_mode` | bool | `false` | 启用随机样本生成模式（通过 LM 自动生成 caption/lyrics/metas）|
| `sample_query` | string | `""` | 用于样本生成的自然语言描述（例如"一首柔和的孟加拉情歌"）。别名：`description`、`desc` |
| `use_format` | bool | `false` | 使用 LM 增强/格式化提供的 caption 和 lyrics。别名：`format` |

**多模型支持**：

| 参数名 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `model` | string | null | 选择使用哪个 DiT 模型（例如 `"acestep-v15-turbo"`、`"acestep-v15-turbo-shift3"`）。使用 `/v1/models` 列出可用模型。如果未指定，使用默认模型。|

**thinking 语义（重要）**：

- `thinking=false`：
  - 服务器**不会**使用 5Hz LM 生成 `audio_code_string`。
  - DiT 以 **text2music** 模式运行，**忽略**任何提供的 `audio_code_string`。
- `thinking=true`：
  - 服务器将使用 5Hz LM 生成 `audio_code_string`（lm-dit 行为）。
  - DiT 使用 LM 生成的代码运行，以增强音乐质量。

**元数据自动补全（条件性）**：

当 `use_cot_caption=true` 或 `use_cot_language=true` 或元数据字段缺失时，服务器可能会调用 5Hz LM 根据 `caption`/`lyrics` 填充缺失的字段：

- `bpm`
- `key_scale`
- `time_signature`
- `audio_duration`

用户提供的值始终优先；LM 只填充空/缺失的字段。

**音乐属性参数**：

| 参数名 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `bpm` | int | null | 指定节奏（BPM），范围 30-300 |
| `key_scale` | string | `""` | 调性（例如"C Major"、"Am"）。别名：`keyscale`、`keyScale` |
| `time_signature` | string | `""` | 拍号（2、3、4、6 分别表示 2/4、3/4、4/4、6/8）。别名：`timesignature`、`timeSignature` |
| `audio_duration` | float | null | 生成时长（秒），范围 10-600。别名：`duration`、`target_duration` |

**音频代码（可选）**：

| 参数名 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `audio_code_string` | string 或 string[] | `""` | 用于 `llm_dit` 的音频语义令牌（5Hz）。别名：`audioCodeString` |

**生成控制参数**：

| 参数名 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `inference_steps` | int | `8` | 推理步数。Turbo 模型：1-20（推荐 8）。Base 模型：1-200（推荐 32-64）|
| `guidance_scale` | float | `7.0` | 提示引导系数。仅对 base 模型有效 |
| `use_random_seed` | bool | `true` | 是否使用随机种子 |
| `seed` | int | `-1` | 指定种子（当 use_random_seed=false 时）|
| `batch_size` | int | `2` | 批量生成数量（最多 8）|

**高级 DiT 参数**：

| 参数名 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `shift` | float | `3.0` | 时间步偏移因子（范围 1.0-5.0）。仅对 base 模型有效，对 turbo 模型无效 |
| `infer_method` | string | `"ode"` | 扩散推理方法：`"ode"`（Euler，更快）或 `"sde"`（随机）|
| `timesteps` | string | null | 自定义时间步，逗号分隔值（例如 `"0.97,0.76,0.615,0.5,0.395,0.28,0.18,0.085,0"`）。覆盖 `inference_steps` 和 `shift` |
| `use_adg` | bool | `false` | 使用自适应双引导（仅 base 模型）|
| `cfg_interval_start` | float | `0.0` | CFG 应用起始比例（0.0-1.0）|
| `cfg_interval_end` | float | `1.0` | CFG 应用结束比例（0.0-1.0）|

**5Hz LM 参数（可选，服务器端）**：

这些参数控制 5Hz LM 采样，用于元数据自动补全和（当 `thinking=true` 时）代码生成。

| 参数名 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `lm_model_path` | string | null | 5Hz LM 检查点目录名（例如 `acestep-5Hz-lm-0.6B`）|
| `lm_backend` | string | `"vllm"` | `vllm` 或 `pt` |
| `lm_temperature` | float | `0.85` | 采样温度 |
| `lm_cfg_scale` | float | `2.5` | CFG 比例（>1 启用 CFG）|
| `lm_negative_prompt` | string | `"NO USER INPUT"` | CFG 使用的负面提示 |
| `lm_top_k` | int | null | Top-k（0/null 禁用）|
| `lm_top_p` | float | `0.9` | Top-p（>=1 将被视为禁用）|
| `lm_repetition_penalty` | float | `1.0` | 重复惩罚 |

**LM CoT（思维链）参数**：

| 参数名 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `use_cot_caption` | bool | `true` | 让 LM 通过 CoT 推理重写/增强输入 caption。别名：`cot_caption`、`cot-caption` |
| `use_cot_language` | bool | `true` | 让 LM 通过 CoT 检测人声语言。别名：`cot_language`、`cot-language` |
| `constrained_decoding` | bool | `true` | 启用基于 FSM 的约束解码以获得结构化 LM 输出。别名：`constrainedDecoding`、`constrained` |
| `constrained_decoding_debug` | bool | `false` | 启用约束解码的调试日志 |
| `allow_lm_batch` | bool | `true` | 允许 LM 批量处理以提高效率 |

**编辑/参考音频参数**（需要服务器上的绝对路径）：

| 参数名 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `reference_audio_path` | string | null | 参考音频路径（风格迁移）|
| `src_audio_path` | string | null | 源音频路径（重绘/翻唱）|
| `task_type` | string | `"text2music"` | 任务类型：`text2music`、`cover`、`repaint`、`lego`、`extract`、`complete` |
| `instruction` | string | auto | 编辑指令（如未提供则根据 task_type 自动生成）|
| `repainting_start` | float | `0.0` | 重绘开始时间（秒）|
| `repainting_end` | float | null | 重绘结束时间（秒），-1 表示音频末尾 |
| `audio_cover_strength` | float | `1.0` | 翻唱强度（0.0-1.0）。风格迁移使用较小值（0.2）|

#### 方法 B：文件上传（multipart/form-data）

当需要上传本地音频文件作为参考或源音频时使用。

除了支持上述所有字段作为表单字段外，还支持以下文件字段：

- `reference_audio` 或 `ref_audio`：（文件）上传参考音频文件
- `src_audio` 或 `ctx_audio`：（文件）上传源音频文件

> **注意**：上传文件后，相应的 `_path` 参数将被自动忽略，系统将使用上传后的临时文件路径。

### 4.3 响应示例

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

### 4.4 使用示例（cURL）

**基本 JSON 方法**：

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "欢快的流行歌曲",
    "lyrics": "你好世界",
    "inference_steps": 8
  }'
```

**使用 thinking=true（LM 生成代码 + 填充缺失元数据）**：

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "欢快的流行歌曲",
    "lyrics": "你好世界",
    "thinking": true,
    "lm_temperature": 0.85,
    "lm_cfg_scale": 2.5
  }'
```

**描述驱动生成（sample_query）**：

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "sample_query": "一首适合安静夜晚的柔和孟加拉情歌",
    "thinking": true
  }'
```

**使用格式增强（use_format=true）**：

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "流行摇滚",
    "lyrics": "[Verse 1]\n走在街上...",
    "use_format": true,
    "thinking": true
  }'
```

**选择特定模型**：

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "电子舞曲",
    "model": "acestep-v15-turbo",
    "thinking": true
  }'
```

**使用自定义时间步**：

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "爵士钢琴三重奏",
    "timesteps": "0.97,0.76,0.615,0.5,0.395,0.28,0.18,0.085,0",
    "thinking": true
  }'
```

**文件上传方法**：

```bash
curl -X POST http://localhost:8001/release_task \
  -F "prompt=重新混音这首歌" \
  -F "src_audio=@/path/to/local/song.mp3" \
  -F "task_type=repaint"
```

---

## 5. 批量查询任务结果

### 5.1 API 定义

- **URL**：`/query_result`
- **方法**：`POST`
- **Content-Type**：`application/json` 或 `application/x-www-form-urlencoded`

### 5.2 请求参数

| 参数名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `task_id_list` | string (JSON array) 或 array | 要查询的任务 ID 列表 |

### 5.3 响应示例

```json
{
  "data": [
    {
      "task_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": 1,
      "result": "[{\"file\": \"/v1/audio?path=...\", \"wave\": \"\", \"status\": 1, \"create_time\": 1700000000, \"env\": \"development\", \"prompt\": \"欢快的流行歌曲\", \"lyrics\": \"你好世界\", \"metas\": {\"bpm\": 120, \"duration\": 30, \"genres\": \"\", \"keyscale\": \"C Major\", \"timesignature\": \"4\"}, \"generation_info\": \"...\", \"seed_value\": \"12345,67890\", \"lm_model\": \"acestep-5Hz-lm-0.6B\", \"dit_model\": \"acestep-v15-turbo\"}]"
    }
  ],
  "code": 200,
  "error": null,
  "timestamp": 1700000000000,
  "extra": null
}
```

**结果字段说明**（result 为 JSON 字符串，解析后包含）：

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `file` | string | 音频文件 URL（配合 `/v1/audio` 端点使用）|
| `wave` | string | 波形数据（通常为空）|
| `status` | int | 状态码（0=进行中，1=成功，2=失败）|
| `create_time` | int | 创建时间（Unix 时间戳）|
| `env` | string | 环境标识 |
| `prompt` | string | 使用的提示词 |
| `lyrics` | string | 使用的歌词 |
| `metas` | object | 元数据（bpm、duration、genres、keyscale、timesignature）|
| `generation_info` | string | 生成信息摘要 |
| `seed_value` | string | 使用的种子值（逗号分隔）|
| `lm_model` | string | 使用的 LM 模型名称 |
| `dit_model` | string | 使用的 DiT 模型名称 |

### 5.4 使用示例

```bash
curl -X POST http://localhost:8001/query_result \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id_list": ["550e8400-e29b-41d4-a716-446655440000"]
  }'
```

---

## 6. 格式化输入

### 6.1 API 定义

- **URL**：`/format_input`
- **方法**：`POST`

此端点使用 LLM 增强和格式化用户提供的 caption 和 lyrics。

### 6.2 请求参数

| 参数名 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `prompt` | string | `""` | 音乐描述提示词 |
| `lyrics` | string | `""` | 歌词内容 |
| `temperature` | float | `0.85` | LM 采样温度 |
| `param_obj` | string (JSON) | `"{}"` | 包含元数据的 JSON 对象（duration、bpm、key、time_signature、language）|

### 6.3 响应示例

```json
{
  "data": {
    "caption": "增强后的音乐描述",
    "lyrics": "格式化后的歌词...",
    "bpm": 120,
    "key_scale": "C Major",
    "time_signature": "4",
    "duration": 180,
    "vocal_language": "zh"
  },
  "code": 200,
  "error": null,
  "timestamp": 1700000000000,
  "extra": null
}
```

### 6.4 使用示例

```bash
curl -X POST http://localhost:8001/format_input \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "流行摇滚",
    "lyrics": "在街上漫步",
    "param_obj": "{\"duration\": 180, \"language\": \"zh\"}"
  }'
```

---

## 7. 获取随机样本

### 7.1 API 定义

- **URL**：`/create_random_sample`
- **方法**：`POST`

此端点从预加载的示例数据中返回随机样本参数，用于表单填充。

### 7.2 请求参数

| 参数名 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `sample_type` | string | `"simple_mode"` | 样本类型：`"simple_mode"` 或 `"custom_mode"` |

### 7.3 响应示例

```json
{
  "data": {
    "caption": "轻快的流行歌曲，带有吉他伴奏",
    "lyrics": "[Verse 1]\n阳光洒在脸上...",
    "bpm": 120,
    "key_scale": "G Major",
    "time_signature": "4",
    "duration": 180,
    "vocal_language": "zh"
  },
  "code": 200,
  "error": null,
  "timestamp": 1700000000000,
  "extra": null
}
```

### 7.4 使用示例

```bash
curl -X POST http://localhost:8001/create_random_sample \
  -H 'Content-Type: application/json' \
  -d '{"sample_type": "simple_mode"}'
```

---

## 8. 列出可用模型

### 8.1 API 定义

- **URL**：`/v1/models`
- **方法**：`GET`

返回服务器上加载的可用 DiT 模型列表。

### 8.2 响应示例

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

### 8.3 使用示例

```bash
curl http://localhost:8001/v1/models
```

---

## 9. 服务器统计

### 9.1 API 定义

- **URL**：`/v1/stats`
- **方法**：`GET`

返回服务器运行统计信息。

### 9.2 响应示例

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

### 9.3 使用示例

```bash
curl http://localhost:8001/v1/stats
```

---

## 10. 下载音频文件

### 10.1 API 定义

- **URL**：`/v1/audio`
- **方法**：`GET`

通过路径下载生成的音频文件。

### 10.2 请求参数

| 参数名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `path` | string | URL 编码的音频文件路径 |

### 10.3 使用示例

```bash
# 使用任务结果中的 URL 下载
curl "http://localhost:8001/v1/audio?path=%2Ftmp%2Fapi_audio%2Fabc123.mp3" -o output.mp3
```

---

## 11. 健康检查

### 11.1 API 定义

- **URL**：`/health`
- **方法**：`GET`

返回服务健康状态。

### 11.2 响应示例

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

## 12. 环境变量

API 服务器可以通过环境变量进行配置：

### 服务器配置

| 变量 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `ACESTEP_API_HOST` | `127.0.0.1` | 服务器绑定主机 |
| `ACESTEP_API_PORT` | `8001` | 服务器绑定端口 |
| `ACESTEP_API_KEY` | （空）| API 认证密钥（空则禁用认证）|
| `ACESTEP_API_WORKERS` | `1` | API 工作线程数 |

### 模型配置

| 变量 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `ACESTEP_CONFIG_PATH` | `acestep-v15-turbo` | 主 DiT 模型路径 |
| `ACESTEP_CONFIG_PATH2` | （空）| 辅助 DiT 模型路径（可选）|
| `ACESTEP_CONFIG_PATH3` | （空）| 第三个 DiT 模型路径（可选）|
| `ACESTEP_DEVICE` | `auto` | 模型加载设备 |
| `ACESTEP_USE_FLASH_ATTENTION` | `true` | 启用 flash attention |
| `ACESTEP_OFFLOAD_TO_CPU` | `false` | 空闲时将模型卸载到 CPU |
| `ACESTEP_OFFLOAD_DIT_TO_CPU` | `false` | 专门将 DiT 卸载到 CPU |

### LM 配置

| 变量 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `ACESTEP_INIT_LLM` | auto | 是否在启动时初始化 LM（auto 根据 GPU 自动决定）|
| `ACESTEP_LM_MODEL_PATH` | `acestep-5Hz-lm-0.6B` | 默认 5Hz LM 模型 |
| `ACESTEP_LM_BACKEND` | `vllm` | LM 后端（vllm 或 pt）|
| `ACESTEP_LM_DEVICE` | （与 ACESTEP_DEVICE 相同）| LM 设备 |
| `ACESTEP_LM_OFFLOAD_TO_CPU` | `false` | 将 LM 卸载到 CPU |

### 队列配置

| 变量 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `ACESTEP_QUEUE_MAXSIZE` | `200` | 最大队列大小 |
| `ACESTEP_QUEUE_WORKERS` | `1` | 队列工作者数量 |
| `ACESTEP_AVG_JOB_SECONDS` | `5.0` | 初始平均任务持续时间估算 |
| `ACESTEP_AVG_WINDOW` | `50` | 平均任务时间计算窗口 |

### 缓存配置

| 变量 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `ACESTEP_TMPDIR` | `.cache/acestep/tmp` | 临时文件目录 |
| `TRITON_CACHE_DIR` | `.cache/acestep/triton` | Triton 缓存目录 |
| `TORCHINDUCTOR_CACHE_DIR` | `.cache/acestep/torchinductor` | TorchInductor 缓存目录 |

---

## 错误处理

**HTTP 状态码**：

- `200`：成功
- `400`：无效请求（错误的 JSON、缺少字段）
- `401`：未授权（缺少或无效的 API Key）
- `404`：资源未找到
- `415`：不支持的 Content-Type
- `429`：服务器繁忙（队列已满）
- `500`：内部服务器错误

**错误响应格式**：

```json
{
  "detail": "描述问题的错误消息"
}
```

---

## 最佳实践

1. **使用 `thinking=true`** 以获得 LM 增强生成的最佳质量结果。

2. **使用 `sample_query`/`description`** 从自然语言描述快速生成。

3. **使用 `use_format=true`** 当你有 caption/lyrics 但希望 LM 增强它们时。

4. **批量查询任务状态** 使用 `/query_result` 端点一次查询多个任务。

5. **检查 `/v1/stats`** 响应来了解服务器负载和平均任务时间。

6. **使用多模型支持** 通过设置 `ACESTEP_CONFIG_PATH2` 和 `ACESTEP_CONFIG_PATH3` 环境变量，然后通过 `model` 参数选择。

7. **生产环境** 中，设置 `ACESTEP_API_KEY` 以启用认证，保护 API 安全。

8. **低显存环境** 中，启用 `ACESTEP_OFFLOAD_TO_CPU=true` 以支持更长的音频生成。
