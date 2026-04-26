# GPU 互換性ガイド

ACE-Step 1.5 は GPU の VRAM に自動的に適応し、生成時間の制限、使用可能な LM モデル、オフロード戦略、UI デフォルト設定を調整します。システムは起動時に GPU メモリを検出し、最適な設定を自動構成します。

## GPU ティア構成

| VRAM | ティア | XL (4B) DiT | LM モデル | 推奨 LM | バックエンド | 最大時間 (LM有 / LM無) | 最大バッチ (LM有 / LM無) | オフロード | 量子化 |
|------|--------|:-----------:|-----------|---------|-------------|------------------------|--------------------------|------------|--------|
| ≤4GB | Tier 1 | ❌ | なし | — | pt | 4分 / 6分 | 1 / 1 | CPU + DiT | INT8 |
| 4-6GB | Tier 2 | ❌ | なし | — | pt | 8分 / 10分 | 1 / 1 | CPU + DiT | INT8 |
| 6-8GB | Tier 3 | ❌ | 0.6B | 0.6B | pt | 8分 / 10分 | 2 / 2 | CPU + DiT | INT8 |
| 8-12GB | Tier 4 | ❌ | 0.6B | 0.6B | vllm | 8分 / 10分 | 2 / 4 | CPU + DiT | INT8 |
| 12-16GB | Tier 5 | ⚠️ | 0.6B, 1.7B | 1.7B | vllm | 8分 / 10分 | 4 / 4 | CPU | INT8 |
| 16-20GB | Tier 6a | ✅ (オフロード) | 0.6B, 1.7B | 1.7B | vllm | 8分 / 10分 | 4 / 8 | CPU | INT8 |
| 20-24GB | Tier 6b | ✅ | 0.6B, 1.7B, 4B | 1.7B | vllm | 8分 / 8分 | 8 / 8 | なし | なし |
| ≥24GB | 無制限 | ✅ | 全モデル (0.6B, 1.7B, 4B) | 4B | vllm | 10分 / 10分 | 8 / 8 | なし | なし |

> **XL (4B) DiT 列**: ❌ = 非対応, ⚠️ = 限定的（オフロード + 量子化が必要、12-16GBでは積極的なオフロードで動作可能）, ✅ (オフロード) = CPUオフロードで対応, ✅ = 完全対応。XLモデルの重みは約9GB（bf16）、2Bは約4.7GB。すべてのLMモデルがXLと互換性があります。

### 列の説明

- **LM モデル**: このティアでロードできる 5Hz 言語モデルのサイズ
- **推奨 LM**: UI でこのティアにデフォルト選択される LM モデル
- **バックエンド**: LM 推論バックエンド（`vllm` は十分な VRAM を持つ NVIDIA GPU 向け、`pt` は PyTorch フォールバック、`mlx` は Apple Silicon 向け）
- **オフロード**:
  - **CPU + DiT**: すべてのモデル（DiT、VAE、テキストエンコーダー）を未使用時に CPU にオフロード；DiT もステップ間でオフロード
  - **CPU**: VAE とテキストエンコーダーを CPU にオフロード；DiT は GPU に保持
  - **なし**: すべてのモデルを GPU に保持
- **量子化**: VRAM 使用量を削減するため、デフォルトで INT8 重み量子化を有効にするかどうか

## アダプティブ UI デフォルト

Gradio UI は検出された GPU ティアに基づいて自動的に設定されます：

- **LM 初期化チェックボックス**: LM をサポートするティア（Tier 3+）ではデフォルトでチェック、Tier 1-2 ではチェックなし・無効
- **LM モデルパス**: ティアの推奨モデルが自動入力；ドロップダウンには互換モデルのみ表示
- **バックエンドドロップダウン**: Tier 1-3 では `pt`/`mlx` に制限（vllm KV キャッシュがメモリを消費しすぎる）；Tier 4+ ではすべてのバックエンドが利用可能
- **CPU オフロード / DiT オフロード**: 低ティアではデフォルトで有効、高ティアでは無効
- **量子化**: Tier 1-6a ではデフォルトで有効、Tier 6b+ では無効（十分な VRAM）
- **モデルコンパイル**: すべてのティアでデフォルトで有効（量子化に必要）

互換性のないオプションを手動で選択した場合（例：6GB GPU で vllm を使用しようとした場合）、システムは警告を表示し、互換性のある設定に自動フォールバックします。

## ランタイム安全機能

- **VRAM ガード**: 各推論前に VRAM 要件を推定し、必要に応じてバッチサイズを自動削減
- **アダプティブ VAE デコード**: 3 段階フォールバック：GPU タイルデコード → GPU デコード+CPU オフロード → 完全 CPU デコード
- **自動チャンクサイズ**: VAE デコードチャンクサイズが利用可能な空き VRAM に適応（64/128/256/512/1024/1536）
- **時間/バッチクランプ**: ティアの制限を超える値を要求した場合、警告とともに自動調整

## 注意事項

- **デフォルト設定** は検出された GPU メモリに基づいて自動構成されます
- **LM モード** は Chain-of-Thought 生成とオーディオ理解に使用される言語モデルを指します
- **Flash Attention** は自動検出され、利用可能な場合に有効化されます
- **制約付きデコード**: LM が初期化されると、LM の時間生成も GPU ティアの最大時間制限内に制約され、CoT 生成時のメモリ不足エラーを防ぎます
- VRAM ≤6GB の GPU（Tier 1-2）では、DiT モデル用のメモリを確保するため、デフォルトで LM 初期化が無効になります
- コマンドライン引数または Gradio UI で設定を手動で上書きできます

> **コミュニティ貢献歓迎**: 上記の GPU ティア構成は一般的なハードウェアでのテストに基づいています。お使いのデバイスの実際のパフォーマンスがこれらのパラメータと異なる場合（例：より長い時間やより大きなバッチサイズを処理できる）、より徹底的なテストを行い、`acestep/gpu_config.py` の構成を最適化する PR を提出することを歓迎します。

## メモリ最適化のヒント

1. **超低 VRAM (≤6GB)**: LM 初期化なしの DiT のみモードを使用。INT8 量子化と完全 CPU オフロードが必須。VAE デコードは自動的に CPU にフォールバックする場合があります。
2. **低 VRAM (6-8GB)**: `pt` バックエンドで 0.6B LM モデルを使用可能。オフロードを有効に保ちます。
3. **中 VRAM (8-16GB)**: 0.6B または 1.7B LM モデルを使用。Tier 4+ では `vllm` バックエンドが良好に動作します。
4. **高 VRAM (16-24GB)**: より大きな LM モデル（1.7B 推奨）を有効化。20GB+ では量子化はオプションになります。
5. **超高 VRAM (≥24GB)**: すべてのモデルがオフロードや量子化なしで動作。最高品質のため 4B LM を使用。

## デバッグモード：異なる GPU 構成のシミュレーション

テストと開発のため、`MAX_CUDA_VRAM` 環境変数を使用して異なる GPU メモリサイズをシミュレートできます：

```bash
# 4GB GPU (Tier 1) をシミュレート
MAX_CUDA_VRAM=4 uv run acestep

# 6GB GPU (Tier 2) をシミュレート
MAX_CUDA_VRAM=6 uv run acestep

# 8GB GPU (Tier 4) をシミュレート
MAX_CUDA_VRAM=8 uv run acestep

# 12GB GPU (Tier 5) をシミュレート
MAX_CUDA_VRAM=12 uv run acestep

# 16GB GPU (Tier 6a) をシミュレート
MAX_CUDA_VRAM=16 uv run acestep
```

`MAX_CUDA_VRAM` を設定すると、システムは `torch.cuda.set_per_process_memory_fraction()` を呼び出して VRAM のハードキャップを強制し、ハイエンド GPU でもリアルなシミュレーションを実現します。

### 自動ティアテスト

UI で各ティアを手動テストする代わりに、`profile_inference.py` の `tier-test` モードを使用できます：

```bash
# すべてのティアを自動テスト
python profile_inference.py --mode tier-test

# 特定のティアをテスト
python profile_inference.py --mode tier-test --tiers 6 8 16

# LM を有効にしてテスト（サポートされるティアで）
python profile_inference.py --mode tier-test --tier-with-lm

# 高速テスト（非量子化ティアで torch.compile をスキップ）
python profile_inference.py --mode tier-test --tier-skip-compile
```

プロファイリングツールの完全なドキュメントは [BENCHMARK.md](BENCHMARK.md) を参照してください。

用途：
- ハイエンドハードウェアで GPU ティア構成をテスト
- 各ティアの警告と制限が正しく機能することを確認
- `acestep/gpu_config.py` 変更後の自動回帰テスト
- CI/CD VRAM 互換性検証

### 境界テスト（最小ティアの特定）

`--tier-boundary` を使用すると、INT8 量子化と CPU オフロードを安全に無効化できる最小 VRAM ティアを実験的に特定できます。各ティアに対して最大3つの構成でテストします：

1. **default** — ティアの標準設定（量子化 + オフロードを設定通りに使用）
2. **no-quant** — オフロード設定はそのまま、量子化を無効化
3. **no-offload** — 量子化なし、CPU オフロードなし（すべてのモデルを GPU に保持）

```bash
# すべてのティアで境界テストを実行
python profile_inference.py --mode tier-test --tier-boundary

# 特定のティアの境界テスト
python profile_inference.py --mode tier-test --tier-boundary --tiers 8 12 16 20 24

# LM を有効にした境界テスト（サポートされるティアで）
python profile_inference.py --mode tier-test --tier-boundary --tier-with-lm

# 結果を JSON に保存
python profile_inference.py --mode tier-test --tier-boundary --benchmark-output boundary_results.json
```

> **注意：** 境界テスト結果は経験的なものであり、DiT モデルバリアント（turbo vs base）、LM の有効化状態、生成時間、flash attention の利用可否によって異なる場合があります。

### バッチサイズ境界テスト

`--tier-batch-boundary` を使用して、バッチサイズ 1、2、4、8 を段階的にテストし、各ティアの最大安全バッチサイズを見つけます：

```bash
# LM 有効でバッチ境界テストを実行
python profile_inference.py --mode tier-test --tier-batch-boundary --tier-with-lm

# 特定のティアをテスト
python profile_inference.py --mode tier-test --tier-batch-boundary --tier-with-lm --tiers 8 12 16 24
```

LM あり/なしの両方の構成をテストし、各ティアの最大成功バッチサイズを報告します。
