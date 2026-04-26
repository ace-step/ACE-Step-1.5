# GPU 兼容性指南

ACE-Step 1.5 会自动适配您的 GPU 显存大小，相应调整生成时长限制、可用的 LM 模型、卸载策略和 UI 默认设置。系统在启动时检测 GPU 显存并自动配置最佳设置。

## GPU 分级配置

| 显存 | 等级 | XL (4B) DiT | LM 模型 | 推荐 LM | 后端 | 最大时长 (有LM / 无LM) | 最大批次 (有LM / 无LM) | 卸载策略 | 量化 |
|------|------|:-----------:|---------|---------|------|------------------------|------------------------|----------|------|
| ≤4GB | Tier 1 | ❌ | 无 | — | pt | 4分 / 6分 | 1 / 1 | CPU + DiT | INT8 |
| 4-6GB | Tier 2 | ❌ | 无 | — | pt | 8分 / 10分 | 1 / 1 | CPU + DiT | INT8 |
| 6-8GB | Tier 3 | ❌ | 0.6B | 0.6B | pt | 8分 / 10分 | 2 / 2 | CPU + DiT | INT8 |
| 8-12GB | Tier 4 | ❌ | 0.6B | 0.6B | vllm | 8分 / 10分 | 2 / 4 | CPU + DiT | INT8 |
| 12-16GB | Tier 5 | ⚠️ | 0.6B, 1.7B | 1.7B | vllm | 8分 / 10分 | 4 / 4 | CPU | INT8 |
| 16-20GB | Tier 6a | ✅ (卸载) | 0.6B, 1.7B | 1.7B | vllm | 8分 / 10分 | 4 / 8 | CPU | INT8 |
| 20-24GB | Tier 6b | ✅ | 0.6B, 1.7B, 4B | 1.7B | vllm | 8分 / 8分 | 8 / 8 | 无 | 无 |
| ≥24GB | 无限制 | ✅ | 全部 (0.6B, 1.7B, 4B) | 4B | vllm | 10分 / 10分 | 8 / 8 | 无 | 无 |

> **XL (4B) DiT 列**: ❌ = 不支持, ⚠️ = 勉强可用（需卸载 + 量化，12-16GB 可通过激进卸载运行），✅ (卸载) = 需 CPU 卸载，✅ = 完全支持。XL 模型权重约 9GB（bf16），2B 约 4.7GB。所有 LM 模型均兼容 XL。

### 列说明

- **LM 模型**: 该等级可以加载的 5Hz 语言模型尺寸
- **推荐 LM**: UI 中该等级默认选择的 LM 模型
- **后端**: LM 推理后端（`vllm` 用于显存充足的 NVIDIA GPU，`pt` 为 PyTorch 回退方案，`mlx` 用于 Apple Silicon）
- **卸载策略**:
  - **CPU + DiT**: 所有模型（DiT、VAE、文本编码器）不使用时卸载到 CPU；DiT 也在步骤间卸载
  - **CPU**: VAE 和文本编码器卸载到 CPU；DiT 保留在 GPU 上
  - **无**: 所有模型保留在 GPU 上
- **量化**: 是否默认启用 INT8 权重量化以减少显存占用

## 自适应 UI 默认设置

Gradio UI 会根据检测到的 GPU 等级自动配置：

- **LM 初始化复选框**: 支持 LM 的等级（Tier 3+）默认勾选，Tier 1-2 默认不勾选且禁用
- **LM 模型路径**: 自动填充该等级推荐的模型；下拉菜单仅显示兼容的模型
- **后端下拉菜单**: Tier 1-3 限制为 `pt`/`mlx`（vllm KV 缓存占用过大）；Tier 4+ 所有后端可用
- **CPU 卸载 / DiT 卸载**: 低等级默认启用，高等级默认禁用
- **量化**: Tier 1-6a 默认启用，Tier 6b+ 默认禁用（显存充足）
- **模型编译**: 所有等级默认启用（量化需要）

如果您手动选择了不兼容的选项（例如在 6GB GPU 上使用 vllm），系统会发出警告并自动回退到兼容配置。

## 运行时安全特性

- **显存守卫**: 每次推理前，系统会估算显存需求，必要时自动减小批次大小
- **自适应 VAE 解码**: 三级回退机制：GPU 分片解码 → GPU 解码+结果卸载到 CPU → 完全 CPU 解码
- **自动分片大小**: VAE 解码分片大小根据可用空闲显存自适应调整（64/128/256/512/1024/1536）
- **时长/批次裁剪**: 如果请求的值超出等级限制，会自动裁剪并显示警告

## 说明

- **默认设置** 会根据检测到的 GPU 显存自动配置
- **LM 模式** 指用于思维链 (Chain-of-Thought) 生成和音频理解的语言模型
- **Flash Attention** 会自动检测并在可用时启用
- **约束解码**: 当 LM 初始化后，LM 生成的时长也会被约束在 GPU 等级的最大时长限制内，防止在 CoT 生成时出现显存不足错误
- 对于显存 ≤6GB 的 GPU（Tier 1-2），默认禁用 LM 初始化以保留显存给 DiT 模型
- 您可以通过命令行参数或 Gradio UI 手动覆盖设置

> **欢迎社区贡献**: 以上 GPU 分级配置基于我们在常见硬件上的测试。如果您发现您的设备实际性能与这些参数不符（例如，可以处理更长的时长或更大的批次），欢迎您进行更充分的测试，并提交 PR 来优化 `acestep/gpu_config.py` 中的配置。您的贡献将帮助改善所有用户的体验！

## 显存优化建议

1. **极低显存 (≤6GB)**: 使用纯 DiT 模式，不初始化 LM。INT8 量化和完全 CPU 卸载是必须的。VAE 解码可能会自动回退到 CPU。
2. **低显存 (6-8GB)**: 可使用 0.6B LM 模型，配合 `pt` 后端。保持卸载启用。
3. **中等显存 (8-16GB)**: 使用 0.6B 或 1.7B LM 模型。Tier 4+ 上 `vllm` 后端表现良好。
4. **高显存 (16-24GB)**: 启用更大的 LM 模型（推荐 1.7B）。20GB+ 量化变为可选。
5. **超高显存 (≥24GB)**: 所有模型无需卸载或量化即可运行。使用 4B LM 获得最佳质量。

## 调试模式：模拟不同的 GPU 配置

在测试和开发时，您可以使用 `MAX_CUDA_VRAM` 环境变量来模拟不同的 GPU 显存大小：

```bash
# 模拟 4GB GPU (Tier 1)
MAX_CUDA_VRAM=4 uv run acestep

# 模拟 6GB GPU (Tier 2)
MAX_CUDA_VRAM=6 uv run acestep

# 模拟 8GB GPU (Tier 4)
MAX_CUDA_VRAM=8 uv run acestep

# 模拟 12GB GPU (Tier 5)
MAX_CUDA_VRAM=12 uv run acestep

# 模拟 16GB GPU (Tier 6a)
MAX_CUDA_VRAM=16 uv run acestep
```

设置 `MAX_CUDA_VRAM` 时，系统还会调用 `torch.cuda.set_per_process_memory_fraction()` 来强制执行显存硬上限，即使在高端 GPU 上也能实现真实的模拟。

### 自动化分级测试

无需通过 UI 手动测试每个等级，可以使用 `profile_inference.py` 的 `tier-test` 模式：

```bash
# 自动测试所有等级
python profile_inference.py --mode tier-test

# 测试特定等级
python profile_inference.py --mode tier-test --tiers 6 8 16

# 测试时启用 LM（在支持的等级上）
python profile_inference.py --mode tier-test --tier-with-lm

# 快速测试（非量化等级跳过 torch.compile）
python profile_inference.py --mode tier-test --tier-skip-compile
```

详见 [BENCHMARK.md](BENCHMARK.md) 获取性能分析工具的完整文档。

适用场景：
- 在高端硬件上测试 GPU 分级配置
- 验证各等级的警告和限制是否正常工作
- 修改 `acestep/gpu_config.py` 后的自动化回归测试
- CI/CD 显存兼容性验证

### 边界测试（查找最低等级）

使用 `--tier-boundary` 可以通过实际运行来确定从哪个显存等级开始可以安全地关闭 INT8 量化和 CPU 卸载。对于每个等级，最多运行三种配置：

1. **default** — 该等级的默认设置（按配置使用量化 + 卸载）
2. **no-quant** — 保持卸载设置不变，但关闭量化
3. **no-offload** — 不使用量化，也不使用 CPU 卸载（所有模型保留在 GPU 上）

```bash
# 在所有等级上运行边界测试
python profile_inference.py --mode tier-test --tier-boundary

# 测试特定等级的边界
python profile_inference.py --mode tier-test --tier-boundary --tiers 8 12 16 20 24

# 启用 LM 的边界测试（在支持的等级上）
python profile_inference.py --mode tier-test --tier-boundary --tier-with-lm

# 将结果保存为 JSON 以便进一步分析
python profile_inference.py --mode tier-test --tier-boundary --benchmark-output boundary_results.json
```

输出包含一个 **边界分析** 部分，显示每种能力的最低等级：

```
BOUNDARY ANALYSIS
=================
  Capability                                    Min Tier   VRAM
  ------------------------------------------------------------
  No INT8 Quantization                          tier6b      20GB
  No CPU Offload (all models on GPU)            tier6b      20GB
  ------------------------------------------------------------
```

> **注意：** 边界测试结果是经验性的，可能因 DiT 模型变体（turbo vs base）、是否启用 LM、生成时长和 flash attention 可用性而有所不同。欢迎社区贡献来完善这些边界值！

### 批次大小边界测试

使用 `--tier-batch-boundary` 通过递进测试批次大小 1、2、4、8 来查找每个等级的最大安全批次大小：

```bash
# 运行启用 LM 的批次边界测试
python profile_inference.py --mode tier-test --tier-batch-boundary --tier-with-lm

# 测试特定等级
python profile_inference.py --mode tier-test --tier-batch-boundary --tier-with-lm --tiers 8 12 16 24
```

该测试同时测试有 LM 和无 LM 的配置，并报告每个等级的最大成功批次大小。
