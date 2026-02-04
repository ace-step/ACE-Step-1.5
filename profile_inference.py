#!/usr/bin/env python3
"""
Enhanced profiling script for ACE-Step inference with deep LLM analysis

This script helps diagnose why LLM generation is slow by tracking:
1. Total tokens generated vs expected throughput (200 tokens/sec baseline)
2. Per-iteration timing to detect compilation overhead or slow operations
3. Constrained decoding overhead
4. CFG overhead (2x forward passes)
5. Model forward time vs sampling/processing time

Usage:
    python profile_inference.py                    # Standard profiling with warmup
    python profile_inference.py --no-warmup        # Profile first run (includes compilation)
    python profile_inference.py --llm-debug        # Deep LLM performance debugging
    python profile_inference.py --detailed         # Add cProfile function-level analysis
    
    Inference mode options:
    python profile_inference.py --thinking                        # Enable CoT for code generation
    python profile_inference.py --use-constrained-decoding        # Use FSM constrained decoding
    python profile_inference.py --use-cot-metas                  # Enable LM to generate metadata via CoT
"""

import time
import argparse
import sys
import os
from contextlib import contextmanager
from collections import defaultdict
import json
from typing import Tuple, Dict, Any, List
from functools import wraps

# Add project root to path
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def load_env_config():
    """从 .env 文件加载配置"""
    env_config = {
        'ACESTEP_CONFIG_PATH': 'acestep-v15-turbo',
        'ACESTEP_LM_MODEL_PATH': 'acestep-5Hz-lm-0.6B',
        'ACESTEP_DEVICE': 'auto',
        'ACESTEP_LM_BACKEND': 'vllm',
    }
    
    env_file = os.path.join(project_root, '.env')
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过空行和注释
                if not line or line.startswith('#'):
                    continue
                # 解析键值对
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    if key in env_config and value:
                        env_config[key] = value
    
    return env_config

import torch
from acestep.inference import generate_music, GenerationParams, GenerationConfig
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler


class PreciseTimer:
    """High-precision timer with CUDA synchronization for accurate GPU timing"""
    
    def __init__(self, device="cuda"):
        self.device = device
        self.timings = defaultdict(list)
        self.enabled = True
        
    def sync(self):
        """Synchronize CUDA operations for accurate timing"""
        if not self.enabled:
            return
        if self.device.startswith("cuda") and torch.cuda.is_available():
            torch.cuda.synchronize()
        elif self.device == "mps" and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            torch.mps.synchronize()
    
    @contextmanager
    def time(self, name: str):
        """Time a code section with CUDA synchronization"""
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
        """Get total accumulated time for a section"""
        return sum(self.timings.get(name, []))
    
    def get_mean(self, name: str) -> float:
        """Get mean time per call for a section"""
        times = self.timings.get(name, [])
        return sum(times) / len(times) if times else 0.0
    
    def get_count(self, name: str) -> int:
        """Get number of calls for a section"""
        return len(self.timings.get(name, []))
    
    def get_all(self, name: str) -> List[float]:
        """Get all timing samples for a section"""
        return self.timings.get(name, [])


class LLMDebugger:
    """Track detailed LLM performance metrics to diagnose slow generation"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset all metrics"""
        self.total_tokens = 0
        self.generation_start = None
        self.generation_end = None
        self.output_text = ""
        self.prompt_length = 0
        
    def start(self, prompt_length: int = 0):
        """Mark generation start"""
        self.generation_start = time.perf_counter()
        self.prompt_length = prompt_length
        
    def end(self, output_text: str = ""):
        """Mark generation end and store output"""
        self.generation_end = time.perf_counter()
        self.output_text = output_text
        
    def set_token_count(self, count: int):
        """Set total token count"""
        self.total_tokens = count
        
    def get_throughput(self) -> float:
        """Calculate actual tokens per second"""
        if self.generation_start and self.generation_end and self.total_tokens > 0:
            total_time = self.generation_end - self.generation_start
            if total_time > 0:
                return self.total_tokens / total_time
        return 0.0
    
    def print_analysis(self):
        """Print detailed LLM performance analysis"""
        if not self.generation_start or not self.generation_end:
            return
            
        print("\n" + "=" * 100)
        print("🔍 LLM PERFORMANCE DEEP DIVE")
        print("=" * 100)
        
        total_time = self.generation_end - self.generation_start
        throughput = self.get_throughput()
        
        # Basic metrics table
        print(f"\n{'Metric':<40} {'Value':<20} {'Notes'}")
        print("-" * 100)
        print(f"{'Total Tokens Generated:':<40} {self.total_tokens:<20} (new tokens only)")
        print(f"{'Prompt Length (estimate):':<40} {self.prompt_length:<20} (input tokens)")
        print(f"{'Total Generation Time:':<40} {total_time:<20.3f} seconds")
        print(f"{'Measured Throughput:':<40} {throughput:<20.1f} tokens/sec")
        print(f"{'Expected Throughput:':<40} {'200':<20} tokens/sec (baseline)")
        
        # Calculate performance gap
        if throughput > 0:
            slowdown = 200.0 / throughput
            efficiency = (throughput / 200.0) * 100
            print(f"{'Performance vs Baseline:':<40} {efficiency:<20.1f}% of expected")
            print(f"{'Slowdown Factor:':<40} {slowdown:<20.2f}x slower")
        
        # Analyze generated output
        if self.output_text:
            print(f"\n{'Output Analysis:':<40}")
            print(f"{'  Output length:':<40} {len(self.output_text):<20} characters")
            
            # Count audio codes
            import re
            code_pattern = r'<\|audio_code_\d+\|>'
            codes = re.findall(code_pattern, self.output_text)
            if codes:
                print(f"{'  Audio codes generated:':<40} {len(codes):<20} codes")
                print(f"{'  Expected audio duration:':<40} {f'~{len(codes)/5:.1f}s':<20} (5 codes per second)")
                if total_time > 0:
                    print(f"{'  Time per audio code:':<40} {f'{total_time/len(codes)*1000:.1f}ms':<20}")
            
            # Check for CoT section
            if '<think>' in self.output_text and '</think>' in self.output_text:
                cot_start = self.output_text.find('<think>')
                cot_end = self.output_text.find('</think>') + 8
                cot_section = self.output_text[cot_start:cot_end]
                cot_token_est = len(cot_section) // 4
                print(f"{'  CoT section tokens (estimate):':<40} {f'~{cot_token_est}':<20}")
        
        # Diagnostic guidance
        print("\n" + "=" * 100)
        print("🔧 DIAGNOSTIC GUIDANCE")
        print("=" * 100)
        
        if throughput < 50:
            print("\n⚠️  CRITICAL: Throughput is extremely low (<50 tokens/sec)")
            print("\nThis is ~4x slower than expected. Likely causes:")
            print("  1. ❗ Constrained decoding FSM overhead")
            print("     → Each token triggers FSM state machine validation")
            print("     → Try: set use_constrained_decoding=False in config")
            print("  2. ❗ CFG with double forward passes")
            print("     → cfg_scale > 1.0 means running model twice per token")
            print("     → Check: params.lm_cfg_scale value")
            print("  3. ❗ Running in eager mode without compilation")
            print("     → PyTorch should compile kernels after warmup")
            print("     → Check: torch._dynamo.config settings")
            
        elif throughput < 100:
            print("\n⚠️  WARNING: Throughput is low (50-100 tokens/sec)")
            print("\nLikely causes:")
            print("  1. Constrained decoding overhead (~30-50% slowdown expected)")
            print("  2. CFG enabled (2x compute per token if cfg_scale > 1.0)")
            print("  3. Small model or inefficient GPU utilization")
            
        elif throughput < 150:
            print("\n⚠️  Throughput is below baseline but acceptable (100-150 tokens/sec)")
            print("\nMinor overhead from:")
            print("  - Constrained decoding: ~20-30% overhead")
            print("  - Profiling instrumentation: ~5-10% overhead")
            
        else:
            print(f"\n✓ Throughput is good ({throughput:.1f} tokens/sec)")
            print("  Performance is within acceptable range")


# Global instances
timer = None
llm_debugger = None


def wrap_method_with_timing(obj, method_name: str, timing_key: str):
    """Wrap a method with timing instrumentation"""
    original_method = getattr(obj, method_name)
    
    @wraps(original_method)
    def timed_wrapper(*args, **kwargs):
        with timer.time(timing_key):
            return original_method(*args, **kwargs)
    
    setattr(obj, method_name, timed_wrapper)
    return original_method


def wrap_llm_with_debug_tracking(llm_handler):
    """Wrap LLM generation with detailed performance tracking"""
    original_method = llm_handler.generate_with_stop_condition
    
    @wraps(original_method)
    def debug_wrapper(*args, **kwargs):
        # Estimate prompt length
        caption = kwargs.get('caption', args[0] if len(args) > 0 else "")
        lyrics = kwargs.get('lyrics', args[1] if len(args) > 1 else "")
        prompt_estimate = len(caption) + len(lyrics)
        prompt_tokens_estimate = prompt_estimate // 4
        
        # Start tracking
        llm_debugger.reset()
        llm_debugger.start(prompt_length=prompt_tokens_estimate)
        
        # Call original with timing
        with timer.time('llm_inference'):
            result = original_method(*args, **kwargs)
        
        # Extract and analyze output
        output_text = ""
        if isinstance(result, tuple) and len(result) >= 2:
            if isinstance(result[1], list):
                # Batch mode
                output_text = "".join(result[1])
            else:
                # Single mode
                cot_output = ""
                if isinstance(result[0], dict):
                    for v in result[0].values():
                        if isinstance(v, str):
                            cot_output += v
                output_text = cot_output + str(result[1])
        
        # Count tokens
        import re
        code_pattern = r'<\|audio_code_\d+\|>'
        codes = re.findall(code_pattern, output_text)
        remaining_text = re.sub(code_pattern, '', output_text)
        cot_tokens_estimate = len(remaining_text) // 4
        total_tokens = len(codes) + cot_tokens_estimate
        
        llm_debugger.set_token_count(total_tokens)
        llm_debugger.end(output_text)
        
        return result
    
    llm_handler.generate_with_stop_condition = debug_wrapper
    return original_method


def instrument_handlers(dit_handler, llm_handler, enable_llm_debug=False):
    """Add timing instrumentation to handler methods"""
    originals = {}
    
    # Instrument LLM
    if llm_handler and llm_handler.llm_initialized:
        if enable_llm_debug:
            originals['llm_generate'] = wrap_llm_with_debug_tracking(llm_handler)
        else:
            originals['llm_generate'] = wrap_method_with_timing(
                llm_handler, 'generate_with_stop_condition', 'llm_inference'
            )
    
    # Instrument DiT handler
    originals['dit_prepare'] = wrap_method_with_timing(
        dit_handler, 'prepare_batch_data', 'prepare_batch_data'
    )
    originals['dit_generate'] = wrap_method_with_timing(
        dit_handler, 'service_generate', 'dit_inference'
    )
    originals['dit_decode'] = wrap_method_with_timing(
        dit_handler, 'tiled_decode', 'vae_decode'
    )
    
    return originals


def restore_handlers(dit_handler, llm_handler, originals):
    """Restore original handler methods after profiling"""
    if llm_handler and 'llm_generate' in originals:
        llm_handler.generate_with_stop_condition = originals['llm_generate']
    
    dit_handler.prepare_batch_data = originals['dit_prepare']
    dit_handler.service_generate = originals['dit_generate']
    dit_handler.tiled_decode = originals['dit_decode']


def print_profiling_results(total_time: float, show_llm_debug: bool = False):
    """Print comprehensive profiling results with performance insights"""
    print("\n" + "=" * 100)
    print("🎯 PROFILING RESULTS")
    print("=" * 100)
    
    # Define timing categories
    model_sections = {
        'llm_inference': 'LLM Inference (5Hz Language Model)',
        'dit_inference': 'DiT Inference (Diffusion Transformer)',
        'vae_decode': 'VAE Decode (Audio Decoder)',
    }
    
    non_model_sections = {
        'prepare_batch_data': 'Prepare Batch Data (embedding, formatting)',
    }
    
    # Calculate totals
    model_time = sum(timer.get_total(k) for k in model_sections.keys())
    non_model_time = sum(timer.get_total(k) for k in non_model_sections.keys())
    other_time = total_time - model_time - non_model_time
    
    # Print summary table
    print(f"\n{'CATEGORY':<50} {'TIME (s)':<12} {'%':<8} {'CALLS':<8}")
    print("-" * 100)
    
    # Model time breakdown
    print(f"\n{'🤖 MODEL TIME (Total)':<50} {model_time:<12.3f} {100*model_time/total_time:>6.1f}% {'':<8}")
    for key, desc in model_sections.items():
        t = timer.get_total(key)
        c = timer.get_count(key)
        if c > 0:
            mean = timer.get_mean(key)
            pct = 100 * t / total_time
            print(f"  {'├─ ' + desc:<48} {t:<12.3f} {pct:>6.1f}% {c:<8} (avg: {mean:.3f}s)")
    
    # Non-model time breakdown
    print(f"\n{'⚙️  NON-MODEL TIME (Total)':<50} {non_model_time:<12.3f} {100*non_model_time/total_time:>6.1f}% {'':<8}")
    for key, desc in non_model_sections.items():
        t = timer.get_total(key)
        c = timer.get_count(key)
        if c > 0:
            mean = timer.get_mean(key)
            pct = 100 * t / total_time
            print(f"  {'├─ ' + desc:<48} {t:<12.3f} {pct:>6.1f}% {c:<8} (avg: {mean:.3f}s)")
    
    # Other time
    if other_time > 0.01:
        pct = 100 * other_time / total_time
        print(f"\n{'📦 OTHER TIME (I/O, overhead, audio save)':<50} {other_time:<12.3f} {pct:>6.1f}% {'':<8}")
    
    print(f"\n{'📊 TOTAL TIME':<50} {total_time:<12.3f} {'100.0%':>6} {'':<8}")
    
    # Show LLM detailed analysis if enabled
    if show_llm_debug:
        llm_debugger.print_analysis()
    
    # Performance insights
    print("\n" + "=" * 100)
    print("💡 PERFORMANCE INSIGHTS")
    print("=" * 100)
    
    llm_t = timer.get_total('llm_inference')
    dit_t = timer.get_total('dit_inference')
    vae_t = timer.get_total('vae_decode')
    prep_t = timer.get_total('prepare_batch_data')
    
    # Model time insights
    if model_time > 0:
        print(f"\n✓ Model operations: {model_time:.3f}s ({100*model_time/total_time:.1f}% of total)")
        
        if llm_t > 0:
            print(f"  - LLM: {llm_t:.3f}s ({100*llm_t/model_time:.1f}% of model time)")
        if dit_t > 0:
            print(f"  - DiT: {dit_t:.3f}s ({100*dit_t/model_time:.1f}% of model time)")
        if vae_t > 0:
            print(f"  - VAE: {vae_t:.3f}s ({100*vae_t/model_time:.1f}% of model time)")
    
    # LLM bottleneck analysis
    if llm_t > dit_t and llm_t > 5.0:
        print(f"\n⚠️  LLM IS THE BOTTLENECK: {llm_t:.3f}s ({100*llm_t/total_time:.1f}% of total)")
        print(f"\n   Possible causes:")
        print(f"   1. Generating too many tokens → use --llm-debug to verify")
        print(f"   2. Constrained decoding overhead → FSM validation per token")
        print(f"   3. CFG overhead → cfg_scale > 1.0 = 2x forward passes")
        print(f"   4. First-token latency → warmup should help")
        print(f"   5. KV cache inefficiency → should be ~5-10ms/token")
    
    # Non-model insights
    if non_model_time / total_time > 0.1:
        print(f"\n⚠️  Non-model operations: {non_model_time:.3f}s ({100*non_model_time/total_time:.1f}%)")
        if prep_t > 0.1:
            print(f"   - Batch preparation: {prep_t:.3f}s")
    
    # I/O overhead
    if other_time / total_time > 0.2:
        print(f"\n⚠️  Overhead/I/O: {other_time:.3f}s ({100*other_time/total_time:.1f}%)")
    
    # Recommendations
    print("\n" + "=" * 100)
    print("🚀 OPTIMIZATION RECOMMENDATIONS")
    print("=" * 100)
    
    if llm_t > dit_t * 2:
        print("\n🎯 Priority: Optimize LLM")
        print("  1. Run: python profile_inference.py --llm-debug")
        print("     → Shows exact token count and throughput")
        print("  2. Check constrained decoding overhead")
        print("  3. Check CFG scaling (lm_cfg_scale parameter)")
        print("  4. Profile nanovllm engine step() timing")
        print("  5. Compare vllm vs transformers backends")


def run_profiled_generation(dit_handler, llm_handler, params, config,
                           enable_cprofile=False, enable_llm_debug=False):
    """Execute generation with full profiling instrumentation"""
    # Instrument handlers
    originals = instrument_handlers(dit_handler, llm_handler, enable_llm_debug)
    
    try:
        print("\n[Profiling] Starting generation...")
        timer.sync()
        total_start = time.perf_counter()
        
        # Optional cProfile
        prof = None
        if enable_cprofile:
            import cProfile
            prof = cProfile.Profile()
            prof.enable()
        
        # Run generation
        result = generate_music(dit_handler, llm_handler, params, config, save_dir="./")
        
        # Stop timing
        timer.sync()
        total_time = time.perf_counter() - total_start
        
        # Save cProfile if enabled
        if enable_cprofile and prof:
            prof.disable()
            
            import pstats
            import io
            
            output_file = "profile_cprofile_detailed.txt"
            with open(output_file, 'w') as f:
                ps = pstats.Stats(prof, stream=f)
                ps.sort_stats('cumulative')
                ps.print_stats(100)
            
            # Print top functions
            print("\n" + "=" * 100)
            print("📊 TOP 20 FUNCTIONS BY CUMULATIVE TIME (cProfile)")
            print("=" * 100)
            s = io.StringIO()
            ps = pstats.Stats(prof, stream=s)
            ps.sort_stats('cumulative')
            ps.print_stats(20)
            print(s.getvalue())
            
            print(f"\nFull report: {output_file}")
        
        # Print results
        print_profiling_results(total_time, show_llm_debug=enable_llm_debug)
        
        return result, total_time
        
    finally:
        restore_handlers(dit_handler, llm_handler, originals)


def load_example_config(example_file: str) -> Tuple[GenerationParams, GenerationConfig]:
    """Load configuration from example JSON file"""
    try:
        with open(example_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        params = GenerationParams(
            caption=data.get('caption', ''),
            lyrics=data.get('lyrics', ''),
            bpm=data.get('bpm'),
            keyscale=data.get('keyscale', ''),
            timesignature=data.get('timesignature', ''),
            vocal_language=data.get('language', 'unknown'),
            duration=data.get('duration'),
            thinking=data.get('think', False),
            inference_steps=data.get('inference_steps', 8),
            seed=data.get('seed', 42),
        )
        
        config = GenerationConfig(batch_size=data.get('batch_size', 1), seeds=[42])
        
        return params, config
        
    except Exception as e:
        print(f"  ❌ Failed to load: {e}")
        return None, None


def main():
    global timer, llm_debugger
    
    # 从 .env 文件加载默认配置
    env_config = load_env_config()
    
    parser = argparse.ArgumentParser(
        description="Profile ACE-Step inference with LLM debugging"
    )
    parser.add_argument("--checkpoint-dir", type=str, default="./checkpoints")
    parser.add_argument("--config-path", type=str, default=env_config['ACESTEP_CONFIG_PATH'],
                       help=f"模型配置路径 (默认从 .env: {env_config['ACESTEP_CONFIG_PATH']})")
    parser.add_argument("--device", type=str, default=env_config['ACESTEP_DEVICE'],
                       help=f"设备 (默认从 .env: {env_config['ACESTEP_DEVICE']})")
    parser.add_argument("--lm-model", type=str, default=env_config['ACESTEP_LM_MODEL_PATH'],
                       help=f"LLM 模型路径 (默认从 .env: {env_config['ACESTEP_LM_MODEL_PATH']})")
    parser.add_argument("--lm-backend", type=str, default=env_config['ACESTEP_LM_BACKEND'],
                       help=f"LLM 后端 (默认从 .env: {env_config['ACESTEP_LM_BACKEND']})")
    parser.add_argument("--no-warmup", action="store_true")
    parser.add_argument("--detailed", action="store_true")
    parser.add_argument("--llm-debug", action="store_true",
                       help="Enable deep LLM debugging (token count, throughput)")
    parser.add_argument("--example", type=str, default="example_05.json")
    
    # Inference mode parameters
    parser.add_argument("--thinking", action="store_true",
                       help="Enable CoT reasoning for LM to generate audio codes")
    parser.add_argument("--use-constrained-decoding", action="store_true",
                       help="Use FSM-based constrained decoding for meta generation")
    parser.add_argument("--use-cot-metas", action="store_true",
                       help="Enable LLM to generate music metadata via CoT reasoning")
    
    args = parser.parse_args()
    
    # Initialize
    timer = PreciseTimer(device=args.device)
    llm_debugger = LLMDebugger()
    
    print("=" * 100)
    print("🎵 ACE-Step Inference Profiler (LLM Performance Analysis)")
    print("=" * 100)
    print(f"\n模型配置 (从 .env 加载):")
    print(f"  DiT 模型: {args.config_path}")
    print(f"  LLM 模型: {args.lm_model}")
    print(f"\n运行配置:")
    print(f"  Device: {args.device}")
    print(f"  LLM Backend: {args.lm_backend}")
    print(f"  LLM Debug: {'Enabled' if args.llm_debug else 'Disabled'}")
    print(f"  Warmup: {'Disabled' if args.no_warmup else 'Enabled'}")
    print(f"\nInference Mode:")
    print(f"  Thinking (CoT): {'Enabled' if args.thinking else 'Disabled'}")
    print(f"  Constrained Decoding: {'Enabled' if args.use_constrained_decoding else 'Disabled'}")
    print(f"  Use CoT for Metas: {'Enabled' if args.use_cot_metas else 'Disabled'}")
    
    # Initialize models
    print(f"\nInitializing models...")
    
    dit_handler = AceStepHandler()
    llm_handler = LLMHandler()
    
    print("  🎹 Initializing DiT...")
    status_dit, success_dit = dit_handler.initialize_service(
        project_root=project_root,
        config_path=args.config_path,
        device=args.device,
        use_flash_attention=True,
    )
    if not success_dit:
        print(f"  ❌ Failed: {status_dit}")
        sys.exit(1)
    print(f"     ✓ DiT ready")
    
    print("  🧠 Initializing LLM...")
    if args.thinking or args.use_cot_metas:
        status_llm, success_llm = llm_handler.initialize(
            checkpoint_dir=args.checkpoint_dir,
            lm_model_path=args.lm_model,
            backend=args.lm_backend,
            device=args.device,
        )
        if success_llm:
            print(f"     ✓ LLM ready ({args.lm_backend})")
        else:
            print(f"     ⚠ Failed: {status_llm}")
    else:
        print(f"     ✓ LLM not initialized (thinking or use_cot_metas is disabled)")
    
    # Load example
    example_file = os.path.join(project_root, "examples", "text2music", args.example)
    if not os.path.exists(example_file):
        print(f"\n❌ Not found: {example_file}")
        sys.exit(1)
    
    print(f"\n📄 Loading: {args.example}")
    params, config = load_example_config(example_file)
    
    if not params or not config:
        print("❌ Failed to load config")
        sys.exit(1)
    
    print(f"   Caption: {params.caption[:60]}...")
    print(f"   Batch: {config.batch_size}, Steps: {params.inference_steps}, LLM: {params.thinking}")
    
    # Warmup
    if not args.no_warmup:
        print("\n" + "=" * 100)
        print("🔥 WARMUP RUN")
        print("=" * 100)
        
        warmup_params = GenerationParams(
            caption=params.caption,
            lyrics=params.lyrics,
            bpm=params.bpm,
            keyscale=params.keyscale,
            timesignature=params.timesignature,
            vocal_language=params.vocal_language,
            duration=params.duration,
            thinking=args.thinking,
            use_cot_metas=args.use_cot_metas,
            inference_steps=params.inference_steps,
            seed=params.seed,
        )
        warmup_config = GenerationConfig(batch_size=1, seeds=[42])
        warmup_config.use_constrained_decoding = args.use_constrained_decoding
        
        warmup_start = time.perf_counter()
        warmup_result = generate_music(dit_handler, llm_handler, warmup_params, warmup_config, save_dir="./")
        warmup_time = time.perf_counter() - warmup_start
        
        print(f"\n✓ Warmup: {warmup_time:.2f}s")
        if not warmup_result.success:
            print(f"⚠️  Warning: {warmup_result.error}")
        
        # Reset
        timer = PreciseTimer(device=args.device)
        llm_debugger = LLMDebugger()
    
    # Profiling run
    print("\n" + "=" * 100)
    print("⏱️  PROFILING RUN")
    print("=" * 100)
    
    # Apply inference mode settings
    config.use_constrained_decoding = args.use_constrained_decoding
    # Override thinking and use_cot_metas parameters if specified via CLI
    if args.thinking:
        params.thinking = True
    if args.use_cot_metas:
        params.use_cot_metas = True
    
    result, total_time = run_profiled_generation(
        dit_handler, llm_handler, params, config,
        enable_cprofile=args.detailed,
        enable_llm_debug=args.llm_debug
    )
    
    if not result.success:
        print(f"\n❌ Failed: {result.error}")
        sys.exit(1)
    
    print(f"\n✅ Success! Generated {len(result.audios)} audio file(s)")
    
    # Final tips
    if args.detailed:
        print("\n💡 Check profile_cprofile_detailed.txt for function-level analysis")
    elif not args.llm_debug:
        print("\n💡 Run with --llm-debug to see LLM token count and throughput analysis")


if __name__ == "__main__":
    main()
