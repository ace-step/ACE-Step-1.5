"""
PyTorch Lightning DataModule for LoRA Training

Handles data loading and preprocessing for training ACE-Step LoRA adapters.
Supports both raw audio loading and preprocessed tensor loading.
"""

import os
import json
import random
from typing import Optional, List, Dict, Any, Tuple
from loguru import logger

import torch
import torchaudio
from torch.utils.data import Dataset, DataLoader

try:
    from lightning.pytorch import LightningDataModule
    LIGHTNING_AVAILABLE = True
except ImportError:
    LIGHTNING_AVAILABLE = False
    logger.warning("Lightning not installed. Training module will not be available.")
    # Create a dummy class for type hints
    class LightningDataModule:
        pass


# ============================================================================
# Preprocessed Tensor Dataset (Recommended for Training)
# ============================================================================

class PreprocessedTensorDataset(Dataset):
    """Dataset that loads preprocessed tensor files.
    
    This is the recommended dataset for training as all tensors are pre-computed:
    - target_latents: VAE-encoded audio [T, 64]
    - encoder_hidden_states: Condition encoder output [L, D]
    - encoder_attention_mask: Condition mask [L]
    - context_latents: Source context [T, 65]
    - attention_mask: Audio latent mask [T]
    
    No VAE/text encoder needed during training - just load tensors directly!
    """
    
    def __init__(self, tensor_dir: str):
        """Initialize from a directory of preprocessed .pt files.
        
        Args:
            tensor_dir: Directory containing preprocessed .pt files and manifest.json
        """
        self.tensor_dir = tensor_dir
        self.sample_paths = []
        
        # Load manifest if exists
        manifest_path = os.path.join(tensor_dir, "manifest.json")
        if os.path.exists(manifest_path):
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            self.sample_paths = manifest.get("samples", [])
        else:
            # Fallback: scan directory for .pt files
            for f in os.listdir(tensor_dir):
                if f.endswith('.pt') and f != "manifest.json":
                    self.sample_paths.append(os.path.join(tensor_dir, f))
        
        # Validate paths
        self.valid_paths = [p for p in self.sample_paths if os.path.exists(p)]
        
        if len(self.valid_paths) != len(self.sample_paths):
            logger.warning(f"Some tensor files not found: {len(self.sample_paths) - len(self.valid_paths)} missing")
        
        logger.info(f"PreprocessedTensorDataset: {len(self.valid_paths)} samples from {tensor_dir}")
    
    def __len__(self) -> int:
        return len(self.valid_paths)
    
    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        """Load a preprocessed tensor file.
        
        Returns:
            Dictionary containing all pre-computed tensors for training
        """
        tensor_path = self.valid_paths[idx]
        data = torch.load(tensor_path, map_location='cpu', weights_only=True)
        
        return {
            "target_latents": data["target_latents"],  # [T, 64]
            "attention_mask": data["attention_mask"],  # [T]
            "encoder_hidden_states": data["encoder_hidden_states"],  # [L, D]
            "encoder_attention_mask": data["encoder_attention_mask"],  # [L]
            "context_latents": data["context_latents"],  # [T, 65]
            "metadata": data.get("metadata", {}),
        }


def collate_preprocessed_batch(batch: List[Dict]) -> Dict[str, torch.Tensor]:
    """Collate function for preprocessed tensor batches.
    
    Handles variable-length tensors by padding to the longest in the batch.
    
    Args:
        batch: List of sample dictionaries with pre-computed tensors
        
    Returns:
        Batched dictionary with all tensors stacked
    """
    # Get max lengths
    max_latent_len = max(s["target_latents"].shape[0] for s in batch)
    max_encoder_len = max(s["encoder_hidden_states"].shape[0] for s in batch)
    
    # Pad and stack tensors
    target_latents = []
    attention_masks = []
    encoder_hidden_states = []
    encoder_attention_masks = []
    context_latents = []
    
    for sample in batch:
        # Pad target_latents [T, 64] -> [max_T, 64]
        tl = sample["target_latents"]
        if tl.shape[0] < max_latent_len:
            pad = torch.zeros(max_latent_len - tl.shape[0], tl.shape[1])
            tl = torch.cat([tl, pad], dim=0)
        target_latents.append(tl)
        
        # Pad attention_mask [T] -> [max_T]
        am = sample["attention_mask"]
        if am.shape[0] < max_latent_len:
            pad = torch.zeros(max_latent_len - am.shape[0])
            am = torch.cat([am, pad], dim=0)
        attention_masks.append(am)
        
        # Pad context_latents [T, 65] -> [max_T, 65]
        cl = sample["context_latents"]
        if cl.shape[0] < max_latent_len:
            pad = torch.zeros(max_latent_len - cl.shape[0], cl.shape[1])
            cl = torch.cat([cl, pad], dim=0)
        context_latents.append(cl)
        
        # Pad encoder_hidden_states [L, D] -> [max_L, D]
        ehs = sample["encoder_hidden_states"]
        if ehs.shape[0] < max_encoder_len:
            pad = torch.zeros(max_encoder_len - ehs.shape[0], ehs.shape[1])
            ehs = torch.cat([ehs, pad], dim=0)
        encoder_hidden_states.append(ehs)
        
        # Pad encoder_attention_mask [L] -> [max_L]
        eam = sample["encoder_attention_mask"]
        if eam.shape[0] < max_encoder_len:
            pad = torch.zeros(max_encoder_len - eam.shape[0])
            eam = torch.cat([eam, pad], dim=0)
        encoder_attention_masks.append(eam)
    
    return {
        "target_latents": torch.stack(target_latents),  # [B, T, 64]
        "attention_mask": torch.stack(attention_masks),  # [B, T]
        "encoder_hidden_states": torch.stack(encoder_hidden_states),  # [B, L, D]
        "encoder_attention_mask": torch.stack(encoder_attention_masks),  # [B, L]
        "context_latents": torch.stack(context_latents),  # [B, T, 65]
        "metadata": [s["metadata"] for s in batch],
    }


class PreprocessedDataModule(LightningDataModule if LIGHTNING_AVAILABLE else object):
    """DataModule for preprocessed tensor files.
    
    This is the recommended DataModule for training. It loads pre-computed tensors
    directly without needing VAE, text encoder, or condition encoder at training time.
    """
    
    def __init__(
        self,
        tensor_dir: str,
        batch_size: int = 1,
        num_workers: int = 4,
        pin_memory: bool = True,
        val_split: float = 0.0,
    ):
        """Initialize the data module.
        
        Args:
            tensor_dir: Directory containing preprocessed .pt files
            batch_size: Training batch size
            num_workers: Number of data loading workers
            pin_memory: Whether to pin memory for faster GPU transfer
            val_split: Fraction of data for validation (0 = no validation)
        """
        if LIGHTNING_AVAILABLE:
            super().__init__()
        
        self.tensor_dir = tensor_dir
        self.batch_size = batch_size
        self.num_workers = num_workers
        self.pin_memory = pin_memory
        self.val_split = val_split
        
        self.train_dataset = None
        self.val_dataset = None
    
    def setup(self, stage: Optional[str] = None):
        """Setup datasets."""
        if stage == 'fit' or stage is None:
            # Create full dataset
            full_dataset = PreprocessedTensorDataset(self.tensor_dir)
            
            # Split if validation requested
            if self.val_split > 0 and len(full_dataset) > 1:
                n_val = max(1, int(len(full_dataset) * self.val_split))
                n_train = len(full_dataset) - n_val
                
                self.train_dataset, self.val_dataset = torch.utils.data.random_split(
                    full_dataset, [n_train, n_val]
                )
            else:
                self.train_dataset = full_dataset
                self.val_dataset = None
    
    def train_dataloader(self) -> DataLoader:
        """Create training dataloader."""
        return DataLoader(
            self.train_dataset,
            batch_size=self.batch_size,
            shuffle=True,
            num_workers=self.num_workers,
            pin_memory=self.pin_memory,
            collate_fn=collate_preprocessed_batch,
            drop_last=True,
        )
    
    def val_dataloader(self) -> Optional[DataLoader]:
        """Create validation dataloader."""
        if self.val_dataset is None:
            return None
        
        return DataLoader(
            self.val_dataset,
            batch_size=self.batch_size,
            shuffle=False,
            num_workers=self.num_workers,
            pin_memory=self.pin_memory,
            collate_fn=collate_preprocessed_batch,
        )


# ============================================================================
# Raw Audio Dataset (Legacy - for backward compatibility)
# ============================================================================

class AceStepTrainingDataset(Dataset):
    """Dataset for ACE-Step LoRA training from raw audio.
    
    DEPRECATED: Use PreprocessedTensorDataset instead for better performance.
    
    Audio Format Requirements (handled automatically):
    - Sample rate: 48kHz (resampled if different)
    - Channels: Stereo (2 channels, mono is duplicated)
    - Max duration: 240 seconds (4 minutes)
    - Min duration: 5 seconds (padded if shorter)
    """
    
    def __init__(
        self,
        samples: List[Dict[str, Any]],
        dit_handler,
        max_duration: float = 240.0,
        target_sample_rate: int = 48000,
    ):
        """Initialize the dataset."""
        self.samples = samples
        self.dit_handler = dit_handler
        self.max_duration = max_duration
        self.target_sample_rate = target_sample_rate
        
        self.valid_samples = self._validate_samples()
        logger.info(f"Dataset initialized with {len(self.valid_samples)} valid samples")
    
    def _validate_samples(self) -> List[Dict[str, Any]]:
        """Validate and filter samples."""
        valid = []
        for i, sample in enumerate(self.samples):
            audio_path = sample.get("audio_path", "")
            if not audio_path or not os.path.exists(audio_path):
                logger.warning(f"Sample {i}: Audio file not found: {audio_path}")
                continue
            
            if not sample.get("caption"):
                logger.warning(f"Sample {i}: Missing caption")
                continue
            
            valid.append(sample)
        
        return valid
    
    def __len__(self) -> int:
        return len(self.valid_samples)
    
    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        """Get a single training sample."""
        sample = self.valid_samples[idx]
        
        audio_path = sample["audio_path"]
        audio, sr = torchaudio.load(audio_path)
        
        # Resample to 48kHz
        if sr != self.target_sample_rate:
            resampler = torchaudio.transforms.Resample(sr, self.target_sample_rate)
            audio = resampler(audio)
        
        # Convert to stereo
        if audio.shape[0] == 1:
            audio = audio.repeat(2, 1)
        elif audio.shape[0] > 2:
            audio = audio[:2, :]
        
        # Truncate/pad
        max_samples = int(self.max_duration * self.target_sample_rate)
        if audio.shape[1] > max_samples:
            audio = audio[:, :max_samples]
        
        min_samples = int(5.0 * self.target_sample_rate)
        if audio.shape[1] < min_samples:
            padding = min_samples - audio.shape[1]
            audio = torch.nn.functional.pad(audio, (0, padding))
        
        return {
            "audio": audio,
            "caption": sample.get("caption", ""),
            "lyrics": sample.get("lyrics", "[Instrumental]"),
            "metadata": {
                "caption": sample.get("caption", ""),
                "lyrics": sample.get("lyrics", "[Instrumental]"),
                "bpm": sample.get("bpm"),
                "keyscale": sample.get("keyscale", ""),
                "timesignature": sample.get("timesignature", ""),
                "duration": sample.get("duration", audio.shape[1] / self.target_sample_rate),
                "language": sample.get("language", "unknown"),
                "is_instrumental": sample.get("is_instrumental", True),
            },
            "audio_path": audio_path,
        }


def collate_training_batch(batch: List[Dict]) -> Dict[str, Any]:
    """Collate function for raw audio batches (legacy)."""
    max_len = max(sample["audio"].shape[1] for sample in batch)
    
    padded_audio = []
    attention_masks = []
    
    for sample in batch:
        audio = sample["audio"]
        audio_len = audio.shape[1]
        
        if audio_len < max_len:
            padding = max_len - audio_len
            audio = torch.nn.functional.pad(audio, (0, padding))
        
        padded_audio.append(audio)
        
        mask = torch.ones(max_len)
        if audio_len < max_len:
            mask[audio_len:] = 0
        attention_masks.append(mask)
    
    return {
        "audio": torch.stack(padded_audio),
        "attention_mask": torch.stack(attention_masks),
        "captions": [s["caption"] for s in batch],
        "lyrics": [s["lyrics"] for s in batch],
        "metadata": [s["metadata"] for s in batch],
        "audio_paths": [s["audio_path"] for s in batch],
    }


class AceStepDataModule(LightningDataModule if LIGHTNING_AVAILABLE else object):
    """DataModule for raw audio loading (legacy).
    
    DEPRECATED: Use PreprocessedDataModule for better training performance.
    """
    
    def __init__(
        self,
        samples: List[Dict[str, Any]],
        dit_handler,
        batch_size: int = 1,
        num_workers: int = 4,
        pin_memory: bool = True,
        max_duration: float = 240.0,
        val_split: float = 0.0,
    ):
        if LIGHTNING_AVAILABLE:
            super().__init__()
        
        self.samples = samples
        self.dit_handler = dit_handler
        self.batch_size = batch_size
        self.num_workers = num_workers
        self.pin_memory = pin_memory
        self.max_duration = max_duration
        self.val_split = val_split
        
        self.train_dataset = None
        self.val_dataset = None
    
    def setup(self, stage: Optional[str] = None):
        if stage == 'fit' or stage is None:
            if self.val_split > 0 and len(self.samples) > 1:
                n_val = max(1, int(len(self.samples) * self.val_split))
                
                indices = list(range(len(self.samples)))
                random.shuffle(indices)
                
                val_indices = indices[:n_val]
                train_indices = indices[n_val:]
                
                train_samples = [self.samples[i] for i in train_indices]
                val_samples = [self.samples[i] for i in val_indices]
                
                self.train_dataset = AceStepTrainingDataset(
                    train_samples, self.dit_handler, self.max_duration
                )
                self.val_dataset = AceStepTrainingDataset(
                    val_samples, self.dit_handler, self.max_duration
                )
            else:
                self.train_dataset = AceStepTrainingDataset(
                    self.samples, self.dit_handler, self.max_duration
                )
                self.val_dataset = None
    
    def train_dataloader(self) -> DataLoader:
        return DataLoader(
            self.train_dataset,
            batch_size=self.batch_size,
            shuffle=True,
            num_workers=self.num_workers,
            pin_memory=self.pin_memory,
            collate_fn=collate_training_batch,
            drop_last=True,
        )
    
    def val_dataloader(self) -> Optional[DataLoader]:
        if self.val_dataset is None:
            return None
        
        return DataLoader(
            self.val_dataset,
            batch_size=self.batch_size,
            shuffle=False,
            num_workers=self.num_workers,
            pin_memory=self.pin_memory,
            collate_fn=collate_training_batch,
        )


def load_dataset_from_json(json_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Load a dataset from JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    metadata = data.get("metadata", {})
    samples = data.get("samples", [])
    
    return samples, metadata
