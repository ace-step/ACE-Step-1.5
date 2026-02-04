# ACE-Step 推論 API ドキュメント

**Language / 语言 / 言語:** [English](../en/INFERENCE.md) | [中文](../zh/INFERENCE.md) | [日本語](INFERENCE.md)

---

本ドキュメントはACE-Step推論APIの包括的なドキュメントを提供し、サポートされているすべてのタスクタイプのパラメータ仕様を含みます。

## 目次

- [クイックスタート](#クイックスタート)
- [API概要](#api概要)
- [GenerationParamsパラメータ](#generationparamsパラメータ)
- [GenerationConfigパラメータ](#generationconfigパラメータ)
- [タスクタイプ](#タスクタイプ)
- [ヘルパー関数](#ヘルパー関数)
- [完全な例](#完全な例)
- [ベストプラクティス](#ベストプラクティス)

---

## クイックスタート

### 基本的な使用法

```python
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.inference import GenerationParams, GenerationConfig, generate_music

# ハンドラーの初期化
dit_handler = AceStepHandler()
llm_handler = LLMHandler()

# サービスの初期化
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

# 生成パラメータの設定
params = GenerationParams(
    caption="重低音のアップビートなエレクトロニックダンスミュージック",
    bpm=128,
    duration=30,
)

# 生成設定の構成
config = GenerationConfig(
    batch_size=2,
    audio_format="flac",
)

# 音楽を生成
result = generate_music(dit_handler, llm_handler, params, config, save_dir="/path/to/output")

# 結果にアクセス
if result.success:
    for audio in result.audios:
        print(f"生成完了：{audio['path']}")
        print(f"Key：{audio['key']}")
        print(f"Seed：{audio['params']['seed']}")
else:
    print(f"エラー：{result.error}")
```

---

## API概要

### メイン関数

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

ACE-Stepモデルを使用して音楽を生成するメイン関数。

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

オーディオセマンティックコードを分析し、メタデータ（caption、lyrics、BPM、キーなど）を抽出します。

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

自然言語の説明から完全な音楽サンプル（caption、lyrics、メタデータ）を生成します。

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

ユーザー提供のcaptionとlyricsをフォーマット・強化し、構造化されたメタデータを生成します。

### 設定オブジェクト

APIは2つの設定データクラスを使用します：

**GenerationParams** - すべての音楽生成パラメータを含む：

```python
@dataclass
class GenerationParams:
    # タスクと指示
    task_type: str = "text2music"
    instruction: str = "Fill the audio semantic mask based on the given conditions:"
    
    # オーディオアップロード
    reference_audio: Optional[str] = None
    src_audio: Optional[str] = None
    
    # LMコードヒント
    audio_codes: str = ""
    
    # テキスト入力
    caption: str = ""
    lyrics: str = ""
    instrumental: bool = False
    
    # メタデータ
    vocal_language: str = "unknown"
    bpm: Optional[int] = None
    keyscale: str = ""
    timesignature: str = ""
    duration: float = -1.0
    
    # 高度な設定
    inference_steps: int = 8
    seed: int = -1
    guidance_scale: float = 7.0
    use_adg: bool = False
    cfg_interval_start: float = 0.0
    cfg_interval_end: float = 1.0
    shift: float = 1.0                    # 新規：タイムステップシフト係数
    infer_method: str = "ode"             # 新規：拡散推論方法
    timesteps: Optional[List[float]] = None  # 新規：カスタムタイムステップ
    
    repainting_start: float = 0.0
    repainting_end: float = -1
    audio_cover_strength: float = 1.0
    
    # 5Hz言語モデルパラメータ
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
    
    # CoT生成値（LMによって自動入力）
    cot_bpm: Optional[int] = None
    cot_keyscale: str = ""
    cot_timesignature: str = ""
    cot_duration: Optional[float] = None
    cot_vocal_language: str = "unknown"
    cot_caption: str = ""
    cot_lyrics: str = ""
```

**GenerationConfig** - バッチと出力設定を含む：

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

### 結果オブジェクト

**GenerationResult** - 音楽生成の結果：

```python
@dataclass
class GenerationResult:
    # オーディオ出力
    audios: List[Dict[str, Any]]  # オーディオ辞書のリスト
    
    # 生成情報
    status_message: str           # 生成からのステータスメッセージ
    extra_outputs: Dict[str, Any] # 追加出力（latents、masks、lm_metadata、time_costs）
    
    # 成功ステータス
    success: bool                 # 生成が成功したかどうか
    error: Optional[str]          # 失敗した場合のエラーメッセージ
```

**オーディオ辞書構造：**

`audios` リストの各アイテムには以下が含まれます：

```python
{
    "path": str,           # 保存されたオーディオへのファイルパス
    "tensor": Tensor,      # オーディオテンソル [channels, samples]、CPU、float32
    "key": str,            # ユニークなオーディオキー（パラメータに基づくUUID）
    "sample_rate": int,    # サンプルレート（デフォルト：48000）
    "params": Dict,        # このオーディオの生成パラメータ（seed、audio_codesなどを含む）
}
```

---

## GenerationParamsパラメータ

### テキスト入力

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|---------|-------------|
| `caption` | `str` | `""` | 希望する音楽のテキスト説明。「リラックスしたピアノ音楽」のような単純なプロンプトや、ジャンル、ムード、楽器などを含む詳細な説明が可能。最大512文字。|
| `lyrics` | `str` | `""` | ボーカル音楽の歌詞テキスト。インストゥルメンタルトラックには `"[Instrumental]"` を使用。複数言語をサポート。最大4096文字。|
| `instrumental` | `bool` | `False` | Trueの場合、歌詞に関係なくインストゥルメンタル音楽を生成。|

### 音楽メタデータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|---------|-------------|
| `bpm` | `Optional[int]` | `None` | 1分あたりのビート数（30-300）。`None` でLM経由の自動検出を有効化。|
| `keyscale` | `str` | `""` | 音楽キー（例：「C Major」、「Am」、「F# minor」）。空文字列で自動検出を有効化。|
| `timesignature` | `str` | `""` | 拍子記号（2は'2/4'、3は'3/4'、4は'4/4'、6は'6/8'）。空文字列で自動検出を有効化。|
| `vocal_language` | `str` | `"unknown"` | ボーカルの言語コード（ISO 639-1）。サポート：`"en"`、`"zh"`、`"ja"`、`"es"`、`"fr"` など。自動検出には `"unknown"` を使用。|
| `duration` | `float` | `-1.0` | 目標オーディオ長（秒）（10-600）。<= 0またはNoneの場合、モデルが歌詞の長さに基づいて自動選択。|

### 生成パラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|---------|-------------|
| `inference_steps` | `int` | `8` | デノイズステップ数。Turboモデル：1-20（推奨8）。Baseモデル：1-200（推奨32-64）。高い = 品質向上だが遅い。|
| `guidance_scale` | `float` | `7.0` | 分類器フリーガイダンススケール（1.0-15.0）。高い値はテキストプロンプトへの忠実性を増加。非turboモデルのみサポート。典型的な範囲：5.0-9.0。|
| `seed` | `int` | `-1` | 再現性のためのランダムシード。ランダムシードには `-1`、固定シードには任意の正の整数を使用。|

### 高度なDiTパラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|---------|-------------|
| `use_adg` | `bool` | `False` | 適応デュアルガイダンスを使用（baseモデルのみ）。速度を犠牲にして品質を向上。|
| `cfg_interval_start` | `float` | `0.0` | CFG適用開始比率（0.0-1.0）。分類器フリーガイダンスの適用開始タイミングを制御。|
| `cfg_interval_end` | `float` | `1.0` | CFG適用終了比率（0.0-1.0）。分類器フリーガイダンスの適用終了タイミングを制御。|
| `shift` | `float` | `1.0` | タイムステップシフト係数（範囲1.0-5.0、デフォルト1.0）。!= 1.0の場合、タイムステップに `t = shift * t / (1 + (shift - 1) * t)` を適用。turboモデルには3.0推奨。|
| `infer_method` | `str` | `"ode"` | 拡散推論方法。`"ode"`（Euler）はより高速で決定的。`"sde"`（確率的）は分散のある異なる結果を生成する可能性あり。|
| `timesteps` | `Optional[List[float]]` | `None` | カスタムタイムステップ、1.0から0.0の浮動小数点リスト（例：`[0.97, 0.76, 0.615, 0.5, 0.395, 0.28, 0.18, 0.085, 0]`）。提供された場合、`inference_steps` と `shift` をオーバーライド。|

### タスク固有パラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|---------|-------------|
| `task_type` | `str` | `"text2music"` | 生成タスクタイプ。詳細は[タスクタイプ](#タスクタイプ)セクションを参照。|
| `instruction` | `str` | `"Fill the audio semantic mask based on the given conditions:"` | タスク固有の指示プロンプト。|
| `reference_audio` | `Optional[str]` | `None` | スタイル転送または継続タスク用の参照オーディオファイルパス。|
| `src_audio` | `Optional[str]` | `None` | オーディオ間タスク（cover、repaintなど）用のソースオーディオファイルパス。|
| `audio_codes` | `str` | `""` | 事前抽出された5Hzオーディオセマンティックコード文字列。高度な使用のみ。|
| `repainting_start` | `float` | `0.0` | リペイント開始時間（秒）（repaint/legoタスク用）。|
| `repainting_end` | `float` | `-1` | リペイント終了時間（秒）。オーディオの終端には `-1` を使用。|
| `audio_cover_strength` | `float` | `1.0` | オーディオカバー/コードの影響強度（0.0-1.0）。スタイル転送タスクには小さい値（0.2）を設定。|

### 5Hz言語モデルパラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|---------|-------------|
| `thinking` | `bool` | `True` | セマンティック/音楽メタデータとコード用の5Hz言語モデル「思考の連鎖」推論を有効化。|
| `lm_temperature` | `float` | `0.85` | LMサンプリング温度（0.0-2.0）。高い = より創造的/多様、低い = より保守的。|
| `lm_cfg_scale` | `float` | `2.0` | LM分類器フリーガイダンススケール。高い = プロンプトへのより強い忠実性。|
| `lm_top_k` | `int` | `0` | LM top-kサンプリング。`0` でtop-kフィルタリングを無効化。典型的な値：40-100。|
| `lm_top_p` | `float` | `0.9` | LM核サンプリング（0.0-1.0）。`1.0` で核サンプリングを無効化。典型的な値：0.9-0.95。|
| `lm_negative_prompt` | `str` | `"NO USER INPUT"` | LMガイダンス用のネガティブプロンプト。不要な特性を避けるのに役立つ。|
| `use_cot_metas` | `bool` | `True` | LM CoT推論を使用してメタデータを生成（BPM、キー、duration など）。|
| `use_cot_caption` | `bool` | `True` | LM CoT推論を使用してユーザーcaptionを改良。|
| `use_cot_language` | `bool` | `True` | LM CoT推論を使用してボーカル言語を検出。|
| `use_cot_lyrics` | `bool` | `False` | （将来の使用のために予約）LM CoTを使用して歌詞を生成/改良。|
| `use_constrained_decoding` | `bool` | `True` | 構造化されたLM出力のための制約付きデコーディングを有効化。|

---

## GenerationConfigパラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|---------|-------------|
| `batch_size` | `int` | `2` | 並列生成するサンプル数（1-8）。高い値はより多くのGPUメモリを必要とする。|
| `allow_lm_batch` | `bool` | `False` | LMでのバッチ処理を許可。`batch_size >= 2` かつ `thinking=True` の場合により高速。|
| `use_random_seed` | `bool` | `True` | ランダムシードを使用するかどうか。`True` で毎回異なる結果、`False` で再現可能な結果。|
| `seeds` | `Optional[List[int]]` | `None` | バッチ生成用のシードリスト。提供された場合、batch_sizeより少なければランダムシードでパディング。単一のintも可。|
| `lm_batch_chunk_size` | `int` | `8` | LM推論チャンクあたりの最大バッチサイズ（GPUメモリ制約）。|
| `constrained_decoding_debug` | `bool` | `False` | 制約付きデコーディングのデバッグログを有効化。|
| `audio_format` | `str` | `"flac"` | 出力オーディオ形式。オプション：`"mp3"`、`"wav"`、`"flac"`。高速保存のためデフォルトはFLAC。|

---

## タスクタイプ

ACE-Stepは6種類の生成タスクタイプをサポートし、それぞれ特定のユースケースに最適化されています。

### 1. Text2Music（デフォルト）

**目的**：テキスト説明とオプションのメタデータから音楽を生成。

**主要パラメータ**：
```python
params = GenerationParams(
    task_type="text2music",
    caption="エレキギターのエネルギッシュなロック音楽",
    lyrics="[Instrumental]",  # または実際の歌詞
    bpm=140,
    duration=30,
)
```

**必須**：
- `caption` または `lyrics`（少なくとも1つ）

**オプションだが推奨**：
- `bpm`：テンポを制御
- `keyscale`：音楽キーを制御
- `timesignature`：リズム構造を制御
- `duration`：長さを制御
- `vocal_language`：ボーカル特性を制御

**ユースケース**：
- テキスト説明から音楽を生成
- プロンプトからバッキングトラックを作成
- 歌詞付きの曲を生成

---

### 2. Cover

**目的**：既存のオーディオを構造を維持しながらスタイル/音色を変更して変換。

**主要パラメータ**：
```python
params = GenerationParams(
    task_type="cover",
    src_audio="original_song.mp3",
    caption="ジャズピアノバージョン",
    audio_cover_strength=0.8,  # 0.0-1.0
)
```

**必須**：
- `src_audio`：ソースオーディオファイルパス
- `caption`：希望するスタイル/変換の説明

**オプション**：
- `audio_cover_strength`：元のオーディオの影響を制御
  - `1.0`：元の構造を強く維持
  - `0.5`：バランスの取れた変換
  - `0.1`：緩やかな解釈
- `lyrics`：新しい歌詞（ボーカルを変更する場合）

**ユースケース**：
- 異なるスタイルのカバーを作成
- メロディを維持しながら楽器編成を変更
- ジャンル変換

---

### 3. Repaint

**目的**：オーディオの特定の時間セグメントを再生成し、残りは変更しない。

**主要パラメータ**：
```python
params = GenerationParams(
    task_type="repaint",
    src_audio="original.mp3",
    repainting_start=10.0,  # 秒
    repainting_end=20.0,    # 秒
    caption="ピアノソロでスムーズなトランジション",
)
```

**必須**：
- `src_audio`：ソースオーディオファイルパス
- `repainting_start`：開始時間（秒）
- `repainting_end`：終了時間（秒）（ファイル終端には `-1` を使用）
- `caption`：リペイントセクションの希望するコンテンツの説明

**ユースケース**：
- 生成された音楽の特定セクションを修正
- 曲の一部にバリエーションを追加
- スムーズなトランジションを作成
- 問題のあるセグメントを置き換え

---

### 4. Lego（Baseモデルのみ）

**目的**：既存のオーディオのコンテキストで特定の楽器トラックを生成。

**主要パラメータ**：
```python
params = GenerationParams(
    task_type="lego",
    src_audio="backing_track.mp3",
    instruction="Generate the guitar track based on the audio context:",
    caption="ブルージーな感じのリードギターメロディ",
    repainting_start=0.0,
    repainting_end=-1,
)
```

**必須**：
- `src_audio`：ソース/バッキングオーディオパス
- `instruction`：トラックタイプを指定する必要あり（例：「Generate the {TRACK_NAME} track...」）
- `caption`：希望するトラック特性の説明

**利用可能なトラック**：
- `"vocals"`、`"backing_vocals"`、`"drums"`、`"bass"`、`"guitar"`、`"keyboard"`、
- `"percussion"`、`"strings"`、`"synth"`、`"fx"`、`"brass"`、`"woodwinds"`

**ユースケース**：
- 特定の楽器トラックを追加
- バッキングトラック上に追加の楽器をレイヤー
- マルチトラック作品を反復的に作成

---

### 5. Extract（Baseモデルのみ）

**目的**：ミックスオーディオから特定の楽器トラックを抽出/分離。

**主要パラメータ**：
```python
params = GenerationParams(
    task_type="extract",
    src_audio="full_mix.mp3",
    instruction="Extract the vocals track from the audio:",
)
```

**必須**：
- `src_audio`：ミックスオーディオファイルパス
- `instruction`：抽出するトラックを指定する必要あり

**利用可能なトラック**：Legoタスクと同じ

**ユースケース**：
- ステム分離
- 特定の楽器を分離
- リミックスを作成
- 個別トラックを分析

---

### 6. Complete（Baseモデルのみ）

**目的**：指定された楽器で部分的なトラックを完成/拡張。

**主要パラメータ**：
```python
params = GenerationParams(
    task_type="complete",
    src_audio="incomplete_track.mp3",
    instruction="Complete the input track with drums, bass, guitar:",
    caption="ロックスタイルの完成",
)
```

**必須**：
- `src_audio`：不完全/部分的なトラックのパス
- `instruction`：追加するトラックを指定する必要あり
- `caption`：希望するスタイルの説明

**ユースケース**：
- 不完全な作品をアレンジ
- バッキングトラックを追加
- 音楽アイデアを自動完成

---

## ヘルパー関数

### understand_music

オーディオコードを分析して音楽についてのメタデータを抽出。

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
    print(f"歌詞：{result.lyrics}")
    print(f"BPM：{result.bpm}")
    print(f"キー：{result.keyscale}")
    print(f"長さ：{result.duration}秒")
    print(f"言語：{result.language}")
else:
    print(f"エラー：{result.error}")
```

**ユースケース**：
- 既存の音楽を分析
- オーディオコードからメタデータを抽出
- 生成パラメータをリバースエンジニアリング

---

### create_sample

自然言語の説明から完全な音楽サンプルを生成。これは「シンプルモード」/「インスピレーションモード」機能です。

```python
from acestep.inference import create_sample

result = create_sample(
    llm_handler=llm_handler,
    query="静かな夜のための柔らかいベンガルのラブソング",
    instrumental=False,
    vocal_language="bn",  # オプション：ベンガル語に制限
    temperature=0.85,
)

if result.success:
    print(f"Caption：{result.caption}")
    print(f"歌詞：{result.lyrics}")
    print(f"BPM：{result.bpm}")
    print(f"長さ：{result.duration}秒")
    print(f"キー：{result.keyscale}")
    print(f"インストゥルメンタルか：{result.instrumental}")
    
    # generate_musicと一緒に使用
    params = GenerationParams(
        caption=result.caption,
        lyrics=result.lyrics,
        bpm=result.bpm,
        duration=result.duration,
        keyscale=result.keyscale,
        vocal_language=result.language,
    )
else:
    print(f"エラー：{result.error}")
```

---

### format_sample

ユーザー提供のcaptionとlyricsをフォーマット・強化し、構造化されたメタデータを生成。

```python
from acestep.inference import format_sample

result = format_sample(
    llm_handler=llm_handler,
    caption="ラテンポップ、レゲトン",
    lyrics="[Verse 1]\nBailando en la noche...",
    user_metadata={"bpm": 95},  # オプション：特定の値を制約
    temperature=0.85,
)

if result.success:
    print(f"強化されたCaption：{result.caption}")
    print(f"フォーマットされた歌詞：{result.lyrics}")
    print(f"BPM：{result.bpm}")
    print(f"長さ：{result.duration}秒")
    print(f"キー：{result.keyscale}")
    print(f"検出された言語：{result.language}")
else:
    print(f"エラー：{result.error}")
```

---

## ベストプラクティス

### 1. Captionの書き方

**良いCaption**：
```python
# 具体的で説明的
caption="重低音とシンセサイザーリードのアップビートなエレクトロニックダンスミュージック"

# ムードとジャンルを含む
caption="アコースティックギターと柔らかいボーカルのメランコリックなインディーフォーク"

# 楽器を指定
caption="ピアノ、アップライトベース、ブラシドラムのジャズトリオ"
```

**避けるべき**：
```python
# 曖昧すぎる
caption="良い音楽"

# 矛盾
caption="速い遅い音楽"  # テンポの矛盾
```

### 2. パラメータチューニング

**最高品質のために**：
- baseモデルを使用し、`inference_steps=64` 以上
- `use_adg=True` を有効化
- `guidance_scale=7.0-9.0` を設定
- より良いタイムステップ分布のために `shift=3.0` を設定
- ロスレスオーディオ形式を使用（`audio_format="wav"`）

**速度のために**：
- turboモデルを使用し、`inference_steps=8`
- ADGを無効化（`use_adg=False`）
- `infer_method="ode"`（デフォルト）を使用
- 圧縮形式を使用（`audio_format="mp3"`）またはデフォルトのFLAC

**一貫性のために**：
- configで `use_random_seed=False` を設定
- 固定 `seeds` リストまたはparamsで単一 `seed` を使用
- `lm_temperature` を低く保つ（0.7-0.85）

**多様性のために**：
- configで `use_random_seed=True` を設定
- `lm_temperature` を増加（0.9-1.1）
- バリエーションのために `batch_size > 1` を使用

### 3. Durationガイドライン

- **インストゥルメンタル**：30-180秒が適切
- **歌詞付き**：自動検出を推奨（`duration=-1` を設定またはデフォルトのまま）
- **短いクリップ**：最小10-20秒
- **長尺**：最大600秒（10分）

### 4. LMの使用

**LMを有効にする場合（`thinking=True`）**：
- 自動メタデータ検出が必要
- caption改良が欲しい
- 最小限の入力から生成
- 多様な出力が必要

**LMを無効にする場合（`thinking=False`）**：
- すでに正確なメタデータがある
- より高速な生成が必要
- パラメータの完全な制御が欲しい

---

## トラブルシューティング

### よくある問題

**問題**：メモリ不足エラー
- **解決策**：`batch_size`、`inference_steps` を減らすか、CPUオフロードを有効化

**問題**：結果の品質が悪い
- **解決策**：`inference_steps` を増やす、`guidance_scale` を調整、baseモデルを使用

**問題**：結果がプロンプトと一致しない
- **解決策**：captionをより具体的に、`guidance_scale` を増やす、LM改良を有効化（`thinking=True`）

**問題**：生成が遅い
- **解決策**：turboモデルを使用、`inference_steps` を減らす、ADGを無効化

**問題**：LMがコードを生成しない
- **解決策**：`llm_handler` が初期化されていることを確認、`thinking=True` と `use_cot_metas=True` を確認

**問題**：シードが尊重されない
- **解決策**：configで `use_random_seed=False` を設定し、`seeds` リストまたはparamsで `seed` を提供

**問題**：カスタムタイムステップが機能しない
- **解決策**：タイムステップが1.0から0.0の浮動小数点リストで、適切に順序付けられていることを確認

---

詳細については以下を参照：
- メインREADME：[`../../README.md`](../../README.md)
- REST APIドキュメント：[`API.md`](API.md)
- Gradioデモガイド：[`GRADIO_GUIDE.md`](GRADIO_GUIDE.md)
- プロジェクトリポジトリ：[ACE-Step-1.5](https://github.com/yourusername/ACE-Step-1.5)
