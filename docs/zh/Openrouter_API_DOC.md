# ACE-Step OpenRouter API 文档

> 兼容 OpenAI Chat Completions 格式的 AI 音乐生成接口

**Base URL:** `http://{host}:{port}` (默认 `http://127.0.0.1:8002`)

---

## 目录

- [认证](#认证)
- [接口列表](#接口列表)
  - [POST /v1/chat/completions - 生成音乐](#1-生成音乐)
  - [GET /v1/models - 模型列表](#2-模型列表)
  - [GET /health - 健康检查](#3-健康检查)
- [输入模式](#输入模式)
- [音频输入](#音频输入)
- [流式响应](#流式响应)
- [完整示例](#完整示例)
- [错误码](#错误码)

---

## 认证

如果服务端配置了 API Key（环境变量 `OPENROUTER_API_KEY` 或启动参数 `--api-key`），所有请求需在 Header 中携带：

```
Authorization: Bearer <your-api-key>
```

未配置 API Key 时无需认证。

---

## 接口列表

### 1. 生成音乐

**POST** `/v1/chat/completions`

通过聊天消息生成音乐，返回音频数据和 LM 生成的元信息。

#### 请求参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 否 | 自动 | 模型 ID（从 `/v1/models` 获取） |
| `messages` | array | **是** | - | 聊天消息列表，见 [输入模式](#输入模式) |
| `stream` | boolean | 否 | `false` | 是否启用流式返回，见 [流式响应](#流式响应) |
| `audio_config` | object | 否 | `null` | 音频生成配置，见下方 |
| `temperature` | float | 否 | `0.85` | LM 采样温度 |
| `top_p` | float | 否 | `0.9` | LM nucleus sampling |
| `seed` | int \| string | 否 | `null` | 随机种子。`batch_size > 1` 时可用逗号分隔指定多个，如 `"42,123,456"` |
| `lyrics` | string | 否 | `""` | 直接传入歌词（优先级高于 messages 中解析的歌词），此时 messages 文本作为 prompt |
| `sample_mode` | boolean | 否 | `false` | 启用 LLM sample 模式，messages 文本作为 sample_query 由 LLM 自动生成 prompt/lyrics |
| `thinking` | boolean | 否 | `false` | 是否启用 LLM thinking 模式（更深度推理） |
| `use_format` | boolean | 否 | `false` | 当用户提供 prompt/lyrics 时，是否先通过 LLM 格式化增强 |
| `use_cot_caption` | boolean | 否 | `true` | 是否通过 CoT 改写/增强音乐描述 |
| `use_cot_language` | boolean | 否 | `true` | 是否通过 CoT 自动检测歌词语言 |
| `guidance_scale` | float | 否 | `7.0` | Classifier-free guidance scale |
| `batch_size` | int | 否 | `1` | 生成音频数量 |
| `task_type` | string | 否 | `"text2music"` | 任务类型，见 [音频输入](#音频输入) |
| `repainting_start` | float | 否 | `0.0` | repaint 区域起始位置（秒） |
| `repainting_end` | float | 否 | `null` | repaint 区域结束位置（秒） |
| `audio_cover_strength` | float | 否 | `1.0` | cover 强度 (0.0~1.0) |

#### audio_config 对象

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `duration` | float | `null` | 音频时长（秒），不传由 LM 自动决定 |
| `bpm` | integer | `null` | 每分钟节拍数，不传由 LM 自动决定 |
| `vocal_language` | string | `"en"` | 歌词语言代码（如 `"zh"`, `"en"`, `"ja"`） |
| `instrumental` | boolean | `null` | 是否为纯器乐（无人声）。不传时根据歌词自动判断 |
| `format` | string | `"mp3"` | 输出音频格式 |
| `key_scale` | string | `null` | 调号（如 `"C major"`） |
| `time_signature` | string | `null` | 拍号（如 `"4/4"`） |

> **messages 文本含义取决于模式：**
> - 设置了 `lyrics` → messages 文本 = caption
> - 设置了 `sample_mode: true` → messages 文本 = sample_query（交给 LLM 生成一切）
> - 均未设置 → 自动检测：有标签走标签模式，像歌词走歌词模式，否则作为 caption 直接传入生成

#### messages 格式

支持纯文本和多模态（文本 + 音频）两种格式：

**纯文本：**

```json
{
  "messages": [
    {"role": "user", "content": "你的输入内容"}
  ]
}
```

**多模态（含音频输入）：**

```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "翻唱这首歌"},
        {
          "type": "input_audio",
          "input_audio": {
            "data": "<base64 音频数据>",
            "format": "mp3"
          }
        }
      ]
    }
  ]
}
```

---

#### 非流式响应 (`stream: false`)

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

**响应字段说明：**

| 字段 | 说明 |
|---|---|
| `choices[0].message.content` | LM 生成的文本信息，包含 Metadata（Caption/BPM/Duration/Key/Time Signature/Language）和 Lyrics。如果 LM 未参与，返回 `"Music generated successfully."` |
| `choices[0].message.audio` | 音频数据数组，每项包含 `type` (`"audio_url"`) 和 `audio_url.url`（Base64 Data URL，格式 `data:audio/mpeg;base64,...`） |
| `choices[0].finish_reason` | `"stop"` 表示正常完成 |

**音频解码格式：**

`audio_url.url` 值为 Data URL 格式：`data:audio/mpeg;base64,<base64_data>`

客户端提取 base64 数据部分后解码即可得到 MP3 文件：

```python
import base64

url = response["choices"][0]["message"]["audio"][0]["audio_url"]["url"]
# 去掉 "data:audio/mpeg;base64," 前缀
b64_data = url.split(",", 1)[1]
audio_bytes = base64.b64decode(b64_data)

with open("output.mp3", "wb") as f:
    f.write(audio_bytes)
```

```javascript
const url = response.choices[0].message.audio[0].audio_url.url;
const b64Data = url.split(",")[1];
const audioBytes = atob(b64Data);
// 或直接用于 <audio> 标签
const audio = new Audio(url);
audio.play();
```

---

### 2. 模型列表

**GET** `/v1/models`

返回可用模型信息。

#### 响应

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

### 3. 健康检查

**GET** `/health`

#### 响应

```json
{
  "status": "ok",
  "service": "ACE-Step OpenRouter API",
  "version": "1.0"
}
```

---

## 输入模式

系统根据 `messages` 中最后一条 `user` 消息的内容自动选择输入模式。也可通过 `lyrics` 或 `sample_mode` 字段显式指定。

### 模式 1: 标签模式（推荐）

使用 `<prompt>` 和 `<lyrics>` 标签明确指定音乐描述和歌词：

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

- `<prompt>...</prompt>` — 音乐风格/场景描述（即 caption）
- `<lyrics>...</lyrics>` — 歌词内容
- 两个标签可以只传其中一个
- 当 `use_format: true` 时，LLM 会自动增强 prompt 和 lyrics

### 模式 2: 自然语言模式（Sample 模式）

直接用自然语言描述想要的音乐，系统自动通过 LLM 生成 prompt 和 lyrics：

```json
{
  "messages": [
    {"role": "user", "content": "帮我生成一首欢快的中文流行歌曲，关于夏天和旅行"}
  ],
  "sample_mode": true,
  "audio_config": {
    "vocal_language": "zh"
  }
}
```

触发条件：`sample_mode: true`，或消息内容不包含标签且不像歌词时自动触发。

### 模式 3: 纯歌词模式

直接传入带结构标记的歌词，系统自动识别：

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

触发条件：消息内容包含 `[Verse]`、`[Chorus]` 等标记，或有多行短文本结构。

### 模式 4: 歌词 + Prompt 分离

通过 `lyrics` 字段直接传入歌词，messages 文本自动作为 prompt：

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

### 器乐模式

设置 `audio_config.instrumental: true`：

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

## 音频输入

支持通过多模态 messages 传入音频文件（base64 编码），用于 cover、repaint 等任务。

### task_type 类型

| task_type | 说明 | 需要音频输入 |
|---|---|---|
| `text2music` | 文本生成音乐（默认） | 可选（作为 reference） |
| `cover` | 翻唱/风格迁移 | 需要 src_audio |
| `repaint` | 局部重绘 | 需要 src_audio |
| `lego` | 音频拼接 | 需要 src_audio |
| `extract` | 音频提取 | 需要 src_audio |
| `complete` | 音频续写 | 需要 src_audio |

### 音频路由规则

多个 `input_audio` 块按顺序路由到不同参数（类似多图片上传）：

| task_type | audio[0] | audio[1] |
|---|---|---|
| `text2music` | reference_audio（风格参考） | - |
| `cover/repaint/lego/extract/complete` | src_audio（待编辑音频） | reference_audio（可选风格参考） |

### 音频输入示例

**Cover 任务（翻唱）：**

```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "<prompt>Jazz style cover with saxophone</prompt>"},
        {
          "type": "input_audio",
          "input_audio": {"data": "<base64 原始音频>", "format": "mp3"}
        }
      ]
    }
  ],
  "task_type": "cover",
  "audio_cover_strength": 0.8,
  "audio_config": {"duration": 30}
}
```

**Repaint 任务（局部重绘）：**

```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "<prompt>Replace with guitar solo</prompt>"},
        {
          "type": "input_audio",
          "input_audio": {"data": "<base64 原始音频>", "format": "mp3"}
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

## 流式响应

设置 `"stream": true` 启用 SSE（Server-Sent Events）流式返回。

### 事件格式

每个事件以 `data: ` 开头，后跟 JSON，以双换行 `\n\n` 结尾：

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{...},"finish_reason":null}]}

```

### 流式事件顺序

| 阶段 | delta 内容 | 说明 |
|---|---|---|
| 1. 初始化 | `{"role":"assistant","content":""}` | 建立连接 |
| 2. LM 内容 | `{"content":"\n\n## Metadata\n..."}` | LM 参与时推送 metadata 和 lyrics |
| 3. 心跳 | `{"content":"."}` | 音频生成期间每 2 秒发送，保持连接 |
| 4. 音频数据 | `{"audio":[{"type":"audio_url","audio_url":{"url":"data:..."}}]}` | 音频 base64 |
| 5. 结束 | `finish_reason: "stop"` | 生成完成 |
| 6. 终止 | `data: [DONE]` | 流结束标记 |

### 流式响应示例

```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{"content":"\n\n## Metadata\n**Caption:** Upbeat pop\n**BPM:** 120"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{"content":"."},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{"audio":[{"type":"audio_url","audio_url":{"url":"data:audio/mpeg;base64,..."}}]},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]

```

### 客户端处理流式响应

```python
import json
import httpx

with httpx.stream("POST", "http://127.0.0.1:8002/v1/chat/completions", json={
    "messages": [{"role": "user", "content": "生成一首轻快的吉他曲"}],
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
    messages: [{ role: "user", content: "生成一首轻快的吉他曲" }],
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

// audioUrl 可直接用于 <audio src="...">
```

---

## 完整示例

### 示例 1: 自然语言生成（最简用法）

```bash
curl -X POST http://127.0.0.1:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "一首温柔的中文民谣，关于故乡和回忆"}
    ],
    "sample_mode": true,
    "audio_config": {"vocal_language": "zh"}
  }'
```

### 示例 2: 标签模式 + 指定参数

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

### 示例 3: 纯器乐 + 关闭 LM 增强

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

### 示例 4: 流式请求

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

### 示例 5: 多种子批量生成

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

## 错误码

| HTTP 状态码 | 说明 |
|---|---|
| 400 | 请求格式错误或缺少有效输入 |
| 401 | API Key 缺失或无效 |
| 429 | 服务繁忙，队列已满 |
| 500 | 音乐生成过程中发生内部错误 |
| 503 | 模型尚未初始化完成 |
| 504 | 生成超时 |

错误响应格式：

```json
{
  "detail": "错误描述信息"
}
```

---

## 环境变量配置

以下环境变量可用于配置服务端（供运维参考）：

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `OPENROUTER_API_KEY` | 无 | API 认证密钥 |
| `OPENROUTER_HOST` | `127.0.0.1` | 监听地址 |
| `OPENROUTER_PORT` | `8002` | 监听端口 |
| `ACESTEP_CONFIG_PATH` | `acestep-v15-turbo` | DiT 模型配置路径 |
| `ACESTEP_DEVICE` | `auto` | 推理设备 |
| `ACESTEP_LM_MODEL_PATH` | `acestep-5Hz-lm-0.6B` | LLM 模型路径 |
| `ACESTEP_LM_BACKEND` | `vllm` | LLM 推理后端 |
| `ACESTEP_QUEUE_MAXSIZE` | `200` | 任务队列最大容量 |
| `ACESTEP_GENERATION_TIMEOUT` | `600` | 非流式请求超时（秒） |
