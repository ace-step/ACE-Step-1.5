# ACE-Step 1.5 インストールガイド

**Language / 语言 / 言語:** [English](../en/INSTALL.md) | [中文](../zh/INSTALL.md) | [日本語](INSTALL.md)

---

## 目次

- [動作要件](#動作要件)
- [クイックスタート（全プラットフォーム）](#クイックスタート全プラットフォーム)
- [起動スクリプト](#-起動スクリプト)
- [Windows ポータブルパッケージ](#-windows-ポータブルパッケージ)
- [AMD / ROCm GPU](#amd--rocm-gpu)
- [Intel GPU](#intel-gpu)
- [CPUのみモード](#cpuのみモード)
- [Linux の注意事項](#linux-の注意事項)
- [環境変数 (.env)](#環境変数-env)
- [コマンドラインオプション](#コマンドラインオプション)
- [モデルダウンロード](#-モデルダウンロード)
- [どのモデルを選ぶべき？](#-どのモデルを選ぶべき)
- [開発](#開発)

---

## 動作要件

| 項目 | 要件 |
|------|------|
| Python | 3.11-3.12（安定版、プレリリース版は不可）<br>**注意：** Windows 上の ROCm は Python 3.12 が必要です |
| GPU | CUDA GPU 推奨。MPS / ROCm / Intel XPU / CPU もサポート |
| VRAM | DiTのみモード ≥4GB、LLM+DiT ≥6GB |
| ディスク | コアモデルに約10GB |

---

## クイックスタート（全プラットフォーム）

### 1. uv のインストール（パッケージマネージャー）

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. クローン & インストール

```bash
git clone https://github.com/ACE-Step/ACE-Step-1.5.git
cd ACE-Step-1.5
uv sync
```

### 3. 起動

**Gradio Web UI（推奨）：**

```bash
uv run acestep
```

**REST API サーバー：**

```bash
uv run acestep-api
```

**Python を直接使用**（Conda / venv / システム Python）：

```bash
# まず環境をアクティベートしてから：
python acestep/acestep_v15_pipeline.py          # Gradio UI
python acestep/api_server.py                     # REST API
```

> 初回実行時にモデルが自動ダウンロードされます。http://localhost:7860（Gradio）または http://localhost:8001（API）を開いてください。

---

## 🚀 起動スクリプト

全プラットフォーム対応のすぐに使える起動スクリプトです。これらのスクリプトは環境検出、依存関係のインストール、アプリケーションの起動を自動的に処理します。すべてのスクリプトはデフォルトで起動時に更新チェックを行います（設定変更可能）。

### 利用可能なスクリプト

| プラットフォーム | スクリプト | 説明 |
|----------|--------|------|
| **Windows** | `start_gradio_ui.bat` | Gradio Web UI を起動（CUDA） |
| **Windows** | `start_api_server.bat` | REST API サーバーを起動（CUDA） |
| **Windows** | `start_gradio_ui_rocm.bat` | Gradio Web UI を起動（AMD ROCm） |
| **Windows** | `start_api_server_rocm.bat` | REST API サーバーを起動（AMD ROCm） |
| **Linux** | `start_gradio_ui.sh` | Gradio Web UI を起動（CUDA） |
| **Linux** | `start_api_server.sh` | REST API サーバーを起動（CUDA） |
| **macOS** | `start_gradio_ui_macos.sh` | Gradio Web UI を起動（MLX） |
| **macOS** | `start_api_server_macos.sh` | REST API サーバーを起動（MLX） |

### Windows

```bash
# Gradio Web UI を起動（NVIDIA CUDA）
start_gradio_ui.bat

# REST API サーバーを起動（NVIDIA CUDA）
start_api_server.bat

# Gradio Web UI を起動（AMD ROCm）
start_gradio_ui_rocm.bat

# REST API サーバーを起動（AMD ROCm）
start_api_server_rocm.bat
```

> **ROCm ユーザー：** ROCm スクリプト（`start_gradio_ui_rocm.bat`、`start_api_server_rocm.bat`）は `HSA_OVERRIDE_GFX_VERSION`、`ACESTEP_LM_BACKEND=pt`、`MIOPEN_FIND_MODE=FAST` およびその他の ROCm 固有の環境変数を自動設定します。CUDA/ROCm wheel の競合を避けるため、別の `venv_rocm` 仮想環境を使用します。

### Linux

```bash
# 実行権限を付与（初回のみ）
chmod +x start_gradio_ui.sh start_api_server.sh

# Gradio Web UI を起動
./start_gradio_ui.sh

# REST API サーバーを起動
./start_api_server.sh
```

> **注意：** Git はシステムのパッケージマネージャーでインストールする必要があります（`sudo apt install git`、`sudo yum install git`、`sudo pacman -S git`）。

### macOS（Apple Silicon / MLX）

macOS スクリプトはネイティブの Apple Silicon アクセラレーション（M1/M2/M3/M4）のために **MLX バックエンド**を使用します。

```bash
# 実行権限を付与（初回のみ）
chmod +x start_gradio_ui_macos.sh start_api_server_macos.sh

# MLX バックエンドで Gradio Web UI を起動
./start_gradio_ui_macos.sh

# MLX バックエンドで REST API サーバーを起動
./start_api_server_macos.sh
```

macOS スクリプトはネイティブの Apple Silicon アクセラレーションのために `ACESTEP_LM_BACKEND=mlx` と `--backend mlx` を自動設定し、非 arm64 マシンでは PyTorch バックエンドにフォールバックします。

> **注意：** Git は `xcode-select --install` または `brew install git` でインストールしてください。

### スクリプトの機能

- 起動時の更新チェック（デフォルトで有効、設定変更可能）
- 自動環境検出（ポータブル Python または uv）
- 必要に応じて `uv` を自動インストール
- ダウンロードソースの設定（HuggingFace/ModelScope）
- モデルとパラメータのカスタマイズ

### 設定の変更方法

すべての設定可能なオプションは、各スクリプトの先頭で変数として定義されています。カスタマイズするには、テキストエディタでスクリプトを開き、変数の値を変更してください。

**例：UI 言語を中国語に変更し、1.7B LM モデルを使用する**

<table>
<tr><th>Windows (.bat)</th><th>Linux / macOS (.sh)</th></tr>
<tr><td>

`start_gradio_ui.bat` で以下の行を見つけます：
```batch
set LANGUAGE=en
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-0.6B
```
以下のように変更します：
```batch
set LANGUAGE=zh
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-1.7B
```

</td><td>

`start_gradio_ui.sh` で以下の行を見つけます：
```bash
LANGUAGE="en"
LM_MODEL_PATH="--lm_model_path acestep-5Hz-lm-0.6B"
```
以下のように変更します：
```bash
LANGUAGE="zh"
LM_MODEL_PATH="--lm_model_path acestep-5Hz-lm-1.7B"
```

</td></tr>
</table>

**例：起動時の更新チェックを無効にする**

<table>
<tr><th>Windows (.bat)</th><th>Linux / macOS (.sh)</th></tr>
<tr><td>

```batch
REM set CHECK_UPDATE=true
set CHECK_UPDATE=false
```

</td><td>

```bash
# CHECK_UPDATE="true"
CHECK_UPDATE="false"
```

</td></tr>
</table>

**例：コメントアウトされたオプションを有効にする** — コメントプレフィックス（.bat は `REM`、.sh は `#`）を削除します：

<table>
<tr><th>Windows (.bat)</th><th>Linux / macOS (.sh)</th></tr>
<tr><td>

変更前：
```batch
REM set SHARE=--share
```
変更後：
```batch
set SHARE=--share
```

</td><td>

変更前：
```bash
# SHARE="--share"
```
変更後：
```bash
SHARE="--share"
```

</td></tr>
</table>

**主な設定可能オプション：**

| オプション | Gradio UI | API サーバー | 説明 |
|--------|:---------:|:----------:|------|
| `LANGUAGE` | ✅ | — | UI 言語：`en`、`zh`、`he`、`ja` |
| `PORT` | ✅ | ✅ | サーバーポート（デフォルト：7860 / 8001） |
| `SERVER_NAME` / `HOST` | ✅ | ✅ | バインドアドレス（`127.0.0.1` または `0.0.0.0`） |
| `CHECK_UPDATE` | ✅ | ✅ | 起動時の更新チェック（`true` / `false`） |
| `CONFIG_PATH` | ✅ | — | DiT モデル（`acestep-v15-turbo` など） |
| `LM_MODEL_PATH` | ✅ | ✅ | LM モデル（`acestep-5Hz-lm-0.6B` / `1.7B` / `4B`） |
| `DOWNLOAD_SOURCE` | ✅ | ✅ | ダウンロードソース（`huggingface` / `modelscope`） |
| `SHARE` | ✅ | — | 公開 Gradio リンクを作成 |
| `INIT_LLM` | ✅ | — | LLM の強制オン/オフ（`true` / `false` / `auto`） |
| `OFFLOAD_TO_CPU` | ✅ | — | 低 VRAM GPU 向け CPU オフロード |

### 更新 & メンテナンスツール

| スクリプト（Windows） | スクリプト（Linux/macOS） | 用途 |
|-------------------|----------------------|------|
| `check_update.bat` | `check_update.sh` | GitHub から更新をチェック |
| `merge_config.bat` | `merge_config.sh` | 更新後にバックアップされた設定をマージ |
| `install_uv.bat` | `install_uv.sh` | uv パッケージマネージャーをインストール |
| `quick_test.bat` | `quick_test.sh` | 環境セットアップをテスト |

**更新ワークフロー：**

```bash
# Windows                          # Linux / macOS
check_update.bat                    ./check_update.sh
merge_config.bat                    ./merge_config.sh
```

---

## 🪟 Windows ポータブルパッケージ

Windows ユーザー向けに、依存関係がプリインストールされたポータブルパッケージを提供しています：

1. ダウンロードして解凍：[ACE-Step-1.5.7z](https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z)
2. `python_embeded` に全依存関係がプリインストール済み
3. **要件：** CUDA 12.8

### クイックスタートスクリプト

| スクリプト | 説明 |
|------------|------|
| `start_gradio_ui.bat` | Gradio Web UI を起動 |
| `start_api_server.bat` | REST API サーバーを起動 |

両スクリプトは自動環境検出、自動 `uv` インストール、ダウンロードソース設定、Git 更新チェック（オプション）、モデル・パラメータのカスタマイズに対応しています。

### 設定

**`start_gradio_ui.bat`：**

```batch
REM UI言語 (en, zh, he, ja)
set LANGUAGE=ja

REM ダウンロードソース (auto, huggingface, modelscope)
set DOWNLOAD_SOURCE=--download-source huggingface

REM Git更新チェック (true/false)
set CHECK_UPDATE=true

REM モデル設定
set CONFIG_PATH=--config_path acestep-v15-turbo
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-1.7B
```

### 更新 & メンテナンス

| スクリプト | 用途 |
|------------|------|
| `check_update.bat` | GitHub から更新をチェック |
| `merge_config.bat` | 更新後にバックアップされた設定をマージ |
| `install_uv.bat` | uv パッケージマネージャーをインストール |
| `quick_test.bat` | 環境セットアップをテスト |

---

## AMD / ROCm GPU

> ⚠️ `uv run acestep` は CUDA PyTorch wheels をインストールするため、既存の ROCm 環境を上書きする可能性があります。

### 推奨ワークフロー

```bash
# 1. 仮想環境を作成してアクティベート
python -m venv .venv
source .venv/bin/activate

# 2. ROCm 対応 PyTorch をインストール
pip install torch --index-url https://download.pytorch.org/whl/rocm6.0

# 3. ACE-Step をインストール
pip install -e .

# 4. サービスを起動
python -m acestep.acestep_v15_pipeline --port 7680
```

### GPU 検出のトラブルシューティング

「No GPU detected, running on CPU」と表示される場合：

1. 診断ツールを実行：`python scripts/check_gpu.py`
2. RDNA3 GPU の場合、`HSA_OVERRIDE_GFX_VERSION` を設定：

| GPU | 値 |
|-----|---|
| RX 7900 XT/XTX, RX 9070 XT | `export HSA_OVERRIDE_GFX_VERSION=11.0.0` |
| RX 7800 XT, RX 7700 XT | `export HSA_OVERRIDE_GFX_VERSION=11.0.1` |
| RX 7600 | `export HSA_OVERRIDE_GFX_VERSION=11.0.2` |

3. Windows では `start_gradio_ui_rocm.bat` / `start_api_server_rocm.bat` を使用
4. ROCm インストールを確認：`rocm-smi`

### Linux（cachy-os / RDNA4）

詳細は [ACE-Step1.5-Rocm-Manual-Linux.md](../en/ACE-Step1.5-Rocm-Manual-Linux.md) を参照してください。

---

## Intel GPU

| 項目 | 詳細 |
|------|------|
| テスト済みデバイス | Windows ノートPC、Ultra 9 285H 内蔵グラフィックス |
| オフロード | デフォルトで無効 |
| コンパイル & 量子化 | デフォルトで有効 |
| LLM 推論 | サポート（`acestep-5Hz-lm-0.6B` でテスト済み） |
| nanovllm アクセラレーション | Intel GPU では未サポート |
| テスト環境 | PyTorch 2.8.0（[Intel Extension for PyTorch](https://pytorch-extension.intel.com/?request=platform)） |

> 注意：2分以上の音声生成時、LLM 推論速度が低下する場合があります。Intel ディスクリート GPU は動作が期待されますが、まだテストされていません。

---

## CPUのみモード

ACE-Step は CPU で**推論のみ**実行できますが、速度は大幅に遅くなります。

- CPU でのトレーニング（LoRA を含む）は**推奨されません**。
- 低 VRAM システムでは、DiTのみモード（LLM 無効）がサポートされています。

GPU がない場合：
- クラウド GPU プロバイダーの利用
- 推論のみのワークフロー
- `ACESTEP_INIT_LLM=false` で DiTのみモードを使用

---

## Linux の注意事項

### Python 3.11 プレリリース版の問題

一部の Linux ディストリビューション（Ubuntu を含む）には Python 3.11.0rc1 プレリリース版が同梱されており、vLLM バックエンドでセグメンテーションフォルトを引き起こす可能性があります。

**推奨：** 安定版 Python（≥ 3.11.12）を使用してください。Ubuntu では deadsnakes PPA からインストールできます。

Python のアップグレードができない場合、PyTorch バックエンドを使用：

```bash
uv run acestep --backend pt
```

---

## 環境変数 (.env)

```bash
cp .env.example .env   # コピーして編集
```

### 主要な変数

| 変数 | 値 | 説明 |
|------|---|------|
| `ACESTEP_INIT_LLM` | `auto` / `true` / `false` | LLM 初期化モード |
| `ACESTEP_CONFIG_PATH` | モデル名 | DiT モデルパス |
| `ACESTEP_LM_MODEL_PATH` | モデル名 | LM モデルパス |
| `ACESTEP_DOWNLOAD_SOURCE` | `auto` / `huggingface` / `modelscope` | ダウンロードソース |
| `ACESTEP_API_KEY` | 文字列 | API 認証キー |

### LLM 初期化 (`ACESTEP_INIT_LLM`)

処理フロー：`GPU 検出 → ACESTEP_INIT_LLM オーバーライド → モデル読み込み`

| 値 | 動作 |
|----|------|
| `auto`（または空） | GPU 自動検出結果を使用（推奨） |
| `true` / `1` / `yes` | GPU 検出後に LLM を強制有効化（OOM の可能性あり） |
| `false` / `0` / `no` | 強制無効化、純粋な DiT モード |

**シナリオ別 `.env` の例：**

```bash
# 自動モード（推奨）
ACESTEP_INIT_LLM=auto

# 低 VRAM GPU で強制有効化
ACESTEP_INIT_LLM=true
ACESTEP_LM_MODEL_PATH=acestep-5Hz-lm-0.6B

# LLM を無効化して高速生成
ACESTEP_INIT_LLM=false
```

---

## コマンドラインオプション

### Gradio UI (`acestep`)

| オプション | デフォルト | 説明 |
|------------|-----------|------|
| `--port` | 7860 | サーバーポート |
| `--server-name` | 127.0.0.1 | サーバーアドレス（ネットワークアクセスには `0.0.0.0`） |
| `--share` | false | 公開 Gradio リンクを作成 |
| `--language` | en | UI 言語：`en`、`zh`、`he`、`ja` |
| `--init_service` | false | 起動時にモデルを自動初期化 |
| `--init_llm` | auto | LLM 初期化：`true` / `false` / 省略で自動 |
| `--config_path` | auto | DiT モデル（例：`acestep-v15-turbo`） |
| `--lm_model_path` | auto | LM モデル（例：`acestep-5Hz-lm-1.7B`） |
| `--offload_to_cpu` | auto | CPU オフロード（GPU ティアに基づいて自動設定） |
| `--download-source` | auto | モデルソース：`auto` / `huggingface` / `modelscope` |
| `--enable-api` | false | Gradio UI と同時に REST API エンドポイントを有効化 |

**例：**

```bash
# ネットワーク公開 + 日本語 UI
uv run acestep --server-name 0.0.0.0 --share --language ja

# 起動時にモデルを事前初期化
uv run acestep --init_service true --config_path acestep-v15-turbo

# ModelScope からダウンロード
uv run acestep --download-source modelscope
```

---

## 📥 モデルダウンロード

初回実行時にモデルが [HuggingFace](https://huggingface.co/ACE-Step/Ace-Step1.5) または [ModelScope](https://modelscope.cn/organization/ACE-Step) から自動ダウンロードされます。

### CLI ダウンロード

```bash
uv run acestep-download                              # メインモデルをダウンロード
uv run acestep-download --all                         # 全モデルをダウンロード
uv run acestep-download --download-source modelscope  # ModelScope から
uv run acestep-download --model acestep-v15-sft       # 特定のモデル
uv run acestep-download --list                        # 利用可能な全モデルを一覧表示
```

### 手動ダウンロード (huggingface-cli)

```bash
# メインモデル（vae, Qwen3-Embedding-0.6B, acestep-v15-turbo, acestep-5Hz-lm-1.7B）
huggingface-cli download ACE-Step/Ace-Step1.5 --local-dir ./checkpoints

# オプションモデル
huggingface-cli download ACE-Step/acestep-5Hz-lm-0.6B --local-dir ./checkpoints/acestep-5Hz-lm-0.6B
huggingface-cli download ACE-Step/acestep-5Hz-lm-4B --local-dir ./checkpoints/acestep-5Hz-lm-4B
```

### 利用可能なモデル

| モデル | 説明 | HuggingFace |
|--------|------|-------------|
| **Ace-Step1.5**（メイン） | コア：vae, Qwen3-Embedding-0.6B, acestep-v15-turbo, acestep-5Hz-lm-1.7B | [リンク](https://huggingface.co/ACE-Step/Ace-Step1.5) |
| acestep-5Hz-lm-0.6B | 軽量 LM（0.6B パラメータ） | [リンク](https://huggingface.co/ACE-Step/acestep-5Hz-lm-0.6B) |
| acestep-5Hz-lm-4B | 大規模 LM（4B パラメータ） | [リンク](https://huggingface.co/ACE-Step/acestep-5Hz-lm-4B) |
| acestep-v15-base | ベース DiT モデル | [リンク](https://huggingface.co/ACE-Step/acestep-v15-base) |
| acestep-v15-sft | SFT DiT モデル | [リンク](https://huggingface.co/ACE-Step/acestep-v15-sft) |
| acestep-v15-turbo-shift1 | Turbo DiT（shift1） | [リンク](https://huggingface.co/ACE-Step/acestep-v15-turbo-shift1) |
| acestep-v15-turbo-shift3 | Turbo DiT（shift3） | [リンク](https://huggingface.co/ACE-Step/acestep-v15-turbo-shift3) |
| acestep-v15-turbo-continuous | Turbo DiT（continuous shift 1-5） | [リンク](https://huggingface.co/ACE-Step/acestep-v15-turbo-continuous) |

---

## 💡 どのモデルを選ぶべき？

ACE-Step は GPU の VRAM に自動適応します。UI は検出された GPU ティアに基づいてすべての設定（LM モデル、バックエンド、オフロード、量子化）を事前構成します：

| GPU VRAM | 推奨 LM モデル | バックエンド | 備考 |
|----------|---------------|-------------|------|
| **≤6GB** | なし（DiTのみ） | — | LM はデフォルトで無効；INT8 量子化 + 完全 CPU オフロード |
| **6-8GB** | `acestep-5Hz-lm-0.6B` | `pt` | 軽量 LM、PyTorch バックエンド |
| **8-16GB** | `0.6B` / `1.7B` | `vllm` | 8-12GB は 0.6B、12-16GB は 1.7B |
| **16-24GB** | `acestep-5Hz-lm-1.7B` | `vllm` | 20GB+ で 4B 利用可能；20GB+ でオフロード不要 |
| **≥24GB** | `acestep-5Hz-lm-4B` | `vllm` | 最高品質、すべてのモデルがオフロードなしで動作 |

> 📖 GPU 互換性の詳細（ティアテーブル、時間制限、バッチサイズ、アダプティブ UI デフォルト、メモリ最適化）は [GPU 互換性ガイド](GPU_COMPATIBILITY.md) を参照してください。

---

## 開発

```bash
# 依存関係を追加
uv add package-name
uv add --dev package-name

# 全依存関係を更新
uv sync --upgrade
```
