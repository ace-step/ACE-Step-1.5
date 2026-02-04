"""
LoRA Trainer for ACE-Step

Lightning Fabric-based trainer for LoRA fine-tuning of ACE-Step DiT decoder.
Supports training from preprocessed tensor files for optimal performance.
"""

import os
import time
from contextlib import nullcontext
from typing import Optional, List, Dict, Any, Tuple, Generator
from loguru import logger

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingWarmRestarts, LinearLR, SequentialLR

try:
    from lightning.fabric import Fabric
    from lightning.fabric.loggers import TensorBoardLogger
    LIGHTNING_AVAILABLE = True
except ImportError:
    LIGHTNING_AVAILABLE = False
    logger.warning("Lightning Fabric not installed. Training will use basic training loop.")

from acestep.training.configs import LoRAConfig, TrainingConfig
from acestep.training.lora_utils import (
    inject_lora_into_dit,
    save_lora_weights,
    save_training_checkpoint,
    load_training_checkpoint,
    check_peft_available,
)
from acestep.training.data_module import PreprocessedDataModule


# Turbo model shift=3.0 discrete timesteps (8 steps, same as inference)
TURBO_SHIFT3_TIMESTEPS = [1.0, 0.9545454545454546, 0.9, 0.8333333333333334, 0.75, 0.6428571428571429, 0.5, 0.3]


def sample_discrete_timestep(bsz, device, dtype):
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
    indices = torch.randint(0, len(TURBO_SHIFT3_TIMESTEPS), (bsz,), device=device)
    
    # Convert to tensor and index
    timesteps_tensor = torch.tensor(TURBO_SHIFT3_TIMESTEPS, device=device, dtype=dtype)
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
        self.device = device
        self.dtype = dtype
        
        # Inject LoRA into the decoder only
        if check_peft_available():
            self.model, self.lora_info = inject_lora_into_dit(model, lora_config)
            logger.info(f"LoRA injected: {self.lora_info['trainable_params']:,} trainable params")
        else:
            self.model = model
            self.lora_info = {}
            logger.warning("PEFT not available, training without LoRA adapters")
        
        # Model config for flow matching
        self.config = model.config
        
        # Store training losses
        self.training_losses = []
    
    def training_step(self, batch: Dict[str, torch.Tensor]) -> torch.Tensor:
        """Single training step using preprocessed tensors.
        
        Note: This is a distilled turbo model, NO CFG is used.
        
        Args:
            batch: Dictionary containing pre-computed tensors:
                - target_latents: [B, T, 64] - VAE encoded audio
                - attention_mask: [B, T] - Valid audio mask
                - encoder_hidden_states: [B, L, D] - Condition encoder output
                - encoder_attention_mask: [B, L] - Condition mask
                - context_latents: [B, T, 128] - Source context
            
        Returns:
            Loss tensor (float32 for stable backward)
        """
        # Use autocast for mixed precision training on supported devices
        device_type = self.device.type if isinstance(self.device, torch.device) else str(self.device)
        if device_type in ["cuda", "xpu"]:
            autocast_ctx = torch.autocast(device_type=device_type, dtype=torch.bfloat16)
        elif device_type == "mps":
            autocast_ctx = torch.autocast(device_type=device_type, dtype=torch.float16)
        else:
            autocast_ctx = nullcontext()

        with autocast_ctx:
            # Get tensors from batch (already on device from Fabric dataloader)
            target_latents = batch["target_latents"].to(self.device)  # x0
            attention_mask = batch["attention_mask"].to(self.device)
            encoder_hidden_states = batch["encoder_hidden_states"].to(self.device)
            encoder_attention_mask = batch["encoder_attention_mask"].to(self.device)
            context_latents = batch["context_latents"].to(self.device)
            
            bsz = target_latents.shape[0]
            
            # Flow matching: sample noise x1 and interpolate with data x0
            x1 = torch.randn_like(target_latents)  # Noise
            x0 = target_latents  # Data
            
            # Sample timesteps from discrete turbo shift=3 schedule (8 steps)
            t, r = sample_discrete_timestep(bsz, self.device, torch.bfloat16)
            t_ = t.unsqueeze(-1).unsqueeze(-1)
            
            # Interpolate: x_t = t * x1 + (1 - t) * x0
            xt = t_ * x1 + (1.0 - t_) * x0
            
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
            # Validate tensor directory
            if not os.path.exists(tensor_dir):
                yield 0, 0.0, f"❌ Tensor directory not found: {tensor_dir}"
                return
            
            # Create training module
            self.module = PreprocessedLoRAModule(
                model=self.dit_handler.model,
                lora_config=self.lora_config,
                training_config=self.training_config,
                device=self.dit_handler.device,
                dtype=self.dit_handler.dtype,
            )
            
            # Create data module
            data_module = PreprocessedDataModule(
                tensor_dir=tensor_dir,
                batch_size=self.training_config.batch_size,
                num_workers=self.training_config.num_workers,
                pin_memory=self.training_config.pin_memory,
            )
            
            # Setup data
            data_module.setup('fit')
            
            if len(data_module.train_dataset) == 0:
                yield 0, 0.0, "❌ No valid samples found in tensor directory"
                return
            
            yield 0, 0.0, f"📂 Loaded {len(data_module.train_dataset)} preprocessed samples"

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
        
        # Force BFloat16 precision (only supported precision for this model)
        precision = "bf16-mixed"
        
        # Create TensorBoard logger
        tb_logger = TensorBoardLogger(
            root_dir=self.training_config.output_dir,
            name="logs"
        )
        
        # Initialize Fabric
        self.fabric = Fabric(
            accelerator="auto",
            devices=1,
            precision=precision,
            loggers=[tb_logger],
        )
        self.fabric.launch()
        
        yield 0, 0.0, f"🚀 Starting training (precision: {precision})..."
        
        # Get dataloader
        train_loader = data_module.train_dataloader()
        
        # Setup optimizer - only LoRA parameters
        trainable_params = [p for p in self.module.model.parameters() if p.requires_grad]
        
        if not trainable_params:
            yield 0, 0.0, "❌ No trainable parameters found!"
            return
        
        yield 0, 0.0, f"🎯 Training {sum(p.numel() for p in trainable_params):,} parameters"
        
        optimizer = AdamW(
            trainable_params,
            lr=self.training_config.learning_rate,
            weight_decay=self.training_config.weight_decay,
        )
        
        # Calculate total steps
        total_steps = len(train_loader) * self.training_config.max_epochs // self.training_config.gradient_accumulation_steps
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
        
        # Convert model to bfloat16 (entire model for consistent dtype)
        self.module.model = self.module.model.to(torch.bfloat16)

        # Setup with Fabric - only the decoder (which has LoRA)
        self.module.model.decoder, optimizer = self.fabric.setup(self.module.model.decoder, optimizer)
        train_loader = self.fabric.setup_dataloaders(train_loader)

        # Handle resume from checkpoint (load AFTER Fabric setup)
        start_epoch = 0
        global_step = 0
        checkpoint_info = None

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
                            state_dict = torch.load(adapter_weights_path, map_location=self.module.device)

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

        self.module.model.decoder.train()

        for epoch in range(start_epoch, self.training_config.max_epochs):
            epoch_loss = 0.0
            num_batches = 0
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
                    self.fabric.clip_gradients(
                        self.module.model.decoder,
                        optimizer,
                        max_norm=self.training_config.max_grad_norm,
                    )
                    
                    optimizer.step()
                    scheduler.step()
                    optimizer.zero_grad()
                    
                    global_step += 1
                    
                    # Log
                    avg_loss = accumulated_loss / accumulation_step
                    self.fabric.log("train/loss", avg_loss, step=global_step)
                    self.fabric.log("train/lr", scheduler.get_last_lr()[0], step=global_step)
                    
                    if global_step % self.training_config.log_every_n_steps == 0:
                        yield global_step, avg_loss, f"Epoch {epoch+1}/{self.training_config.max_epochs}, Step {global_step}, Loss: {avg_loss:.4f}"
                    
                    epoch_loss += accumulated_loss
                    num_batches += 1
                    accumulated_loss = 0.0
                    accumulation_step = 0
            
            # End of epoch
            epoch_time = time.time() - epoch_start_time
            avg_epoch_loss = epoch_loss / max(num_batches, 1)
            
            self.fabric.log("train/epoch_loss", avg_epoch_loss, step=epoch + 1)
            yield global_step, avg_epoch_loss, f"✅ Epoch {epoch+1}/{self.training_config.max_epochs} in {epoch_time:.1f}s, Loss: {avg_epoch_loss:.4f}"
            
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
        
        optimizer = AdamW(
            trainable_params,
            lr=self.training_config.learning_rate,
            weight_decay=self.training_config.weight_decay,
        )
        
        total_steps = len(train_loader) * self.training_config.max_epochs // self.training_config.gradient_accumulation_steps
        warmup_steps = min(self.training_config.warmup_steps, max(1, total_steps // 10))
        
        warmup_scheduler = LinearLR(optimizer, start_factor=0.1, end_factor=1.0, total_iters=warmup_steps)
        main_scheduler = CosineAnnealingWarmRestarts(optimizer, T_0=max(1, total_steps - warmup_steps), T_mult=1, eta_min=self.training_config.learning_rate * 0.01)
        scheduler = SequentialLR(optimizer, schedulers=[warmup_scheduler, main_scheduler], milestones=[warmup_steps])
        
        global_step = 0
        accumulation_step = 0
        accumulated_loss = 0.0
        
        self.module.model.decoder.train()
        
        for epoch in range(self.training_config.max_epochs):
            epoch_loss = 0.0
            num_batches = 0
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
                    optimizer.zero_grad()
                    global_step += 1
                    
                    if global_step % self.training_config.log_every_n_steps == 0:
                        avg_loss = accumulated_loss / accumulation_step
                        yield global_step, avg_loss, f"Epoch {epoch+1}, Step {global_step}, Loss: {avg_loss:.4f}"
                    
                    epoch_loss += accumulated_loss
                    num_batches += 1
                    accumulated_loss = 0.0
                    accumulation_step = 0
            
            epoch_time = time.time() - epoch_start_time
            avg_epoch_loss = epoch_loss / max(num_batches, 1)
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
