# ACE-Step 1.5 LoRA トレーニングチュートリアル

## ハードウェア要件

| VRAM | 説明 |
|------|------|
| 16 GB（最低） | 通常は使用可能ですが、長い楽曲ではメモリ不足になる場合があります |
| 20 GB 以上（推奨） | フルレングスの楽曲に対応可能。トレーニング中のVRAM使用量は通常17 GB前後です |

> **ヒント：** トレーニング前の前処理段階では、VRAMを解放するためにGradioを複数回再起動する必要があります。具体的なタイミングは以降の手順で説明します。

## 免責事項

本チュートリアルでは、**ナユタン星人 (NayutalieN)** のアルバム *ナユタン星からの物体Y*（全13曲）をデモとして使用し、500エポック（バッチサイズ1）でトレーニングを行いました。**本チュートリアルはLoRAファインチューニング技術を理解するための教育目的のみに使用されます。ご自身のオリジナル作品でLoRAをトレーニングしてください。**

開発者として、私はナユタン星人の楽曲が大好きで、そのアルバムの一つを例として選びました。権利者の方で本チュートリアルが正当な権利を侵害していると思われる場合は、すぐにご連絡ください。有効な通知を受け次第、関連コンテンツを削除いたします。

技術は合理的かつ合法的に使用されるべきです。アーティストの創作を尊重し、オリジナルアーティストの名誉、権利、利益を**損害または傷つける**行為は行わないでください。

---

## データ準備

> **ヒント：** プログラミングに詳しくない方は、本ドキュメントをClaude Code / Codex CLI / Cursor / Copilotなどのコーディングツールに渡して、作業を代行してもらうことができます。

### 概要

各楽曲のトレーニングデータには以下が含まれます：

1. **音声ファイル** — `.mp3`、`.wav`、`.flac`、`.ogg`、`.opus` 形式に対応
2. **歌詞** — 音声ファイルと同名の `.lyrics.txt` ファイル（後方互換のため `.txt` も対応）
3. **アノテーションデータ** — `caption`、`bpm`、`keyscale`、`timesignature`、`language` などのメタデータ

### アノテーションデータ形式

完全なアノテーションデータをお持ちの場合は、JSONファイルを作成し、音声・歌詞と同じディレクトリに配置できます。ファイル構造は以下の通りです：

```
dataset/
├── song1.mp3               # 音声
├── song1.lyrics.txt        # 歌詞
├── song1.json              # アノテーション（任意）
├── song1.caption.txt       # キャプション（任意、JSONに含めることも可能）
├── song2.mp3
├── song2.lyrics.txt
├── song2.json
└── ...
```

JSONファイルの構造（すべてのフィールドは任意）：

```json
{
    "caption": "A high-energy J-pop track with synthesizer leads and fast tempo",
    "bpm": 190,
    "keyscale": "D major",
    "timesignature": "4",
    "language": "ja"
}
```

アノテーションデータがない場合は、後続のセクションで紹介する方法で取得できます。

---

### 歌詞

歌詞を音声ファイルと同名の `.lyrics.txt` ファイルとして保存し、同じディレクトリに配置してください。歌詞の正確性を確認してください。

スキャン時の歌詞ファイル検索優先順位：

1. `{ファイル名}.lyrics.txt`（推奨）
2. `{ファイル名}.txt`（後方互換）

#### 歌詞の文字起こし

既存の歌詞テキストがない場合は、以下のツールで文字起こしが可能です：

| ツール | 構造化タグ | 精度 | 使いやすさ | デプロイ方式 |
|--------|-----------|------|-----------|------------|
| [acestep-transcriber](https://huggingface.co/ACE-Step/acestep-transcriber) | なし | 誤字の可能性あり | 高難度（モデルのデプロイが必要） | セルフホスト |
| [Gemini](https://aistudio.google.com/) | あり | 誤字の可能性あり | 簡単 | 有料API |
| [Whisper](https://github.com/openai/whisper) | なし | 誤字の可能性あり | 普通 | セルフホスト / 有料API |
| [ElevenLabs](https://elevenlabs.io/app/developers) | なし | 誤字の可能性あり | 普通 | 有料API（無料枠あり） |

本プロジェクトでは `scripts/lora_data_prepare/` に対応する文字起こしスクリプトを提供しています：

- `whisper_transcription.py` — OpenAI Whisper APIによる文字起こし
- `elevenlabs_transcription.py` — ElevenLabs Scribe APIによる文字起こし

両スクリプトとも `process_folder()` メソッドによるフォルダ一括処理に対応しています。

#### 確認とクリーニング（必須）

文字起こしされた歌詞には誤字が含まれる可能性があり、**手動で確認・修正する必要があります**。

LRC形式の歌詞を使用している場合は、タイムスタンプを除去する必要があります。以下は簡単なクリーニング例です：

```python
import re

def clean_lrc_content(lines):
    """LRCファイルの内容をクリーニングし、タイムスタンプを除去"""
    result = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # タイムスタンプを除去 [mm:ss.x] [mm:ss.xx] [mm:ss.xxx]
        cleaned = re.sub(r"\[\d{2}:\d{2}\.\d{1,3}\]", "", line)
        result.append(cleaned)

    # 末尾の空行を除去
    while result and not result[-1]:
        result.pop()

    return result
```

#### 構造化タグ（任意）

歌詞に構造化タグ（`[Verse]`、`[Chorus]` など）が含まれていると、モデルが楽曲構造をより効果的に学習できます。構造化タグがなくてもトレーニングは可能です。

> **ヒント：** [Gemini](https://aistudio.google.com/) を使用して既存の歌詞に構造化タグを追加できます。

例：

```
[Intro]
La la la...

[Verse 1]
Walking down the empty street
Echoes dancing at my feet

[Chorus]
We are the stars tonight
Shining through the endless sky

[Bridge]
Close your eyes and feel the sound
```

---

### 自動アノテーション

#### 1. BPMとKeyの取得

[Key-BPM-Finder](https://vocalremover.org/key-bpm-finder) を使用してBPMとキーのアノテーションをオンラインで取得します：

1. ウェブページを開き、**Browse my files** をクリックして処理する音声ファイルを選択します（一度に多すぎるとフリーズする場合があります。分割して処理し、CSVを結合することを推奨）。処理はローカルで行われ、サーバーにはアップロードされません。
   ![key-bpm-finder-0.jpg](../pics/key-bpm-finder-0.jpg)

2. 処理完了後、**Export CSV** をクリックしてCSVファイルをダウンロードします。
   ![key-bpm-finder-1.jpg](../pics/key-bpm-finder-1.jpg)

3. CSVファイルの内容例：

   ```csv
   File,Artist,Title,BPM,Key,Camelot
   song1.wav,,,190,D major,10B
   song2.wav,,,128,A minor,8A
   ```

4. CSVファイルをデータセットフォルダに配置します。キャプションデータを追加する場合は、`Camelot` 列の後に新しい列を追加してください。

#### 2. Captionの取得

以下の方法で楽曲のキャプションを取得できます：

- **acestep-5Hz-lmを使用**（0.6B / 1.7B / 4B）— Gradio UIのAuto Label機能から呼び出し（後続の手順を参照）
- **Gemini APIを使用** — スクリプト `scripts/lora_data_prepare/gemini_caption.py` を参照。`process_folder()` による一括処理に対応し、各音声ファイルに対して以下を生成します：
  - `{ファイル名}.lyrics.txt` — 歌詞
  - `{ファイル名}.caption.txt` — キャプション

---

## データの前処理

データの準備が完了したら、Gradio UIを使用してデータの確認と前処理を行います。

> **重要：** 起動スクリプトを使用する場合、サービスの事前初期化を無効にするために起動パラメータを変更する必要があります：
>
> - **Windows** (`start_gradio_ui.bat`)：`if not defined INIT_SERVICE set INIT_SERVICE=--init_service true` を `if not defined INIT_SERVICE set INIT_SERVICE=--init_service false` に変更
> - **Linux/macOS** (`start_gradio_ui.sh`)：`: "${INIT_SERVICE:=--init_service true}"` を `: "${INIT_SERVICE:=--init_service false}"` に変更

Gradio UIを起動します（起動スクリプトまたは `acestep/acestep_v15_pipeline.py` を直接実行）。

### ステップ 1：モデルの読み込み

- **LMでキャプションを生成する場合：** 初期化時に使用したいLMモデル（acestep-5Hz-lm-0.6B / 1.7B / 4B）を選択します。
  ![](../pics/00_select_model_to_load.jpg)

- **LMを使用しない場合：** LMモデルを選択しないでください。
  ![](../pics/00_select_model_to_load_1.jpg)

### ステップ 2：データの読み込み

**LoRA Training** タブに切り替え、データセットディレクトリのパスを入力し、**Scan** をクリックします。

スキャナーは以下のファイルを自動認識します：

| ファイル | 説明 |
|---------|------|
| `*.mp3` / `*.wav` / `*.flac` / ... | 音声ファイル |
| `{ファイル名}.lyrics.txt`（または `{ファイル名}.txt`） | 歌詞 |
| `{ファイル名}.caption.txt` | キャプション |
| `{ファイル名}.json` | アノテーションメタデータ（caption / bpm / keyscale / timesignature / language） |
| `*.csv` | BPM / Key の一括アノテーション（Key-BPM-Finderからエクスポート） |

![](../pics/01_load_dataset_path.jpg)

### ステップ 3：データセットのプレビューと調整

- **Duration** — 音声ファイルから自動的に読み取り
- **Lyrics** — 対応する `.lyrics.txt` ファイルが必要（`.txt` も対応）
- **Labeled** — キャプションがある場合は ✅、ない場合は ❌ と表示
- **BPM / Key / Caption** — JSONまたはCSVファイルから読み込み
- データセットがすべてインストゥルメンタルでない場合は、**All Instrumental** のチェックを外してください
- **Format Lyrics** と **Transcribe Lyrics** は現在無効化されています（[acestep-transcriber](https://huggingface.co/ACE-Step/acestep-transcriber) 未接続のため、LMの直接使用はハルシネーションが発生しやすい）
- **Custom Trigger Tag** を入力してください（現在は効果が限定的です。`Replace Caption` 以外であれば問題ありません）
- **Genre Ratio** はキャプションの代わりにジャンルを使用するサンプルの割合を制御します。現在のLMが生成するジャンル記述はキャプションに遠く及ばないため、0のままにして��ださい

![](../pics/02_preview_dataset.jpg)

### ステップ 4：Auto Label Data

- 既にキャプションがある場合は、このステップをスキップできます
- データにキャプションがない場合は、LM推論で生成できます
- BPM / Key の値が不足している場合は、まず [Key-BPM-Finder](https://vocalremover.org/key-bpm-finder) で取得してください。LMによる直接生成はハルシネーションが発生します

![](../pics/03_label_data.jpg)

### ステップ 5：データのプレビューと編集

必要に応じて、データを一件ずつ確認・修正できます。**各データの編集後は必ず保存をクリックしてください。**

![](../pics/04_edit_data.jpg)

### ステップ 6：データセットの保存

保存パスを入力し、データセットをJSONファイルとして保存します。

![](../pics/05_save_dataset.jpg)

### ステップ 7：前処理によるTensorファイルの生成

> **注意：** 以前にLMでキャプションを生成し、VRAMが不足している場合は、まずGradioを再起動してVRAMを解放してください。再起動時は**LMモデルを選択しないでください**。再起動後、保存したJSONファイルのパスを入力して読み込みます。

Tensorファイルの保存パスを入力し、前処理を開始して完了を待ちます。

![](../pics/06_preprocess_tensor.jpg)

---

## トレーニング

> **注意：** Tensorファイル生成後も、VRAMを解放するためにGradioを再起動することを推奨します。

1. **Train LoRA** タブに切り替え、Tensorファイルのパスを入力してデータセットを読み込みます。
2. トレーニングパラメータに詳しくない場合は、デフォルト値で問題ありません。

### パラメータ参考

| パラメータ | 説明 | 推奨値 |
|-----------|------|--------|
| **Max Epochs** | データセットのサイズに応じて調整 | 約100曲 → 500エポック、10〜20曲 → 800エポック（参考値） |
| **Batch Size** | VRAMに余裕がある場合は増加可能 | 1（デフォルト）、VRAMが十分であれば 2 または 4 |
| **Save Every N Epochs** | チェックポイントの保存間隔 | Max Epochsが小さい場合は短く、大きい場合は長く設定 |

> 上記の数値は参考値です。実際の状況に応じて調整してください。

> **💡 LoKr のおすすめ：** LoKR はトレーニング効率を大幅に向上させました。以前は1時間かかっていたトレーニングが、わずか5分で完了します——10倍以上の高速化です。これは消費者向けGPUでのトレーニングにとって非常に重要です。**Train LoKr** タブで LoKr トレーニングをお試しいただくか、[Side-Step](https://github.com/koda-dernet/Side-Step) ツールキットでCLIベースの LoKr ワークフローをご利用ください。詳細は [Training Guide](../sidestep/Training%20Guide.md) をご参照ください。

3. **Start Training** をクリックし、トレーニングの完了を待ちます。

![](../pics/07_train.jpg)

---

## LoRAの使用

1. トレーニング完了後、**Gradioを再起動**し、モデルを再読み込みします（LMモデルは選択しないでください）。
2. モデルの初期化完了後、トレーニング済みのLoRAウェイトを読み込みます。
   ![](../pics/08_load_lora.jpg)
3. 音楽生成を開始します。

おめでとうございます！LoRAトレーニングの全プロセスが完了しました。

---

## 高度なトレーニング：Side-Step

LoRAトレーニングをより細かく制御したい場合——修正されたタイムステップサンプリング、LoKRアダプター、CLIベースのワークフロー、VRAM最適化、勾配感度分析など——コミュニティ開発の **[Side-Step](https://github.com/koda-dernet/Side-Step)** ツールキットが高度な代替手段を提供します。ドキュメントは本リポジトリの `docs/sidestep/` に収録されています。

| トピック | 説明 |
|---------|------|
| [Getting Started](../sidestep/Getting%20Started.md) | インストール、前提条件、初回セットアップ |
| [End-to-End Tutorial](../sidestep/End-to-End%20Tutorial.md) | 生音声ファイルから生成までの完全ガイド |
| [Dataset Preparation](../sidestep/Dataset%20Preparation.md) | JSONスキーマ、音声形式、メタデータフィールド、カスタムタグ |
| [Training Guide](../sidestep/Training%20Guide.md) | LoRA vs LoKR、修正モード vs バニラモード、ハイパーパラメータガイド |
| [Using Your Adapter](../sidestep/Using%20Your%20Adapter.md) | 出力ディレクトリ構造、Gradioでの読み込み、LoKRの制限 |
| [VRAM Optimization Guide](../sidestep/VRAM%20Optimization%20Guide.md) | VRAM最適化戦略とGPUティア別設定 |
| [Estimation Guide](../sidestep/Estimation%20Guide.md) | ターゲットトレーニングのための勾配感度分析 |
| [Shift and Timestep Sampling](../sidestep/Shift%20and%20Timestep%20Sampling.md) | トレーニングタイムステップの仕組みとSide-Stepの違い |
| [Preset Management](../sidestep/Preset%20Management.md) | ビルトインプリセット、保存/読み込み/インポート/エクスポート |
| [The Settings Wizard](../sidestep/The%20Settings%20Wizard.md) | ウィザード設定の完全リファレンス |
| [Model Management](../sidestep/Model%20Management.md) | チェックポイント構造とファインチューンサポート |
| [Windows Notes](../sidestep/Windows%20Notes.md) | Windows固有のセットアップと回避策 |
