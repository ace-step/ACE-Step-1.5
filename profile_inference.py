#!/usr/bin/env python3
"""
ACE-Step 1.5 Inference Profiler & Benchmark

Comprehensive profiling tool that supports all features, devices, and backends.
Uses the high-level inference API and built-in time_costs for accurate timing.

Modes:
    profile         - Profile a single generation run with detailed timing breakdown
    benchmark       - Run a matrix of configurations and produce a summary table
    tier-test       - Auto-test across simulated GPU tiers (4/6/8/12/16/24/48 GB)
    understand      - Profile the understand_music() API (audio codes -> metadata)
    create_sample   - Profile the create_sample() API (inspiration/simple mode)
    format_sample   - Profile the format_sample() API (caption+lyrics -> metadata)

Usage:
    # Profile text2music with default settings
    python profile_inference.py

    # Profile with thinking enabled on MPS
    python profile_inference.py --device mps --thinking

    # Benchmark across configurations
    python profile_inference.py --mode benchmark

    # Test all GPU tiers automatically (the key feature!)
    python profile_inference.py --mode tier-test

    # Test specific tiers only
    python profile_inference.py --mode tier-test --tiers 6 8 16

    # Test tiers with LM enabled (where supported)
    python profile_inference.py --mode tier-test --tier-with-lm

    # Profile create_sample (inspiration mode)
    python profile_inference.py --mode create_sample --sample-query "a soft Bengali love song"

    # Profile understand mode
    python profile_inference.py --mode understand

    # Full profiling with cProfile
    python profile_inference.py --detailed --llm-debug
"""

import time
import argparse
import sys
import os
import json
import tempfile
import traceback
from contextlib import contextmanager
from collections import defaultdict
from typing import Tuple, Dict, Any, List, Optional

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import torch

from acestep.inference import (
    generate_music,
    understand_music,
    create_sample,
    format_sample,
    GenerationParams,
    GenerationConfig,
    GenerationResult,
)
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.gpu_config import (
    get_gpu_config,
    set_global_gpu_config,
    get_gpu_tier,
    find_best_lm_model_on_disk,
    is_lm_model_size_allowed,
    GPUConfig,
    VRAM_AUTO_OFFLOAD_THRESHOLD_GB,
)


# =============================================================================
# Device / Backend helpers
# =============================================================================


def resolve_device(device: str) -> str:
    """Resolve 'auto' device to the best available device."""
    if device == "auto":
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            return "xpu"
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    return device


def auto_detect_backend(device: str) -> str:
    """Auto-detect the best LLM backend for the resolved device."""
    if device == "mps":
        try:
            import mlx.core  # noqa: F401
            return "mlx"
        except ImportError:
            return "pt"
    if device.startswith("cuda"):
        return "vllm"
    return "pt"


def load_env_config() -> Dict[str, str]:
    """Load configuration defaults from .env file."""
    env_config = {
        "ACESTEP_CONFIG_PATH": "acestep-v15-turbo",
        "ACESTEP_LM_MODEL_PATH": "acestep-5Hz-lm-0.6B",
        "ACESTEP_DEVICE": "auto",
        "ACESTEP_LM_BACKEND": "auto",
    }
    env_file = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if key in env_config and value:
                        env_config[key] = value
    return env_config


# =============================================================================
# Timer utilities
# =============================================================================


class PreciseTimer:
    """High-precision timer with GPU synchronization for accurate timing."""

    def __init__(self, device: str = "cpu"):
        self.device = device
        self.timings: Dict[str, List[float]] = defaultdict(list)
        self.enabled = True

    def sync(self):
        """Synchronize GPU operations for accurate timing."""
        if not self.enabled:
            return
        if self.device.startswith("cuda") and torch.cuda.is_available():
            torch.cuda.synchronize()
        elif self.device == "mps" and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            if hasattr(torch, "mps"):
                torch.mps.synchronize()
        elif self.device.startswith("xpu") and hasattr(torch, "xpu"):
            torch.xpu.synchronize()

    @contextmanager
    def time(self, name: str):
        """Time a code section with GPU synchronization."""
        if not self.enabled:
            yield
            return
        self.sync()
        start = time.perf_counter()
        try:
            yield
        finally:
            self.sync()
            elapsed = time.perf_counter() - start
            self.timings[name].append(elapsed)

    def get_total(self, name: str) -> float:
        return sum(self.timings.get(name, []))

    def get_mean(self, name: str) -> float:
        times = self.timings.get(name, [])
        return sum(times) / len(times) if times else 0.0

    def get_count(self, name: str) -> int:
        return len(self.timings.get(name, []))

    def reset(self):
        self.timings.clear()


# =============================================================================
# Example config loader
# =============================================================================


def load_example_config(
    example_file: str, cli_overrides: argparse.Namespace
) -> Tuple[Optional[GenerationParams], Optional[GenerationConfig]]:
    """Load configuration from example JSON file, applying CLI overrides."""
    try:
        with open(example_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        params = GenerationParams(
            caption=data.get("caption", ""),
            lyrics=data.get("lyrics", ""),
            bpm=data.get("bpm"),
            keyscale=data.get("keyscale", ""),
            timesignature=data.get("timesignature", ""),
            vocal_language=data.get("language", "unknown"),
            duration=(
                cli_overrides.duration
                if cli_overrides.duration is not None
                else data.get("duration", -1.0)
            ),
            thinking=cli_overrides.thinking,
            use_cot_metas=cli_overrides.use_cot_metas,
            use_cot_caption=cli_overrides.use_cot_caption,
            use_cot_language=cli_overrides.use_cot_language,
            use_constrained_decoding=cli_overrides.use_constrained_decoding,
            inference_steps=(
                cli_overrides.inference_steps
                if cli_overrides.inference_steps is not None
                else data.get("inference_steps", 8)
            ),
            seed=(
                cli_overrides.seed
                if cli_overrides.seed is not None
                else data.get("seed", 42)
            ),
            task_type=cli_overrides.task_type,
            lm_temperature=cli_overrides.lm_temperature,
            lm_cfg_scale=cli_overrides.lm_cfg_scale,
            guidance_scale=cli_overrides.guidance_scale,
            reference_audio=cli_overrides.reference_audio,
            src_audio=cli_overrides.src_audio,
        )

        config = GenerationConfig(
            batch_size=(
                cli_overrides.batch_size
                if cli_overrides.batch_size is not None
                else data.get("batch_size", 1)
            ),
            seeds=[params.seed] if params.seed >= 0 else None,
            use_random_seed=(params.seed < 0),
            audio_format="flac",
        )

        return params, config

    except Exception as e:
        print(f"  Failed to load example: {e}")
        return None, None


# =============================================================================
# Printing helpers
# =============================================================================


def print_time_costs_breakdown(
    time_costs: Dict[str, float], total_wall_time: float
):
    """Print a detailed timing breakdown from result.extra_outputs['time_costs']."""
    print("\n" + "=" * 100)
    print("PROFILING RESULTS")
    print("=" * 100)

    if not time_costs:
        print("\n  (No time_costs data available from the pipeline)")
        print(f"\n  Total wall time: {total_wall_time:.3f}s")
        return

    # Categorize keys
    lm_keys = {
        k: v
        for k, v in time_costs.items()
        if k.startswith("lm_") and isinstance(v, (int, float))
    }
    dit_keys = {
        k: v
        for k, v in time_costs.items()
        if k.startswith("dit_") and isinstance(v, (int, float))
    }
    pipeline_keys = {
        k: v
        for k, v in time_costs.items()
        if k.startswith("pipeline_") and isinstance(v, (int, float))
    }
    other_keys = {
        k: v
        for k, v in time_costs.items()
        if not k.startswith(("lm_", "dit_", "pipeline_"))
        and isinstance(v, (int, float))
    }

    print(f"\n{'COMPONENT':<50} {'TIME (s)':<12} {'% of wall':<10}")
    print("-" * 72)

    # LM timing
    lm_total = lm_keys.get("lm_total_time", 0.0)
    if lm_keys:
        print(
            f"\n{'LLM (5Hz Language Model)':<50} "
            f"{lm_total:<12.3f} {100 * lm_total / total_wall_time:>6.1f}%"
        )
        for k, v in sorted(lm_keys.items()):
            if k != "lm_total_time":
                label = k.replace("lm_", "  ")
                print(
                    f"  {label:<48} "
                    f"{v:<12.3f} {100 * v / total_wall_time:>6.1f}%"
                )

    # DiT timing
    dit_total = dit_keys.get("dit_total_time_cost", 0.0)
    if dit_keys:
        print(
            f"\n{'DiT (Diffusion Transformer)':<50} "
            f"{dit_total:<12.3f} {100 * dit_total / total_wall_time:>6.1f}%"
        )
        for k, v in sorted(dit_keys.items()):
            if k != "dit_total_time_cost":
                label = k.replace("dit_", "  ")
                print(
                    f"  {label:<48} "
                    f"{v:<12.3f} {100 * v / total_wall_time:>6.1f}%"
                )

    # Pipeline total
    if pipeline_keys:
        for k, v in sorted(pipeline_keys.items()):
            print(
                f"\n{'Pipeline: ' + k:<50} "
                f"{v:<12.3f} {100 * v / total_wall_time:>6.1f}%"
            )

    # Other keys
    if other_keys:
        print(f"\n{'Other:':<50}")
        for k, v in sorted(other_keys.items()):
            print(
                f"  {k:<48} "
                f"{v:<12.3f} {100 * v / total_wall_time:>6.1f}%"
            )

    # Overhead (wall time minus accounted time)
    accounted = lm_total + dit_total
    overhead = total_wall_time - accounted
    if overhead > 0.01:
        print(
            f"\n{'Overhead (I/O, audio save, etc.)':<50} "
            f"{overhead:<12.3f} {100 * overhead / total_wall_time:>6.1f}%"
        )

    print(f"\n{'TOTAL WALL TIME':<50} {total_wall_time:<12.3f} {'100.0%':>6}")

    # Performance insights
    print("\n" + "=" * 100)
    print("PERFORMANCE INSIGHTS")
    print("=" * 100)

    if lm_total > 0 and dit_total > 0:
        if lm_total > dit_total * 2:
            print(
                f"\n  LLM is the bottleneck: {lm_total:.1f}s "
                f"({100 * lm_total / total_wall_time:.0f}% of total)"
            )
            print("  Suggestions:")
            print("    1. Run with --llm-debug for token-level throughput analysis")
            print("    2. Try --no-constrained-decoding to reduce FSM overhead")
            print("    3. Compare backends: --lm-backend vllm vs pt vs mlx")
            print(
                "    4. Reduce lm_cfg_scale "
                "(currently doubles forward passes if > 1.0)"
            )
        elif dit_total > lm_total * 2:
            print(
                f"\n  DiT is the bottleneck: {dit_total:.1f}s "
                f"({100 * dit_total / total_wall_time:.0f}% of total)"
            )
            print("  Suggestions:")
            print("    1. Reduce --inference-steps (turbo model supports 4-8)")
            print("    2. Reduce --duration")
            print("    3. Try --quantization int8_weight_only")
        else:
            print(
                f"\n  Balanced pipeline: LLM={lm_total:.1f}s, DiT={dit_total:.1f}s"
            )
    elif dit_total > 0:
        print(f"\n  DiT only (no LLM): {dit_total:.1f}s")
        vae_time = dit_keys.get("dit_vae_decode_time_cost", 0.0)
        diffusion_time = dit_keys.get(
            "dit_diffusion_time_cost", dit_total - vae_time
        )
        if vae_time > 0:
            print(
                f"    Diffusion: {diffusion_time:.1f}s, "
                f"VAE decode: {vae_time:.1f}s"
            )


def print_result_summary(result: GenerationResult, mode: str = "profile"):
    """Print a short summary of the generation result."""
    if result.success:
        n_audios = len(result.audios)
        silent_count = sum(1 for a in result.audios if a.get("silent", False))
        print(f"\n  Success! Generated {n_audios} audio(s)", end="")
        if silent_count:
            print(f" ({silent_count} silent)", end="")
        print()
    else:
        print(f"\n  FAILED: {result.error}")


# =============================================================================
# Mode: profile (text2music and other task types)
# =============================================================================


def run_profile_mode(dit_handler, llm_handler, args, timer: PreciseTimer):
    """Run a single profiled generation."""
    example_dir = "text2music"
    example_file = os.path.join(
        PROJECT_ROOT, "examples", example_dir, args.example
    )
    if not os.path.exists(example_file):
        print(f"\n  Example not found: {example_file}")
        sys.exit(1)

    print(f"\n  Loading example: {args.example}")
    params, config = load_example_config(example_file, args)
    if not params or not config:
        print("  Failed to load example config")
        sys.exit(1)

    caption_preview = (
        params.caption[:80] + "..."
        if len(params.caption) > 80
        else params.caption
    )
    print(f"  Caption: {caption_preview}")
    print(
        f"  Task: {params.task_type}, Batch: {config.batch_size}, "
        f"Steps: {params.inference_steps}"
    )
    print(
        f"  Thinking: {params.thinking}, CoT Metas: {params.use_cot_metas}, "
        f"CoT Caption: {params.use_cot_caption}"
    )

    # Use a temporary directory for output (don't pollute project root)
    save_dir = tempfile.mkdtemp(prefix="acestep_profile_")

    # Warmup
    if not args.no_warmup:
        print("\n" + "-" * 100)
        print("WARMUP RUN")
        print("-" * 100)
        warmup_params = GenerationParams(
            caption=params.caption,
            lyrics=params.lyrics,
            bpm=params.bpm,
            keyscale=params.keyscale,
            timesignature=params.timesignature,
            vocal_language=params.vocal_language,
            duration=params.duration,
            thinking=params.thinking,
            use_cot_metas=params.use_cot_metas,
            use_cot_caption=params.use_cot_caption,
            use_cot_language=params.use_cot_language,
            use_constrained_decoding=params.use_constrained_decoding,
            inference_steps=params.inference_steps,
            seed=42,
            task_type=params.task_type,
            lm_temperature=params.lm_temperature,
            lm_cfg_scale=params.lm_cfg_scale,
            guidance_scale=params.guidance_scale,
        )
        warmup_config = GenerationConfig(
            batch_size=1, seeds=[42], use_random_seed=False, audio_format="flac"
        )
        warmup_start = time.perf_counter()
        warmup_result = generate_music(
            dit_handler, llm_handler, warmup_params, warmup_config,
            save_dir=save_dir,
        )
        warmup_time = time.perf_counter() - warmup_start
        print(f"  Warmup completed: {warmup_time:.2f}s")
        if not warmup_result.success:
            print(f"  Warning: warmup failed: {warmup_result.error}")
        timer.reset()

    # Profiling run
    print("\n" + "=" * 100)
    print("PROFILING RUN")
    print("=" * 100)

    # Optional cProfile
    prof = None
    if args.detailed:
        import cProfile
        prof = cProfile.Profile()
        prof.enable()

    timer.sync()
    total_start = time.perf_counter()

    result = generate_music(
        dit_handler, llm_handler, params, config, save_dir=save_dir
    )

    timer.sync()
    total_wall_time = time.perf_counter() - total_start

    if args.detailed and prof:
        prof.disable()
        _print_cprofile(prof)

    # Print results
    print_result_summary(result, "profile")

    time_costs = (
        result.extra_outputs.get("time_costs", {}) if result.success else {}
    )
    print_time_costs_breakdown(time_costs, total_wall_time)

    # Cleanup temp dir
    _cleanup_dir(save_dir)

    return result, total_wall_time


# =============================================================================
# Mode: benchmark
# =============================================================================


def run_benchmark_mode(dit_handler, llm_handler, args, timer: PreciseTimer):
    """Run a matrix of configurations and produce a summary table."""
    example_file = os.path.join(
        PROJECT_ROOT, "examples", "text2music", args.example
    )
    if not os.path.exists(example_file):
        print(f"\n  Example not found: {example_file}")
        sys.exit(1)

    with open(example_file, "r", encoding="utf-8") as f:
        example_data = json.load(f)

    save_dir = tempfile.mkdtemp(prefix="acestep_bench_")

    # Define benchmark matrix
    durations = [30, 60, 120]
    batch_sizes = [1, 2]
    thinking_options = (
        [False, True] if llm_handler.llm_initialized else [False]
    )
    inference_steps_options = [8]

    # Clamp to GPU limits
    gpu_config = get_gpu_config()
    max_dur = gpu_config.max_duration_without_lm
    max_batch = gpu_config.max_batch_size_without_lm
    durations = [d for d in durations if d <= max_dur]
    batch_sizes = [b for b in batch_sizes if b <= max_batch]

    if not durations:
        durations = [30]
    if not batch_sizes:
        batch_sizes = [1]

    configs = []
    for dur in durations:
        for bs in batch_sizes:
            for think in thinking_options:
                for steps in inference_steps_options:
                    configs.append(
                        {
                            "duration": dur,
                            "batch_size": bs,
                            "thinking": think,
                            "inference_steps": steps,
                        }
                    )

    print(f"\n  Running {len(configs)} benchmark configurations...")
    print(f"  Durations: {durations}, Batch sizes: {batch_sizes}")
    print(f"  Thinking: {thinking_options}, Steps: {inference_steps_options}")

    # Warmup
    if not args.no_warmup:
        print("\n  Warmup run...")
        warmup_params = GenerationParams(
            caption=example_data.get("caption", ""),
            lyrics=example_data.get("lyrics", ""),
            duration=30,
            thinking=False,
            inference_steps=8,
            seed=42,
        )
        warmup_config = GenerationConfig(
            batch_size=1, seeds=[42], use_random_seed=False, audio_format="flac"
        )
        generate_music(
            dit_handler, llm_handler, warmup_params, warmup_config,
            save_dir=save_dir,
        )
        print("  Warmup done.")

    # Run benchmark
    results = []
    for i, cfg in enumerate(configs):
        label = (
            f"dur={cfg['duration']}s, bs={cfg['batch_size']}, "
            f"think={cfg['thinking']}, steps={cfg['inference_steps']}"
        )
        print(f"\n  [{i + 1}/{len(configs)}] {label}")

        params = GenerationParams(
            caption=example_data.get("caption", ""),
            lyrics=example_data.get("lyrics", ""),
            bpm=example_data.get("bpm"),
            keyscale=example_data.get("keyscale", ""),
            timesignature=example_data.get("timesignature", ""),
            vocal_language=example_data.get("language", "unknown"),
            duration=cfg["duration"],
            thinking=cfg["thinking"],
            use_cot_metas=cfg["thinking"],
            use_cot_caption=cfg["thinking"],
            use_cot_language=cfg["thinking"],
            use_constrained_decoding=args.use_constrained_decoding,
            inference_steps=cfg["inference_steps"],
            seed=42,
            lm_temperature=args.lm_temperature,
            lm_cfg_scale=args.lm_cfg_scale,
            guidance_scale=args.guidance_scale,
        )
        config = GenerationConfig(
            batch_size=cfg["batch_size"],
            seeds=[42 + j for j in range(cfg["batch_size"])],
            use_random_seed=False,
            audio_format="flac",
        )

        timer.sync()
        t0 = time.perf_counter()
        result = generate_music(
            dit_handler, llm_handler, params, config, save_dir=save_dir
        )
        timer.sync()
        wall_time = time.perf_counter() - t0

        tc = (
            result.extra_outputs.get("time_costs", {})
            if result.success
            else {}
        )
        entry = {
            "config": cfg,
            "wall_time": wall_time,
            "success": result.success,
            "error": result.error,
            "lm_time": tc.get("lm_total_time", 0.0),
            "dit_time": tc.get("dit_total_time_cost", 0.0),
            "vae_time": tc.get("dit_vae_decode_time_cost", 0.0),
            "n_audios": len(result.audios) if result.success else 0,
        }
        results.append(entry)

        status = "OK" if result.success else f"FAIL: {result.error}"
        print(
            f"    {status} | wall={wall_time:.1f}s, "
            f"lm={entry['lm_time']:.1f}s, dit={entry['dit_time']:.1f}s"
        )

    # Print summary table
    print("\n" + "=" * 120)
    print("BENCHMARK SUMMARY")
    print("=" * 120)

    header = (
        f"{'Duration':<10} {'Batch':<7} {'Think':<7} {'Steps':<7} "
        f"{'Wall(s)':<10} {'LM(s)':<10} {'DiT(s)':<10} "
        f"{'VAE(s)':<10} {'Status':<10}"
    )
    print(header)
    print("-" * 120)

    for entry in results:
        cfg = entry["config"]
        status = "OK" if entry["success"] else "FAIL"
        print(
            f"{cfg['duration']:<10} {cfg['batch_size']:<7} "
            f"{str(cfg['thinking']):<7} {cfg['inference_steps']:<7} "
            f"{entry['wall_time']:<10.2f} {entry['lm_time']:<10.2f} "
            f"{entry['dit_time']:<10.2f} {entry['vae_time']:<10.2f} "
            f"{status:<10}"
        )

    # Save benchmark results as JSON
    if args.benchmark_output:
        output_path = args.benchmark_output
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n  Benchmark results saved to: {output_path}")

    _cleanup_dir(save_dir)
    return results


# =============================================================================
# Mode: tier-test  (THE KEY FEATURE)
# =============================================================================


def _get_vram_info_str() -> str:
    """Get current VRAM usage string for logging."""
    if not torch.cuda.is_available():
        return "N/A"
    allocated = torch.cuda.memory_allocated() / (1024 ** 3)
    reserved = torch.cuda.memory_reserved() / (1024 ** 3)
    return f"alloc={allocated:.2f}GB, reserved={reserved:.2f}GB"


def _run_single_tier_test(
    sim_gb: float,
    gpu_config: GPUConfig,
    args,
    example_data: Dict,
    checkpoint_dir: str,
    disk_lm_models: List[str],
    *,
    offload_override: Optional[bool] = None,
    offload_dit_override: Optional[bool] = None,
    quantization_override: Optional[str] = "USE_DEFAULT",
    test_variant: str = "default",
    batch_size_override: Optional[int] = None,
    use_lm_override: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Run a single tier test with the given configuration.

    Args:
        sim_gb: Simulated VRAM in GB
        gpu_config: GPU configuration for this tier
        args: CLI arguments
        example_data: Example JSON data for generation
        checkpoint_dir: Path to checkpoints directory
        disk_lm_models: List of LM models found on disk
        offload_override: If not None, override offload_to_cpu setting
        offload_dit_override: If not None, override offload_dit_to_cpu setting
        quantization_override: If not "USE_DEFAULT", override quantization setting
                               (None means no quantization, "int8_weight_only" etc.)
        test_variant: Label for this test variant ("default", "no-quant", "no-offload")
        batch_size_override: If not None, override batch size (used by batch boundary tests)
        use_lm_override: If not None, force LM on (True) or off (False)

    Returns:
        Result dictionary for this test
    """
    tier = gpu_config.tier

    # Determine test configuration
    if use_lm_override is not None:
        use_lm = use_lm_override and gpu_config.init_lm_default and bool(gpu_config.available_lm_models)
    else:
        use_lm = args.tier_with_lm and gpu_config.init_lm_default and bool(gpu_config.available_lm_models)

    if hasattr(torch, "xpu") and torch.xpu.is_available():
        offload_override = False

    if offload_override is not None:
        offload = offload_override
    else:
        offload = gpu_config.offload_to_cpu_default

    if offload_dit_override is not None:
        offload_dit = offload_dit_override
    else:
        offload_dit = gpu_config.offload_dit_to_cpu_default

    if quantization_override != "USE_DEFAULT":
        quantization = quantization_override
    else:
        quantization = "int8_weight_only" if gpu_config.quantization_default else None

    # Find LM model on disk
    lm_model = None
    lm_backend = gpu_config.recommended_backend
    if use_lm:
        lm_model = find_best_lm_model_on_disk(
            gpu_config.recommended_lm_model, disk_lm_models
        )
        if not lm_model:
            print(f"  ⚠️ No compatible LM model on disk for tier {tier}, skipping LM")
            use_lm = False

    # Clamp duration to tier limit
    test_duration = args.tier_duration
    max_dur = gpu_config.max_duration_with_lm if use_lm else gpu_config.max_duration_without_lm
    if test_duration > max_dur:
        test_duration = max_dur
        print(f"  Duration clamped to {test_duration}s (tier limit)")

    batch_size = batch_size_override if batch_size_override is not None else 1

    print(f"\n  Test config [{test_variant}]: duration={test_duration}s, batch={batch_size}, LM={use_lm}")
    if use_lm:
        print(f"    LM model: {lm_model}, backend: {lm_backend}")
    print(f"    offload={offload}, offload_dit={offload_dit}, quant={quantization}")

    # Enforce VRAM cap
    if torch.cuda.is_available():
        total_bytes = torch.cuda.get_device_properties(0).total_memory
        total_gb = total_bytes / (1024 ** 3)
        if sim_gb < total_gb:
            reference_context_gb = 0.5
            allocator_budget_gb = max(0.5, sim_gb - reference_context_gb)
            fraction = max(0.01, min(1.0, allocator_budget_gb / total_gb))
            torch.cuda.set_per_process_memory_fraction(fraction)

        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()

    # Initialize result entry
    result_entry = {
        "tier_gb": sim_gb,
        "tier": tier,
        "test_variant": test_variant,
        "use_lm": use_lm,
        "lm_model": lm_model,
        "lm_backend": lm_backend,
        "offload": offload,
        "offload_dit": offload_dit,
        "quantization": quantization,
        "duration": test_duration,
        "batch_size": batch_size,
        "init_success": False,
        "gen_success": False,
        "wall_time": 0.0,
        "error": None,
        "peak_vram_gb": 0.0,
    }

    dit_handler = None
    llm_handler = None

    try:
        print(f"\n  Initializing DiT handler... ({_get_vram_info_str()})")
        dit_handler = AceStepHandler()

        # Determine flash attention availability
        use_flash_attention = False
        try:
            import flash_attn  # noqa: F401
            use_flash_attention = True
        except ImportError:
            pass

        # compile_model must be True when quantization is used;
        # --tier-skip-compile can skip it for non-quantized tiers to save time
        if quantization:
            compile_model = True
        elif args.tier_skip_compile:
            compile_model = False
        else:
            compile_model = gpu_config.compile_model_default

        status_dit, success_dit = dit_handler.initialize_service(
            project_root=PROJECT_ROOT,
            config_path=args.config_path,
            device="auto",
            use_flash_attention=use_flash_attention,
            compile_model=compile_model,
            offload_to_cpu=offload,
            offload_dit_to_cpu=offload_dit,
            quantization=quantization,
        )

        if not success_dit:
            result_entry["error"] = f"DiT init failed: {status_dit}"
            print(f"  ❌ DiT init failed: {status_dit}")
            _cleanup_handlers(dit_handler, None)
            return result_entry

        print(f"  ✅ DiT ready ({_get_vram_info_str()})")

        llm_handler = LLMHandler()

        if use_lm:
            print(f"  Initializing LLM handler (backend={lm_backend})... ({_get_vram_info_str()})")
            status_llm, success_llm = llm_handler.initialize(
                checkpoint_dir=checkpoint_dir,
                lm_model_path=lm_model,
                backend=lm_backend,
                device="auto",
                offload_to_cpu=offload,
                dtype=None,
            )
            if success_llm:
                print(f"  ✅ LLM ready ({_get_vram_info_str()})")
            else:
                print(f"  ⚠️ LLM init failed: {status_llm}")
                use_lm = False
                result_entry["use_lm"] = False
                result_entry["error"] = f"LM init failed (non-fatal): {status_llm}"

        result_entry["init_success"] = True

    except torch.cuda.OutOfMemoryError as e:
        result_entry["error"] = f"Init OOM: {e}"
        print(f"  ❌ Init OOM: {e}")
        _cleanup_handlers(dit_handler, llm_handler)
        return result_entry
    except Exception as e:
        result_entry["error"] = f"Init exception: {e}"
        print(f"  ❌ Init exception: {e}")
        traceback.print_exc()
        _cleanup_handlers(dit_handler, llm_handler)
        return result_entry

    # Run generation
    try:
        print(f"\n  Running generation... ({_get_vram_info_str()})")
        save_dir = tempfile.mkdtemp(prefix=f"acestep_tier{int(sim_gb)}_{test_variant}_")

        params = GenerationParams(
            caption=example_data.get("caption", ""),
            lyrics=example_data.get("lyrics", ""),
            bpm=example_data.get("bpm"),
            keyscale=example_data.get("keyscale", ""),
            timesignature=example_data.get("timesignature", ""),
            vocal_language=example_data.get("language", "unknown"),
            duration=test_duration,
            thinking=use_lm,
            use_cot_metas=use_lm,
            use_cot_caption=False,
            use_cot_language=False,
            use_constrained_decoding=True,
            inference_steps=8,
            seed=42,
            lm_temperature=0.85,
            lm_cfg_scale=2.0,
            guidance_scale=7.0,
        )
        config = GenerationConfig(
            batch_size=batch_size,
            seeds=[42 + j for j in range(batch_size)],
            use_random_seed=False,
            audio_format="flac",
        )

        # When testing batch boundaries, temporarily override the GPU tier config's
        # max_batch limits so that inference.py's clamping doesn't reduce our test
        # batch size. We restore the original values after the test.
        _patched_tier_config = False
        _orig_batch_with_lm = None
        _orig_batch_without_lm = None
        if batch_size_override is not None and batch_size_override > 1:
            from acestep.gpu_config import GPU_TIER_CONFIGS as _tier_configs
            tier = gpu_config.tier
            if tier in _tier_configs:
                _patched_tier_config = True
                _orig_batch_with_lm = _tier_configs[tier]["max_batch_size_with_lm"]
                _orig_batch_without_lm = _tier_configs[tier]["max_batch_size_without_lm"]
                _tier_configs[tier]["max_batch_size_with_lm"] = max(batch_size_override, _orig_batch_with_lm)
                _tier_configs[tier]["max_batch_size_without_lm"] = max(batch_size_override, _orig_batch_without_lm)

        t0 = time.perf_counter()
        try:
            result = generate_music(
                dit_handler, llm_handler, params, config, save_dir=save_dir
            )
        finally:
            # Restore original tier config values
            if _patched_tier_config:
                _tier_configs[tier]["max_batch_size_with_lm"] = _orig_batch_with_lm
                _tier_configs[tier]["max_batch_size_without_lm"] = _orig_batch_without_lm
        wall_time = time.perf_counter() - t0

        result_entry["wall_time"] = wall_time
        result_entry["gen_success"] = result.success

        if result.success:
            tc = result.extra_outputs.get("time_costs", {})
            result_entry["lm_time"] = tc.get("lm_total_time", 0.0)
            result_entry["dit_time"] = tc.get("dit_total_time_cost", 0.0)
            result_entry["vae_time"] = tc.get("dit_vae_decode_time_cost", 0.0)
            n_audios = len(result.audios)
            print(f"  ✅ [{test_variant}] Generation OK: {n_audios} audio(s) in {wall_time:.1f}s")
        else:
            result_entry["error"] = result.error
            print(f"  ❌ [{test_variant}] Generation FAILED: {result.error}")

        _cleanup_dir(save_dir)

    except torch.cuda.OutOfMemoryError as e:
        result_entry["error"] = f"OOM: {e}"
        print(f"  ❌ [{test_variant}] OOM ERROR: {e}")
    except Exception as e:
        result_entry["error"] = f"Generation exception: {e}"
        print(f"  ❌ [{test_variant}] Exception: {e}")
        traceback.print_exc()

    # Record peak VRAM
    if torch.cuda.is_available():
        peak_bytes = torch.cuda.max_memory_allocated()
        result_entry["peak_vram_gb"] = peak_bytes / (1024 ** 3)
        print(f"  Peak VRAM: {result_entry['peak_vram_gb']:.2f}GB")

    # Cleanup
    _cleanup_handlers(dit_handler, llm_handler)

    return result_entry


def run_tier_test_mode(args):
    """
    Automatically test inference across multiple simulated GPU tiers.

    For each tier:
      1. Set MAX_CUDA_VRAM to simulate the VRAM limit
      2. Initialize gpu_config for that tier
      3. Initialize DiT + (optionally) LLM handlers with tier-appropriate settings
      4. Run a short generation and verify it completes without OOM
      5. Report results

    When --tier-boundary is enabled, each tier is tested with up to 3 configurations:
      - default: tier's default settings (quantization + offload as configured)
      - no-quant: same as default but with quantization disabled
      - no-offload: no quantization AND no CPU offload (all models on GPU)

    This replaces the manual workflow of:
      MAX_CUDA_VRAM=8 uv run acestep → click UI → wait → check
    """
    # Determine which tiers to test
    default_tiers = [4, 6, 8, 12, 16, 24, 48]
    tiers_to_test = args.tiers if args.tiers else default_tiers

    # Load example for generation
    example_file = os.path.join(
        PROJECT_ROOT, "examples", "text2music", args.example
    )
    if not os.path.exists(example_file):
        print(f"\n  Example not found: {example_file}")
        sys.exit(1)

    with open(example_file, "r", encoding="utf-8") as f:
        example_data = json.load(f)

    # Scan available LM models on disk
    checkpoint_dir = os.path.join(PROJECT_ROOT, "checkpoints")
    disk_lm_models = []
    if os.path.exists(checkpoint_dir):
        for item in sorted(os.listdir(checkpoint_dir)):
            if os.path.isdir(os.path.join(checkpoint_dir, item)) and item.startswith("acestep-5Hz-lm-"):
                disk_lm_models.append(item)

    boundary_mode = getattr(args, "tier_boundary", False)
    batch_boundary_mode = getattr(args, "tier_batch_boundary", False)

    print(f"\n  Tiers to test: {tiers_to_test}")
    print(f"  LM models on disk: {disk_lm_models}")
    print(f"  Test with LM: {args.tier_with_lm}")
    print(f"  Test duration: {args.tier_duration}s")
    print(f"  Boundary testing: {boundary_mode}")
    print(f"  Batch boundary testing: {batch_boundary_mode}")
    print(f"  Example: {args.example}")

    # Results collector
    all_results = []

    for sim_gb in tiers_to_test:
        print("\n" + "=" * 120)
        print(f"  TIER TEST: {sim_gb}GB simulated VRAM")
        print("=" * 120)

        # Configure GPU simulation
        os.environ["MAX_CUDA_VRAM"] = str(sim_gb)

        # Force re-detection of GPU config
        gpu_config = get_gpu_config(gpu_memory_gb=float(sim_gb))
        set_global_gpu_config(gpu_config)

        tier = gpu_config.tier
        print(f"  Tier: {tier}")
        print(f"  init_lm_default: {gpu_config.init_lm_default}")
        print(f"  available_lm_models: {gpu_config.available_lm_models}")
        print(f"  recommended_lm_model: {gpu_config.recommended_lm_model}")
        print(f"  recommended_backend: {gpu_config.recommended_backend}")
        print(f"  lm_backend_restriction: {gpu_config.lm_backend_restriction}")
        print(f"  offload_to_cpu: {gpu_config.offload_to_cpu_default}")
        print(f"  offload_dit_to_cpu: {gpu_config.offload_dit_to_cpu_default}")
        print(f"  quantization: {gpu_config.quantization_default}")
        print(f"  max_duration_with_lm: {gpu_config.max_duration_with_lm}s")
        print(f"  max_duration_without_lm: {gpu_config.max_duration_without_lm}s")
        print(f"  max_batch_with_lm: {gpu_config.max_batch_size_with_lm}")
        print(f"  max_batch_without_lm: {gpu_config.max_batch_size_without_lm}")

        # ---- Test 1: Default configuration ----
        print(f"\n  --- Variant: default ---")
        result_default = _run_single_tier_test(
            sim_gb, gpu_config, args, example_data,
            checkpoint_dir, disk_lm_models,
            test_variant="default",
        )
        all_results.append(result_default)

        if boundary_mode:
            # ---- Test 2: No quantization (keep offload as default) ----
            # Skip if the tier already doesn't use quantization (no point re-testing)
            if gpu_config.quantization_default:
                print(f"\n  --- Variant: no-quant (offload={gpu_config.offload_to_cpu_default}) ---")
                result_no_quant = _run_single_tier_test(
                    sim_gb, gpu_config, args, example_data,
                    checkpoint_dir, disk_lm_models,
                    quantization_override=None,
                    test_variant="no-quant",
                )
                all_results.append(result_no_quant)
            else:
                print(f"\n  --- Variant: no-quant — SKIPPED (tier already has quantization=False) ---")

            # ---- Test 3: No quantization AND no offload ----
            # Skip if the tier already has both disabled
            # Also skip if simulated VRAM is too small — the unquantized DiT model
            # alone needs ~6GB; without offload there is no room left for VAE decode,
            # which causes a fallback to CPU VAE with tiny chunk_size and 20+ hour runs.
            MIN_VRAM_FOR_NO_OFFLOAD = 8  # GB — DiT (~6GB) + VAE headroom (~2GB)
            if sim_gb < MIN_VRAM_FOR_NO_OFFLOAD:
                print(f"\n  --- Variant: no-offload — SKIPPED (simulated {sim_gb}GB < {MIN_VRAM_FOR_NO_OFFLOAD}GB minimum for no-offload) ---")
            elif gpu_config.quantization_default or gpu_config.offload_to_cpu_default:
                print(f"\n  --- Variant: no-offload (quant=None, offload=False) ---")
                result_no_offload = _run_single_tier_test(
                    sim_gb, gpu_config, args, example_data,
                    checkpoint_dir, disk_lm_models,
                    offload_override=False,
                    offload_dit_override=False,
                    quantization_override=None,
                    test_variant="no-offload",
                )
                all_results.append(result_no_offload)
            else:
                print(f"\n  --- Variant: no-offload — SKIPPED (tier already has offload=False, quant=False) ---")

        if batch_boundary_mode:
            # ---- Batch boundary tests: escalate batch size until OOM ----
            BATCH_SIZES_TO_TEST = [1, 2, 4, 8]

            # Test WITHOUT LM
            print(f"\n  --- Batch boundary: without LM ---")
            for bs in BATCH_SIZES_TO_TEST:
                print(f"\n  --- Variant: batch-noLM-{bs} (batch_size={bs}, no LM) ---")
                result_batch = _run_single_tier_test(
                    sim_gb, gpu_config, args, example_data,
                    checkpoint_dir, disk_lm_models,
                    test_variant=f"batch-noLM-{bs}",
                    batch_size_override=bs,
                    use_lm_override=False,
                )
                all_results.append(result_batch)
                if not result_batch["gen_success"]:
                    print(f"  ⚠️ Batch size {bs} failed without LM — stopping escalation")
                    break

            # Test WITH LM (if tier supports it)
            if gpu_config.init_lm_default and bool(gpu_config.available_lm_models):
                print(f"\n  --- Batch boundary: with LM ---")
                for bs in BATCH_SIZES_TO_TEST:
                    print(f"\n  --- Variant: batch-LM-{bs} (batch_size={bs}, with LM) ---")
                    result_batch_lm = _run_single_tier_test(
                        sim_gb, gpu_config, args, example_data,
                        checkpoint_dir, disk_lm_models,
                        test_variant=f"batch-LM-{bs}",
                        batch_size_override=bs,
                        use_lm_override=True,
                    )
                    all_results.append(result_batch_lm)
                    if not result_batch_lm["gen_success"]:
                        print(f"  ⚠️ Batch size {bs} failed with LM — stopping escalation")
                        break

    # ---- Print summary ----
    _print_tier_test_summary(all_results)

    if boundary_mode:
        _print_boundary_summary(all_results)

    if batch_boundary_mode:
        _print_batch_boundary_summary(all_results)

    # Save results
    if args.benchmark_output:
        with open(args.benchmark_output, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, default=str)
        print(f"\n  Results saved to: {args.benchmark_output}")

    return all_results


def _cleanup_handlers(dit_handler, llm_handler):
    """Clean up handlers and free GPU memory."""
    try:
        if dit_handler is not None:
            if hasattr(dit_handler, 'model') and dit_handler.model is not None:
                dit_handler.model = None
            if hasattr(dit_handler, 'vae') and dit_handler.vae is not None:
                dit_handler.vae = None
            if hasattr(dit_handler, 'text_encoder') and dit_handler.text_encoder is not None:
                dit_handler.text_encoder = None
            del dit_handler
    except Exception:
        pass

    try:
        if llm_handler is not None:
            if hasattr(llm_handler, 'llm') and llm_handler.llm is not None:
                llm_handler.llm = None
            del llm_handler
    except Exception:
        pass

    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()


def _print_tier_test_summary(results: List[Dict]):
    """Print a summary table of all tier test results."""
    # Detect if any result has a test_variant (boundary mode)
    has_variants = any(r.get("test_variant", "default") != "default" for r in results)

    print("\n" + "=" * 160)
    print("TIER TEST SUMMARY")
    print("=" * 160)

    if has_variants:
        header = (
            f"{'VRAM':>6} {'Tier':<10} {'Variant':<12} {'LM':>4} {'LM Model':<24} {'Backend':<8} "
            f"{'Offload':<8} {'Quant':<6} {'Init':>5} {'Gen':>5} "
            f"{'Wall(s)':>8} {'Peak(GB)':>9} {'Status':<30}"
        )
    else:
        header = (
            f"{'VRAM':>6} {'Tier':<10} {'LM':>4} {'LM Model':<28} {'Backend':<8} "
            f"{'Offload':<8} {'Quant':<6} {'Init':>5} {'Gen':>5} "
            f"{'Wall(s)':>8} {'Peak(GB)':>9} {'Status':<30}"
        )
    print(header)
    print("-" * 160)

    pass_count = 0
    fail_count = 0

    for r in results:
        lm_model_short = (r.get("lm_model") or "-")
        max_lm_len = 22 if has_variants else 26
        if len(lm_model_short) > max_lm_len:
            lm_model_short = lm_model_short[:max_lm_len] + ".."

        init_ok = "✅" if r["init_success"] else "❌"
        gen_ok = "✅" if r["gen_success"] else "❌"
        status = "PASS" if r["gen_success"] else (r.get("error", "FAIL") or "FAIL")
        if len(status) > 28:
            status = status[:28] + ".."

        if r["gen_success"]:
            pass_count += 1
        else:
            fail_count += 1

        quant = "int8" if r.get("quantization") else "-"
        variant = r.get("test_variant", "default")

        if has_variants:
            print(
                f"{r['tier_gb']:5d}GB {r['tier']:<10} {variant:<12} "
                f"{'Y' if r['use_lm'] else 'N':>4} {lm_model_short:<24} "
                f"{r.get('lm_backend', '-'):<8} "
                f"{'Y' if r['offload'] else 'N':<8} {quant:<6} "
                f"{init_ok:>5} {gen_ok:>5} "
                f"{r['wall_time']:>8.1f} {r.get('peak_vram_gb', 0):>9.2f} "
                f"{status:<30}"
            )
        else:
            print(
                f"{r['tier_gb']:5d}GB {r['tier']:<10} "
                f"{'Y' if r['use_lm'] else 'N':>4} {lm_model_short:<28} "
                f"{r.get('lm_backend', '-'):<8} "
                f"{'Y' if r['offload'] else 'N':<8} {quant:<6} "
                f"{init_ok:>5} {gen_ok:>5} "
                f"{r['wall_time']:>8.1f} {r.get('peak_vram_gb', 0):>9.2f} "
                f"{status:<30}"
            )

    print("-" * 160)
    print(f"  Total: {len(results)} tests run, {pass_count} PASSED, {fail_count} FAILED")


def _print_boundary_summary(results: List[Dict]):
    """
    Print a boundary analysis summary showing the minimum tier for each capability.

    Analyzes results from boundary testing to determine:
    - Minimum tier that works WITHOUT INT8 quantization
    - Minimum tier that works WITHOUT CPU offload (and without quantization)
    """
    print("\n" + "=" * 100)
    print("BOUNDARY ANALYSIS")
    print("=" * 100)
    print()
    print("  This analysis shows the minimum VRAM tier at which each optimization")
    print("  can be safely disabled while still completing inference successfully.")
    print()

    # Collect results by variant
    no_quant_results = [r for r in results if r.get("test_variant") == "no-quant"]
    no_offload_results = [r for r in results if r.get("test_variant") == "no-offload"]
    default_results = [r for r in results if r.get("test_variant") == "default"]

    # Also consider default results where the tier already has quant/offload disabled
    # (e.g., tier6b default already has quantization=False)
    for r in default_results:
        if not r.get("quantization") and r not in no_quant_results:
            # This tier's default already runs without quantization
            no_quant_results.append(r)
        if not r.get("offload") and not r.get("quantization") and r not in no_offload_results:
            # This tier's default already runs without offload and without quantization
            no_offload_results.append(r)

    # Sort by VRAM
    no_quant_results.sort(key=lambda r: r["tier_gb"])
    no_offload_results.sort(key=lambda r: r["tier_gb"])

    # Find minimum passing tier for each capability
    def _find_min_passing(result_list, capability_name):
        passing = [r for r in result_list if r.get("gen_success")]
        failing = [r for r in result_list if not r.get("gen_success")]

        if passing:
            min_pass = passing[0]
            print(f"  {capability_name}:")
            print(f"    Minimum tier:  {min_pass['tier']} ({min_pass['tier_gb']}GB)")
            print(f"    Peak VRAM:     {min_pass.get('peak_vram_gb', 0):.2f}GB")
            if failing:
                max_fail = failing[-1]
                print(f"    Last failure:  {max_fail['tier']} ({max_fail['tier_gb']}GB) — {max_fail.get('error', 'unknown')[:60]}")
        else:
            if failing:
                print(f"  {capability_name}:")
                print(f"    ❌ No tier passed this test. All tested tiers failed.")
                for r in failing:
                    err = (r.get("error") or "unknown")[:50]
                    print(f"       {r['tier_gb']}GB ({r['tier']}): {err}")
            else:
                print(f"  {capability_name}:")
                print(f"    ⚠️ No test results available for this capability.")
        print()
        return passing[0] if passing else None

    min_no_quant = _find_min_passing(no_quant_results, "Without INT8 Quantization")
    min_no_offload = _find_min_passing(no_offload_results, "Without CPU Offload (and no quantization)")

    # Print compact summary table
    print("  " + "-" * 60)
    print(f"  {'Capability':<45} {'Min Tier':<10} {'VRAM':>6}")
    print("  " + "-" * 60)

    if min_no_quant:
        print(f"  {'No INT8 Quantization':<45} {min_no_quant['tier']:<10} {min_no_quant['tier_gb']:>5}GB")
    else:
        print(f"  {'No INT8 Quantization':<45} {'N/A':<10} {'N/A':>6}")

    if min_no_offload:
        print(f"  {'No CPU Offload (all models on GPU)':<45} {min_no_offload['tier']:<10} {min_no_offload['tier_gb']:>5}GB")
    else:
        print(f"  {'No CPU Offload (all models on GPU)':<45} {'N/A':<10} {'N/A':>6}")

    print("  " + "-" * 60)
    print()
    print("  Note: These boundaries are empirical and may vary based on:")
    print("    - DiT model variant (turbo vs base)")
    print("    - Whether LM is enabled (--tier-with-lm)")
    print("    - Generation duration and batch size")
    print("    - Flash attention availability")


def _print_batch_boundary_summary(results: List[Dict]):
    """
    Print a batch boundary analysis summary showing the maximum safe batch size per tier.

    Analyzes results from batch boundary testing to determine:
    - Maximum batch size WITHOUT LM for each tier
    - Maximum batch size WITH LM for each tier
    """
    print("\n" + "=" * 120)
    print("BATCH BOUNDARY ANALYSIS")
    print("=" * 120)
    print()
    print("  This analysis shows the maximum batch size that completed successfully")
    print("  for each simulated VRAM tier.")
    print()

    # Collect batch boundary results
    batch_no_lm = [r for r in results if r.get("test_variant", "").startswith("batch-noLM-")]
    batch_with_lm = [r for r in results if r.get("test_variant", "").startswith("batch-LM-")]

    # Group by tier_gb
    def _group_by_tier(result_list):
        groups = {}
        for r in result_list:
            tier_gb = r["tier_gb"]
            if tier_gb not in groups:
                groups[tier_gb] = {"tier": r["tier"], "results": []}
            groups[tier_gb]["results"].append(r)
        return groups

    no_lm_groups = _group_by_tier(batch_no_lm)
    with_lm_groups = _group_by_tier(batch_with_lm)

    # Find max passing batch per tier
    def _max_passing_batch(group_results):
        max_bs = 0
        peak_vram = 0.0
        for r in group_results:
            if r.get("gen_success"):
                bs = r.get("batch_size", 1)
                if bs > max_bs:
                    max_bs = bs
                    peak_vram = r.get("peak_vram_gb", 0)
        return max_bs, peak_vram

    # Collect all tier_gb values
    all_tier_gbs = sorted(set(list(no_lm_groups.keys()) + list(with_lm_groups.keys())))

    # Print table
    print(f"  {'VRAM':>6}  {'Tier':<12}  {'Max Batch (no LM)':>18}  {'Peak VRAM':>10}  {'Max Batch (with LM)':>20}  {'Peak VRAM':>10}")
    print("  " + "-" * 90)

    summary_rows = []
    for tier_gb in all_tier_gbs:
        tier_name = no_lm_groups.get(tier_gb, with_lm_groups.get(tier_gb, {})).get("tier", "?")

        no_lm_max, no_lm_peak = (0, 0.0)
        if tier_gb in no_lm_groups:
            no_lm_max, no_lm_peak = _max_passing_batch(no_lm_groups[tier_gb]["results"])

        with_lm_max, with_lm_peak = (0, 0.0)
        if tier_gb in with_lm_groups:
            with_lm_max, with_lm_peak = _max_passing_batch(with_lm_groups[tier_gb]["results"])

        no_lm_str = str(no_lm_max) if no_lm_max > 0 else "FAIL"
        with_lm_str = str(with_lm_max) if with_lm_max > 0 else ("N/A" if tier_gb not in with_lm_groups else "FAIL")

        no_lm_peak_str = f"{no_lm_peak:.2f}GB" if no_lm_max > 0 else "-"
        with_lm_peak_str = f"{with_lm_peak:.2f}GB" if with_lm_max > 0 else "-"

        print(
            f"  {tier_gb:5d}GB  {tier_name:<12}  {no_lm_str:>18}  {no_lm_peak_str:>10}  "
            f"{with_lm_str:>20}  {with_lm_peak_str:>10}"
        )

        summary_rows.append({
            "tier_gb": tier_gb,
            "tier": tier_name,
            "max_batch_no_lm": no_lm_max,
            "max_batch_with_lm": with_lm_max if tier_gb in with_lm_groups else None,
        })

    print("  " + "-" * 90)
    print()

    # Print comparison with current GPU_TIER_CONFIGS
    print("  Comparison with current GPU_TIER_CONFIGS:")
    print(f"  {'VRAM':>6}  {'Tier':<12}  {'Config (no LM)':>15}  {'Tested (no LM)':>15}  {'Config (LM)':>12}  {'Tested (LM)':>12}  {'Recommendation':<30}")
    print("  " + "-" * 110)

    for row in summary_rows:
        tier_gb = row["tier_gb"]
        tier_name = row["tier"]
        cfg = get_gpu_config(gpu_memory_gb=float(tier_gb))

        cfg_no_lm = cfg.max_batch_size_without_lm
        cfg_with_lm = cfg.max_batch_size_with_lm
        tested_no_lm = row["max_batch_no_lm"]
        tested_with_lm = row["max_batch_with_lm"]

        tested_no_lm_str = str(tested_no_lm) if tested_no_lm > 0 else "FAIL"
        tested_with_lm_str = str(tested_with_lm) if tested_with_lm is not None and tested_with_lm > 0 else ("N/A" if tested_with_lm is None else "FAIL")

        # Recommendation
        rec_parts = []
        if tested_no_lm > 0 and tested_no_lm != cfg_no_lm:
            rec_parts.append(f"no_lm: {cfg_no_lm}→{tested_no_lm}")
        if tested_with_lm is not None and tested_with_lm > 0 and tested_with_lm != cfg_with_lm:
            rec_parts.append(f"lm: {cfg_with_lm}→{tested_with_lm}")
        recommendation = ", ".join(rec_parts) if rec_parts else "OK"

        print(
            f"  {tier_gb:5d}GB  {tier_name:<12}  {cfg_no_lm:>15}  {tested_no_lm_str:>15}  "
            f"{cfg_with_lm:>12}  {tested_with_lm_str:>12}  {recommendation:<30}"
        )

    print("  " + "-" * 110)
    print()
    print("  Note: Batch boundary results are empirical and depend on:")
    print("    - DiT model variant (turbo vs base)")
    print("    - Generation duration (longer = more VRAM per batch)")
    print("    - Flash attention availability")
    print("    - LM model size (0.6B vs 1.7B vs 4B)")
    print("    - Quantization and offload settings")


# =============================================================================
# Mode: understand
# =============================================================================


def run_understand_mode(dit_handler, llm_handler, args, timer: PreciseTimer):
    """Profile the understand_music() API."""
    if not llm_handler.llm_initialized:
        print("\n  LLM not initialized. understand mode requires LLM.")
        print("  Re-run with --thinking or ensure LLM is available.")
        sys.exit(1)

    audio_codes = args.audio_codes if args.audio_codes else ""

    print(
        f"\n  Audio codes: "
        f"{'<provided>' if audio_codes else '<empty - will generate sample>'}"
    )

    timer.sync()
    t0 = time.perf_counter()

    result = understand_music(
        llm_handler=llm_handler,
        audio_codes=audio_codes,
        temperature=args.lm_temperature,
        use_constrained_decoding=args.use_constrained_decoding,
    )

    timer.sync()
    wall_time = time.perf_counter() - t0

    print(f"\n  Wall time: {wall_time:.3f}s")
    print(f"  Success: {result.success}")
    if result.success:
        print(f"  Caption: {result.caption[:100]}...")
        print(
            f"  BPM: {result.bpm}, Duration: {result.duration}, "
            f"Key: {result.keyscale}"
        )
        print(
            f"  Language: {result.language}, Time Sig: {result.timesignature}"
        )
        if result.lyrics:
            print(f"  Lyrics: {result.lyrics[:100]}...")
    else:
        print(f"  Error: {result.error}")

    return result, wall_time


# =============================================================================
# Mode: create_sample
# =============================================================================


def run_create_sample_mode(
    dit_handler, llm_handler, args, timer: PreciseTimer
):
    """Profile the create_sample() API (inspiration/simple mode)."""
    if not llm_handler.llm_initialized:
        print("\n  LLM not initialized. create_sample mode requires LLM.")
        sys.exit(1)

    query = args.sample_query or "a soft love song for a quiet evening"
    print(f"\n  Query: {query}")
    print(f"  Instrumental: {args.instrumental}")

    timer.sync()
    t0 = time.perf_counter()

    result = create_sample(
        llm_handler=llm_handler,
        query=query,
        instrumental=args.instrumental,
        temperature=args.lm_temperature,
        use_constrained_decoding=args.use_constrained_decoding,
    )

    timer.sync()
    wall_time = time.perf_counter() - t0

    print(f"\n  Wall time: {wall_time:.3f}s")
    print(f"  Success: {result.success}")
    if result.success:
        print(f"  Caption: {result.caption[:100]}...")
        print(
            f"  BPM: {result.bpm}, Duration: {result.duration}, "
            f"Key: {result.keyscale}"
        )
        print(
            f"  Language: {result.language}, Time Sig: {result.timesignature}"
        )
        print(f"  Instrumental: {result.instrumental}")
        if result.lyrics:
            print(f"  Lyrics: {result.lyrics[:100]}...")
    else:
        print(f"  Error: {result.error}")

    return result, wall_time


# =============================================================================
# Mode: format_sample
# =============================================================================


def run_format_sample_mode(
    dit_handler, llm_handler, args, timer: PreciseTimer
):
    """Profile the format_sample() API."""
    if not llm_handler.llm_initialized:
        print("\n  LLM not initialized. format_sample mode requires LLM.")
        sys.exit(1)

    example_file = os.path.join(
        PROJECT_ROOT, "examples", "text2music", args.example
    )
    if not os.path.exists(example_file):
        print(f"\n  Example not found: {example_file}")
        sys.exit(1)

    with open(example_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    caption = data.get("caption", "Latin pop, reggaeton")
    lyrics = data.get("lyrics", "[Verse 1]\nHola mundo")

    print(f"\n  Caption: {caption[:80]}...")
    print(f"  Lyrics: {lyrics[:80]}...")

    timer.sync()
    t0 = time.perf_counter()

    result = format_sample(
        llm_handler=llm_handler,
        caption=caption,
        lyrics=lyrics,
        temperature=args.lm_temperature,
        use_constrained_decoding=args.use_constrained_decoding,
    )

    timer.sync()
    wall_time = time.perf_counter() - t0

    print(f"\n  Wall time: {wall_time:.3f}s")
    print(f"  Success: {result.success}")
    if result.success:
        print(f"  Caption: {result.caption[:100]}...")
        print(
            f"  BPM: {result.bpm}, Duration: {result.duration}, "
            f"Key: {result.keyscale}"
        )
        print(
            f"  Language: {result.language}, Time Sig: {result.timesignature}"
        )
    else:
        print(f"  Error: {result.error}")

    return result, wall_time


# =============================================================================
# cProfile helper
# =============================================================================


def _print_cprofile(prof):
    """Print cProfile results and save to file."""
    import pstats
    import io

    output_file = "profile_cprofile_detailed.txt"
    with open(output_file, "w") as f:
        ps = pstats.Stats(prof, stream=f)
        ps.sort_stats("cumulative")
        ps.print_stats(100)

    print("\n" + "=" * 100)
    print("TOP 20 FUNCTIONS BY CUMULATIVE TIME (cProfile)")
    print("=" * 100)
    s = io.StringIO()
    ps = pstats.Stats(prof, stream=s)
    ps.sort_stats("cumulative")
    ps.print_stats(20)
    print(s.getvalue())
    print(f"Full report saved to: {output_file}")


def _cleanup_dir(path: str):
    """Remove temporary directory silently."""
    try:
        import shutil
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


# =============================================================================
# Handler initialization (for non-tier-test modes)
# =============================================================================


def initialize_handlers(
    args, device: str
) -> Tuple[AceStepHandler, LLMHandler]:
    """Initialize DiT and LLM handlers with current API."""
    dit_handler = AceStepHandler()
    llm_handler = LLMHandler()

    # Determine flash attention availability
    use_flash_attention = False
    if device.startswith("cuda"):
        try:
            import flash_attn  # noqa: F401
            use_flash_attention = True
        except ImportError:
            pass

    compile_model = os.environ.get(
        "ACESTEP_COMPILE_MODEL", ""
    ).strip().lower() in {"1", "true", "yes", "y", "on"}

    print("  Initializing DiT handler...")
    status_dit, success_dit = dit_handler.initialize_service(
        project_root=PROJECT_ROOT,
        config_path=args.config_path,
        device=args.device,  # Pass original device string (handler resolves "auto")
        use_flash_attention=use_flash_attention,
        compile_model=compile_model,
        offload_to_cpu=args.offload_to_cpu,
        offload_dit_to_cpu=args.offload_dit_to_cpu,
        quantization=args.quantization,
    )
    if not success_dit:
        print(f"  DiT initialization failed: {status_dit}")
        sys.exit(1)
    print(f"  DiT ready (device={dit_handler.device})")

    # Determine if LLM should be initialized
    need_llm = (
        args.thinking
        or args.use_cot_metas
        or args.use_cot_caption
        or args.use_cot_language
        or args.mode in ("understand", "create_sample", "format_sample")
    )

    if need_llm:
        print(f"  Initializing LLM handler (backend={args.lm_backend})...")
        status_llm, success_llm = llm_handler.initialize(
            checkpoint_dir=os.path.join(PROJECT_ROOT, "checkpoints"),
            lm_model_path=args.lm_model,
            backend=args.lm_backend,
            device=args.device,
            offload_to_cpu=args.offload_to_cpu,
            dtype=None,
        )
        if success_llm:
            print(f"  LLM ready (backend={llm_handler.llm_backend})")
        else:
            print(f"  LLM initialization failed: {status_llm}")
            if args.mode in ("understand", "create_sample", "format_sample"):
                sys.exit(1)
    else:
        print(
            "  LLM not needed for current configuration "
            "(thinking/CoT disabled)"
        )

    return dit_handler, llm_handler


# =============================================================================
# CLI argument parser
# =============================================================================


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with all options."""
    env_config = load_env_config()

    parser = argparse.ArgumentParser(
        description="ACE-Step 1.5 Inference Profiler & Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python profile_inference.py                                    # Profile text2music
  python profile_inference.py --thinking --llm-debug             # With LLM analysis
  python profile_inference.py --mode benchmark                   # Benchmark matrix
  python profile_inference.py --mode tier-test                   # Test all GPU tiers
  python profile_inference.py --mode tier-test --tiers 6 8 16    # Test specific tiers
  python profile_inference.py --mode tier-test --tier-with-lm    # Test tiers with LM
  python profile_inference.py --mode understand                  # Profile understand API
  python profile_inference.py --mode create_sample --sample-query "jazz ballad"
  python profile_inference.py --device mps --lm-backend mlx      # Apple Silicon
  python profile_inference.py --device cuda --lm-backend vllm    # NVIDIA GPU
""",
    )

    # Mode
    parser.add_argument(
        "--mode",
        type=str,
        default="profile",
        choices=[
            "profile",
            "benchmark",
            "tier-test",
            "understand",
            "create_sample",
            "format_sample",
        ],
        help="Profiling mode (default: profile)",
    )

    # Device & backend
    parser.add_argument(
        "--device",
        type=str,
        default=env_config["ACESTEP_DEVICE"],
        help=(
            f"Device: auto/cuda/mps/cpu "
            f"(default: {env_config['ACESTEP_DEVICE']})"
        ),
    )
    parser.add_argument(
        "--lm-backend",
        type=str,
        default=env_config["ACESTEP_LM_BACKEND"],
        choices=["auto", "vllm", "pt", "mlx"],
        help=(
            f"LLM backend "
            f"(default: {env_config['ACESTEP_LM_BACKEND']})"
        ),
    )

    # Model paths
    parser.add_argument(
        "--config-path",
        type=str,
        default=env_config["ACESTEP_CONFIG_PATH"],
        help=(
            f"DiT model config "
            f"(default: {env_config['ACESTEP_CONFIG_PATH']})"
        ),
    )
    parser.add_argument(
        "--lm-model",
        type=str,
        default=env_config["ACESTEP_LM_MODEL_PATH"],
        help=(
            f"LLM model path "
            f"(default: {env_config['ACESTEP_LM_MODEL_PATH']})"
        ),
    )

    # Hardware options
    parser.add_argument(
        "--offload-to-cpu",
        action="store_true",
        help="Offload models to CPU when not in use",
    )
    parser.add_argument(
        "--offload-dit-to-cpu",
        action="store_true",
        help="Offload DiT to CPU when not in use",
    )
    parser.add_argument(
        "--quantization",
        type=str,
        default=None,
        choices=["int8_weight_only", "fp8_weight_only", "w8a8_dynamic"],
        help="Quantization mode for DiT model",
    )

    # Example & input
    parser.add_argument(
        "--example",
        type=str,
        default="example_05.json",
        help="Example JSON file from examples/text2music/",
    )

    # Task type
    parser.add_argument(
        "--task-type",
        type=str,
        default="text2music",
        choices=[
            "text2music",
            "cover",
            "repaint",
            "lego",
            "extract",
            "complete",
        ],
        help="Generation task type (default: text2music)",
    )
    parser.add_argument(
        "--reference-audio",
        type=str,
        default=None,
        help="Reference audio path (for cover/style transfer)",
    )
    parser.add_argument(
        "--src-audio",
        type=str,
        default=None,
        help="Source audio path (for audio-to-audio tasks)",
    )

    # Generation parameters
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Audio duration in seconds (overrides example)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Batch size (overrides example)",
    )
    parser.add_argument(
        "--inference-steps",
        type=int,
        default=None,
        help="Diffusion inference steps (overrides example)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed (overrides example)",
    )
    parser.add_argument(
        "--guidance-scale",
        type=float,
        default=7.0,
        help="CFG guidance scale for DiT (default: 7.0)",
    )

    # LLM / CoT parameters
    parser.add_argument(
        "--thinking",
        action="store_true",
        help="Enable 5Hz LM Chain-of-Thought reasoning",
    )
    parser.add_argument(
        "--use-cot-metas",
        action="store_true",
        help="Enable LLM to generate music metadata via CoT",
    )
    parser.add_argument(
        "--use-cot-caption",
        action="store_true",
        help="Enable LLM to rewrite/format caption via CoT",
    )
    parser.add_argument(
        "--use-cot-language",
        action="store_true",
        help="Enable LLM to detect vocal language via CoT",
    )
    parser.add_argument(
        "--use-constrained-decoding",
        action="store_true",
        default=True,
        help="Use FSM-based constrained decoding (default: True)",
    )
    parser.add_argument(
        "--no-constrained-decoding",
        action="store_true",
        help="Disable constrained decoding",
    )
    parser.add_argument(
        "--lm-temperature",
        type=float,
        default=0.85,
        help="LLM sampling temperature (default: 0.85)",
    )
    parser.add_argument(
        "--lm-cfg-scale",
        type=float,
        default=2.0,
        help="LLM CFG scale (default: 2.0)",
    )

    # Profiling options
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="Skip warmup run (includes compilation overhead)",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Enable cProfile function-level analysis",
    )
    parser.add_argument(
        "--llm-debug",
        action="store_true",
        help="Enable deep LLM debugging (token count, throughput)",
    )

    # Benchmark options
    parser.add_argument(
        "--benchmark-output",
        type=str,
        default=None,
        help="Save benchmark results to JSON file",
    )

    # Tier-test options
    parser.add_argument(
        "--tiers",
        type=int,
        nargs="+",
        default=None,
        help="Specific VRAM tiers to test (e.g., --tiers 6 8 16). Default: all tiers",
    )
    parser.add_argument(
        "--tier-with-lm",
        action="store_true",
        help="Enable LM for tiers that support it (default: DiT-only test)",
    )
    parser.add_argument(
        "--tier-duration",
        type=float,
        default=240,
        help="Test generation duration in seconds for tier-test (default: 240)",
    )
    parser.add_argument(
        "--tier-skip-compile",
        action="store_true",
        help="Skip torch.compile for non-quantized tiers (faster testing, less realistic)",
    )
    parser.add_argument(
        "--tier-boundary",
        action="store_true",
        help="Enable boundary testing: for each tier, also test without INT8 quantization "
             "and without CPU offload to find the minimum VRAM tier for each capability",
    )
    parser.add_argument(
        "--tier-batch-boundary",
        action="store_true",
        help="Enable batch size boundary testing: for each tier, progressively test "
             "batch sizes 1, 2, 4, 8 (stop at first OOM) to find the maximum safe batch "
             "size. Tests both with-LM and without-LM configurations.",
    )

    # create_sample / understand options
    parser.add_argument(
        "--sample-query",
        type=str,
        default=None,
        help="Query for create_sample mode",
    )
    parser.add_argument(
        "--instrumental",
        action="store_true",
        help="Generate instrumental music (for create_sample)",
    )
    parser.add_argument(
        "--audio-codes",
        type=str,
        default=None,
        help="Audio codes string (for understand mode)",
    )

    return parser


# =============================================================================
# Main
# =============================================================================


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Handle --no-constrained-decoding
    if args.no_constrained_decoding:
        args.use_constrained_decoding = False

    # Tier-test mode has its own initialization flow
    if args.mode == "tier-test":
        print("=" * 120)
        print("ACE-Step 1.5 Tier Compatibility Test")
        print("=" * 120)
        run_tier_test_mode(args)
        print("\n" + "=" * 120)
        print("DONE")
        print("=" * 120)
        return

    # Resolve device
    device = resolve_device(args.device)

    # Auto-detect backend
    if args.lm_backend == "auto":
        args.lm_backend = auto_detect_backend(device)

    # Setup GPU config
    gpu_config = get_gpu_config()
    set_global_gpu_config(gpu_config)

    # Auto-enable offload for small GPUs
    if (
        gpu_config.gpu_memory_gb > 0
        and gpu_config.gpu_memory_gb < VRAM_AUTO_OFFLOAD_THRESHOLD_GB
        and not args.offload_to_cpu
    ):
        args.offload_to_cpu = True

    # Print header
    print("=" * 100)
    print("ACE-Step 1.5 Inference Profiler")
    print("=" * 100)
    print(f"\n  Mode:           {args.mode}")
    print(f"  Device:         {device} (requested: {args.device})")
    print(f"  LLM Backend:    {args.lm_backend}")
    print(f"  DiT Config:     {args.config_path}")
    print(f"  LLM Model:      {args.lm_model}")
    print(
        f"  GPU Memory:     {gpu_config.gpu_memory_gb:.1f} GB "
        f"(tier: {gpu_config.tier})"
    )
    if args.quantization:
        print(f"  Quantization:   {args.quantization}")
    if args.offload_to_cpu:
        print("  CPU Offload:    enabled")
    print(f"\n  Thinking:       {args.thinking}")
    print(f"  CoT Metas:      {args.use_cot_metas}")
    print(f"  CoT Caption:    {args.use_cot_caption}")
    print(f"  CoT Language:   {args.use_cot_language}")
    print(f"  Constrained:    {args.use_constrained_decoding}")
    print(f"  Warmup:         {'disabled' if args.no_warmup else 'enabled'}")

    # Initialize handlers
    print("\n" + "-" * 100)
    print("INITIALIZING MODELS")
    print("-" * 100)

    dit_handler, llm_handler = initialize_handlers(args, device)

    # Create timer with resolved device
    actual_device = getattr(dit_handler, "device", device)
    timer = PreciseTimer(device=actual_device)

    # Dispatch to mode
    print("\n" + "=" * 100)
    print(f"RUNNING MODE: {args.mode.upper()}")
    print("=" * 100)

    if args.mode == "profile":
        run_profile_mode(dit_handler, llm_handler, args, timer)
    elif args.mode == "benchmark":
        run_benchmark_mode(dit_handler, llm_handler, args, timer)
    elif args.mode == "understand":
        run_understand_mode(dit_handler, llm_handler, args, timer)
    elif args.mode == "create_sample":
        run_create_sample_mode(dit_handler, llm_handler, args, timer)
    elif args.mode == "format_sample":
        run_format_sample_mode(dit_handler, llm_handler, args, timer)

    print("\n" + "=" * 100)
    print("DONE")
    print("=" * 100)


if __name__ == "__main__":
    main()
