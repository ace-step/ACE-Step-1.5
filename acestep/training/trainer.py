"""
LoRA Trainer for ACE-Step

Lightning Fabric-based trainer for LoRA fine-tuning of ACE-Step DiT decoder.
Supports training from preprocessed tensor files for optimal performance.
"""

import os
import time
import random
import math
from typing import Optional, List, Dict, Any, Tuple, Generator
from loguru import logger

import torch
import torch.nn as nn
import torch.nn.functional as F
from contextlib import nullcontext
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingWarmRestarts, LinearLR, SequentialLR

try:
    from lightning.fabric import Fabric
    from lightning.fabric.loggers import TensorBoardLogger
    LIGHTNING_AVAILABLE = True
except ImportError:
    LIGHTNING_AVAILABLE = False
    logger.warning("Lightning Fabric not installed. Training will use basic training loop.")

# OPTIMIZATION: Use 8-bit Adam to save some VRAM
try:
    import bitsandbytes as bnb
    HAS_BNB = True
except ImportError:
    HAS_BNB = False
    logger.warning("bitsandbytes not installed. Using standard AdamW.")

from acestep.training.configs import LoRAConfig, LoKRConfig, TrainingConfig
from acestep.training.lora_utils import (
    inject_lora_into_dit,
    save_lora_weights,
    save_training_checkpoint,
    load_training_checkpoint,
    check_peft_available,
)
from acestep.training.lokr_utils import (
    inject_lokr_into_dit,
    save_lokr_weights,
    save_lokr_training_checkpoint,
    check_lycoris_available,
)
from acestep.training.data_module import PreprocessedDataModule
from acestep.training.path_safety import safe_path


# Turbo model shift=3.0 discrete timesteps (8 steps, same as inference)
TURBO_SHIFT3_TIMESTEPS = [1.0, 0.9545454545454546, 0.9, 0.8333333333333334, 0.75, 0.6428571428571429, 0.5, 0.3]


def _normalize_device_type(device: Any) -> str:
    """Normalize torch device or string to canonical device type."""
    if isinstance(device, torch.device):
        return device.type
    if isinstance(device, str):
        return device.split(":", 1)[0]
    return str(device)


def _select_compute_dtype(device_type: str) -> torch.dtype:
    """Pick the compute dtype for each accelerator."""
    if device_type in ("cuda", "xpu"):
        return torch.bfloat16
    if device_type == "mps":
        return torch.float16
    return torch.float32


def _select_fabric_precision(device_type: str) -> str:
    """Pick Fabric precision plugin setting for each accelerator."""
    if device_type in ("cuda", "xpu"):
        return "bf16-mixed"
    if device_type == "mps":
        # Use AMP on MPS for better throughput. Trainable LoRA parameters are
        # explicitly forced to fp32 before optimizer/Fabric setup.
        return "16-mixed"
    return "32-true"


def _ensure_trainable_params_fp32(module: nn.Module) -> Tuple[int, int]:
    """Force trainable floating-point parameters to fp32."""
    casted = 0
    total = 0
    for p in module.parameters():
        if not p.requires_grad:
            continue
        total += 1
        if p.is_floating_point() and p.dtype != torch.float32:
            with torch.no_grad():
                p.data = p.data.float()
            casted += 1
    return casted, total


def _count_nonfinite_grads(params: List[torch.nn.Parameter]) -> Tuple[int, int]:
    """Count non-finite gradient tensors among params with gradients."""
    nonfinite = 0
    total_with_grad = 0
    for p in params:
        g = p.grad
        if g is None:
            continue
        total_with_grad += 1
        if not torch.isfinite(g).all():
            nonfinite += 1
    return nonfinite, total_with_grad


def _ensure_optimizer_params_fp32(optimizer: torch.optim.Optimizer) -> Tuple[int, int]:
    """Force optimizer parameter tensors to fp32 when trainable."""
    casted = 0
    total = 0
    for group in optimizer.param_groups:
        for p in group.get("params", []):
            if p is None:
                continue
            total += 1
            if p.is_floating_point() and p.dtype != torch.float32:
                with torch.no_grad():
                    p.data = p.data.float()
                casted += 1
    return casted, total


def _build_param_name_lookup(module: nn.Module, extra_module: Optional[nn.Module] = None) -> Dict[int, str]:
    """Build a best-effort id(param) -> name lookup for debug logging."""
    lookup: Dict[int, str] = {}
    for name, p in module.named_parameters():
        lookup[id(p)] = name
    if extra_module is not None:
        for name, p in extra_module.named_parameters():
            lookup.setdefault(id(p), f"lycoris_net.{name}")
    return lookup


def _count_nonfinite_grads_detailed(
    params: List[torch.nn.Parameter],
    param_name_lookup: Dict[int, str],
    detail_limit: int = 8,
) -> Tuple[int, int, List[str]]:
    """Count non-finite grads and return up to `detail_limit` offending tensor details."""
    nonfinite = 0
    total_with_grad = 0
    details: List[str] = []

    for p in params:
        g = p.grad
        if g is None:
            continue
        total_with_grad += 1
        if torch.isfinite(g).all():
            continue

        nonfinite += 1
        if len(details) >= detail_limit:
            continue

        pname = param_name_lookup.get(id(p), f"<unnamed:{id(p)}>")
        g32 = g.detach().float()
        nan_count = int(torch.isnan(g32).sum().item())
        inf_count = int(torch.isinf(g32).sum().item())
        finite_vals = g32[torch.isfinite(g32)]
        max_abs_finite = float(finite_vals.abs().max().item()) if finite_vals.numel() else float("nan")

        p32 = p.detach().float()
        param_nonfinite = int((~torch.isfinite(p32)).sum().item())
        details.append(
            f"{pname} | shape={tuple(p.shape)} grad_dtype={g.dtype} "
            f"nan={nan_count} inf={inf_count} max_abs_finite={max_abs_finite:.3e} "
            f"param_nonfinite={param_nonfinite}"
        )

    return nonfinite, total_with_grad, details


def _collect_lokr_trainable_params(module: nn.Module, lycoris_net: Optional[nn.Module]) -> List[torch.nn.Parameter]:
    """
    Collect LoKr trainable params robustly.

    Primary path is model parameter traversal. If that returns empty due to
    wrapper/registration quirks, fall back to LyCORIS module parameters.
    """
    params = [p for p in module.parameters() if p.requires_grad]
    if params:
        return list({id(p): p for p in params}.values())

    fallback: List[torch.nn.Parameter] = []
    if lycoris_net is None:
        return fallback

    for m in getattr(lycoris_net, "loras", []) or []:
        for p in m.parameters():
            if p.requires_grad:
                fallback.append(p)
    if not fallback:
        for p in lycoris_net.parameters():
            if p.requires_grad:
                fallback.append(p)
    return list({id(p): p for p in fallback}.values())


def _unwrap_stale_fabric_decoder(model: nn.Module) -> bool:
    """
    Unwrap stale Lightning Fabric wrappers from decoder left by previous runs.

    Returns:
        True if decoder was unwrapped, else False.
    """
    if model is None or not hasattr(model, "decoder"):
        return False
    decoder = model.decoder
    unwrapped = False
    while hasattr(decoder, "_forward_module") and isinstance(getattr(decoder, "_forward_module"), nn.Module):
        decoder = decoder._forward_module
        unwrapped = True
    if unwrapped:
        model.decoder = decoder
    return unwrapped


def _iter_module_wrappers(module: nn.Module) -> List[nn.Module]:
    """Collect wrapper chain modules (Fabric/PEFT/compile/base-model wrappers)."""
    modules: List[nn.Module] = []
    stack = [module]
    visited = set()

    while stack:
        current = stack.pop()
        if not isinstance(current, nn.Module):
            continue
        module_id = id(current)
        if module_id in visited:
            continue
        visited.add(module_id)
        modules.append(current)

        for attr_name in ("_forward_module", "_orig_mod", "base_model", "model", "module"):
            child = getattr(current, attr_name, None)
            if isinstance(child, nn.Module):
                stack.append(child)

    return modules


def _configure_training_memory_features(decoder: nn.Module) -> Tuple[bool, bool, bool]:
    """
    Enable gradient checkpointing and disable use_cache across wrapped decoder modules.

    Returns:
        Tuple[checkpointing_enabled, cache_disabled, input_grads_enabled]
    """
    checkpointing_enabled = False
    cache_disabled = False
    input_grads_enabled = False

    for mod in _iter_module_wrappers(decoder):
        if hasattr(mod, "gradient_checkpointing_enable"):
            try:
                mod.gradient_checkpointing_enable()
                checkpointing_enabled = True
            except Exception:
                pass
        elif hasattr(mod, "gradient_checkpointing"):
            try:
                mod.gradient_checkpointing = True
                checkpointing_enabled = True
            except Exception:
                pass

        # PEFT + gradient checkpointing can require input embeddings to have
        # gradients enabled, otherwise loss may be detached (no grad_fn).
        if hasattr(mod, "enable_input_require_grads"):
            try:
                mod.enable_input_require_grads()
                hook_enabled = bool(getattr(mod, "_acestep_input_grads_hook_enabled", False))
                has_require_hook = getattr(mod, "_require_grads_hook", None) is not None
                if hook_enabled or has_require_hook:
                    input_grads_enabled = True
            except Exception:
                pass

        cfg = getattr(mod, "config", None)
        if cfg is not None and hasattr(cfg, "use_cache"):
            try:
                if getattr(cfg, "use_cache", None) is not False:
                    cfg.use_cache = False
                    cache_disabled = True
            except Exception:
                pass

    return checkpointing_enabled, cache_disabled, input_grads_enabled


def sample_discrete_timestep(bsz, timesteps_tensor):
    """Sample timesteps from discrete turbo shift=3 schedule.
    
    For each sample in the batch, randomly select one of the 8 discrete timesteps
    used by the turbo model with shift=3.0.
    
    Args:
        bsz: Batch size
        device: Device
        dtype: Data type (should be bfloat16)
        
    Returns:
        Tuple of (t, r) where both are the same sampled timestep
    """
    # Randomly select indices for each sample in batch
    indices = torch.randint(0, timesteps_tensor.shape[0], (bsz,), device=timesteps_tensor.device)
    t = timesteps_tensor[indices]
    
    # r = t for this training setup
    r = t
    
    return t, r


class PreprocessedLoRAModule(nn.Module):
    """LoRA Training Module using preprocessed tensors.
    
    This module trains only the DiT decoder with LoRA adapters.
    All inputs are pre-computed tensors - no VAE or text encoder needed!
    
    Training flow:
    1. Load pre-computed tensors (target_latents, encoder_hidden_states, context_latents)
    2. Sample noise and timestep
    3. Forward through decoder (with LoRA)
    4. Compute flow matching loss
    """
    
    def __init__(
        self,
        model: nn.Module,
        lora_config: LoRAConfig,
        training_config: TrainingConfig,
        device: torch.device,
        dtype: torch.dtype,
    ):
        """Initialize the training module.
        
        Args:
            model: The AceStepConditionGenerationModel
            lora_config: LoRA configuration
            training_config: Training configuration
            device: Device to use
            dtype: Data type to use
        """
        super().__init__()
        
        self.lora_config = lora_config
        self.training_config = training_config
        self.device = torch.device(device) if isinstance(device, str) else device
        self.device_type = _normalize_device_type(self.device)
        self.dtype = _select_compute_dtype(self.device_type)
        self.transfer_non_blocking = self.device_type in ("cuda", "xpu")
        self.timesteps_tensor = torch.tensor(TURBO_SHIFT3_TIMESTEPS, device=self.device, dtype=self.dtype)
        # When gradient checkpointing is enabled via wrapper layers that don't expose
        # enable_input_require_grads(), force at least one forward input to require grad
        # so checkpointed segments keep a valid autograd graph.
        self.force_input_grads_for_checkpointing = False
        
        # Inject LoRA into the decoder only
        if check_peft_available():
            # Fix: Force tensors out of inference mode before injection
            for param in model.parameters():
                param.data = param.data.clone() 
                if param.is_inference():
                    with torch.no_grad():
                        param.data = param.data.clone()

            self.model, self.lora_info = inject_lora_into_dit(model, lora_config)
            logger.info(f"LoRA injected: {self.lora_info['trainable_params']:,} trainable params")
        else:
            self.model = model
            self.lora_info = {}
            logger.warning("PEFT not available, training without LoRA adapters")
            
        # torch.compile: optional perf optimization.
        # PEFT LoRA wraps the decoder in PeftModelForFeatureExtraction which is
        # incompatible with torch.compile/inductor on PyTorch 2.7.x
        # (AssertionError at first forward pass, not at compile time).
        # Only compile when NOT using PEFT adapters.
        has_peft = bool(self.lora_info)
        if hasattr(torch, "compile") and self.device_type == "cuda" and not has_peft:
            try:
                logger.info("Compiling DiT decoder...")
                self.model.decoder = torch.compile(self.model.decoder, mode="default")
                logger.info("torch.compile successful")
            except Exception as e:
                logger.warning(f"torch.compile failed ({e}), continuing without compilation")
        else:
            if has_peft:
                logger.info("Skipping torch.compile (incompatible with PEFT LoRA adapters)")
            else:
                logger.info("torch.compile not available on this device/PyTorch version, skipping")
        
        # Model config for flow matching
        self.config = model.config
        
        # Store training losses
        self.training_losses = []
    
    def training_step(
        self,
        batch: Dict[str, torch.Tensor],
        record_loss: bool = True,
    ) -> torch.Tensor:
        """Single training step using preprocessed tensors.
        
        Note: This is a distilled turbo model, NO CFG is used.
        
        Args:
            batch: Dictionary containing pre-computed tensors:
                - target_latents: [B, T, 64] - VAE encoded audio
                - attention_mask: [B, T] - Valid audio mask
                - encoder_hidden_states: [B, L, D] - Condition encoder output
                - encoder_attention_mask: [B, L] - Condition mask
                - context_latents: [B, T, 128] - Source context
            record_loss: If True, append loss to training_losses (set False for validation).
            
        Returns:
            Loss tensor (float32 for stable backward)
        """
        # Use autocast for mixed precision training (bf16 on CUDA/XPU, fp16 on MPS)
        if self.device_type in ("cuda", "xpu", "mps"):
            autocast_ctx = torch.autocast(device_type=self.device_type, dtype=self.dtype)
        else:
            autocast_ctx = nullcontext()
        with autocast_ctx:
            # Get tensors from batch (already on device from Fabric dataloader)
            target_latents = batch["target_latents"].to(
                self.device, dtype=self.dtype, non_blocking=self.transfer_non_blocking
            )  # x0
            attention_mask = batch["attention_mask"].to(
                self.device, dtype=self.dtype, non_blocking=self.transfer_non_blocking
            )
            encoder_hidden_states = batch["encoder_hidden_states"].to(
                self.device, dtype=self.dtype, non_blocking=self.transfer_non_blocking
            )
            encoder_attention_mask = batch["encoder_attention_mask"].to(
                self.device, dtype=self.dtype, non_blocking=self.transfer_non_blocking
            )
            context_latents = batch["context_latents"].to(
                self.device, dtype=self.dtype, non_blocking=self.transfer_non_blocking
            )
            
            bsz = target_latents.shape[0]
            
            # Flow matching: sample noise x1 and interpolate with data x0
            x1 = torch.randn_like(target_latents)  # Noise
            x0 = target_latents  # Data
            
            # Sample timesteps from discrete turbo shift=3 schedule (8 steps)
            t, r = sample_discrete_timestep(bsz, self.timesteps_tensor)
            t_ = t.unsqueeze(-1).unsqueeze(-1)
            
            # Interpolate: x_t = t * x1 + (1 - t) * x0
            xt = t_ * x1 + (1.0 - t_) * x0
            if self.force_input_grads_for_checkpointing:
                xt = xt.requires_grad_(True)
            
            # Forward through decoder (distilled turbo model, no CFG)
            decoder_outputs = self.model.decoder(
                hidden_states=xt,
                timestep=t,
                timestep_r=t,
                attention_mask=attention_mask,
                encoder_hidden_states=encoder_hidden_states,
                encoder_attention_mask=encoder_attention_mask,
                context_latents=context_latents,
            )
            
            # Flow matching loss: predict the flow field v = x1 - x0
            flow = x1 - x0
            diffusion_loss = F.mse_loss(decoder_outputs[0], flow)
        
        # Convert loss to float32 for stable backward pass
        diffusion_loss = diffusion_loss.float()
        
        if record_loss:
            self.training_losses.append(diffusion_loss.item())
        
        return diffusion_loss


class LoRATrainer:
    """High-level trainer for ACE-Step LoRA fine-tuning.
    
    Uses Lightning Fabric for distributed training and mixed precision.
    Supports training from preprocessed tensor directories.
    """
    
    def __init__(
        self,
        dit_handler,
        lora_config: LoRAConfig,
        training_config: TrainingConfig,
    ):
        """Initialize the trainer.
        
        Args:
            dit_handler: Initialized DiT handler (for model access)
            lora_config: LoRA configuration
            training_config: Training configuration
        """
        self.dit_handler = dit_handler
        self.lora_config = lora_config
        # Validate output_dir early so all downstream path operations are safe
        training_config.output_dir = safe_path(training_config.output_dir)
        self.training_config = training_config
        
        self.module = None
        self.fabric = None
        self.is_training = False
    
    def train_from_preprocessed(
        self,
        tensor_dir: str,
        training_state: Optional[Dict] = None,
        resume_from: Optional[str] = None,
    ) -> Generator[Tuple[int, float, str], None, None]:
        """Train LoRA adapters from preprocessed tensor files.

        This is the recommended training method for best performance.

        Args:
            tensor_dir: Directory containing preprocessed .pt files
            training_state: Optional state dict for stopping control
            resume_from: Optional path to checkpoint directory to resume from

        Yields:
            Tuples of (step, loss, status_message)
        """
        self.is_training = True
        
        try:
            # LoRA injection via PEFT is incompatible with torchao-quantized
            # decoder modules in this runtime. Fail fast with actionable guidance.
            quantization_mode = getattr(self.dit_handler, "quantization", None)
            if quantization_mode is not None:
                yield 0, 0.0, (
                    "❌ LoRA training requires a non-quantized DiT model. "
                    f"Current quantization: {quantization_mode}. "
                    "Re-initialize service with INT8 Quantization disabled, then retry training."
                )
                return

            # Validate tensor directory
            try:
                tensor_dir = safe_path(tensor_dir)
            except ValueError:
                yield 0, 0.0, f"❌ Rejected unsafe tensor directory: {tensor_dir}"
                return
            if not os.path.isdir(tensor_dir):
                yield 0, 0.0, f"❌ Tensor directory not found: {tensor_dir}"
                return
            
            # Create training module
            torch.manual_seed(self.training_config.seed)
            random.seed(self.training_config.seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(self.training_config.seed)
            try:
                import numpy as np
                np.random.seed(self.training_config.seed)
            except Exception:
                pass

            self.module = PreprocessedLoRAModule(
                model=self.dit_handler.model,
                lora_config=self.lora_config,
                training_config=self.training_config,
                device=self.dit_handler.device,
                dtype=self.dit_handler.dtype,
            )
            ckpt_enabled, cache_disabled, input_grads_enabled = _configure_training_memory_features(self.module.model.decoder)
            # DiT decoder does not expose token embeddings like causal LMs.
            # Force grad-carrying inputs for checkpointed segments to avoid
            # detached losses regardless of wrapper hook availability.
            self.module.force_input_grads_for_checkpointing = ckpt_enabled
            logger.info(
                f"Training memory features: gradient_checkpointing={ckpt_enabled}, "
                f"use_cache_disabled={cache_disabled}, input_grads_enabled={input_grads_enabled}"
            )
            
            # Create data module
            data_module = PreprocessedDataModule(
                tensor_dir=tensor_dir,
                batch_size=self.training_config.batch_size,
                num_workers=self.training_config.num_workers,
                pin_memory=self.training_config.pin_memory,
                prefetch_factor=self.training_config.prefetch_factor,
                persistent_workers=self.training_config.persistent_workers,
                pin_memory_device=self.training_config.pin_memory_device,
                val_split=getattr(self.training_config, "val_split", 0.0),
            )
            
            # Setup data
            data_module.setup('fit')
            
            if len(data_module.train_dataset) == 0:
                yield 0, 0.0, "❌ No valid samples found in tensor directory"
                return
            
            yield 0, 0.0, f"📂 Loaded {len(data_module.train_dataset)} preprocessed samples"
            if ckpt_enabled:
                yield 0, 0.0, "🧠 Gradient checkpointing enabled for decoder"
            else:
                yield 0, 0.0, "⚠️ Gradient checkpointing not enabled (model wrapper did not expose it)"
            if not input_grads_enabled:
                yield 0, 0.0, "ℹ️ Input-grad hook not available on this DiT; using explicit checkpointing fallback"

            if LIGHTNING_AVAILABLE:
                yield from self._train_with_fabric(data_module, training_state, resume_from)
            else:
                yield from self._train_basic(data_module, training_state)
                
        except Exception as e:
            logger.exception("Training failed")
            yield 0, 0.0, f"❌ Training failed: {str(e)}"
        finally:
            self.is_training = False
    
    def _train_with_fabric(
        self,
        data_module: PreprocessedDataModule,
        training_state: Optional[Dict],
        resume_from: Optional[str] = None,
    ) -> Generator[Tuple[int, float, str], None, None]:
        """Train using Lightning Fabric."""
        # Create output directory
        os.makedirs(self.training_config.output_dir, exist_ok=True)
        
        device_type = self.module.device_type
        precision = _select_fabric_precision(device_type)
        accelerator = device_type if device_type in ("cuda", "xpu", "mps", "cpu") else "auto"
        
        # Create TensorBoard logger when available; continue without it otherwise.
        tb_logger = None
        try:
            tb_logger = TensorBoardLogger(
                root_dir=self.training_config.output_dir,
                name="logs"
            )
        except ModuleNotFoundError as e:
            logger.warning(f"TensorBoard logger unavailable, continuing without logger: {e}")
        
        # Initialize Fabric
        fabric_kwargs = {
            "accelerator": accelerator,
            "devices": 1,
            "precision": precision,
        }
        if tb_logger is not None:
            fabric_kwargs["loggers"] = [tb_logger]
        self.fabric = Fabric(**fabric_kwargs)
        self.fabric.launch()
        
        yield 0, 0.0, f"🚀 Starting training (device: {device_type}, precision: {precision})..."
        
        # Keep decoder weights in a stable dtype before optimizer/Fabric setup.
        # MPS stays in fp32 weights for stability; computation still uses fp16
        # autocast inside training_step.
        if device_type == "mps" or precision.endswith("-mixed"):
            self.module.model.decoder = self.module.model.decoder.to(dtype=torch.float32)
        else:
            self.module.model.decoder = self.module.model.decoder.to(dtype=self.module.dtype)
        casted_trainable, total_trainable_tensors = _ensure_trainable_params_fp32(self.module.model.decoder)
        logger.info(
            f"Trainable tensor dtype fixup: casted {casted_trainable}/{total_trainable_tensors} to fp32"
        )

        # Get dataloader
        train_loader = data_module.train_dataloader()
        val_loader = data_module.val_dataloader() if hasattr(data_module, "val_dataloader") else None

        if training_state is not None:
            training_state["plot_steps"] = []
            training_state["plot_loss"] = []
            training_state["plot_ema"] = []
            training_state["plot_val_steps"] = []
            training_state["plot_val_loss"] = []
            training_state["plot_best_step"] = None
        ema_loss = None
        ema_alpha = 0.1
        best_val_loss = float("inf")
        best_val_step = None

        # Setup optimizer - only LoRA parameters
        trainable_params = [p for p in self.module.model.parameters() if p.requires_grad]
        
        if not trainable_params:
            yield 0, 0.0, "❌ No trainable parameters found!"
            return
        
        yield 0, 0.0, f"🎯 Training {sum(p.numel() for p in trainable_params):,} parameters"
        
        optimizer_kwargs = {
            "lr": self.training_config.learning_rate,
            "weight_decay": self.training_config.weight_decay,
        }

        # Optimizer selection: AdamW 8-bit vs Standard AdamW
        if HAS_BNB and device_type == "cuda":
            logger.info("train_with_fabric using bitsandbytes 8-bit AdamW optimizer")
            optimizer = bnb.optim.AdamW8bit(trainable_params, **optimizer_kwargs)
        else:
            if self.module.device.type == "cuda":
                optimizer_kwargs["fused"] = True
            optimizer = AdamW(trainable_params, **optimizer_kwargs)
        
        # Calculate total steps
        steps_per_epoch = max(1, math.ceil(len(train_loader) / self.training_config.gradient_accumulation_steps))
        total_steps = steps_per_epoch * self.training_config.max_epochs
        warmup_steps = min(self.training_config.warmup_steps, max(1, total_steps // 10))
        
        # Scheduler
        warmup_scheduler = LinearLR(
            optimizer,
            start_factor=0.1,
            end_factor=1.0,
            total_iters=warmup_steps,
        )
        
        main_scheduler = CosineAnnealingWarmRestarts(
            optimizer,
            T_0=max(1, total_steps - warmup_steps),
            T_mult=1,
            eta_min=self.training_config.learning_rate * 0.01,
        )
        
        scheduler = SequentialLR(
            optimizer,
            schedulers=[warmup_scheduler, main_scheduler],
            milestones=[warmup_steps],
        )
        
        # Setup with Fabric - only the decoder (which has LoRA)
        self.module.model.decoder, optimizer = self.fabric.setup(self.module.model.decoder, optimizer)
        casted_opt_params, total_opt_params = _ensure_optimizer_params_fp32(optimizer)
        logger.info(
            f"Optimizer param dtype fixup: casted {casted_opt_params}/{total_opt_params} to fp32"
        )
        train_loader = self.fabric.setup_dataloaders(train_loader)

        # Handle resume from checkpoint (load AFTER Fabric setup)
        start_epoch = 0
        global_step = 0
        checkpoint_info = None

        if resume_from:
            try:
                resume_from = safe_path(resume_from)
            except ValueError:
                yield 0, 0.0, f"⚠️ Rejected unsafe checkpoint path: {resume_from}, starting fresh"
                resume_from = None
        if resume_from and os.path.exists(resume_from):
            try:
                yield 0, 0.0, f"🔄 Loading checkpoint from {resume_from}..."

                # Load checkpoint using utility function
                checkpoint_info = load_training_checkpoint(
                    resume_from,
                    optimizer=optimizer,
                    scheduler=scheduler,
                    device=self.module.device,
                )

                if checkpoint_info["adapter_path"]:
                    adapter_path = checkpoint_info["adapter_path"]
                    adapter_weights_path = os.path.join(adapter_path, "adapter_model.safetensors")
                    if not os.path.exists(adapter_weights_path):
                        adapter_weights_path = os.path.join(adapter_path, "adapter_model.bin")

                    if os.path.exists(adapter_weights_path):
                        # Load adapter weights
                        from safetensors.torch import load_file
                        if adapter_weights_path.endswith(".safetensors"):
                            state_dict = load_file(adapter_weights_path)
                        else:
                            state_dict = torch.load(adapter_weights_path, map_location=self.module.device, weights_only=True)

                        # Get the decoder (might be wrapped by Fabric)
                        decoder = self.module.model.decoder
                        if hasattr(decoder, '_forward_module'):
                            decoder = decoder._forward_module

                        decoder.load_state_dict(state_dict, strict=False)

                        start_epoch = checkpoint_info["epoch"]
                        global_step = checkpoint_info["global_step"]

                        status_parts = [f"✅ Resumed from epoch {start_epoch}, step {global_step}"]
                        if checkpoint_info["loaded_optimizer"]:
                            status_parts.append("optimizer ✓")
                        if checkpoint_info["loaded_scheduler"]:
                            status_parts.append("scheduler ✓")
                        yield 0, 0.0, ", ".join(status_parts)
                    else:
                        yield 0, 0.0, f"⚠️ Adapter weights not found in {adapter_path}"
                else:
                    yield 0, 0.0, f"⚠️ No valid checkpoint found in {resume_from}"

            except Exception as e:
                logger.exception("Failed to load checkpoint")
                yield 0, 0.0, f"⚠️ Failed to load checkpoint: {e}, starting fresh"
                start_epoch = 0
                global_step = 0
        elif resume_from:
            yield 0, 0.0, f"⚠️ Checkpoint path not found: {resume_from}, starting fresh"

        # Training loop
        accumulation_step = 0
        accumulated_loss = 0.0
        optimizer.zero_grad(set_to_none=True)

        self.module.model.decoder.train()

        for epoch in range(start_epoch, self.training_config.max_epochs):
            epoch_loss = 0.0
            num_updates = 0
            epoch_start_time = time.time()
            
            for batch_idx, batch in enumerate(train_loader):
                # Check for stop signal
                if training_state and training_state.get("should_stop", False):
                    yield global_step, accumulated_loss / max(accumulation_step, 1), "⏹️ Training stopped by user"
                    return
                
                # Forward pass
                loss = self.module.training_step(batch)
                loss = loss / self.training_config.gradient_accumulation_steps
                
                # Backward pass
                self.fabric.backward(loss)
                accumulated_loss += loss.item()
                accumulation_step += 1
                
                # Optimizer step
                if accumulation_step >= self.training_config.gradient_accumulation_steps:
                    nonfinite_grads, grad_tensors = _count_nonfinite_grads(trainable_params)
                    if nonfinite_grads > 0:
                        optimizer.zero_grad(set_to_none=True)
                        yield global_step, float("nan"), (
                            f"⚠️ Non-finite gradients ({nonfinite_grads}/{grad_tensors}); "
                            "skipping optimizer step"
                        )
                        accumulated_loss = 0.0
                        accumulation_step = 0
                        continue

                    self.fabric.clip_gradients(
                        self.module.model.decoder,
                        optimizer,
                        max_norm=self.training_config.max_grad_norm,
                        error_if_nonfinite=False,
                    )
                    
                    optimizer.step()
                    scheduler.step()
                    optimizer.zero_grad(set_to_none=True)
                    
                    global_step += 1
                    
                    # Log
                    avg_loss = accumulated_loss / accumulation_step
                    if global_step % self.training_config.log_every_n_steps == 0:
                        if training_state is not None:
                            if ema_loss is None:
                                ema_loss = avg_loss
                            else:
                                ema_loss = ema_alpha * avg_loss + (1 - ema_alpha) * ema_loss
                            training_state["plot_steps"].append(global_step)
                            training_state["plot_loss"].append(avg_loss)
                            training_state["plot_ema"].append(ema_loss)
                        self.fabric.log("train/loss", avg_loss, step=global_step)
                        self.fabric.log("train/lr", scheduler.get_last_lr()[0], step=global_step)
                        yield global_step, avg_loss, f"Epoch {epoch+1}/{self.training_config.max_epochs}, Step {global_step}, Loss: {avg_loss:.4f}"
                    
                    epoch_loss += avg_loss
                    num_updates += 1
                    accumulated_loss = 0.0
                    accumulation_step = 0

            # Flush remainder to avoid dropping gradients when epoch length is not
            # divisible by gradient_accumulation_steps.
            if accumulation_step > 0:
                nonfinite_grads, grad_tensors = _count_nonfinite_grads(trainable_params)
                if nonfinite_grads > 0:
                    optimizer.zero_grad(set_to_none=True)
                    yield global_step, float("nan"), (
                        f"⚠️ Non-finite gradients ({nonfinite_grads}/{grad_tensors}); "
                        "skipping optimizer remainder step"
                    )
                    accumulated_loss = 0.0
                    accumulation_step = 0
                else:
                    self.fabric.clip_gradients(
                        self.module.model.decoder,
                        optimizer,
                        max_norm=self.training_config.max_grad_norm,
                        error_if_nonfinite=False,
                    )

                    optimizer.step()
                    scheduler.step()
                    optimizer.zero_grad(set_to_none=True)

                global_step += 1
                avg_loss = accumulated_loss / accumulation_step
                if global_step % self.training_config.log_every_n_steps == 0:
                    if training_state is not None:
                        if ema_loss is None:
                            ema_loss = avg_loss
                        else:
                            ema_loss = ema_alpha * avg_loss + (1 - ema_alpha) * ema_loss
                        training_state["plot_steps"].append(global_step)
                        training_state["plot_loss"].append(avg_loss)
                        training_state["plot_ema"].append(ema_loss)
                    self.fabric.log("train/loss", avg_loss, step=global_step)
                    self.fabric.log("train/lr", scheduler.get_last_lr()[0], step=global_step)
                    yield global_step, avg_loss, f"Epoch {epoch+1}/{self.training_config.max_epochs}, Step {global_step}, Loss: {avg_loss:.4f}"

                    epoch_loss += avg_loss
                    num_updates += 1
                    accumulated_loss = 0.0
                    accumulation_step = 0
            
            # End of epoch
            epoch_time = time.time() - epoch_start_time
            avg_epoch_loss = epoch_loss / max(num_updates, 1)
            if training_state is not None:
                if ema_loss is None:
                    ema_loss = avg_epoch_loss
                else:
                    ema_loss = ema_alpha * avg_epoch_loss + (1 - ema_alpha) * ema_loss
                # Avoid duplicating the last step if it was already logged in the batch loop
                plot_steps = training_state["plot_steps"]
                if not plot_steps or plot_steps[-1] != global_step:
                    training_state["plot_steps"].append(global_step)
                    training_state["plot_loss"].append(avg_epoch_loss)
                    training_state["plot_ema"].append(ema_loss)
            self.fabric.log("train/epoch_loss", avg_epoch_loss, step=epoch + 1)
            yield global_step, avg_epoch_loss, f"✅ Epoch {epoch+1}/{self.training_config.max_epochs} in {epoch_time:.1f}s, Loss: {avg_epoch_loss:.4f}"

            # Validation and best checkpoint (if validation set exists)
            if val_loader is not None:
                self.module.model.decoder.eval()
                total_val_loss = 0.0
                n_val = 0
                with torch.no_grad():
                    for val_batch in val_loader:
                        v_loss = self.module.training_step(val_batch, record_loss=False)
                        total_val_loss += v_loss.item()
                        n_val += 1
                self.module.model.decoder.train()
                val_loss = total_val_loss / max(n_val, 1)
                if training_state is not None:
                    training_state["plot_val_steps"].append(global_step)
                    training_state["plot_val_loss"].append(val_loss)
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    best_val_step = global_step
                    if training_state is not None:
                        training_state["plot_best_step"] = best_val_step
                    best_dir = os.path.join(self.training_config.output_dir, "checkpoints", "best")
                    save_training_checkpoint(
                        self.module.model,
                        optimizer,
                        scheduler,
                        epoch + 1,
                        global_step,
                        best_dir,
                    )
            
            # Save checkpoint
            if (epoch + 1) % self.training_config.save_every_n_epochs == 0:
                checkpoint_dir = os.path.join(self.training_config.output_dir, "checkpoints", f"epoch_{epoch+1}")
                save_training_checkpoint(
                    self.module.model,
                    optimizer,
                    scheduler,
                    epoch + 1,
                    global_step,
                    checkpoint_dir,
                )
                yield global_step, avg_epoch_loss, f"💾 Checkpoint saved at epoch {epoch+1}"

        # Save final model
        final_path = os.path.join(self.training_config.output_dir, "final")
        save_lora_weights(self.module.model, final_path)
        
        final_loss = self.module.training_losses[-1] if self.module.training_losses else 0.0
        yield global_step, final_loss, f"✅ Training complete! LoRA saved to {final_path}"
    
    def _train_basic(
        self,
        data_module: PreprocessedDataModule,
        training_state: Optional[Dict],
    ) -> Generator[Tuple[int, float, str], None, None]:
        """Basic training loop without Fabric."""
        yield 0, 0.0, "🚀 Starting basic training loop..."
        
        os.makedirs(self.training_config.output_dir, exist_ok=True)
        
        train_loader = data_module.train_dataloader()
        
        trainable_params = [p for p in self.module.model.parameters() if p.requires_grad]
        
        if not trainable_params:
            yield 0, 0.0, "❌ No trainable parameters found!"
            return
        
        if HAS_BNB and self.module.device_type == "cuda":
            optimizer = bnb.optim.AdamW8bit(
                trainable_params,
                lr=self.training_config.learning_rate,
                weight_decay=self.training_config.weight_decay,
            )
            logger.info("train_basic using bitsandbytes 8-bit AdamW optimizer")
        else:
            optimizer = AdamW(
                trainable_params,
                lr=self.training_config.learning_rate,
                weight_decay=self.training_config.weight_decay,
            )
        
        steps_per_epoch = max(1, math.ceil(len(train_loader) / self.training_config.gradient_accumulation_steps))
        total_steps = steps_per_epoch * self.training_config.max_epochs
        warmup_steps = min(self.training_config.warmup_steps, max(1, total_steps // 10))
        
        warmup_scheduler = LinearLR(optimizer, start_factor=0.1, end_factor=1.0, total_iters=warmup_steps)
        main_scheduler = CosineAnnealingWarmRestarts(optimizer, T_0=max(1, total_steps - warmup_steps), T_mult=1, eta_min=self.training_config.learning_rate * 0.01)
        scheduler = SequentialLR(optimizer, schedulers=[warmup_scheduler, main_scheduler], milestones=[warmup_steps])
        
        global_step = 0
        accumulation_step = 0
        accumulated_loss = 0.0
        optimizer.zero_grad(set_to_none=True)
        
        self.module.model.decoder.train()
        
        for epoch in range(self.training_config.max_epochs):
            epoch_loss = 0.0
            num_updates = 0
            epoch_start_time = time.time()
            
            for batch in train_loader:
                if training_state and training_state.get("should_stop", False):
                    yield global_step, accumulated_loss / max(accumulation_step, 1), "⏹️ Training stopped"
                    return
                
                loss = self.module.training_step(batch)
                loss = loss / self.training_config.gradient_accumulation_steps
                loss.backward()
                accumulated_loss += loss.item()
                accumulation_step += 1
                
                if accumulation_step >= self.training_config.gradient_accumulation_steps:
                    torch.nn.utils.clip_grad_norm_(trainable_params, self.training_config.max_grad_norm)
                    optimizer.step()
                    scheduler.step()
                    optimizer.zero_grad(set_to_none=True)
                    global_step += 1
                    
                    avg_loss = accumulated_loss / accumulation_step
                    if global_step % self.training_config.log_every_n_steps == 0:
                        yield global_step, avg_loss, f"Epoch {epoch+1}, Step {global_step}, Loss: {avg_loss:.4f}"
                    
                    epoch_loss += avg_loss
                    num_updates += 1
                    accumulated_loss = 0.0
                    accumulation_step = 0

            if accumulation_step > 0:
                torch.nn.utils.clip_grad_norm_(trainable_params, self.training_config.max_grad_norm)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
                global_step += 1

                avg_loss = accumulated_loss / accumulation_step
                if global_step % self.training_config.log_every_n_steps == 0:
                    yield global_step, avg_loss, f"Epoch {epoch+1}, Step {global_step}, Loss: {avg_loss:.4f}"

                epoch_loss += avg_loss
                num_updates += 1
                accumulated_loss = 0.0
                accumulation_step = 0
            
            epoch_time = time.time() - epoch_start_time
            avg_epoch_loss = epoch_loss / max(num_updates, 1)
            yield global_step, avg_epoch_loss, f"✅ Epoch {epoch+1}/{self.training_config.max_epochs} in {epoch_time:.1f}s"
            
            if (epoch + 1) % self.training_config.save_every_n_epochs == 0:
                checkpoint_dir = os.path.join(self.training_config.output_dir, "checkpoints", f"epoch_{epoch+1}")
                save_lora_weights(self.module.model, checkpoint_dir)
                yield global_step, avg_epoch_loss, f"💾 Checkpoint saved"
        
        final_path = os.path.join(self.training_config.output_dir, "final")
        save_lora_weights(self.module.model, final_path)
        final_loss = self.module.training_losses[-1] if self.module.training_losses else 0.0
        yield global_step, final_loss, f"✅ Training complete! LoRA saved to {final_path}"
    
    def stop(self):
        """Stop training."""
        self.is_training = False


class PreprocessedLoKRModule(nn.Module):
    """LoKr training module using preprocessed tensors."""

    def __init__(
        self,
        model: nn.Module,
        lokr_config: LoKRConfig,
        training_config: TrainingConfig,
        device: torch.device,
        dtype: torch.dtype,
    ):
        super().__init__()

        self.lokr_config = lokr_config
        self.training_config = training_config
        self.device = torch.device(device) if isinstance(device, str) else device
        self.device_type = _normalize_device_type(self.device)
        self.dtype = _select_compute_dtype(self.device_type)
        self.transfer_non_blocking = self.device_type in ("cuda", "xpu")
        self.timesteps_tensor = torch.tensor(TURBO_SHIFT3_TIMESTEPS, device=self.device, dtype=self.dtype)
        self.force_input_grads_for_checkpointing = False
        self.lycoris_net = None

        if check_lycoris_available():
            self.model, self.lycoris_net, self.lokr_info = inject_lokr_into_dit(model, lokr_config)
            logger.info(f"LoKr injected: {self.lokr_info['trainable_params']:,} trainable params")
        else:
            self.model = model
            self.lokr_info = {}
            logger.warning("LyCORIS not available, training without LoKr adapters")

        self.config = model.config
        self.training_losses = []

    def training_step(self, batch: Dict[str, torch.Tensor]) -> torch.Tensor:
        """Single LoKr training step."""
        if self.device_type in ("cuda", "xpu", "mps"):
            autocast_ctx = torch.autocast(device_type=self.device_type, dtype=self.dtype)
        else:
            autocast_ctx = nullcontext()

        with autocast_ctx:
            target_latents = batch["target_latents"].to(
                self.device, dtype=self.dtype, non_blocking=self.transfer_non_blocking
            )
            attention_mask = batch["attention_mask"].to(
                self.device, dtype=self.dtype, non_blocking=self.transfer_non_blocking
            )
            encoder_hidden_states = batch["encoder_hidden_states"].to(
                self.device, dtype=self.dtype, non_blocking=self.transfer_non_blocking
            )
            encoder_attention_mask = batch["encoder_attention_mask"].to(
                self.device, dtype=self.dtype, non_blocking=self.transfer_non_blocking
            )
            context_latents = batch["context_latents"].to(
                self.device, dtype=self.dtype, non_blocking=self.transfer_non_blocking
            )

            bsz = target_latents.shape[0]
            x1 = torch.randn_like(target_latents)
            x0 = target_latents

            t, _ = sample_discrete_timestep(bsz, self.timesteps_tensor)
            t_ = t.unsqueeze(-1).unsqueeze(-1)
            xt = t_ * x1 + (1.0 - t_) * x0
            if self.force_input_grads_for_checkpointing:
                xt = xt.requires_grad_(True)

            decoder_outputs = self.model.decoder(
                hidden_states=xt,
                timestep=t,
                timestep_r=t,
                attention_mask=attention_mask,
                encoder_hidden_states=encoder_hidden_states,
                encoder_attention_mask=encoder_attention_mask,
                context_latents=context_latents,
            )

            flow = x1 - x0
            diffusion_loss = F.mse_loss(decoder_outputs[0], flow)

        diffusion_loss = diffusion_loss.float()
        self.training_losses.append(diffusion_loss.item())
        return diffusion_loss


class LoKRTrainer:
    """High-level trainer for ACE-Step LoKr fine-tuning."""

    def __init__(
        self,
        dit_handler,
        lokr_config: LoKRConfig,
        training_config: TrainingConfig,
    ):
        self.dit_handler = dit_handler
        self.lokr_config = lokr_config
        # Validate output_dir early so all downstream path operations are safe
        training_config.output_dir = safe_path(training_config.output_dir)
        self.training_config = training_config

        self.module = None
        self.fabric = None
        self.is_training = False
        self.run_metadata: Dict[str, Any] = {}

    def train_from_preprocessed(
        self,
        tensor_dir: str,
        training_state: Optional[Dict] = None,
    ) -> Generator[Tuple[int, float, str], None, None]:
        """Train LoKr adapters from preprocessed tensors."""
        self.is_training = True
        try:
            if _unwrap_stale_fabric_decoder(self.dit_handler.model):
                logger.info("Unwrapped stale Fabric decoder wrapper before LoKr training")

            quantization_mode = getattr(self.dit_handler, "quantization", None)
            if quantization_mode is not None:
                yield 0, 0.0, (
                    "❌ LoKr training requires a non-quantized DiT model. "
                    f"Current quantization: {quantization_mode}. "
                    "Re-initialize service with INT8 Quantization disabled, then retry training."
                )
                return

            try:
                tensor_dir = safe_path(tensor_dir)
            except ValueError:
                yield 0, 0.0, f"❌ Rejected unsafe tensor directory: {tensor_dir}"
                return
            if not os.path.isdir(tensor_dir):
                yield 0, 0.0, f"❌ Tensor directory not found: {tensor_dir}"
                return

            if not check_lycoris_available():
                yield 0, 0.0, "❌ LyCORIS not installed. Install lycoris-lora to train LoKr."
                return

            torch.manual_seed(self.training_config.seed)
            random.seed(self.training_config.seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(self.training_config.seed)
            try:
                import numpy as np
                np.random.seed(self.training_config.seed)
            except Exception:
                pass

            self.module = PreprocessedLoKRModule(
                model=self.dit_handler.model,
                lokr_config=self.lokr_config,
                training_config=self.training_config,
                device=self.dit_handler.device,
                dtype=self.dit_handler.dtype,
            )
            ckpt_enabled, cache_disabled, input_grads_enabled = _configure_training_memory_features(
                self.module.model.decoder
            )
            self.module.force_input_grads_for_checkpointing = ckpt_enabled
            logger.info(
                f"Training memory features: gradient_checkpointing={ckpt_enabled}, "
                f"use_cache_disabled={cache_disabled}, input_grads_enabled={input_grads_enabled}"
            )

            data_module = PreprocessedDataModule(
                tensor_dir=tensor_dir,
                batch_size=self.training_config.batch_size,
                num_workers=self.training_config.num_workers,
                pin_memory=self.training_config.pin_memory,
                prefetch_factor=self.training_config.prefetch_factor,
                persistent_workers=self.training_config.persistent_workers,
                pin_memory_device=self.training_config.pin_memory_device,
                val_split=self.training_config.val_split,
            )
            data_module.setup('fit')

            if len(data_module.train_dataset) == 0:
                yield 0, 0.0, "❌ No valid samples found in tensor directory"
                return

            self.run_metadata = {
                "tensor_dir": tensor_dir,
                "num_samples": int(len(data_module.train_dataset)),
                "training_config": self.training_config.to_dict(),
            }

            yield 0, 0.0, f"📂 Loaded {len(data_module.train_dataset)} preprocessed samples"
            if ckpt_enabled:
                yield 0, 0.0, "🧠 Gradient checkpointing enabled for decoder"
            else:
                yield 0, 0.0, "⚠️ Gradient checkpointing not enabled (model wrapper did not expose it)"
            if not input_grads_enabled:
                yield 0, 0.0, "ℹ️ Input-grad hook not available on this DiT; using explicit checkpointing fallback"

            if LIGHTNING_AVAILABLE:
                yield from self._train_with_fabric(data_module, training_state)
            else:
                yield from self._train_basic(data_module, training_state)

        except Exception as e:
            logger.exception("LoKr training failed")
            yield 0, 0.0, f"❌ Training failed: {str(e)}"
        finally:
            if self.module is not None and hasattr(self.module, "model"):
                _unwrap_stale_fabric_decoder(self.module.model)
            if getattr(self, "dit_handler", None) is not None and getattr(self.dit_handler, "model", None) is not None:
                _unwrap_stale_fabric_decoder(self.dit_handler.model)
            self.is_training = False

    def _train_with_fabric(
        self,
        data_module: PreprocessedDataModule,
        training_state: Optional[Dict],
    ) -> Generator[Tuple[int, float, str], None, None]:
        os.makedirs(self.training_config.output_dir, exist_ok=True)

        device_type = self.module.device_type
        precision = _select_fabric_precision(device_type)
        accelerator = device_type if device_type in ("cuda", "xpu", "mps", "cpu") else "auto"
        manual_nonfinite_check = not precision.endswith("-mixed")

        tb_logger = None
        try:
            tb_logger = TensorBoardLogger(
                root_dir=self.training_config.output_dir,
                name="logs",
            )
        except ModuleNotFoundError as exc:
            logger.warning(f"TensorBoard logger unavailable, continuing without logger: {exc}")

        fabric_kwargs = {
            "accelerator": accelerator,
            "devices": 1,
            "precision": precision,
        }
        if tb_logger is not None:
            fabric_kwargs["loggers"] = [tb_logger]
        self.fabric = Fabric(**fabric_kwargs)
        self.fabric.launch()

        yield 0, 0.0, f"🚀 Starting training (device: {device_type}, precision: {precision})..."
        if not manual_nonfinite_check:
            logger.info(
                "LoKr mixed precision detected: disabling pre-unscale non-finite grad checks; "
                "relying on AMP/GradScaler handling."
            )

        if device_type == "mps" or precision.endswith("-mixed"):
            self.module.model.decoder = self.module.model.decoder.to(dtype=torch.float32)
        else:
            self.module.model.decoder = self.module.model.decoder.to(dtype=self.module.dtype)
        casted_trainable, total_trainable_tensors = _ensure_trainable_params_fp32(self.module.model.decoder)
        if total_trainable_tensors == 0 and getattr(self.module, "lycoris_net", None) is not None:
            casted_fallback, total_fallback = _ensure_trainable_params_fp32(self.module.lycoris_net)
            casted_trainable += casted_fallback
            total_trainable_tensors += total_fallback
        logger.info(
            f"Trainable tensor dtype fixup: casted {casted_trainable}/{total_trainable_tensors} to fp32"
        )

        train_loader = data_module.train_dataloader()
        trainable_params = _collect_lokr_trainable_params(
            self.module.model,
            getattr(self.module, "lycoris_net", None),
        )
        param_name_lookup = _build_param_name_lookup(
            self.module.model,
            getattr(self.module, "lycoris_net", None),
        )

        if not trainable_params:
            yield 0, 0.0, "❌ No trainable parameters found!"
            return
        if total_trainable_tensors == 0:
            logger.warning(
                "LoKr trainable params discovered via LyCORIS fallback traversal; "
                "decoder parameter traversal returned 0 trainables."
            )

        yield 0, 0.0, f"🎯 Training {sum(p.numel() for p in trainable_params):,} parameters"

        optimizer_kwargs = {
            "lr": self.training_config.learning_rate,
            "weight_decay": self.training_config.weight_decay,
        }
        if self.module.device.type == "cuda":
            optimizer_kwargs["fused"] = True
        optimizer = AdamW(trainable_params, **optimizer_kwargs)

        steps_per_epoch = max(1, math.ceil(len(train_loader) / self.training_config.gradient_accumulation_steps))
        total_steps = steps_per_epoch * self.training_config.max_epochs
        warmup_steps = min(self.training_config.warmup_steps, max(1, total_steps // 10))

        warmup_scheduler = LinearLR(
            optimizer,
            start_factor=0.1,
            end_factor=1.0,
            total_iters=warmup_steps,
        )
        main_scheduler = CosineAnnealingWarmRestarts(
            optimizer,
            T_0=max(1, total_steps - warmup_steps),
            T_mult=1,
            eta_min=self.training_config.learning_rate * 0.01,
        )
        scheduler = SequentialLR(
            optimizer,
            schedulers=[warmup_scheduler, main_scheduler],
            milestones=[warmup_steps],
        )

        self.module.model.decoder, optimizer = self.fabric.setup(self.module.model.decoder, optimizer)
        casted_opt_params, total_opt_params = _ensure_optimizer_params_fp32(optimizer)
        logger.info(
            f"Optimizer param dtype fixup: casted {casted_opt_params}/{total_opt_params} to fp32"
        )
        train_loader = self.fabric.setup_dataloaders(train_loader)

        accumulation_step = 0
        accumulated_loss = 0.0
        global_step = 0
        optimizer.zero_grad(set_to_none=True)
        self.module.model.decoder.train()

        for epoch in range(self.training_config.max_epochs):
            epoch_loss = 0.0
            num_updates = 0
            epoch_start_time = time.time()

            for batch in train_loader:
                if training_state and training_state.get("should_stop", False):
                    yield global_step, accumulated_loss / max(accumulation_step, 1), "⏹️ Training stopped by user"
                    return

                loss = self.module.training_step(batch)
                loss = loss / self.training_config.gradient_accumulation_steps

                self.fabric.backward(loss)
                accumulated_loss += loss.item()
                accumulation_step += 1

                if accumulation_step >= self.training_config.gradient_accumulation_steps:
                    if manual_nonfinite_check:
                        nonfinite_grads, grad_tensors, nonfinite_details = _count_nonfinite_grads_detailed(
                            trainable_params,
                            param_name_lookup,
                            detail_limit=10,
                        )
                        if nonfinite_grads > 0:
                            if nonfinite_details:
                                logger.warning(
                                    f"LoKr non-finite gradients ({nonfinite_grads}/{grad_tensors}) at epoch "
                                    f"{epoch+1}, step {global_step}. Top offending tensors:\n"
                                    + "\n".join(f"  - {d}" for d in nonfinite_details)
                                )
                            optimizer.zero_grad(set_to_none=True)
                            yield global_step, float("nan"), (
                                f"⚠️ Non-finite gradients ({nonfinite_grads}/{grad_tensors}); "
                                "skipping optimizer step (see logs for tensor names)"
                            )
                            accumulated_loss = 0.0
                            accumulation_step = 0
                            continue

                    self.fabric.clip_gradients(
                        self.module.model.decoder,
                        optimizer,
                        max_norm=self.training_config.max_grad_norm,
                        error_if_nonfinite=False,
                    )

                    optimizer.step()
                    scheduler.step()
                    optimizer.zero_grad(set_to_none=True)
                    global_step += 1

                    avg_loss = accumulated_loss / accumulation_step
                    if global_step % self.training_config.log_every_n_steps == 0:
                        self.fabric.log("train/loss", avg_loss, step=global_step)
                        self.fabric.log("train/lr", scheduler.get_last_lr()[0], step=global_step)
                        yield global_step, avg_loss, (
                            f"Epoch {epoch+1}/{self.training_config.max_epochs}, "
                            f"Step {global_step}, Loss: {avg_loss:.4f}"
                        )

                    epoch_loss += avg_loss
                    num_updates += 1
                    accumulated_loss = 0.0
                    accumulation_step = 0

            if accumulation_step > 0:
                if manual_nonfinite_check:
                    nonfinite_grads, grad_tensors, nonfinite_details = _count_nonfinite_grads_detailed(
                        trainable_params,
                        param_name_lookup,
                        detail_limit=10,
                    )
                    if nonfinite_grads > 0:
                        if nonfinite_details:
                            logger.warning(
                                f"LoKr non-finite remainder gradients ({nonfinite_grads}/{grad_tensors}) at epoch "
                                f"{epoch+1}, step {global_step}. Top offending tensors:\n"
                                + "\n".join(f"  - {d}" for d in nonfinite_details)
                            )
                        optimizer.zero_grad(set_to_none=True)
                        yield global_step, float("nan"), (
                            f"⚠️ Non-finite gradients ({nonfinite_grads}/{grad_tensors}); "
                            "skipping optimizer remainder step (see logs for tensor names)"
                        )
                        accumulated_loss = 0.0
                        accumulation_step = 0
                        continue

                self.fabric.clip_gradients(
                    self.module.model.decoder,
                    optimizer,
                    max_norm=self.training_config.max_grad_norm,
                    error_if_nonfinite=False,
                )

                optimizer.step()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
                global_step += 1
                avg_loss = accumulated_loss / accumulation_step
                if global_step % self.training_config.log_every_n_steps == 0:
                    self.fabric.log("train/loss", avg_loss, step=global_step)
                    self.fabric.log("train/lr", scheduler.get_last_lr()[0], step=global_step)
                    yield global_step, avg_loss, (
                        f"Epoch {epoch+1}/{self.training_config.max_epochs}, "
                        f"Step {global_step}, Loss: {avg_loss:.4f}"
                    )

                epoch_loss += avg_loss
                num_updates += 1
                accumulated_loss = 0.0
                accumulation_step = 0

            epoch_time = time.time() - epoch_start_time
            avg_epoch_loss = epoch_loss / max(num_updates, 1)

            self.fabric.log("train/epoch_loss", avg_epoch_loss, step=epoch + 1)
            yield global_step, avg_epoch_loss, (
                f"✅ Epoch {epoch+1}/{self.training_config.max_epochs} "
                f"in {epoch_time:.1f}s, Loss: {avg_epoch_loss:.4f}"
            )

            if (epoch + 1) % self.training_config.save_every_n_epochs == 0:
                checkpoint_dir = os.path.join(self.training_config.output_dir, "checkpoints", f"epoch_{epoch+1}")
                save_lokr_training_checkpoint(
                    self.module.lycoris_net,
                    optimizer,
                    scheduler,
                    epoch + 1,
                    global_step,
                    checkpoint_dir,
                    lokr_config=self.lokr_config,
                    run_metadata=self.run_metadata,
                )
                yield global_step, avg_epoch_loss, f"💾 Checkpoint saved at epoch {epoch+1}"

        final_path = os.path.join(self.training_config.output_dir, "final")
        final_metadata: Dict[str, Any] = {"lokr_config": self.lokr_config.to_dict()}
        if self.run_metadata:
            final_metadata["run_metadata"] = self.run_metadata
        save_lokr_weights(
            self.module.lycoris_net,
            final_path,
            metadata=final_metadata,
        )
        final_loss = self.module.training_losses[-1] if self.module.training_losses else 0.0
        yield global_step, final_loss, f"✅ Training complete! LoKr saved to {final_path}"

    def _train_basic(
        self,
        data_module: PreprocessedDataModule,
        training_state: Optional[Dict],
    ) -> Generator[Tuple[int, float, str], None, None]:
        yield 0, 0.0, "🚀 Starting basic training loop..."
        os.makedirs(self.training_config.output_dir, exist_ok=True)

        train_loader = data_module.train_dataloader()
        trainable_params = _collect_lokr_trainable_params(
            self.module.model,
            getattr(self.module, "lycoris_net", None),
        )
        if not trainable_params:
            yield 0, 0.0, "❌ No trainable parameters found!"
            return

        optimizer = AdamW(
            trainable_params,
            lr=self.training_config.learning_rate,
            weight_decay=self.training_config.weight_decay,
        )
        steps_per_epoch = max(1, math.ceil(len(train_loader) / self.training_config.gradient_accumulation_steps))
        total_steps = steps_per_epoch * self.training_config.max_epochs
        warmup_steps = min(self.training_config.warmup_steps, max(1, total_steps // 10))

        warmup_scheduler = LinearLR(optimizer, start_factor=0.1, end_factor=1.0, total_iters=warmup_steps)
        main_scheduler = CosineAnnealingWarmRestarts(
            optimizer,
            T_0=max(1, total_steps - warmup_steps),
            T_mult=1,
            eta_min=self.training_config.learning_rate * 0.01,
        )
        scheduler = SequentialLR(optimizer, schedulers=[warmup_scheduler, main_scheduler], milestones=[warmup_steps])

        global_step = 0
        accumulation_step = 0
        accumulated_loss = 0.0
        optimizer.zero_grad(set_to_none=True)
        self.module.model.decoder.train()

        for epoch in range(self.training_config.max_epochs):
            epoch_loss = 0.0
            num_updates = 0
            epoch_start_time = time.time()

            for batch in train_loader:
                if training_state and training_state.get("should_stop", False):
                    yield global_step, accumulated_loss / max(accumulation_step, 1), "⏹️ Training stopped"
                    return

                loss = self.module.training_step(batch)
                loss = loss / self.training_config.gradient_accumulation_steps
                loss.backward()
                accumulated_loss += loss.item()
                accumulation_step += 1

                if accumulation_step >= self.training_config.gradient_accumulation_steps:
                    torch.nn.utils.clip_grad_norm_(trainable_params, self.training_config.max_grad_norm)
                    optimizer.step()
                    scheduler.step()
                    optimizer.zero_grad(set_to_none=True)
                    global_step += 1

                    avg_loss = accumulated_loss / accumulation_step
                    if global_step % self.training_config.log_every_n_steps == 0:
                        yield global_step, avg_loss, f"Epoch {epoch+1}, Step {global_step}, Loss: {avg_loss:.4f}"

                    epoch_loss += avg_loss
                    num_updates += 1
                    accumulated_loss = 0.0
                    accumulation_step = 0

            if accumulation_step > 0:
                torch.nn.utils.clip_grad_norm_(trainable_params, self.training_config.max_grad_norm)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
                global_step += 1

                avg_loss = accumulated_loss / accumulation_step
                if global_step % self.training_config.log_every_n_steps == 0:
                    yield global_step, avg_loss, f"Epoch {epoch+1}, Step {global_step}, Loss: {avg_loss:.4f}"

                epoch_loss += avg_loss
                num_updates += 1
                accumulated_loss = 0.0
                accumulation_step = 0

            epoch_time = time.time() - epoch_start_time
            avg_epoch_loss = epoch_loss / max(num_updates, 1)
            yield global_step, avg_epoch_loss, f"✅ Epoch {epoch+1}/{self.training_config.max_epochs} in {epoch_time:.1f}s"

            if (epoch + 1) % self.training_config.save_every_n_epochs == 0:
                checkpoint_dir = os.path.join(self.training_config.output_dir, "checkpoints", f"epoch_{epoch+1}")
                save_lokr_training_checkpoint(
                    self.module.lycoris_net,
                    optimizer,
                    scheduler,
                    epoch + 1,
                    global_step,
                    checkpoint_dir,
                    lokr_config=self.lokr_config,
                    run_metadata=self.run_metadata,
                )
                yield global_step, avg_epoch_loss, "💾 Checkpoint saved"

        final_path = os.path.join(self.training_config.output_dir, "final")
        final_metadata: Dict[str, Any] = {"lokr_config": self.lokr_config.to_dict()}
        if self.run_metadata:
            final_metadata["run_metadata"] = self.run_metadata
        save_lokr_weights(
            self.module.lycoris_net,
            final_path,
            metadata=final_metadata,
        )
        final_loss = self.module.training_losses[-1] if self.module.training_losses else 0.0
        yield global_step, final_loss, f"✅ Training complete! LoKr saved to {final_path}"

    def stop(self):
        """Stop training."""
        self.is_training = False
