"""
Audio saving and transcoding utility module

Independent audio file operations outside of handler, supporting:
- Save audio tensor/numpy to files (default FLAC format, fast)
- Format conversion (FLAC/WAV/MP3)
- Batch processing
"""


import io
import json
import os
import subprocess
import hashlib
import tempfile
from pathlib import Path
from typing import Union, Optional, List, Tuple
import torch
import numpy as np
import torchaudio
from loguru import logger


def apply_fade(
    audio_data: Union[torch.Tensor, np.ndarray],
    fade_in_samples: int = 0,
    fade_out_samples: int = 0,
) -> Union[torch.Tensor, np.ndarray]:
    """Apply linear fade in and/or fade out to audio data.

    Args:
        audio_data: Audio data as torch.Tensor [channels, samples] or numpy.ndarray.
        fade_in_samples: Number of samples for fade in ramp (0 = no fade in).
        fade_out_samples: Number of samples for fade out ramp (0 = no fade out).

    Returns:
        Audio data with fades applied, in the same format as input.
    """
    if fade_in_samples <= 0 and fade_out_samples <= 0:
        return audio_data

    is_tensor = isinstance(audio_data, torch.Tensor)
    if is_tensor:
        audio = audio_data.clone()
        total_samples = audio.shape[-1]
    else:
        audio = audio_data.copy()
        total_samples = audio.shape[-1]

    if fade_in_samples > 0:
        actual_in = min(fade_in_samples, total_samples)
        if is_tensor:
            ramp = torch.linspace(0.0, 1.0, actual_in, dtype=audio.dtype, device=audio.device)
            audio[..., :actual_in] = audio[..., :actual_in] * ramp
        else:
            ramp = np.linspace(0.0, 1.0, actual_in, dtype=np.float32)
            audio[..., :actual_in] = audio[..., :actual_in] * ramp

    if fade_out_samples > 0:
        actual_out = min(fade_out_samples, total_samples)
        if is_tensor:
            ramp = torch.linspace(1.0, 0.0, actual_out, dtype=audio.dtype, device=audio.device)
            audio[..., total_samples - actual_out:] = audio[..., total_samples - actual_out:] * ramp
        else:
            ramp = np.linspace(1.0, 0.0, actual_out, dtype=np.float32)
            audio[..., total_samples - actual_out:] = audio[..., total_samples - actual_out:] * ramp

    return audio


def normalize_audio(audio_data: Union[torch.Tensor, np.ndarray], target_db: float = -1.0) -> Union[torch.Tensor, np.ndarray]:
    """
    Apply peak normalization to audio data.
    
    Args:
        audio_data: Audio data as torch.Tensor or numpy.ndarray
        target_db: Target peak level in dB (default: -1.0)
        
    Returns:
        Normalized audio data in the same format as input
    """
    # Create a copy to avoid modifying original in-place
    if isinstance(audio_data, torch.Tensor):
        audio = audio_data.clone()
        is_tensor = True
    else:
        audio = audio_data.copy()
        is_tensor = False
        
    # Calculate current peak
    if is_tensor:
        peak = torch.max(torch.abs(audio))
    else:
        peak = np.max(np.abs(audio))
        
    # Handle silence/near-silence to avoid division by zero or extreme gain
    if peak < 1e-6:
        return audio_data
        
    # Convert target dB to linear amplitude
    target_amp = 10 ** (target_db / 20.0)
    
    # Calculate needed gain
    gain = target_amp / peak
    
    # Apply gain
    audio = audio * gain
    
    return audio



class AudioSaver:
    """Audio saving and transcoding utility class"""

    MP3_DEFAULT_BITRATE = "128k"
    MP3_ALLOWED_BITRATES = {"128k", "192k", "256k", "320k"}
    MP3_DEFAULT_SAMPLE_RATE = 48000
    MP3_ALLOWED_SAMPLE_RATES = {44100, 48000}
    
    def __init__(self, default_format: str = "flac"):
        """
        Initialize audio saver
        
        Args:
            default_format: Default save format ('flac', 'wav', 'mp3', 'wav32', 'opus', 'aac')
        """
        self.default_format = default_format.lower()
        if self.default_format not in ["flac", "wav", "mp3", "wav32", "opus", "aac"]:
            logger.warning(f"Unsupported format {default_format}, using 'flac'")
            self.default_format = "flac"
    
    def _save_mp3(
        self,
        audio_tensor: torch.Tensor,
        output_path: Path,
        input_sample_rate: int,
        mp3_bitrate: Optional[str] = None,
        mp3_sample_rate: Optional[int] = None,
    ) -> None:
        """Save MP3 with explicit ffmpeg settings and 128k/48k defaults."""
        bitrate = str(mp3_bitrate or self.MP3_DEFAULT_BITRATE).strip().lower()
        if bitrate not in self.MP3_ALLOWED_BITRATES:
            bitrate = self.MP3_DEFAULT_BITRATE

        try:
            target_sample_rate = int(mp3_sample_rate or self.MP3_DEFAULT_SAMPLE_RATE)
        except Exception:
            target_sample_rate = self.MP3_DEFAULT_SAMPLE_RATE
        if target_sample_rate not in self.MP3_ALLOWED_SAMPLE_RATES:
            target_sample_rate = self.MP3_DEFAULT_SAMPLE_RATE

        tensor_to_save = audio_tensor
        if int(input_sample_rate) != int(target_sample_rate):
            tensor_to_save = torchaudio.functional.resample(audio_tensor, int(input_sample_rate), int(target_sample_rate))

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            temp_wav_path = Path(temp_wav.name)

        try:
            torchaudio.save(
                str(temp_wav_path),
                tensor_to_save,
                int(target_sample_rate),
                channels_first=True,
                backend='soundfile',
            )
            cmd = [
                'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                '-i', str(temp_wav_path),
                '-codec:a', 'libmp3lame',
                '-ar', str(int(target_sample_rate)),
                '-b:a', bitrate,
                str(output_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            logger.debug(f"[AudioSaver] Saved audio to {output_path} (mp3, {target_sample_rate}Hz, {bitrate})")
        except FileNotFoundError as e:
            raise RuntimeError("ffmpeg executable not found. Install ffmpeg or add it to PATH to export MP3 files.") from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("ffmpeg MP3 export timed out after 120 seconds.") from e
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            raise RuntimeError(f"ffmpeg MP3 export failed: {stderr}") from e
        finally:
            try:
                temp_wav_path.unlink(missing_ok=True)
            except Exception:
                logger.warning(f"[AudioSaver] Failed to remove temporary WAV file: {temp_wav_path}")

    def save_audio(
        self,
        audio_data: Union[torch.Tensor, np.ndarray],
        output_path: Union[str, Path],
        sample_rate: int = 48000,
        format: Optional[str] = None,
        channels_first: bool = True,
        mp3_bitrate: Optional[str] = None,
        mp3_sample_rate: Optional[int] = None,
    ) -> str:
        """
        Save audio data to file
        
        Args:
            audio_data: Audio data, torch.Tensor [channels, samples] or numpy.ndarray
            output_path: Output file path (extension can be omitted)
            sample_rate: Sample rate
            format: Audio format ('flac', 'wav', 'mp3', 'wav32', 'opus', 'aac'), defaults to default_format
            channels_first: If True, tensor format is [channels, samples], else [samples, channels]
            mp3_bitrate: Optional MP3 bitrate override (128k/192k/256k/320k)
            mp3_sample_rate: Optional MP3 sample rate override (44100/48000)
        
        Returns:
            Actual saved file path
        """
        format = (format or self.default_format).lower()
        if format not in ["flac", "wav", "mp3", "wav32", "opus", "aac"]:
            logger.warning(f"Unsupported format {format}, using {self.default_format}")
            format = self.default_format
        
        # Ensure output path has correct extension
        output_path = Path(output_path)
        
        # Determine extension based on format
        ext = ".wav" if format == "wav32" else f".{format}"
        
        if output_path.suffix.lower() not in ['.flac', '.wav', '.mp3', '.opus', '.aac', '.m4a']:
            output_path = output_path.with_suffix(ext)
        elif format == "wav32" and output_path.suffix.lower() == ".wav32":
             # Explicitly fix .wav32 extension if present
             output_path = output_path.with_suffix(".wav")
        elif format == "aac" and output_path.suffix.lower() == ".m4a":
             # Allow .m4a as valid extension for AAC (it's a container format for AAC)
             pass
        
        # Convert to torch tensor
        if isinstance(audio_data, np.ndarray):
            if channels_first:
                # numpy already [channels, samples]
                audio_tensor = torch.from_numpy(audio_data).float()
            else:
                # numpy [samples, channels] -> tensor [samples, channels] -> [channels, samples] (if transposed)
                audio_tensor = torch.from_numpy(audio_data).float()
                if audio_tensor.dim() == 2 and audio_tensor.shape[0] > audio_tensor.shape[1]:
                     # Assume [samples, channels] if dim0 > dim1 (heuristic)
                     audio_tensor = audio_tensor.T
        else:
            # torch tensor
            audio_tensor = audio_data.cpu().float()
            if not channels_first and audio_tensor.dim() == 2:
                # [samples, channels] -> [channels, samples]
                if audio_tensor.shape[0] > audio_tensor.shape[1]:
                    audio_tensor = audio_tensor.T
        
        # Ensure memory is contiguous
        audio_tensor = audio_tensor.contiguous()
        
        # Select backend and save
        try:
            if format == "mp3":
                self._save_mp3(
                    audio_tensor,
                    output_path,
                    sample_rate,
                    mp3_bitrate=mp3_bitrate,
                    mp3_sample_rate=mp3_sample_rate,
                )
                return str(output_path)
            elif format in ["opus", "aac"]:
                # Opus and AAC use ffmpeg backend
                torchaudio.save(
                    str(output_path),
                    audio_tensor,
                    sample_rate,
                    channels_first=True,
                    backend='ffmpeg',
                )
            elif format in ["flac", "wav", "wav32"]:
                # FLAC and WAV use soundfile backend (fastest)
                # handle 32-bit float wav
                if format == "wav32":
                    try:
                        import soundfile as sf
                        
                        # Use soundfile directly for 32-bit float
                        audio_np = audio_tensor.transpose(0, 1).numpy() # [channels, samples] -> [samples, channels]
                        
                        # Explicitly specify format as WAV to avoid issues with extension detection or custom extensions
                        sf.write(str(output_path), audio_np, sample_rate, subtype='FLOAT', format='WAV')
                        logger.debug(f"[AudioSaver] Saved audio to {output_path} (wav32, {sample_rate}Hz)")
                        return str(output_path)
                    except Exception as e:
                        logger.error(f"Failed to save wav32: {e}, falling back to standard wav")
                        format = "wav"
                        # Fallthrough to standard wav saving

                torchaudio.save(
                    str(output_path),
                    audio_tensor,
                    sample_rate,
                    channels_first=True,
                    backend='soundfile',
                )
            else:
                # Other formats use default backend
                torchaudio.save(
                    str(output_path),
                    audio_tensor,
                    sample_rate,
                    channels_first=True,
                )
            
            logger.debug(f"[AudioSaver] Saved audio to {output_path} ({format}, {sample_rate}Hz)")
            return str(output_path)
            
        except Exception as e:
            if format == "mp3":
                logger.error(f"[AudioSaver] MP3 export failed without fallback: {e}")
                raise
            try:
                import soundfile as sf
                audio_np = audio_tensor.transpose(0, 1).numpy()  # -> [samples, channels]
                
                # Handle wav32 fallback formatting
                if format == "wav32":
                    sf_format = "WAV"
                    subtype = "FLOAT"
                else:
                    sf_format = format.upper()
                    subtype = None
                    
                sf.write(str(output_path), audio_np, sample_rate, format=sf_format, subtype=subtype)
                logger.debug(f"[AudioSaver] Fallback soundfile Saved audio to {output_path} ({format}, {sample_rate}Hz)")
                return str(output_path)
            except Exception as inner_e:
                logger.error(f"[AudioSaver] Failed to save audio: {e} -> Fallback failed: {inner_e}")
                raise
    
    def convert_audio(
        self,
        input_path: Union[str, Path],
        output_path: Union[str, Path],
        output_format: str,
        remove_input: bool = False,
        mp3_bitrate: Optional[str] = None,
        mp3_sample_rate: Optional[int] = None,
    ) -> str:
        """
        Convert audio format
        
        Args:
            input_path: Input audio file path
            output_path: Output audio file path
            output_format: Target format ('flac', 'wav', 'mp3', 'wav32', 'opus', 'aac')
            remove_input: Whether to delete input file
            mp3_bitrate: Optional MP3 bitrate override (128k/192k/256k/320k)
            mp3_sample_rate: Optional MP3 sample rate override (44100/48000)

        Returns:
            Output file path
        """
        input_path = Path(input_path)
        output_path = Path(output_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        # Load audio
        audio_tensor, sample_rate = torchaudio.load(str(input_path))
        
        # Save as new format
        output_path = self.save_audio(
            audio_tensor,
            output_path,
            sample_rate=sample_rate,
            format=output_format,
            channels_first=True,
            mp3_bitrate=mp3_bitrate,
            mp3_sample_rate=mp3_sample_rate,
        )
        
        # Delete input file if needed
        if remove_input:
            input_path.unlink()
            logger.debug(f"[AudioSaver] Removed input file: {input_path}")
        
        return output_path
    
    def save_batch(
        self,
        audio_batch: Union[List[torch.Tensor], torch.Tensor],
        output_dir: Union[str, Path],
        file_prefix: str = "audio",
        sample_rate: int = 48000,
        format: Optional[str] = None,
        channels_first: bool = True,
        mp3_bitrate: Optional[str] = None,
        mp3_sample_rate: Optional[int] = None,
    ) -> List[str]:
        """
        Save audio batch
        
        Args:
            audio_batch: Audio batch, List[tensor] or tensor [batch, channels, samples]
            output_dir: Output directory
            file_prefix: File prefix
            sample_rate: Sample rate
            format: Audio format
            channels_first: Tensor format flag
            mp3_bitrate: Optional MP3 bitrate override (128k/192k/256k/320k)
            mp3_sample_rate: Optional MP3 sample rate override (44100/48000)

        Returns:
            List of saved file paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Process batch
        if isinstance(audio_batch, torch.Tensor) and audio_batch.dim() == 3:
            # [batch, channels, samples]
            audio_list = [audio_batch[i] for i in range(audio_batch.shape[0])]
        elif isinstance(audio_batch, list):
            audio_list = audio_batch
        else:
            audio_list = [audio_batch]
        
        saved_paths = []
        for i, audio in enumerate(audio_list):
            output_path = output_dir / f"{file_prefix}_{i:04d}"
            saved_path = self.save_audio(
                audio,
                output_path,
                sample_rate=sample_rate,
                format=format,
                channels_first=channels_first,
                mp3_bitrate=mp3_bitrate,
                mp3_sample_rate=mp3_sample_rate,
            )
            saved_paths.append(saved_path)
        
        return saved_paths


def get_lora_weights_hash(dit_handler) -> str:
    """Compute an MD5 hash identifying the currently loaded LoRA adapter weights.

    Iterates over the handler's LoRA service registry to find adapter weight
    file paths, then hashes each file to produce a combined fingerprint.

    Args:
        dit_handler: DiT handler instance with LoRA state attributes.

    Returns:
        Hex digest string uniquely identifying the loaded LoRA weights,
        or empty string if no LoRA is active.
    """
    if not getattr(dit_handler, "lora_loaded", False):
        return ""
    if not getattr(dit_handler, "use_lora", False):
        return ""

    lora_service = getattr(dit_handler, "_lora_service", None)
    if lora_service is None or not lora_service.registry:
        return ""

    hash_obj = hashlib.sha256()
    found_any = False

    for adapter_name in sorted(lora_service.registry.keys()):
        meta = lora_service.registry[adapter_name]
        lora_path = meta.get("path")
        if not lora_path:
            continue

        # Try common weight file names at lora_path
        candidates = []
        if os.path.isfile(lora_path):
            candidates.append(lora_path)
        elif os.path.isdir(lora_path):
            for fname in (
                "adapter_model.safetensors",
                "adapter_model.bin",
                "lokr_weights.safetensors",
            ):
                fpath = os.path.join(lora_path, fname)
                if os.path.isfile(fpath):
                    candidates.append(fpath)

        for fpath in candidates:
            try:
                with open(fpath, "rb") as f:
                    while True:
                        chunk = f.read(1 << 20)  # 1 MB chunks
                        if not chunk:
                            break
                        hash_obj.update(chunk)
                found_any = True
            except OSError:
                continue

    return hash_obj.hexdigest() if found_any else ""


def get_audio_file_hash(audio_file) -> str:
    """
    Get hash identifier for an audio file.
    
    Args:
        audio_file: Path to audio file (str) or file-like object
    
    Returns:
        Hash string or empty string
    """
    if audio_file is None:
        return ""
    
    try:
        if isinstance(audio_file, str):
            if os.path.exists(audio_file):
                with open(audio_file, 'rb') as f:
                    return hashlib.sha256(f.read()).hexdigest()
            return hashlib.sha256(audio_file.encode('utf-8')).hexdigest()
        elif hasattr(audio_file, 'name'):
            return hashlib.sha256(str(audio_file.name).encode('utf-8')).hexdigest()
        return hashlib.sha256(str(audio_file).encode('utf-8')).hexdigest()
    except Exception:
        return hashlib.sha256(str(audio_file).encode('utf-8')).hexdigest()


def generate_uuid_from_params(params_dict) -> str:
    """
    Generate deterministic UUID from generation parameters.
    Same parameters will always generate the same UUID.
    
    Args:
        params_dict: Dictionary of parameters
    
    Returns:
        UUID string
    """
    
    params_json = json.dumps(params_dict, sort_keys=True, ensure_ascii=False)
    hash_obj = hashlib.sha256(params_json.encode('utf-8'))
    hash_hex = hash_obj.hexdigest()
    uuid_str = f"{hash_hex[0:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"
    return uuid_str


def generate_uuid_from_audio_data(
    audio_data: Union[torch.Tensor, np.ndarray],
    seed: Optional[int] = None
) -> str:
    """
    Generate UUID from audio data (for caching/deduplication)
    
    Args:
        audio_data: Audio data
        seed: Optional seed value
    
    Returns:
        UUID string
    """
    if isinstance(audio_data, torch.Tensor):
        # Convert to numpy and calculate hash
        audio_np = audio_data.cpu().numpy()
    else:
        audio_np = audio_data
    
    # Calculate data hash
    data_hash = hashlib.sha256(audio_np.tobytes()).hexdigest()
    
    if seed is not None:
        combined = f"{data_hash}_{seed}"
        return hashlib.sha256(combined.encode()).hexdigest()
    
    return data_hash


# Global default instance
_default_saver = AudioSaver(default_format="flac")


def save_audio(
    audio_data: Union[torch.Tensor, np.ndarray],
    output_path: Union[str, Path],
    sample_rate: int = 48000,
    format: Optional[str] = None,
    channels_first: bool = True,
    mp3_bitrate: Optional[str] = None,
    mp3_sample_rate: Optional[int] = None,
) -> str:
    """
    Convenience function: save audio (using default configuration)
    
    Args:
        audio_data: Audio data
        output_path: Output path
        sample_rate: Sample rate
        format: Format (default flac)
        channels_first: Tensor format flag
        mp3_bitrate: Optional MP3 bitrate override (128k/192k/256k/320k)
        mp3_sample_rate: Optional MP3 sample rate override (44100/48000)

    Returns:
        Saved file path
    """
    return _default_saver.save_audio(
        audio_data,
        output_path,
        sample_rate,
        format,
        channels_first,
        mp3_bitrate,
        mp3_sample_rate,
    )

