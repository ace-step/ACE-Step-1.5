# ACE-Step OpenRouter API ドキュメント

> OpenAI Chat Completions 互換の AI 音楽生成 API

**ベース URL:** `http://{host}:{port}`（デフォルト `http://127.0.0.1:8002`）

---

## 目次

- [認証](#認証)
- [エンドポイント一覧](#エンドポイント一覧)
  - [POST /v1/chat/completions - 音楽生成](#1-音楽生成)
  - [GET /v1/models - モデル一覧](#2-モデル一覧)
  - [GET /health - ヘルスチェック](#3-ヘルスチェック)
- [入力モード](#入力モード)
- [オーディオ入力](#オーディオ入力)
- [ストリーミングレスポンス](#ストリーミングレスポンス)
- [リクエスト例](#リクエスト例)
- [エラーコード](#エラーコード)

---

## 認証

サーバーに API キーが設定されている場合（環境変数 `OPENROUTER_API_KEY` または起動パラメータ `--api-key`）、すべてのリクエストに以下のヘッダーが必要です：

```
Authorization: Bearer <your-api-key>
```

API キーが未設定の場合、認証は不要です。

---

## エンドポイント一覧

### 1. 音楽生成

**POST** `/v1/chat/completions`

チャットメッセージから音楽を生成し、オーディオデータと LM が生成したメタ情報を返します。

#### リクエストパラメータ

| フィールド | 型 | 必須 | デフォルト | 説明 |
|---|---|---|---|---|
| `model` | string | いいえ | 自動 | モデル ID（`/v1/models` から取得） |
| `messages` | array | **はい** | - | チャットメッセージリスト。[入力モード](#入力モード)を参照 |
| `stream` | boolean | いいえ | `false` | ストリーミングレスポンスを有効にする。[ストリーミングレスポンス](#ストリーミングレスポンス)を参照 |
| `audio_config` | object | いいえ | `null` | オーディオ生成設定。下記参照 |
| `temperature` | float | いいえ | `0.85` | LM サンプリング温度 |
| `top_p` | float | いいえ | `0.9` | LM nucleus sampling パラメータ |
| `seed` | int \| string | いいえ | `null` | ランダムシード。`batch_size > 1` の場合、カンマ区切りで複数指定可能（例: `"42,123,456"`） |
| `lyrics` | string | いいえ | `""` | 歌詞を直接指定（messages から解析された歌詞より優先）。設定時、messages テキストは prompt として扱われる |
| `sample_mode` | boolean | いいえ | `false` | LLM sample モードを有効化。messages テキストが sample_query として LLM に渡され、prompt/lyrics が自動生成される |
| `thinking` | boolean | いいえ | `false` | LLM の thinking モード（深い推論）を有効にする |
| `use_format` | boolean | いいえ | `false` | ユーザーが prompt/lyrics を提供した場合、LLM でフォーマット・強化する |
| `use_cot_caption` | boolean | いいえ | `true` | CoT で音楽説明文を書き換え・強化する |
| `use_cot_language` | boolean | いいえ | `true` | CoT でボーカル言語を自動検出する |
| `guidance_scale` | float | いいえ | `7.0` | Classifier-free guidance scale |
| `batch_size` | int | いいえ | `1` | 生成するオーディオの数 |
| `task_type` | string | いいえ | `"text2music"` | タスクタイプ。[オーディオ入力](#オーディオ入力)を参照 |
| `repainting_start` | float | いいえ | `0.0` | repaint 領域の開始位置（秒） |
| `repainting_end` | float | いいえ | `null` | repaint 領域の終了位置（秒） |
| `audio_cover_strength` | float | いいえ | `1.0` | カバー強度（0.0〜1.0） |

#### audio_config オブジェクト

| フィールド | 型 | デフォルト | 説明 |
|---|---|---|---|
| `duration` | float | `null` | オーディオの長さ（秒）。省略時は LM が自動決定 |
| `bpm` | integer | `null` | テンポ（BPM）。省略時は LM が自動決定 |
| `vocal_language` | string | `"en"` | ボーカル言語コード（例: `"zh"`, `"en"`, `"ja"`） |
| `instrumental` | boolean | `null` | インストゥルメンタル（ボーカルなし）かどうか。省略時は歌詞に基づき自動判定 |
| `format` | string | `"mp3"` | 出力オーディオフォーマット |
| `key_scale` | string | `null` | 調号（例: `"C major"`） |
| `time_signature` | string | `null` | 拍子（例: `"4/4"`） |

> **messages テキストの意味はモードにより異なります：**
> - `lyrics` を設定 → messages テキスト = caption
> - `sample_mode: true` を設定 → messages テキスト = sample_query（LLM にすべて生成させる）
> - どちらも未設定 → 自動検出：タグがあればタグモード、歌詞らしければ歌詞モード、それ以外は caption としてそのまま生成に使用

#### messages フォーマット

プレーンテキストとマルチモーダル（テキスト＋オーディオ）の2つの形式をサポート：

**プレーンテキスト：**

```json
{
  "messages": [
    {"role": "user", "content": "入力内容"}
  ]
}
```

**マルチモーダル（オーディオ入力あり）：**

```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "この曲をカバーして"},
        {
          "type": "input_audio",
          "input_audio": {
            "data": "<base64 オーディオデータ>",
            "format": "mp3"
          }
        }
      ]
    }
  ]
}
```

---

#### 非ストリーミングレスポンス (`stream: false`)

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

**レスポンスフィールド説明：**

| フィールド | 説�� |
|---|---|
| `choices[0].message.content` | LM が生成したテキスト情報。Metadata（Caption/BPM/Duration/Key/Time Signature/Language）と Lyrics を含む。LM が関与していない場合は `"Music generated successfully."` を返す |
| `choices[0].message.audio` | オーディオデータ配列。各項目に `type`（`"audio_url"`）と `audio_url.url`（Base64 Data URL、形式: `data:audio/mpeg;base64,...`）を含む |
| `choices[0].finish_reason` | `"stop"` は正常完了を示す |

**オーディオのデコード方法：**

`audio_url.url` の値は Data URL 形式です: `data:audio/mpeg;base64,<base64_data>`

カンマ以降の base64 データ部分を抽出してデコードすると MP3 ファイルが得られます：

```python
import base64

url = response["choices"][0]["message"]["audio"][0]["audio_url"]["url"]
# "data:audio/mpeg;base64," プレフィックスを除去
b64_data = url.split(",", 1)[1]
audio_bytes = base64.b64decode(b64_data)

with open("output.mp3", "wb") as f:
    f.write(audio_bytes)
```

```javascript
const url = response.choices[0].message.audio[0].audio_url.url;
const b64Data = url.split(",")[1];
const audioBytes = atob(b64Data);
// Data URL を直接 <audio> タグで使用可能
const audio = new Audio(url);
audio.play();
```

---

### 2. モデル一覧

**GET** `/v1/models`

利用可能なモデル情報を返します。

#### レスポンス

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

### 3. ヘルスチェック

**GET** `/health`

#### レスポンス

```json
{
  "status": "ok",
  "service": "ACE-Step OpenRouter API",
  "version": "1.0"
}
```

---

## 入力モード

システムは最後の `user` メッセージの内容に基づいて入力モードを自動選択します。`lyrics` または `sample_mode` フィールドで明示的に指定することも可能です。

### モード 1: タグモード（推奨）

`<prompt>` と `<lyrics>` タグを使用して、音楽の説明と歌詞を明示的に指定します：

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

- `<prompt>...</prompt>` — 音楽のスタイル・シーンの説明（キャプション）
- `<lyrics>...</lyrics>` — 歌詞の内容
- どちらか一方のタグだけでも使用可能
- `use_format: true` の場合、LLM が prompt と lyrics を自動的に強化

### モード 2: 自然言語モード（サンプルモード）

自然言語で欲しい音楽を記述すると、システムが LLM を使って prompt と lyrics を自動生成します：

```json
{
  "messages": [
    {"role": "user", "content": "夏と旅行をテーマにした明るい日本語のポップソングを作ってください"}
  ],
  "sample_mode": true,
  "audio_config": {
    "vocal_language": "ja"
  }
}
```

トリガー条件：`sample_mode: true`、またはメッセージにタグが含まれず歌詞らしくない内容の場合に自動トリガー。

### モード 3: 歌詞のみモード

構造マーカー付きの歌詞を直接渡すと、システムが自動認識します：

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

トリガー条件：メッセージに `[Verse]`、`[Chorus]` などのマーカーが含まれている、または複数行の短いテキスト構造を持つ場合。

### モード 4: 歌詞 + Prompt 分離

`lyrics` フィールドで歌詞を直接渡し、messages テキストは自動的に prompt として扱われます：

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

### インストゥルメンタルモード

`audio_config.instrumental: true` を設定：

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

## オーディオ入力

マルチモーダル messages でオーディオファイル（base64 エンコード）を渡すことで、cover、repaint などのタスクに使用できます。

### task_type タイプ

| task_type | 説明 | オーディオ入力 |
|---|---|---|
| `text2music` | テキストから音楽生成（デフォルト） | 任意（reference として） |
| `cover` | カバー/スタイル変換 | src_audio が必要 |
| `repaint` | 部分的なリペイント | src_audio が必要 |
| `lego` | オーディオ接合 | src_audio が必要 |
| `extract` | オーディオ抽出 | src_audio が必要 |
| `complete` | オーディオ続き生成 | src_audio が必要 |

### オーディオルーティングルール

複数の `input_audio` ブロックは順番に異なるパラメータにルーティングされます（複数画像アップロードと同様）：

| task_type | audio[0] | audio[1] |
|---|---|---|
| `text2music` | reference_audio（スタイル参照） | - |
| `cover/repaint/lego/extract/complete` | src_audio（編集対象オーディオ） | reference_audio（任意のスタイル参照） |

### オーディオ入力の例

**Cover タスク（カバー）：**

```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "<prompt>Jazz style cover with saxophone</prompt>"},
        {
          "type": "input_audio",
          "input_audio": {"data": "<base64 元オーディオ>", "format": "mp3"}
        }
      ]
    }
  ],
  "task_type": "cover",
  "audio_cover_strength": 0.8,
  "audio_config": {"duration": 30}
}
```

**Repaint タスク（部分リペイント）：**

```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "<prompt>Replace with guitar solo</prompt>"},
        {
          "type": "input_audio",
          "input_audio": {"data": "<base64 元オーディオ>", "format": "mp3"}
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

## ストリーミングレスポンス

`"stream": true` を設定すると SSE（Server-Sent Events）ストリーミングが有効になります。

### イベントフォーマット

各イベントは `data: ` で始まり、JSON が続き、二重改行 `\n\n` で終了します：

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{...},"finish_reason":null}]}

```

### ストリーミングイベントの順序

| フェーズ | delta の内容 | 説明 |
|---|---|---|
| 1. 初期化 | `{"role":"assistant","content":""}` | 接続の確立 |
| 2. LM コンテンツ | `{"content":"\n\n## Metadata\n..."}` | LM 使用時に metadata と lyrics を送信 |
| 3. ハートビート | `{"content":"."}` | オーディオ生成中に2秒ごとに送信（接続維持） |
| 4. オーディオデータ | `{"audio":[{"type":"audio_url","audio_url":{"url":"data:..."}}]}` | オーディオ base64 データ |
| 5. 完了 | `finish_reason: "stop"` | 生成完了 |
| 6. 終了 | `data: [DONE]` | ストリーム終了マーカー |

### ストリーミングレスポンス例

```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{"content":"\n\n## Metadata\n**Caption:** Upbeat pop\n**BPM:** 120"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{"content":"."},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{"audio":[{"type":"audio_url","audio_url":{"url":"data:audio/mpeg;base64,..."}}]},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706688000,"model":"acemusic/acestep-v15-turbo","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]

```

### クライアント側のストリーミング処理

```python
import json
import httpx

with httpx.stream("POST", "http://127.0.0.1:8002/v1/chat/completions", json={
    "messages": [{"role": "user", "content": "明るいギター曲を生成してください"}],
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
            print("生成完了！")

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
    messages: [{ role: "user", content: "明るいギター曲を生成してください" }],
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

// audioUrl は <audio src="..."> で直接使用可能
```

---

## リクエスト例

### 例 1: 自然言語生成（最もシンプルな使い方）

```bash
curl -X POST http://127.0.0.1:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "故郷と思い出についての優しい日本語のフォークソング"}
    ],
    "sample_mode": true,
    "audio_config": {"vocal_language": "ja"}
  }'
```

### 例 2: タグモード + パラメータ指定

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

### 例 3: インストゥルメンタル + LM 強化無効

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

### 例 4: ストリーミングリクエスト

```bash
curl -X POST http://127.0.0.1:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -N \
  -d '{
    "messages": [
      {"role": "user", "content": "誕生日おめでとうの歌を作ってください"}
    ],
    "sample_mode": true,
    "stream": true
  }'
```

### 例 5: マルチシード バッチ生成

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

## エラーコード

| HTTP ステータス | 説明 |
|---|---|
| 400 | リクエスト形式が不正、または有効な入力がない |
| 401 | API キーが未指定、または無効 |
| 429 | サービスがビジー状態、キューが満杯 |
| 500 | 音楽生成中に内部エラーが発生 |
| 503 | モデルがまだ初期化されていない |
| 504 | 生成タイムアウト |

エラーレスポンス形式：

```json
{
  "detail": "エラーの説明メッセージ"
}
```

---

## サーバー設定（環境変数）

以下の環境変数でサーバーを設定できます（運用担当者向け）：

| 変数名 | デフォルト | 説明 |
|---|---|---|
| `OPENROUTER_API_KEY` | なし | API 認証キー |
| `OPENROUTER_HOST` | `127.0.0.1` | リッスンアドレス |
| `OPENROUTER_PORT` | `8002` | リッスンポート |
| `ACESTEP_CONFIG_PATH` | `acestep-v15-turbo` | DiT モデル設定パス |
| `ACESTEP_DEVICE` | `auto` | 推論デバイス |
| `ACESTEP_LM_MODEL_PATH` | `acestep-5Hz-lm-0.6B` | LLM モデルパス |
| `ACESTEP_LM_BACKEND` | `vllm` | LLM 推論バックエンド |
| `ACESTEP_QUEUE_MAXSIZE` | `200` | タスクキューの最大容量 |
| `ACESTEP_GENERATION_TIMEOUT` | `600` | 非ストリーミングリクエストのタイムアウト（秒） |
