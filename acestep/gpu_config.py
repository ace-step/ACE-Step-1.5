"""
GPU Configuration Module
Centralized GPU memory detection and adaptive configuration management

    Debug Mode:
        Set environment variable MAX_CUDA_VRAM to simulate different GPU memory sizes.
        Example: MAX_CUDA_VRAM=8 python acestep  # Simulates 8GB GPU
        
        For MPS testing, use MAX_MPS_VRAM to simulate MPS memory.
        Example: MAX_MPS_VRAM=16 python acestep  # Simulates 16GB MPS
    
    This is useful for testing GPU tier configurations on high-end hardware.
"""

import os
import sys
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from loguru import logger


# Environment variable for debugging/testing different GPU memory configurations
DEBUG_MAX_CUDA_VRAM_ENV = "MAX_CUDA_VRAM"
DEBUG_MAX_MPS_VRAM_ENV = "MAX_MPS_VRAM"

# Tolerance for 16GB detection: reported VRAM like 15.5GB is effectively 16GB hardware
# Real-world 16GB GPUs often report 15.7-15.9GB due to system/driver reservations
VRAM_16GB_TOLERANCE_GB = 0.5
VRAM_16GB_MIN_GB = 16.0 - VRAM_16GB_TOLERANCE_GB  # treat as 16GB class if >= this

# Threshold below which auto_offload is enabled.
# 16GB GPUs cannot hold DiT + VAE + text_encoder + LM simultaneously without offloading.
VRAM_AUTO_OFFLOAD_THRESHOLD_GB = 20.0

# PyTorch installation URLs for diagnostics
PYTORCH_CUDA_INSTALL_URL = "https://download.pytorch.org/whl/cu121"
PYTORCH_ROCM_INSTALL_URL = "https://download.pytorch.org/whl/rocm6.0"


def is_mps_platform() -> bool:
    """Check if running on macOS with MPS (Apple Silicon) available.
    
    This is the canonical check used across the codebase to apply
    Mac-specific configuration overrides (no compile, no quantization,
    mlx backend, no offload, etc.).
    """
    if sys.platform != "darwin":
        return False
    try:
        import torch
        return hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    except Exception:
        return False


def is_cuda_available() -> bool:
    """Return whether CUDA runtime is available."""
    try:
        import torch

        return torch.cuda.is_available()
    except Exception:
        return False


def is_mps_available() -> bool:
    """Return whether MPS runtime is available."""
    try:
        import torch

        return hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    except Exception:
        return False


def is_xpu_available() -> bool:
    """Return whether XPU runtime is available."""
    try:
        import torch

        return hasattr(torch, "xpu") and torch.xpu.is_available()
    except Exception:
        return False


# ===========================================================================
# Empirical VRAM measurements (GB) -- model weights only, bf16 precision
# These values should be calibrated using scripts/profile_vram.py
# ===========================================================================

# Base model weights (loaded once at startup)
MODEL_VRAM = {
    "dit_turbo": 4.7,        # DiT turbo model weights (bf16)
    "dit_base": 4.7,         # DiT base model weights (bf16)
    "vae": 0.33,             # VAE (AutoencoderOobleck) weights (fp16)
    "text_encoder": 1.2,     # Qwen3-Embedding-0.6B text encoder (bf16)
    "silence_latent": 0.01,  # Silence latent tensor
    "cuda_context": 0.5,     # CUDA context + driver overhead
}

# LM model weights (bf16) + KV cache estimates
LM_VRAM = {
    "0.6B": {"weights": 1.2, "kv_cache_2k": 0.3, "kv_cache_4k": 0.6},
    "1.7B": {"weights": 3.4, "kv_cache_2k": 0.5, "kv_cache_4k": 1.0},
    "4B":   {"weights": 8.0, "kv_cache_2k": 0.8, "kv_cache_4k": 1.6},
}

# DiT inference peak VRAM per batch item (approximate, depends on duration)
# These are additional activations/intermediates on top of model weights.
#
# Profiling on A800 (flash attention) shows only ~0.001-0.004 GB per batch item.
# Consumer GPUs without flash attention will be higher due to materialised
# attention matrices.  We use conservative estimates that cover the worst case
# (no flash attention, long sequences).
DIT_INFERENCE_VRAM_PER_BATCH = {
    "turbo": 0.3,   # GB per batch item (no CFG)
    "base":  0.6,    # GB per batch item (with CFG, 2x forward)
}

# Safety margin to keep free for OS/driver/fragmentation (GB)
VRAM_SAFETY_MARGIN_GB = 0.5


@dataclass
class GPUConfig:
    """GPU configuration based on available memory"""
    tier: str  # "tier1", "tier2", etc. or "unlimited"
    gpu_memory_gb: float
    
    # Duration limits (in seconds)
    max_duration_with_lm: int  # When LM is initialized
    max_duration_without_lm: int  # When LM is not initialized
    
    # Batch size limits
    max_batch_size_with_lm: int
    max_batch_size_without_lm: int
    
    # LM configuration
    init_lm_default: bool  # Whether to initialize LM by default
    available_lm_models: List[str]  # Available LM models for this tier
    recommended_lm_model: str  # Recommended default LM model path (empty if LM not available)
    
    # LM backend restriction
    # "all" = any backend, "pt_mlx_only" = only pt/mlx (no vllm), used for MPS (vllm requires CUDA)
    lm_backend_restriction: str  # "all" or "pt_mlx_only"
    recommended_backend: str  # Recommended default backend: "vllm", "pt", or "mlx"
    
    # Offload defaults
    offload_to_cpu_default: bool  # Whether offload_to_cpu should be enabled by default
    offload_dit_to_cpu_default: bool  # Whether offload_dit_to_cpu should be enabled by default
    
    # Quantization / compile defaults
    quantization_default: bool  # Whether INT8 quantization should be enabled by default
    compile_model_default: bool  # Whether torch.compile should be enabled by default
    
    # LM memory allocation (GB) for each model size
    lm_memory_gb: Dict[str, float]  # e.g., {"0.6B": 3, "1.7B": 8, "4B": 12}


# GPU tier configurations
# tier6 has been split into tier6a (16-20GB) and tier6b (20-24GB) to fix the
# 16GB regression. 16GB GPUs cannot hold all models simultaneously with the
# same batch sizes as 24GB GPUs.
GPU_TIER_CONFIGS = {
    "tier1": {  # <= 4GB
        # Offload mode required.  DiT(4.46) barely fits with CUDA context(0.5).
        # VAE decode falls back to CPU.  Keep durations moderate.
        "max_duration_with_lm": 240,  # 4 minutes
        "max_duration_without_lm": 360,  # 6 minutes
        "max_batch_size_with_lm": 1,
        "max_batch_size_without_lm": 1,
        "init_lm_default": False,
        "available_lm_models": [],
        "recommended_lm_model": "",
        "lm_backend_restriction": "all",
        "recommended_backend": "vllm",
        "offload_to_cpu_default": True,
        "offload_dit_to_cpu_default": True,
        "quantization_default": True,  # INT8 essential to fit DiT in ~4GB
        "compile_model_default": True,
        "lm_memory_gb": {},
    },
    "tier2": {  # 4-6GB
        # Offload mode.  DiT(4.46) + context(0.5) + activations ≈ 5.0GB.
        # ~1GB headroom.  Tiled VAE decode fits with chunk=256 (~0.8GB peak).
        # Duration barely affects peak VRAM (latent tensor is <2MB even at 10min).
        "max_duration_with_lm": 480,  # 8 minutes
        "max_duration_without_lm": 600,  # 10 minutes (max supported)
        "max_batch_size_with_lm": 1,
        "max_batch_size_without_lm": 1,
        "init_lm_default": False,
        "available_lm_models": [],
        "recommended_lm_model": "",
        "lm_backend_restriction": "all",
        "recommended_backend": "vllm",
        "offload_to_cpu_default": True,
        "offload_dit_to_cpu_default": True,
        "quantization_default": True,
        "compile_model_default": True,
        "lm_memory_gb": {},
    },
    "tier3": {  # 6-8GB
        # Offload mode.  DiT(4.46) + context(0.5) ≈ 5.0GB.
        # ~1.5-3GB headroom allows LM 0.6B (1.2+0.6=1.8GB) and batch=2.
        # With CPU offload, DiT is offloaded before LM runs → vllm can use freed VRAM.
        "max_duration_with_lm": 480,  # 8 minutes
        "max_duration_without_lm": 600,  # 10 minutes (max supported)
        "max_batch_size_with_lm": 2,
        "max_batch_size_without_lm": 2,
        "init_lm_default": True,
        "available_lm_models": ["acestep-5Hz-lm-0.6B"],
        "recommended_lm_model": "acestep-5Hz-lm-0.6B",
        "lm_backend_restriction": "all",
        "recommended_backend": "vllm",
        "offload_to_cpu_default": True,
        "offload_dit_to_cpu_default": True,
        "quantization_default": True,
        "compile_model_default": True,
        "lm_memory_gb": {"0.6B": 3},
    },
    "tier4": {  # 8-12GB
        # Can keep DiT + 0.6B LM simultaneously on GPU (4.46+1.2+0.6=6.26GB).
        # Offload VAE/TextEnc.  Plenty of room for inference activations.
        "max_duration_with_lm": 480,  # 8 minutes
        "max_duration_without_lm": 600,  # 10 minutes (max supported)
        "max_batch_size_with_lm": 2,
        "max_batch_size_without_lm": 4,
        "init_lm_default": True,
        "available_lm_models": ["acestep-5Hz-lm-0.6B"],
        "recommended_lm_model": "acestep-5Hz-lm-0.6B",
        "lm_backend_restriction": "all",  # vllm fits with 0.6B
        "recommended_backend": "vllm",
        "offload_to_cpu_default": True,
        "offload_dit_to_cpu_default": True,
        "quantization_default": True,
        "compile_model_default": True,
        "lm_memory_gb": {"0.6B": 3},
    },
    "tier5": {  # 12-16GB
        # DiT + 1.7B LM (4.46+3.45+0.44=8.35GB) fits comfortably.
        # VAE decode is batch-sequential so batch size doesn't affect VAE VRAM.
        "max_duration_with_lm": 480,  # 8 minutes
        "max_duration_without_lm": 600,  # 10 minutes (max supported)
        "max_batch_size_with_lm": 4,
        "max_batch_size_without_lm": 4,
        "init_lm_default": True,
        "available_lm_models": ["acestep-5Hz-lm-0.6B", "acestep-5Hz-lm-1.7B"],
        "recommended_lm_model": "acestep-5Hz-lm-1.7B",
        "lm_backend_restriction": "all",
        "recommended_backend": "vllm",
        "offload_to_cpu_default": True,
        "offload_dit_to_cpu_default": False,  # 12-16GB can keep DiT on GPU
        "quantization_default": True,
        "compile_model_default": True,
        "lm_memory_gb": {"0.6B": 3, "1.7B": 8},
    },
    "tier6a": {  # 16-20GB (e.g., RTX 4060 Ti 16GB, RTX 3080 16GB)
        # On 16GB GPUs: DiT(INT8, ~2.4GB) + LM 1.7B(~7.6GB peak with offload) = ~10GB peak
        # Empirical batch tests (60s, turbo): noLM-4→13.3GB, LM-2→11.9GB, LM-4→~13.5GB
        # With CPU offload, LM is offloaded after inference → DiT batch has full 16GB budget.
        "max_duration_with_lm": 480,  # 8 minutes
        "max_duration_without_lm": 600,  # 10 minutes (max supported)
        "max_batch_size_with_lm": 4,
        "max_batch_size_without_lm": 8,
        "init_lm_default": True,
        "available_lm_models": ["acestep-5Hz-lm-0.6B", "acestep-5Hz-lm-1.7B"],
        "recommended_lm_model": "acestep-5Hz-lm-1.7B",
        "lm_backend_restriction": "all",
        "recommended_backend": "vllm",
        "offload_to_cpu_default": True,  # Still offload VAE/TextEnc to save VRAM for LM
        "offload_dit_to_cpu_default": False,
        "quantization_default": True,
        "compile_model_default": True,
        "lm_memory_gb": {"0.6B": 3, "1.7B": 8},
    },
    "tier6b": {  # 20-24GB (e.g., RTX 3090, RTX 4090)
        # 20-24GB: no offload, no quantization. DiT(bf16, ~4.7GB) + LM 1.7B(~3.4GB) = ~8.1GB
        # Remaining ~12-16GB easily fits batch=8. VAE decode is batch-sequential.
        "max_duration_with_lm": 480,  # 8 minutes
        "max_duration_without_lm": 480,  # 8 minutes
        "max_batch_size_with_lm": 8,
        "max_batch_size_without_lm": 8,
        "init_lm_default": True,
        "available_lm_models": ["acestep-5Hz-lm-0.6B", "acestep-5Hz-lm-1.7B", "acestep-5Hz-lm-4B"],
        "recommended_lm_model": "acestep-5Hz-lm-1.7B",
        "lm_backend_restriction": "all",
        "recommended_backend": "vllm",
        "offload_to_cpu_default": False,  # 20-24GB can hold all models
        "offload_dit_to_cpu_default": False,
        "quantization_default": False,  # Enough VRAM, quantization optional
        "compile_model_default": True,
        "lm_memory_gb": {"0.6B": 3, "1.7B": 8, "4B": 12},
    },
    "unlimited": {  # >= 24GB
        "max_duration_with_lm": 600,  # 10 minutes (max supported)
        "max_duration_without_lm": 600,  # 10 minutes
        "max_batch_size_with_lm": 8,
        "max_batch_size_without_lm": 8,
        "init_lm_default": True,
        "available_lm_models": ["acestep-5Hz-lm-0.6B", "acestep-5Hz-lm-1.7B", "acestep-5Hz-lm-4B"],
        "recommended_lm_model": "acestep-5Hz-lm-4B",
        "lm_backend_restriction": "all",
        "recommended_backend": "vllm",
        "offload_to_cpu_default": False,
        "offload_dit_to_cpu_default": False,
        "quantization_default": False,  # Plenty of VRAM
        "compile_model_default": True,
        "lm_memory_gb": {"0.6B": 3, "1.7B": 8, "4B": 12},
    },
}

# Backward compatibility alias: code that references "tier6" gets tier6b behavior
GPU_TIER_CONFIGS["tier6"] = GPU_TIER_CONFIGS["tier6b"]


def get_gpu_memory_gb() -> float:
    """
    Get GPU memory in GB. Returns 0 if no GPU is available.
    
    Debug Mode:
        Set environment variable MAX_CUDA_VRAM to override the detected GPU memory.
        Example: MAX_CUDA_VRAM=8 python acestep  # Simulates 8GB GPU
        
        For MPS testing, set MAX_MPS_VRAM to override MPS memory detection.
        Example: MAX_MPS_VRAM=16 python acestep  # Simulates 16GB MPS
        
        This allows testing different GPU tier configurations on high-end hardware.
    """
    # Check for debug override first
    debug_vram = os.environ.get(DEBUG_MAX_CUDA_VRAM_ENV)
    if debug_vram is not None:
        try:
            simulated_gb = float(debug_vram)
            logger.warning(f"⚠️ DEBUG MODE: Simulating GPU memory as {simulated_gb:.1f}GB (set via {DEBUG_MAX_CUDA_VRAM_ENV} environment variable)")
            # Also enforce a hard VRAM cap via PyTorch so that the allocator
            # cannot use more than the simulated amount.  This makes the
            # simulation realistic — without it, models still load into the
            # real (larger) GPU memory and nvitop shows much higher usage.
            try:
                import torch
                if torch.cuda.is_available():
                    total_bytes = torch.cuda.get_device_properties(0).total_memory
                    total_gb = total_bytes / (1024 ** 3)
                    if simulated_gb < total_gb:
                        # When simulating a smaller GPU on a larger one, the host
                        # GPU's CUDA context is typically much bigger (e.g. A100
                        # ~1.4GB vs GTX 1060 ~0.3GB).  Using the host context
                        # would over-penalise the allocator budget.
                        #
                        # Instead we use a *reference* context size that matches
                        # what the target-class GPU would actually have.  Consumer
                        # GPUs (≤24GB) typically have 0.3-0.5GB context overhead.
                        REFERENCE_CONTEXT_GB = MODEL_VRAM.get("cuda_context", 0.5)
                        allocator_budget_gb = max(0.5, simulated_gb - REFERENCE_CONTEXT_GB)
                        fraction = allocator_budget_gb / total_gb
                        # Clamp to [0.01, 1.0] to satisfy PyTorch constraints
                        fraction = max(0.01, min(1.0, fraction))
                        torch.cuda.set_per_process_memory_fraction(fraction)
                        logger.warning(
                            f"⚠️ DEBUG MODE: Set CUDA memory fraction to {fraction:.4f} "
                            f"(allocator_budget={allocator_budget_gb:.2f}GB, "
                            f"ref_context={REFERENCE_CONTEXT_GB:.2f}GB, target={simulated_gb:.1f}GB, "
                            f"total={total_gb:.1f}GB) to enforce hard VRAM cap"
                        )
            except Exception as e:
                logger.warning(f"⚠️ DEBUG MODE: Could not enforce CUDA memory cap: {e}")
            return simulated_gb
        except ValueError:
            logger.warning(f"Invalid {DEBUG_MAX_CUDA_VRAM_ENV} value: {debug_vram}, ignoring")
    debug_mps_vram = os.environ.get(DEBUG_MAX_MPS_VRAM_ENV)
    if debug_mps_vram is not None:
        try:
            simulated_gb = float(debug_mps_vram)
            logger.warning(f"⚠️ DEBUG MODE: Simulating MPS memory as {simulated_gb:.1f}GB (set via {DEBUG_MAX_MPS_VRAM_ENV} environment variable)")
            return simulated_gb
        except ValueError:
            logger.warning(f"Invalid {DEBUG_MAX_MPS_VRAM_ENV} value: {debug_mps_vram}, ignoring")
    
    try:
        import torch
        if torch.cuda.is_available():
            # Get total memory of the first GPU in GB
            total_memory = torch.cuda.get_device_properties(0).total_memory
            memory_gb = total_memory / (1024**3)  # Convert bytes to GB
            device_name = torch.cuda.get_device_name(0)
            is_rocm = hasattr(torch.version, 'hip') and torch.version.hip is not None
            if is_rocm:
                logger.info(f"ROCm GPU detected: {device_name} ({memory_gb:.1f} GB, HIP {torch.version.hip})")
            else:
                logger.info(f"CUDA GPU detected: {device_name} ({memory_gb:.1f} GB)")
            return memory_gb
        elif hasattr(torch, 'xpu') and torch.xpu.is_available():
            # Get total memory of the first XPU in GB
            total_memory = torch.xpu.get_device_properties(0).total_memory
            memory_gb = total_memory / (1024**3)  # Convert bytes to GB
            return memory_gb
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            mps_module = getattr(torch, "mps", None)
            try:
                if mps_module is not None and hasattr(mps_module, "recommended_max_memory"):
                    total_memory = mps_module.recommended_max_memory()
                    memory_gb = total_memory / (1024**3)  # Convert bytes to GB
                    return memory_gb
                if mps_module is not None and hasattr(mps_module, "get_device_properties"):
                    props = mps_module.get_device_properties(0)
                    total_memory = getattr(props, "total_memory", None)
                    if total_memory:
                        memory_gb = total_memory / (1024**3)
                        return memory_gb
            except Exception as e:
                logger.warning(f"Failed to detect MPS memory: {e}")

            # Fallback: estimate from system unified memory (Apple Silicon shares CPU/GPU RAM)
            try:
                import subprocess
                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True, text=True, timeout=5
                )
                total_system_bytes = int(result.stdout.strip())
                # MPS can use up to ~75% of unified memory for GPU workloads
                memory_gb = (total_system_bytes / (1024**3)) * 0.75
                return memory_gb
            except Exception:
                logger.warning(f"MPS available but total memory not exposed. Set {DEBUG_MAX_MPS_VRAM_ENV} to enable tiering.")
                # Conservative fallback for M1/M2
                return 8.0
        else:
            # No GPU detected - provide diagnostic information
            _log_gpu_diagnostic_info(torch)
            return 0
    except Exception as e:
        logger.warning(f"Failed to detect GPU memory: {e}")
        return 0


def _log_gpu_diagnostic_info(torch_module):
    """
    Log diagnostic information when GPU is not detected to help users troubleshoot.
    
    Args:
        torch_module: The torch module to inspect for build information
    """
    logger.warning("=" * 80)
    logger.warning("⚠️ GPU NOT DETECTED - DIAGNOSTIC INFORMATION")
    logger.warning("=" * 80)
    
    # Check PyTorch build type
    is_rocm_build = hasattr(torch_module.version, 'hip') and torch_module.version.hip is not None
    is_cuda_build = hasattr(torch_module.version, 'cuda') and torch_module.version.cuda is not None
    
    if is_rocm_build:
        logger.warning("✓ PyTorch ROCm build detected")
        logger.warning(f"  HIP version: {torch_module.version.hip}")
        logger.warning("")
        logger.warning("❌ torch.cuda.is_available() returned False")
        logger.warning("")
        logger.warning("Common causes for AMD/ROCm GPUs:")
        logger.warning("  1. ROCm drivers not installed or not properly configured")
        logger.warning("  2. GPU not supported by installed ROCm version")
        logger.warning("  3. Missing or incorrect HSA_OVERRIDE_GFX_VERSION environment variable")
        logger.warning("  4. ROCm runtime libraries not in system path")
        logger.warning("")
        
        # Check for common environment variables
        hsa_override = os.environ.get('HSA_OVERRIDE_GFX_VERSION')
        if hsa_override:
            logger.warning(f"  HSA_OVERRIDE_GFX_VERSION is set to: {hsa_override}")
        else:
            logger.warning("  ⚠️ HSA_OVERRIDE_GFX_VERSION is not set")
            logger.warning("     For RDNA3 GPUs (RX 7000 series, RX 9000 series):")
            logger.warning("       - RX 7900 XT/XTX, RX 9070 XT: set HSA_OVERRIDE_GFX_VERSION=11.0.0")
            logger.warning("       - RX 7800 XT, RX 7700 XT: set HSA_OVERRIDE_GFX_VERSION=11.0.1")
            logger.warning("       - RX 7600: set HSA_OVERRIDE_GFX_VERSION=11.0.2")
        
        logger.warning("")
        logger.warning("Troubleshooting steps:")
        logger.warning("  1. Verify ROCm installation:")
        logger.warning("     rocm-smi  # Should list your GPU")
        logger.warning("  2. Check PyTorch ROCm build:")
        logger.warning("     python -c \"import torch; print(f'ROCm: {torch.version.hip}')\"")
        logger.warning("  3. Set HSA_OVERRIDE_GFX_VERSION for your GPU (see above)")
        logger.warning("  4. On Windows: Use start_gradio_ui_rocm.bat which sets required env vars")
        logger.warning("  5. See docs/en/ACE-Step1.5-Rocm-Manual-Linux.md for Linux setup")
        logger.warning("  6. See requirements-rocm.txt for Windows ROCm setup instructions")
        
    elif is_cuda_build:
        logger.warning("✓ PyTorch CUDA build detected")
        logger.warning(f"  CUDA version: {torch_module.version.cuda}")
        logger.warning("")
        logger.warning("❌ torch.cuda.is_available() returned False")
        logger.warning("")
        logger.warning("Common causes for NVIDIA GPUs:")
        logger.warning("  1. NVIDIA drivers not installed")
        logger.warning("  2. CUDA runtime not installed or version mismatch")
        logger.warning("  3. GPU not supported by installed CUDA version")
        logger.warning("")
        logger.warning("Troubleshooting steps:")
        logger.warning("  1. Verify NVIDIA driver installation:")
        logger.warning("     nvidia-smi  # Should list your GPU")
        logger.warning("  2. Check CUDA version compatibility")
        logger.warning("  3. Reinstall PyTorch with CUDA support:")
        logger.warning(f"     pip install torch --index-url {PYTORCH_CUDA_INSTALL_URL}")
        
    else:
        logger.warning("⚠️ PyTorch build type: CPU-only")
        logger.warning("")
        logger.warning("You have installed a CPU-only version of PyTorch!")
        logger.warning("")
        logger.warning("For NVIDIA GPUs:")
        logger.warning(f"  pip install torch --index-url {PYTORCH_CUDA_INSTALL_URL}")
        logger.warning("")
        logger.warning("For AMD GPUs with ROCm:")
        logger.warning("  Windows: See requirements-rocm.txt for detailed instructions")
        logger.warning(f"  Linux: pip install torch --index-url {PYTORCH_ROCM_INSTALL_URL}")
        logger.warning("")
        logger.warning("For more information, see README.md section 'AMD / ROCm GPUs'")
    
    logger.warning("=" * 80)


def get_gpu_tier(gpu_memory_gb: float) -> str:
    """
    Determine GPU tier based on available memory.
    
    Args:
        gpu_memory_gb: GPU memory in GB
        
    Returns:
        Tier string: "tier1", "tier2", "tier3", "tier4", "tier5", "tier6a", "tier6b", or "unlimited"
    """
    if gpu_memory_gb <= 0:
        # CPU mode - use tier1 limits
        return "tier1"
    elif gpu_memory_gb <= 4:
        return "tier1"
    elif gpu_memory_gb <= 6:
        return "tier2"
    elif gpu_memory_gb <= 8:
        return "tier3"
    elif gpu_memory_gb <= 12:
        return "tier4"
    elif gpu_memory_gb < VRAM_16GB_MIN_GB:
        return "tier5"
    elif gpu_memory_gb < VRAM_AUTO_OFFLOAD_THRESHOLD_GB:
        # 16-20GB range: tier6a (constrained, needs offload)
        if gpu_memory_gb < 16.0:
            logger.info(f"Detected {gpu_memory_gb:.2f}GB VRAM — treating as 16GB class GPU")
        return "tier6a"
    elif gpu_memory_gb <= 24:
        return "tier6b"
    else:
        return "unlimited"


def get_gpu_config(gpu_memory_gb: Optional[float] = None) -> GPUConfig:
    """
    Get GPU configuration based on detected or provided GPU memory.
    
    On macOS with MPS (Apple Silicon), several overrides are applied
    automatically regardless of the tier selected by memory size:
    
    - ``compile_model_default = False`` — ``torch.compile`` is not supported
      on MPS and would error or silently fall back to eager mode.
    - ``quantization_default = False`` — torchao INT8 quantization is
      incompatible with MPS / macOS.
    - ``recommended_backend = "mlx"`` — MLX provides native Apple Silicon
      acceleration for the 5Hz LM; vllm requires CUDA.
    - ``lm_backend_restriction = "pt_mlx_only"`` — vllm cannot run on MPS.
    - ``offload_to_cpu_default = False`` — Apple Silicon uses unified memory;
      offloading to CPU provides no benefit and adds overhead.
    - ``offload_dit_to_cpu_default = False`` — same reason.
    
    Args:
        gpu_memory_gb: GPU memory in GB. If None, will be auto-detected.
        
    Returns:
        GPUConfig object with all configuration parameters
    """
    if gpu_memory_gb is None:
        gpu_memory_gb = get_gpu_memory_gb()
    
    tier = get_gpu_tier(gpu_memory_gb)
    config = GPU_TIER_CONFIGS[tier]
    
    # --- MPS (Apple Silicon) overrides ---
    _mps = is_mps_platform()
    if _mps:
        logger.info(
            f"macOS MPS detected ({gpu_memory_gb:.1f} GB unified memory, tier={tier}). "
            "Applying Apple Silicon optimizations: no compile, no quantization, "
            "mlx backend, no CPU offload."
        )
    
    return GPUConfig(
        tier=tier,
        gpu_memory_gb=gpu_memory_gb,
        max_duration_with_lm=config["max_duration_with_lm"],
        max_duration_without_lm=config["max_duration_without_lm"],
        max_batch_size_with_lm=config["max_batch_size_with_lm"],
        max_batch_size_without_lm=config["max_batch_size_without_lm"],
        init_lm_default=config["init_lm_default"],
        available_lm_models=config["available_lm_models"],
        recommended_lm_model=config.get("recommended_lm_model", ""),
        # MPS: vllm requires CUDA, restrict to pt/mlx; prefer mlx for native acceleration
        lm_backend_restriction="pt_mlx_only" if _mps else config.get("lm_backend_restriction", "all"),
        recommended_backend="mlx" if _mps else config.get("recommended_backend", "vllm"),
        # MPS: unified memory — offloading to CPU is pointless overhead
        offload_to_cpu_default=False if _mps else config.get("offload_to_cpu_default", True),
        offload_dit_to_cpu_default=False if _mps else config.get("offload_dit_to_cpu_default", True),
        # MPS: torchao quantization is not supported
        quantization_default=False if _mps else config.get("quantization_default", True),
        # MPS: torch.compile unsupported (redirected to mx.compile at runtime);
        # default to False — user can opt in via the UI checkbox.
        compile_model_default=False if _mps else config.get("compile_model_default", True),
        lm_memory_gb=config["lm_memory_gb"],
    )


def get_lm_model_size(model_path: str) -> str:
    """
    Extract LM model size from model path.
    
    Args:
        model_path: Model path string (e.g., "acestep-5Hz-lm-0.6B", "acestep-5Hz-lm-0.6B-v4-fix")
        
    Returns:
        Model size string: "0.6B", "1.7B", or "4B"
    """
    if "0.6B" in model_path:
        return "0.6B"
    elif "1.7B" in model_path:
        return "1.7B"
    elif "4B" in model_path:
        return "4B"
    else:
        # Default to smallest model assumption
        return "0.6B"


def is_lm_model_size_allowed(disk_model_name: str, tier_available_models: List[str]) -> bool:
    """
    Check if a disk LM model is allowed by the tier's available models list.
    
    Uses size-based matching so that variants like "acestep-5Hz-lm-0.6B-v4-fix"
    are correctly matched against "acestep-5Hz-lm-0.6B" in the tier config.
    
    Args:
        disk_model_name: Actual model directory name on disk (e.g., "acestep-5Hz-lm-0.6B-v4-fix")
        tier_available_models: List of tier-allowed model base names (e.g., ["acestep-5Hz-lm-0.6B"])
        
    Returns:
        True if the model's size class is allowed by the tier
    """
    if not tier_available_models:
        return False
    model_size = get_lm_model_size(disk_model_name)
    for tier_model in tier_available_models:
        if model_size == get_lm_model_size(tier_model):
            return True
    return False


def find_best_lm_model_on_disk(recommended_model: str, disk_models: List[str]) -> Optional[str]:
    """
    Find the best matching disk model for a recommended tier model.
    
    If the exact recommended model exists on disk, return it.
    Otherwise, find a disk model with the same size class (e.g., "0.6B").
    Prefers models with version suffixes (e.g., "-v4-fix") as they are likely newer.
    
    Args:
        recommended_model: Tier-recommended model name (e.g., "acestep-5Hz-lm-0.6B")
        disk_models: List of model names actually on disk
        
    Returns:
        Best matching disk model name, or None if no match
    """
    if not recommended_model or not disk_models:
        return disk_models[0] if disk_models else None
    
    # Exact match first
    if recommended_model in disk_models:
        return recommended_model
    
    # Size-based match: find all disk models with same size
    target_size = get_lm_model_size(recommended_model)
    candidates = [m for m in disk_models if get_lm_model_size(m) == target_size]
    
    if candidates:
        # Prefer the one with the longest name (likely has version suffix = newer)
        return max(candidates, key=len)
    
    # No match for recommended size; return first available disk model
    return disk_models[0] if disk_models else None


def get_lm_gpu_memory_ratio(model_path: str, total_gpu_memory_gb: float) -> Tuple[float, float]:
    """
    Calculate GPU memory utilization ratio for LM model.
    
    This function now uses *actually free* VRAM (via torch.cuda.mem_get_info)
    when available, instead of computing the ratio purely from total VRAM.
    This is critical because DiT, VAE, and text encoder are already loaded
    when the LM initializes, so the "available" memory is much less than total.
    
    Args:
        model_path: LM model path (e.g., "acestep-5Hz-lm-0.6B")
        total_gpu_memory_gb: Total GPU memory in GB (used as fallback)
        
    Returns:
        Tuple of (gpu_memory_utilization_ratio, target_memory_gb)
    """
    model_size = get_lm_model_size(model_path)
    
    # Use empirical LM VRAM measurements for target memory
    lm_info = LM_VRAM.get(model_size, LM_VRAM["0.6B"])
    lm_weights_gb = lm_info["weights"]
    lm_kv_cache_gb = lm_info["kv_cache_4k"]
    
    # Total target = model weights + KV cache + small overhead
    target_gb = lm_weights_gb
    total_target_gb = lm_weights_gb + lm_kv_cache_gb + 0.3  # 0.3 GB overhead
    
    # Try to use actual free memory for a more accurate ratio
    free_gb = None
    try:
        import torch
        if torch.cuda.is_available():
            free_bytes, total_bytes = torch.cuda.mem_get_info()
            free_gb = free_bytes / (1024**3)
            actual_total_gb = total_bytes / (1024**3)
            
            # If MAX_CUDA_VRAM is set, use the simulated values instead
            # because set_per_process_memory_fraction limits actual allocation
            debug_vram = os.environ.get(DEBUG_MAX_CUDA_VRAM_ENV)
            if debug_vram is not None:
                try:
                    simulated_gb = float(debug_vram)
                    if simulated_gb < actual_total_gb:
                        # Use reference context (matching set_per_process_memory_fraction)
                        ref_context_gb = MODEL_VRAM.get("cuda_context", 0.5)
                        allocator_budget_gb = max(0.5, simulated_gb - ref_context_gb)
                        reserved_gb = torch.cuda.memory_reserved() / (1024**3)
                        free_gb = max(0, allocator_budget_gb - reserved_gb)
                        actual_total_gb = simulated_gb
                except (ValueError, TypeError):
                    pass
            
            # The ratio is relative to total GPU memory (nano-vllm convention),
            # but we compute it so that the LM only claims what's actually free
            # minus a safety margin for DiT inference activations.
            # Reserve at least 1.5 GB for DiT inference activations
            dit_reserve_gb = 1.5
            usable_for_lm = max(0, free_gb - dit_reserve_gb - VRAM_SAFETY_MARGIN_GB)
            
            # Cap to what the LM actually needs
            usable_for_lm = min(usable_for_lm, total_target_gb)
            
            # Convert to ratio of total GPU memory
            # nano-vllm uses: target_total_usage = total * gpu_memory_utilization
            # We want: (total * ratio) = current_usage + usable_for_lm
            current_usage_gb = actual_total_gb - free_gb
            desired_total_usage = current_usage_gb + usable_for_lm
            ratio = desired_total_usage / actual_total_gb
            
            ratio = min(0.9, max(0.1, ratio))
            
            logger.info(
                f"[get_lm_gpu_memory_ratio] model={model_size}, free={free_gb:.2f}GB, "
                f"current_usage={current_usage_gb:.2f}GB, lm_target={total_target_gb:.2f}GB, "
                f"usable_for_lm={usable_for_lm:.2f}GB, ratio={ratio:.3f}"
            )
            return ratio, target_gb
    except Exception as e:
        logger.warning(f"[get_lm_gpu_memory_ratio] Failed to query free VRAM: {e}, using fallback")
    
    # Fallback: compute ratio from total VRAM (less accurate)
    if total_gpu_memory_gb >= 24:
        ratio = min(0.9, max(0.2, total_target_gb / total_gpu_memory_gb))
    else:
        ratio = min(0.9, max(0.1, total_target_gb / total_gpu_memory_gb))
    
    return ratio, target_gb


def compute_adaptive_config(total_vram_gb: float, dit_type: str = "turbo") -> GPUConfig:
    """
    Compute GPU configuration based on what actually fits in VRAM.
    
    This is a VRAM-budget-based approach: instead of hard-coded tier boundaries,
    we calculate how much memory each component needs and determine what fits.
    
    Args:
        total_vram_gb: Total GPU VRAM in GB
        dit_type: "turbo" or "base" (affects inference VRAM due to CFG)
        
    Returns:
        GPUConfig with parameters that fit within the VRAM budget
    """
    # Calculate base VRAM usage (always loaded)
    dit_key = f"dit_{dit_type}" if f"dit_{dit_type}" in MODEL_VRAM else "dit_turbo"
    base_usage = (
        MODEL_VRAM[dit_key]
        + MODEL_VRAM["vae"]
        + MODEL_VRAM["text_encoder"]
        + MODEL_VRAM["cuda_context"]
        + MODEL_VRAM["silence_latent"]
        + VRAM_SAFETY_MARGIN_GB
    )
    
    available = total_vram_gb - base_usage
    
    if available <= 0:
        # Not enough for even base models - CPU offload required
        return get_gpu_config(total_vram_gb)
    
    # Determine which LM models fit
    available_lm_models = []
    lm_memory_gb = {}
    
    for size_key in ["0.6B", "1.7B", "4B"]:
        lm_info = LM_VRAM[size_key]
        lm_total = lm_info["weights"] + lm_info["kv_cache_4k"]
        # LM needs to fit with some room left for inference activations
        inference_per_batch = DIT_INFERENCE_VRAM_PER_BATCH.get(dit_type, 0.8)
        if lm_total + inference_per_batch <= available:
            model_name = f"acestep-5Hz-lm-{size_key}"
            available_lm_models.append(model_name)
            lm_memory_gb[size_key] = lm_info["weights"] + lm_info["kv_cache_4k"]
    
    # Determine max batch sizes
    inference_per_batch = DIT_INFERENCE_VRAM_PER_BATCH.get(dit_type, 0.8)
    
    # Without LM: all available VRAM goes to inference
    max_batch_no_lm = max(1, int(available / inference_per_batch))
    max_batch_no_lm = min(max_batch_no_lm, 8)  # Cap at 8
    
    # With LM: subtract the largest available LM from available
    if available_lm_models:
        largest_lm_size = list(lm_memory_gb.keys())[-1]
        lm_usage = lm_memory_gb[largest_lm_size]
        remaining_for_inference = available - lm_usage
        max_batch_with_lm = max(1, int(remaining_for_inference / inference_per_batch))
        max_batch_with_lm = min(max_batch_with_lm, 8)
    else:
        max_batch_with_lm = max_batch_no_lm
    
    # Determine duration limits based on available VRAM
    # Longer durations need more VRAM for latents
    if total_vram_gb >= 24:
        max_dur_lm = 600
        max_dur_no_lm = 600
    elif total_vram_gb >= 20:
        max_dur_lm = 480
        max_dur_no_lm = 480
    elif total_vram_gb >= 16:
        max_dur_lm = 360
        max_dur_no_lm = 480
    elif total_vram_gb >= 12:
        max_dur_lm = 240
        max_dur_no_lm = 360
    elif total_vram_gb >= 8:
        max_dur_lm = 240
        max_dur_no_lm = 360
    else:
        max_dur_lm = 180
        max_dur_no_lm = 180
    
    tier = get_gpu_tier(total_vram_gb)
    tier_config = GPU_TIER_CONFIGS.get(tier, {})
    
    return GPUConfig(
        tier=tier,
        gpu_memory_gb=total_vram_gb,
        max_duration_with_lm=max_dur_lm,
        max_duration_without_lm=max_dur_no_lm,
        max_batch_size_with_lm=max_batch_with_lm,
        max_batch_size_without_lm=max_batch_no_lm,
        init_lm_default=bool(available_lm_models),
        available_lm_models=available_lm_models,
        recommended_lm_model=tier_config.get("recommended_lm_model", available_lm_models[0] if available_lm_models else ""),
        lm_backend_restriction=tier_config.get("lm_backend_restriction", "all"),
        recommended_backend=tier_config.get("recommended_backend", "vllm"),
        offload_to_cpu_default=tier_config.get("offload_to_cpu_default", True),
        offload_dit_to_cpu_default=tier_config.get("offload_dit_to_cpu_default", True),
        quantization_default=tier_config.get("quantization_default", True),
        compile_model_default=tier_config.get("compile_model_default", True),
        lm_memory_gb=lm_memory_gb,
    )


def get_effective_free_vram_gb(device_index: int = 0) -> float:
    """
    Get the effective free VRAM in GB, accounting for per-process memory fraction.
    
    torch.cuda.mem_get_info() reports *device-level* free memory, which ignores
    the per-process cap set by torch.cuda.set_per_process_memory_fraction().
    
    This function computes:
        effective_free = min(device_free, process_allowed - process_allocated)
    
    where process_allowed = total_memory * memory_fraction.
    
    Returns 0 if no GPU is available or on error.
    """
    try:
        import torch
        if hasattr(torch, 'cuda') and torch.cuda.is_available():
            device_free_bytes, total_bytes = torch.cuda.mem_get_info(device_index)
            
            # Check if a per-process memory fraction has been set
            # We detect this by checking MAX_CUDA_VRAM env var (our simulation mechanism)
            debug_vram = os.environ.get(DEBUG_MAX_CUDA_VRAM_ENV)
            if debug_vram is not None:
                try:
                    simulated_gb = float(debug_vram)
                    total_gb = total_bytes / (1024 ** 3)
                    if simulated_gb < total_gb:
                        # Per-process cap is active.
                        # Use the same reference context as set_per_process_memory_fraction.
                        ref_context_gb = MODEL_VRAM.get("cuda_context", 0.5)
                        allocator_budget_gb = max(0.5, simulated_gb - ref_context_gb)
                        allocator_budget_bytes = allocator_budget_gb * (1024 ** 3)
                        reserved_bytes = torch.cuda.memory_reserved(device_index)
                        # Free = what the allocator is allowed minus what it has reserved
                        process_free = allocator_budget_bytes - reserved_bytes
                        effective_free = min(device_free_bytes, process_free)
                        return max(0.0, effective_free / (1024 ** 3))
                except (ValueError, TypeError):
                    pass
            
            return device_free_bytes / (1024 ** 3)

        elif hasattr(torch, 'xpu') and torch.xpu.is_available():
            # Support for Intel XPU (IPEX)
            # Try mem_get_info first (available in newer IPEX versions)
            if hasattr(torch.xpu, 'mem_get_info'):
                try:
                    device_free_bytes, _ = torch.xpu.mem_get_info(device_index)
                    return device_free_bytes / (1024 ** 3)
                except Exception:
                    pass
            
            # Fallback for older IPEX or if mem_get_info fails: total - reserved
            try:
                total_bytes = torch.xpu.get_device_properties(device_index).total_memory
                reserved_bytes = torch.xpu.memory_reserved(device_index)
                return max(0.0, (total_bytes - reserved_bytes) / (1024 ** 3))
            except Exception:
                return 0.0
        
        return 0.0
    except Exception:
        return 0.0


def get_available_vram_gb() -> float:
    """
    Get currently available (free) GPU VRAM in GB.
    Returns 0 if no GPU is available or on error.
    
    This is an alias for get_effective_free_vram_gb() that accounts for
    per-process memory fraction caps.
    """
    return get_effective_free_vram_gb()


def estimate_inference_vram(
    batch_size: int,
    duration_s: float,
    dit_type: str = "turbo",
    with_lm: bool = False,
    lm_size: str = "0.6B",
) -> float:
    """
    Estimate total VRAM needed for a generation request.
    
    Args:
        batch_size: Number of samples to generate
        duration_s: Audio duration in seconds
        dit_type: "turbo" or "base"
        with_lm: Whether LM is loaded
        lm_size: LM model size if with_lm is True
        
    Returns:
        Estimated VRAM in GB
    """
    # Base model weights
    dit_key = f"dit_{dit_type}" if f"dit_{dit_type}" in MODEL_VRAM else "dit_turbo"
    base = (
        MODEL_VRAM[dit_key]
        + MODEL_VRAM["vae"]
        + MODEL_VRAM["text_encoder"]
        + MODEL_VRAM["cuda_context"]
    )
    
    # DiT inference activations (scales with batch size and duration)
    per_batch = DIT_INFERENCE_VRAM_PER_BATCH.get(dit_type, 0.8)
    # Duration scaling: longer audio = more latent frames = more memory
    duration_factor = max(1.0, duration_s / 60.0)  # Normalize to 60s baseline
    inference = per_batch * batch_size * duration_factor
    
    # LM memory
    lm_mem = 0.0
    if with_lm and lm_size in LM_VRAM:
        lm_info = LM_VRAM[lm_size]
        lm_mem = lm_info["weights"] + lm_info["kv_cache_4k"]
    
    return base + inference + lm_mem + VRAM_SAFETY_MARGIN_GB


def check_duration_limit(
    duration: float,
    gpu_config: GPUConfig,
    lm_initialized: bool
) -> Tuple[bool, str]:
    """
    Check if requested duration is within limits for current GPU configuration.
    
    Args:
        duration: Requested duration in seconds
        gpu_config: Current GPU configuration
        lm_initialized: Whether LM is initialized
        
    Returns:
        Tuple of (is_valid, warning_message)
    """
    max_duration = gpu_config.max_duration_with_lm if lm_initialized else gpu_config.max_duration_without_lm
    
    if duration > max_duration:
        warning_msg = (
            f"⚠️ Requested duration ({duration:.0f}s) exceeds the limit for your GPU "
            f"({gpu_config.gpu_memory_gb:.1f}GB). Maximum allowed: {max_duration}s "
            f"({'with' if lm_initialized else 'without'} LM). "
            f"Duration will be clamped to {max_duration}s."
        )
        return False, warning_msg
    
    return True, ""


def check_batch_size_limit(
    batch_size: int,
    gpu_config: GPUConfig,
    lm_initialized: bool
) -> Tuple[bool, str]:
    """
    Check if requested batch size is within limits for current GPU configuration.
    
    Args:
        batch_size: Requested batch size
        gpu_config: Current GPU configuration
        lm_initialized: Whether LM is initialized
        
    Returns:
        Tuple of (is_valid, warning_message)
    """
    max_batch_size = gpu_config.max_batch_size_with_lm if lm_initialized else gpu_config.max_batch_size_without_lm
    
    if batch_size > max_batch_size:
        warning_msg = (
            f"⚠️ Requested batch size ({batch_size}) exceeds the limit for your GPU "
            f"({gpu_config.gpu_memory_gb:.1f}GB). Maximum allowed: {max_batch_size} "
            f"({'with' if lm_initialized else 'without'} LM). "
            f"Batch size will be clamped to {max_batch_size}."
        )
        return False, warning_msg
    
    return True, ""


def is_lm_model_supported(model_path: str, gpu_config: GPUConfig) -> Tuple[bool, str]:
    """
    Check if the specified LM model is supported for current GPU configuration.
    
    Args:
        model_path: LM model path
        gpu_config: Current GPU configuration
        
    Returns:
        Tuple of (is_supported, warning_message)
    """
    if not gpu_config.available_lm_models:
        return False, (
            f"⚠️ Your GPU ({gpu_config.gpu_memory_gb:.1f}GB) does not have enough memory "
            f"to run any LM model. Please disable LM initialization."
        )
    
    model_size = get_lm_model_size(model_path)
    
    # Check if model size is in available models
    for available_model in gpu_config.available_lm_models:
        if model_size in available_model:
            return True, ""
    
    return False, (
        f"⚠️ LM model {model_path} ({model_size}) is not supported for your GPU "
        f"({gpu_config.gpu_memory_gb:.1f}GB). Available models: {', '.join(gpu_config.available_lm_models)}"
    )


def get_recommended_lm_model(gpu_config: GPUConfig) -> Optional[str]:
    """
    Get recommended LM model for current GPU configuration.
    
    Args:
        gpu_config: Current GPU configuration
        
    Returns:
        Recommended LM model path, or None if LM is not supported
    """
    if not gpu_config.available_lm_models:
        return None
    
    # Return the largest available model (last in the list)
    return gpu_config.available_lm_models[-1]


def print_gpu_config_info(gpu_config: GPUConfig):
    """Print GPU configuration information for debugging."""
    logger.info(f"GPU Configuration:")
    logger.info(f"  - GPU Memory: {gpu_config.gpu_memory_gb:.1f} GB")
    logger.info(f"  - Tier: {gpu_config.tier}")
    logger.info(f"  - Max Duration (with LM): {gpu_config.max_duration_with_lm}s ({gpu_config.max_duration_with_lm // 60} min)")
    logger.info(f"  - Max Duration (without LM): {gpu_config.max_duration_without_lm}s ({gpu_config.max_duration_without_lm // 60} min)")
    logger.info(f"  - Max Batch Size (with LM): {gpu_config.max_batch_size_with_lm}")
    logger.info(f"  - Max Batch Size (without LM): {gpu_config.max_batch_size_without_lm}")
    logger.info(f"  - Init LM by Default: {gpu_config.init_lm_default}")
    logger.info(f"  - Available LM Models: {gpu_config.available_lm_models or 'None'}")


# Human-readable tier labels for UI display
GPU_TIER_LABELS = {
    "tier1": "tier1 (≤4GB)",
    "tier2": "tier2 (4-6GB)",
    "tier3": "tier3 (6-8GB)",
    "tier4": "tier4 (8-12GB)",
    "tier5": "tier5 (12-16GB)",
    "tier6a": "tier6a (16-20GB)",
    "tier6b": "tier6b (20-24GB)",
    "unlimited": "unlimited (≥24GB)",
}

# Ordered list of tier keys for dropdown
GPU_TIER_CHOICES = list(GPU_TIER_LABELS.items())  # [(value, label), ...]


def get_gpu_device_name() -> str:
    """
    Get the GPU device name string.
    
    Returns:
        Human-readable GPU name, e.g. "NVIDIA GeForce RTX 4060 Ti",
        "Apple M2 Pro (MPS)", "CPU only", etc.
    """
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
        elif hasattr(torch, 'xpu') and torch.xpu.is_available():
            props = torch.xpu.get_device_properties(0)
            return getattr(props, 'name', 'Intel XPU')
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            # MPS doesn't expose a device name; use platform info
            try:
                import platform
                chip = platform.processor() or "Apple Silicon"
                return f"{chip} (MPS)"
            except Exception:
                return "Apple Silicon (MPS)"
        else:
            return "CPU only"
    except ImportError:
        return "Unknown (PyTorch not available)"


def get_gpu_config_for_tier(tier: str) -> GPUConfig:
    """
    Create a GPUConfig for a specific tier, applying platform overrides.
    
    This is used when the user manually selects a different tier in the UI.
    The actual gpu_memory_gb is preserved from the real hardware detection,
    but all tier-based settings come from the selected tier's config.
    
    Args:
        tier: Tier key, e.g. "tier3", "tier6a", "unlimited"
        
    Returns:
        GPUConfig with the selected tier's settings
    """
    if tier not in GPU_TIER_CONFIGS:
        logger.warning(f"Unknown tier '{tier}', falling back to auto-detected config")
        return get_gpu_config()
    
    # Keep the real GPU memory for informational purposes
    real_gpu_memory = get_gpu_memory_gb()
    config = GPU_TIER_CONFIGS[tier]
    
    _mps = is_mps_platform()
    if _mps:
        logger.info(f"Manual tier override to {tier} on macOS MPS — applying Apple Silicon overrides")
    
    return GPUConfig(
        tier=tier,
        gpu_memory_gb=real_gpu_memory,
        max_duration_with_lm=config["max_duration_with_lm"],
        max_duration_without_lm=config["max_duration_without_lm"],
        max_batch_size_with_lm=config["max_batch_size_with_lm"],
        max_batch_size_without_lm=config["max_batch_size_without_lm"],
        init_lm_default=config["init_lm_default"],
        available_lm_models=config["available_lm_models"],
        recommended_lm_model=config.get("recommended_lm_model", ""),
        lm_backend_restriction="pt_mlx_only" if _mps else config.get("lm_backend_restriction", "all"),
        recommended_backend="mlx" if _mps else config.get("recommended_backend", "vllm"),
        offload_to_cpu_default=False if _mps else config.get("offload_to_cpu_default", True),
        offload_dit_to_cpu_default=False if _mps else config.get("offload_dit_to_cpu_default", True),
        quantization_default=False if _mps else config.get("quantization_default", True),
        compile_model_default=False if _mps else config.get("compile_model_default", True),
        lm_memory_gb=config["lm_memory_gb"],
    )


# Global GPU config instance (initialized lazily)
_global_gpu_config: Optional[GPUConfig] = None


def get_global_gpu_config() -> GPUConfig:
    """Get the global GPU configuration, initializing if necessary."""
    global _global_gpu_config
    if _global_gpu_config is None:
        _global_gpu_config = get_gpu_config()
    return _global_gpu_config


def set_global_gpu_config(config: GPUConfig):
    """Set the global GPU configuration."""
    global _global_gpu_config
    _global_gpu_config = config
