# ACE-Step API クライアントドキュメント

**Language / 语言 / 言語:** [English](../en/API.md) | [中文](../zh/API.md) | [日本語](API.md)

---

本サービスはHTTPベースの非同期音楽生成APIを提供します。

**基本的なワークフロー**：
1. `POST /release_task` を呼び出してタスクを送信し、`task_id` を取得します。
2. `POST /query_result` を呼び出してタスクステータスを一括クエリし、`status` が `1`（成功）または `2`（失敗）になるまで待ちます。
3. 結果で返された `GET /v1/audio?path=...` URL から音声ファイルをダウンロードします。

---

## 目次

- [認証](#1-認証)
- [レスポンス形式](#2-レスポンス形式)
- [タスクステータスの説明](#3-タスクステータスの説明)
- [生成タスクの作成](#4-生成タスクの作成)
- [タスク結果の一括クエリ](#5-タスク結果の一括クエリ)
- [入力のフォーマット](#6-入力のフォーマット)
- [ランダムサンプルの取得](#7-ラ���ダムサンプルの取得)
- [利用可能なモデルの一覧](#8-利用可能なモデルの一覧)
- [サーバー統計](#9-サーバー統計)
- [音声ファイルのダウンロード](#10-音声ファイルのダウンロード)
- [ヘルスチェック](#11-ヘルスチェック)
- [環境変数](#12-環境変数)

---

## 1. 認証

APIはオプションのAPIキー認証をサポートしています。有効にすると、リクエストに有効なキーを提供する必要があります。

### 認証方法

2つの認証方法をサポート：

**方法 A：リクエストボディの ai_token**

```json
{
  "ai_token": "your-api-key",
  "prompt": "アップビートなポップソング",
  ...
}
```

**方法 B：Authorization ヘッダー**

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Authorization: Bearer your-api-key' \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "アップビートなポップソング"}'
```

### APIキーの設定

環境変数またはコマンドライン引数で設定：

```bash
# 環境変数
export ACESTEP_API_KEY=your-secret-key

# またはコマンドライン引数
python -m acestep.api_server --api-key your-secret-key
```

---

## 2. レスポンス形式

すべてのAPIレスポンスは統一されたラッパー形式を使用します：

```json
{
  "data": { ... },
  "code": 200,
  "error": null,
  "timestamp": 1700000000000,
  "extra": null
}
```

| フィールド | 型 | 説明 |
| :--- | :--- | :--- |
| `data` | any | 実際のレスポンスデータ |
| `code` | int | ステータスコード（200=成功）|
| `error` | string | エラーメッセージ（成功時はnull）|
| `timestamp` | int | レスポンスタイムスタンプ（ミリ秒）|
| `extra` | any | 追加情報���通常はnull）|

---

## 3. タスクステータスの説明

タスクステータス（`status`）は整数で表されます：

| ステータスコード | ステータス名 | 説明 |
| :--- | :--- | :--- |
| `0` | queued/running | タスクがキュー中または実行中 |
| `1` | succeeded | 生成成功、結果が準備完了 |
| `2` | failed | 生成失敗 |

---

## 4. 生成タスクの作成

### 4.1 API 定義

- **URL**：`/release_task`
- **メソッド**：`POST`
- **Content-Type**：`application/json`、`multipart/form-data`、または `application/x-www-form-urlencoded`

### 4.2 リクエストパラメータ

#### パラメータ命名規則

APIはほとんどのパラメータで **snake_case** と **camelCase** の両方の命名をサポートしています。例：
- `audio_duration` / `duration` / `audioDuration`
- `key_scale` / `keyscale` / `keyScale`
- `time_signature` / `timesignature` / `timeSignature`
- `sample_query` / `sampleQuery` / `description` / `desc`
- `use_format` / `useFormat` / `format`

また、メタデータはネストされたオブジェクト（`metas`、`metadata`、または `user_metadata`）で渡すことができます。

#### 方法 A：JSONリクエスト（application/json）

テキストパラメータのみを渡す場合、またはサーバー上に既に存在する音声ファイルパスを参照する場合に適しています。

**基本パラメータ**：

| パラメータ名 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `prompt` | string | `""` | 音楽の説明プロンプト（別名：`caption`）|
| `lyrics` | string | `""` | 歌詞の内容 |
| `thinking` | bool | `false` | 5Hz LMを使用してオーディオコードを生成するかどうか（lm-dit動作）|
| `vocal_language` | string | `"en"` | 歌詞の言語（en、zh、jaなど）|
| `audio_format` | string | `"mp3"` | 出力形式（mp3、wav、flac）|

**サンプル/説明モードパラメータ**：

| パラメータ名 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `sample_mode` | bool | `false` | ランダムサンプル生成モードを有効にする（LM経由でcaption/lyrics/metasを自動生成）|
| `sample_query` | string | `""` | サンプル生成のための自然言語の説明（例：「静かな夜のための柔らかいベンガルのラブソング」）。別名：`description`、`desc` |
| `use_format` | bool | `false` | LMを使用して提供されたcaptionとlyricsを強化/フォーマットする。別名：`format` |

**マルチモデルサポート**：

| パラメータ名 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `model` | string | null | 使用するDiTモデルを選択（例：`"acestep-v15-turbo"`、`"acestep-v15-turbo-shift3"`）。`/v1/models` で利用可能なモデルを一覧表示。指定しない場合はデフォルトモデルを使用。|

**thinkingのセマンティクス（重要）**：

- `thinking=false`：
  - サーバーは5Hz LMを使用して `audio_code_string` を生成**しません**。
  - DiTは **text2music** モードで実行され、提供された `audio_code_string` を**無視**します。
- `thinking=true`：
  - サーバーは5Hz LMを使用して `audio_code_string` を生成します（lm-dit動作）。
  - DiTはLM生成のコードで実行され、音楽品質が向上します。

**メタデータの自動補完（条件付き）**：

`use_cot_caption=true` または `use_cot_language=true` またはメタデータフィールドが欠落している場合、サーバーは `caption`/`lyrics` に基づいて5Hz LMを呼び出し、欠落しているフィールドを補完することがあります：

- `bpm`
- `key_scale`
- `time_signature`
- `audio_duration`

ユーザー提供の値が常に優先されます。LMは空/欠落しているフィールドのみを補完します。

**音楽属性パラメータ**：

| パラメータ名 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `bpm` | int | null | テンポ（BPM）を指定、範囲30-300 |
| `key_scale` | string | `""` | キー/スケール（例：「C Major」、「Am」）。別名：`keyscale`、`keyScale` |
| `time_signature` | string | `""` | 拍子記号（2、3、4、6はそれぞれ2/4、3/4、4/4、6/8）。別名：`timesignature`、`timeSignature` |
| `audio_duration` | float | null | 生成時間（秒）、範囲10-600。別名：`duration`、`target_duration` |

**オーディオコード（オプション）**：

| パラメータ名 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `audio_code_string` | string または string[] | `""` | `llm_dit` 用のオーディオセマンティックトークン（5Hz）。別名：`audioCodeString` |

**生成制御パラメータ**：

| パラメータ名 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `inference_steps` | int | `8` | 推論ステップ数。Turboモデル：1-20（推奨8）。Baseモデル：1-200（推奨32-64）|
| `guidance_scale` | float | `7.0` | プロンプトガイダンス係数。baseモデルのみ有効 |
| `use_random_seed` | bool | `true` | ランダムシードを使用するかどうか |
| `seed` | int | `-1` | シードを指定（use_random_seed=falseの場合）|
| `batch_size` | int | `2` | バッチ生成数（最大8）|

**高度なDiTパラメータ**：

| パラメータ名 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `shift` | float | `3.0` | タイムステップシフト係数（範囲1.0-5.0）。baseモデルのみ有効、turboモデルには無効 |
| `infer_method` | string | `"ode"` | 拡散推論方法：`"ode"`（Euler、より高速）または `"sde"`（確率的）|
| `timesteps` | string | null | カンマ区切りのカスタムタイムステップ（例：`"0.97,0.76,0.615,0.5,0.395,0.28,0.18,0.085,0"`）。`inference_steps` と `shift` をオーバーライド |
| `use_adg` | bool | `false` | 適応デュアルガイダンスを使用（baseモデルのみ）|
| `cfg_interval_start` | float | `0.0` | CFG適用開始比率（0.0-1.0）|
| `cfg_interval_end` | float | `1.0` | CFG適用終了比率（0.0-1.0）|

**5Hz LMパラメータ（オプション、サーバー側）**：

これらのパラメータは5Hz LMサンプリングを制御し、メタデータの自動補完と（`thinking=true` の場合）コード生成に使用されます。

| パラメータ名 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `lm_model_path` | string | null | 5Hz LMチェックポイントディレクトリ名（例：`acestep-5Hz-lm-0.6B`）|
| `lm_backend` | string | `"vllm"` | `vllm` または `pt` |
| `lm_temperature` | float | `0.85` | サンプリング温度 |
| `lm_cfg_scale` | float | `2.5` | CFGスケール（>1でCFGを有効化）|
| `lm_negative_prompt` | string | `"NO USER INPUT"` | CFGで使用するネガティブプロンプト |
| `lm_top_k` | int | null | Top-k（0/nullで無効）|
| `lm_top_p` | float | `0.9` | Top-p（>=1は無効として扱われる）|
| `lm_repetition_penalty` | float | `1.0` | 繰り返しペナルティ |

**LM CoT（思考の連鎖）パラメータ**：

| パラメータ名 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `use_cot_caption` | bool | `true` | LMにCoT推論で入力captionを書き換え/強化させる。別名：`cot_caption`、`cot-caption` |
| `use_cot_language` | bool | `true` | LMにCoTでボーカル言語を検出させる。別名：`cot_language`、`cot-language` |
| `constrained_decoding` | bool | `true` | 構造化されたLM出力のためのFSMベースの制約付きデコーディングを有効にする。別名：`constrainedDecoding`、`constrained` |
| `constrained_decoding_debug` | bool | `false` | 制約付きデコーディングのデバッグログを有効にする |
| `allow_lm_batch` | bool | `true` | 効率向上のためにLMバッチ処理を許可 |

**編集/参照オーディオパラメータ**（サーバー上の絶対パスが必要）：

| パラメータ名 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `reference_audio_path` | string | null | 参照オーディオパス（スタイル転送）|
| `src_audio_path` | string | null | ソースオーディオパス（リペイント/カバー）|
| `task_type` | string | `"text2music"` | タスクタイプ：`text2music`、`cover`、`repaint`、`lego`、`extract`、`complete` |
| `instruction` | string | auto | 編集指示（提供されない場合はtask_typeに基づいて自動生成）|
| `repainting_start` | float | `0.0` | リペイント開始時間（秒）|
| `repainting_end` | float | null | リペイント終了時間（秒）、-1でオーディオの終端 |
| `audio_cover_strength` | float | `1.0` | カバー強度（0.0-1.0）。スタイル転送には小さい値（0.2）を使用 |

#### 方法 B：ファイルアップロード（multipart/form-data）

参照またはソースオーディオとしてローカルオーディオファイルをアップロードする必要がある場合に使用します。

上記のすべてのフィールドをフォームフィールドとしてサポートすることに加えて、以下のファイルフィールドもサポートしています：

- `reference_audio` または `ref_audio`：（ファイル）参照オーディオファイルをアップロード
- `src_audio` または `ctx_audio`：（ファイル）ソースオーディオファイルをアップロード

> **注意**：ファイルをアップロードすると、対応する `_path` パラメータは自動的に無視され、システムはアップロード後の一時ファイルパスを使用します。

### 4.3 レスポンス例

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

### 4.4 使用例（cURL）

**基本的なJSONメソッド**：

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "アップビートなポップソング",
    "lyrics": "Hello world",
    "inference_steps": 8
  }'
```

**thinking=trueの場合（LMがコードを生成 + 欠落メタを補完）**：

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "アップビートなポップソング",
    "lyrics": "Hello world",
    "thinking": true,
    "lm_temperature": 0.85,
    "lm_cfg_scale": 2.5
  }'
```

**説明駆動型生成（sample_query）**：

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "sample_query": "静かな夜のための柔らかいベンガルのラブソング",
    "thinking": true
  }'
```

**フォーマット強化（use_format=true）**：

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "ポップロック",
    "lyrics": "[Verse 1]\n街を歩いて...",
    "use_format": true,
    "thinking": true
  }'
```

**特定のモデルを選択**：

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "エレクトロニックダンスミュージック",
    "model": "acestep-v15-turbo",
    "thinking": true
  }'
```

**カスタムタイムステップを使用**：

```bash
curl -X POST http://localhost:8001/release_task \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "ジャズピアノトリオ",
    "timesteps": "0.97,0.76,0.615,0.5,0.395,0.28,0.18,0.085,0",
    "thinking": true
  }'
```

**ファイルアップロードメソッド**：

```bash
curl -X POST http://localhost:8001/release_task \
  -F "prompt=この曲をリミックス" \
  -F "src_audio=@/path/to/local/song.mp3" \
  -F "task_type=repaint"
```

---

## 5. タスク結果の一括クエリ

### 5.1 API 定義

- **URL**：`/query_result`
- **メソッド**：`POST`
- **Content-Type**：`application/json` または `application/x-www-form-urlencoded`

### 5.2 リクエストパラメータ

| パラメータ名 | 型 | 説明 |
| :--- | :--- | :--- |
| `task_id_list` | string (JSON array) または array | クエリするタスクIDのリスト |

### 5.3 レスポンス例

```json
{
  "data": [
    {
      "task_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": 1,
      "result": "[{\"file\": \"/v1/audio?path=...\", \"wave\": \"\", \"status\": 1, \"create_time\": 1700000000, \"env\": \"development\", \"prompt\": \"アップビートなポップソング\", \"lyrics\": \"Hello world\", \"metas\": {\"bpm\": 120, \"duration\": 30, \"genres\": \"\", \"keyscale\": \"C Major\", \"timesignature\": \"4\"}, \"generation_info\": \"...\", \"seed_value\": \"12345,67890\", \"lm_model\": \"acestep-5Hz-lm-0.6B\", \"dit_model\": \"acestep-v15-turbo\"}]"
    }
  ],
  "code": 200,
  "error": null,
  "timestamp": 1700000000000,
  "extra": null
}
```

**結果フィールドの説明**（resultはJSON文字列、パース後に含まれる）：

| フィールド | 型 | 説明 |
| :--- | :--- | :--- |
| `file` | string | オーディオファイルURL（`/v1/audio` エンドポイントと併用）|
| `wave` | string | 波形データ（通常は空）|
| `status` | int | ステータスコード（0=進行中、1=成功、2=失敗）|
| `create_time` | int | 作成時間（Unixタイムスタンプ）|
| `env` | string | 環境識別子 |
| `prompt` | string | 使用されたプロンプト |
| `lyrics` | string | 使用された歌詞 |
| `metas` | object | メタデータ（bpm、duration、genres、keyscale、timesignature）|
| `generation_info` | string | 生成情報の概要 |
| `seed_value` | string | 使用されたシード値（カンマ区切り）|
| `lm_model` | string | 使用されたLMモデル名 |
| `dit_model` | string | 使用されたDiTモデル名 |

### 5.4 使用例

```bash
curl -X POST http://localhost:8001/query_result \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id_list": ["550e8400-e29b-41d4-a716-446655440000"]
  }'
```

---

## 6. 入力のフォーマット

### 6.1 API 定義

- **URL**：`/format_input`
- **メソッド**：`POST`

このエンドポイントはLLMを使用してユーザー提供のcaptionとlyricsを強化・フォーマットします。

### 6.2 リクエストパラメータ

| パラメータ名 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `prompt` | string | `""` | 音楽の説明プロンプト |
| `lyrics` | string | `""` | 歌詞の内容 |
| `temperature` | float | `0.85` | LMサンプリング温度 |
| `param_obj` | string (JSON) | `"{}"` | メタデータを含むJSONオブジェクト（duration、bpm、key、time_signature、language）|

### 6.3 レスポンス例

```json
{
  "data": {
    "caption": "強化された音楽の説明",
    "lyrics": "フォーマットされた歌詞...",
    "bpm": 120,
    "key_scale": "C Major",
    "time_signature": "4",
    "duration": 180,
    "vocal_language": "ja"
  },
  "code": 200,
  "error": null,
  "timestamp": 1700000000000,
  "extra": null
}
```

### 6.4 使用例

```bash
curl -X POST http://localhost:8001/format_input \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "ポップロック",
    "lyrics": "街を歩いて",
    "param_obj": "{\"duration\": 180, \"language\": \"ja\"}"
  }'
```

---

## 7. ランダムサンプルの取得

### 7.1 API 定義

- **URL**：`/create_random_sample`
- **メソッド**：`POST`

このエンドポイントは事前にロードされたサンプルデータからランダムなサンプルパラメータを返します。フォーム入力に使用します。

### 7.2 リクエストパラメータ

| パラメータ名 | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `sample_type` | string | `"simple_mode"` | サンプルタイプ：`"simple_mode"` または `"custom_mode"` |

### 7.3 レスポンス例

```json
{
  "data": {
    "caption": "ギター伴奏のある軽快なポップソング",
    "lyrics": "[Verse 1]\n陽の光が顔に...",
    "bpm": 120,
    "key_scale": "G Major",
    "time_signature": "4",
    "duration": 180,
    "vocal_language": "ja"
  },
  "code": 200,
  "error": null,
  "timestamp": 1700000000000,
  "extra": null
}
```

### 7.4 使用例

```bash
curl -X POST http://localhost:8001/create_random_sample \
  -H 'Content-Type: application/json' \
  -d '{"sample_type": "simple_mode"}'
```

---

## 8. 利用可能なモデルの一覧

### 8.1 API 定義

- **URL**：`/v1/models`
- **メソッド**：`GET`

サーバーにロードされている利用可能なDiTモデルのリストを返します。

### 8.2 レスポンス例

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

### 8.3 使用例

```bash
curl http://localhost:8001/v1/models
```

---

## 9. サーバー統計

### 9.1 API 定義

- **URL**：`/v1/stats`
- **メソッド**：`GET`

サーバーの実���統計情報を返します。

### 9.2 レスポンス例

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

### 9.3 使用例

```bash
curl http://localhost:8001/v1/stats
```

---

## 10. 音声ファイルのダウンロード

### 10.1 API 定義

- **URL**：`/v1/audio`
- **メソッド**：`GET`

パスで生成されたオーディオファイルをダウンロードします。

### 10.2 リクエストパラメータ

| パラメータ名 | 型 | 説明 |
| :--- | :--- | :--- |
| `path` | string | URLエンコードされたオーディオファイルパス |

### 10.3 使用例

```bash
# タスク結果のURLを使用してダウンロード
curl "http://localhost:8001/v1/audio?path=%2Ftmp%2Fapi_audio%2Fabc123.mp3" -o output.mp3
```

---

## 11. ヘルスチェック

### 11.1 API 定義

- **URL**：`/health`
- **メソッド**：`GET`

サービスのヘルスステータスを返します。

### 11.2 レスポンス例

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

## 12. 環境変数

APIサーバーは環境変数で設定できます：

### サーバー設定

| 変数 | デフォルト | 説明 |
| :--- | :--- | :--- |
| `ACESTEP_API_HOST` | `127.0.0.1` | サーバーバインドホスト |
| `ACESTEP_API_PORT` | `8001` | サーバーバインドポート |
| `ACESTEP_API_KEY` | （空）| API認証キー（空の場合は認証無効）|
| `ACESTEP_API_WORKERS` | `1` | APIワーカースレッド数 |

### モデル設定

| 変数 | デフォルト | 説明 |
| :--- | :--- | :--- |
| `ACESTEP_CONFIG_PATH` | `acestep-v15-turbo` | プライマリDiTモデルパス |
| `ACESTEP_CONFIG_PATH2` | （空）| セカンダリDiTモデルパス（オプション）|
| `ACESTEP_CONFIG_PATH3` | （空）| 3番目のDiTモデルパス（オプション）|
| `ACESTEP_DEVICE` | `auto` | モデルロードデバイス |
| `ACESTEP_USE_FLASH_ATTENTION` | `true` | flash attentionを有効化 |
| `ACESTEP_OFFLOAD_TO_CPU` | `false` | アイドル時にモデルをCPUにオフロード |
| `ACESTEP_OFFLOAD_DIT_TO_CPU` | `false` | DiTを特にCPUにオフロード |

### LM設定

| 変数 | デフォルト | 説明 |
| :--- | :--- | :--- |
| `ACESTEP_INIT_LLM` | auto | 起動時にLMを初期化するかどうか（autoはGPUに基づいて自動決定）|
| `ACESTEP_LM_MODEL_PATH` | `acestep-5Hz-lm-0.6B` | デフォルト5Hz LMモデル |
| `ACESTEP_LM_BACKEND` | `vllm` | LMバックエンド（vllmまたはpt）|
| `ACESTEP_LM_DEVICE` | （ACESTEP_DEVICEと同じ）| LMデバイス |
| `ACESTEP_LM_OFFLOAD_TO_CPU` | `false` | LMをCPUにオフロード |

### キュー設定

| 変数 | デフォルト | 説明 |
| :--- | :--- | :--- |
| `ACESTEP_QUEUE_MAXSIZE` | `200` | 最大キューサイズ |
| `ACESTEP_QUEUE_WORKERS` | `1` | キューワーカー数 |
| `ACESTEP_AVG_JOB_SECONDS` | `5.0` | 初期平均ジョブ時間推定 |
| `ACESTEP_AVG_WINDOW` | `50` | 平均ジョブ時間計算ウィンドウ |

### キャッシュ設定

| 変数 | デフォルト | 説明 |
| :--- | :--- | :--- |
| `ACESTEP_TMPDIR` | `.cache/acestep/tmp` | 一時ファイルディレクトリ |
| `TRITON_CACHE_DIR` | `.cache/acestep/triton` | Tritonキャッシュディレクトリ |
| `TORCHINDUCTOR_CACHE_DIR` | `.cache/acestep/torchinductor` | TorchInductorキャッシュディレクトリ |

---

## エラー処理

**HTTPステータスコード**：

- `200`：成功
- `400`：無効なリクエスト（不正なJSON、フィールドの欠落）
- `401`：未認証（APIキーがないか無効）
- `404`：リソースが見つからない
- `415`：サポートされていないContent-Type
- `429`：サーバービジー（キューが満杯）
- `500`：内部サーバーエラー

**エラーレスポンス形式**：

```json
{
  "detail": "問題を説明するエラーメッセージ"
}
```

---

## ベストプラクティス

1. **`thinking=true` を使用** してLM強化生成で最高品質の結果を得る。

2. **`sample_query`/`description` を使用** して自然言語の説明から素早く生成。

3. **`use_format=true` を使用** してcaption/lyricsがあるがLMに強化してもらいたい場合。

4. **タスクステータスの一括クエリ** `/query_result` エンドポイントを使用して複数のタスクを一度にクエリ。

5. **`/v1/stats` を確認** してサーバーの負荷と平均ジョブ時間を把握。

6. **マルチモデルサポートを使用** するには `ACESTEP_CONFIG_PATH2` と `ACESTEP_CONFIG_PATH3` 環境変数を設定し、`model` パラメータで選択。

7. **本番環境** では `ACESTEP_API_KEY` を設定して認証を有効にし、APIを保護。

8. **低VRAM環境** では `ACESTEP_OFFLOAD_TO_CPU=true` を有効にして、より長いオーディオ生成をサポート。
