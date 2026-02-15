"""Preprocess labeled audio samples to tensor files for LoRA/LoKr training.

Orchestrates VAE encoding, text encoding, lyric encoding, and the DiT
condition-encoder pass.  Each model phase is wrapped in the handler's
``_load_model_context`` so that only the active model resides on the GPU
when CPU offloading is enabled.  VAE encoding uses overlap-discard
tiling to cap peak VRAM on long audio.
"""

import os
from typing import List, Tuple

import torch
from loguru import logger

from .models import AudioSample
from .preprocess_audio import load_audio_stereo
from .preprocess_context import build_context_latents
from .preprocess_encoder import run_encoder
from .preprocess_lyrics import encode_lyrics
from .preprocess_manifest import save_manifest
from .preprocess_text import build_text_prompt, encode_text
from .preprocess_utils import select_genre_indices
from .preprocess_vae import tiled_vae_encode
from acestep.debug_utils import (
    debug_log_for,
    debug_log_verbose_for,
    debug_start_verbose_for,
    debug_end_verbose_for,
)


def _empty_gpu_cache() -> None:
    """Release cached GPU memory (CUDA / MPS / XPU)."""
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    if hasattr(torch, "xpu") and torch.xpu.is_available():
        torch.xpu.empty_cache()
    if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
        try:
            torch.mps.empty_cache()
        except Exception:
            pass


class PreprocessMixin:
    """Preprocess labeled samples to tensor files."""

    def preprocess_to_tensors(
        self,
        dit_handler,
        output_dir: str,
        max_duration: float = 240.0,
        preprocess_mode: str = "lora",
        progress_callback=None,
    ) -> Tuple[List[str], str]:
        """Preprocess all labeled samples to tensor files for efficient training.

        Each model phase (VAE, text-encoder, DiT encoder) is wrapped in
        ``dit_handler._load_model_context`` so that only one model is on
        the GPU at a time when CPU offloading is active.

        Args:
            dit_handler: Initialised ``AceStepHandler`` with models loaded.
            output_dir: Directory for output ``.pt`` files.
            max_duration: Maximum audio duration in seconds.
            preprocess_mode: ``"lora"`` or ``"lokr"``.
            progress_callback: Optional ``(message) -> None`` callback.

        Returns:
            ``(output_paths, status_message)`` tuple.
        """
        mode = str(preprocess_mode or "lora").strip().lower()
        if mode not in {"lora", "lokr"}:
            mode = "lora"

        debug_log_for(
            "dataset",
            f"preprocess_to_tensors: output_dir='{output_dir}', max_duration={max_duration}, mode={mode}",
        )
        if not self.samples:
            return [], "❌ No samples to preprocess"

        labeled_samples = [s for s in self.samples if s.labeled]
        if not labeled_samples:
            return [], "❌ No labeled samples to preprocess"

        if dit_handler is None or dit_handler.model is None:
            return [], "❌ Model not initialized. Please initialize the service first."

        os.makedirs(output_dir, exist_ok=True)

        output_paths: List[str] = []
        success_count = 0
        fail_count = 0

        model = dit_handler.model
        vae = dit_handler.vae
        text_encoder = dit_handler.text_encoder
        text_tokenizer = dit_handler.text_tokenizer
        silence_latent = dit_handler.silence_latent
        device = dit_handler.device
        dtype = dit_handler.dtype

        target_sample_rate = 48000

        genre_indices = select_genre_indices(labeled_samples, self.metadata.genre_ratio)
        debug_log_verbose_for("dataset", f"selected genre indices: count={len(genre_indices)}")

        for i, sample in enumerate(labeled_samples):
            try:
                debug_log_verbose_for("dataset", f"sample[{i}] id={sample.id} file={sample.filename}")
                if progress_callback:
                    progress_callback(f"Preprocessing {i+1}/{len(labeled_samples)}: {sample.filename}")

                use_genre = i in genre_indices

                # -- Load audio ------------------------------------------------
                t0 = debug_start_verbose_for("dataset", f"load_audio_stereo[{i}]")
                audio, _ = load_audio_stereo(sample.audio_path, target_sample_rate, max_duration)
                debug_end_verbose_for("dataset", f"load_audio_stereo[{i}]", t0)
                debug_log_verbose_for("dataset", f"audio shape={tuple(audio.shape)} dtype={audio.dtype}")
                audio = audio.unsqueeze(0)

                # -- VAE encode (tiled, with CPU offloading) -------------------
                with dit_handler._load_model_context("vae"):
                    vae_device = next(vae.parameters()).device
                    audio_gpu = audio.to(vae_device).to(vae.dtype)
                    debug_log_verbose_for(
                        "dataset",
                        f"vae device={vae_device} vae dtype={vae.dtype} "
                        f"audio device={audio_gpu.device} audio dtype={audio_gpu.dtype}",
                    )

                    with torch.no_grad():
                        t0 = debug_start_verbose_for("dataset", f"vae_encode[{i}]")
                        target_latents = tiled_vae_encode(vae, audio_gpu, dtype)
                        debug_end_verbose_for("dataset", f"vae_encode[{i}]", t0)

                    del audio_gpu

                _empty_gpu_cache()

                latent_length = target_latents.shape[1]
                attention_mask = torch.ones(1, latent_length, device=device, dtype=dtype)
                debug_log_verbose_for(
                    "dataset",
                    f"target_latents shape={tuple(target_latents.shape)} latent_length={latent_length}",
                )

                # -- Text / lyric encode (with CPU offloading) -----------------
                caption = sample.get_training_prompt(self.metadata.tag_position, use_genre=use_genre)
                text_prompt = build_text_prompt(sample, self.metadata.tag_position, use_genre)

                if i == 0:
                    logger.info(f"\n{'='*70}")
                    logger.info("🔍 [DEBUG] DiT TEXT ENCODER INPUT (Training Preprocess)")
                    logger.info(f"{'='*70}")
                    logger.info(f"text_prompt:\n{text_prompt}")
                    logger.info(f"{'='*70}\n")

                with dit_handler._load_model_context("text_encoder"):
                    t0 = debug_start_verbose_for("dataset", f"encode_text[{i}]")
                    text_hidden_states, text_attention_mask = encode_text(
                        text_encoder, text_tokenizer, text_prompt, device, dtype
                    )
                    debug_end_verbose_for("dataset", f"encode_text[{i}]", t0)
                    debug_log_verbose_for(
                        "dataset",
                        f"text_hidden_states shape={tuple(text_hidden_states.shape)} "
                        f"text_attention_mask shape={tuple(text_attention_mask.shape)}",
                    )

                    lyrics = sample.lyrics if sample.lyrics else "[Instrumental]"
                    t0 = debug_start_verbose_for("dataset", f"encode_lyrics[{i}]")
                    lyric_hidden_states, lyric_attention_mask = encode_lyrics(
                        text_encoder, text_tokenizer, lyrics, device, dtype
                    )
                    debug_end_verbose_for("dataset", f"encode_lyrics[{i}]", t0)
                    debug_log_verbose_for(
                        "dataset",
                        f"lyric_hidden_states shape={tuple(lyric_hidden_states.shape)} "
                        f"lyric_attention_mask shape={tuple(lyric_attention_mask.shape)}",
                    )

                _empty_gpu_cache()

                # -- DiT condition encoder (with CPU offloading) ---------------
                t0 = debug_start_verbose_for("dataset", f"run_encoder[{i}]")
                # Ensure DiT encoder runs on the active residency device (GPU when loaded via
                # offload context). This prevents flash-attn CPU backend crashes.
                with dit_handler._load_model_context("model"):
                    model_device = next(model.parameters()).device
                    model_dtype = next(model.parameters()).dtype
                    if text_hidden_states.device != model_device:
                        text_hidden_states = text_hidden_states.to(model_device)
                    if text_attention_mask.device != model_device:
                        text_attention_mask = text_attention_mask.to(model_device)
                    if lyric_hidden_states.device != model_device:
                        lyric_hidden_states = lyric_hidden_states.to(model_device)
                    if lyric_attention_mask.device != model_device:
                        lyric_attention_mask = lyric_attention_mask.to(model_device)
                    if text_hidden_states.dtype != model_dtype:
                        text_hidden_states = text_hidden_states.to(model_dtype)
                    if lyric_hidden_states.dtype != model_dtype:
                        lyric_hidden_states = lyric_hidden_states.to(model_dtype)

                    refer_audio_hidden = None
                    refer_audio_order_mask_val = None
                    if mode == "lokr":
                        # LoKr mode uses per-sample audio latents as reference-audio conditioning.
                        refer_audio_hidden = target_latents.to(device=model_device, dtype=model_dtype)
                        refer_audio_order_mask_val = torch.zeros(
                            refer_audio_hidden.shape[0],
                            device=model_device,
                            dtype=torch.long,
                        )

                    encoder_hidden_states, encoder_attention_mask = run_encoder(
                        model,
                        text_hidden_states=text_hidden_states,
                        text_attention_mask=text_attention_mask,
                        lyric_hidden_states=lyric_hidden_states,
                        lyric_attention_mask=lyric_attention_mask,
                        device=model_device,
                        dtype=model_dtype,
                        refer_audio_hidden_states_packed=refer_audio_hidden,
                        refer_audio_order_mask=refer_audio_order_mask_val,
                    )
                debug_end_verbose_for("dataset", f"run_encoder[{i}]", t0)
                debug_log_verbose_for(
                    "dataset",
                    f"encoder_hidden_states shape={tuple(encoder_hidden_states.shape)} "
                    f"encoder_attention_mask shape={tuple(encoder_attention_mask.shape)}",
                )

                _empty_gpu_cache()

                t0 = debug_start_verbose_for("dataset", f"build_context_latents[{i}]")
                context_src = target_latents if mode == "lokr" else None
                context_latents = build_context_latents(
                    silence_latent,
                    latent_length,
                    device,
                    dtype,
                    src_latents=context_src,
                )
                debug_end_verbose_for("dataset", f"build_context_latents[{i}]", t0)

                output_data = {
                    "target_latents": target_latents.squeeze(0).cpu(),
                    "attention_mask": attention_mask.squeeze(0).cpu(),
                    "encoder_hidden_states": encoder_hidden_states.squeeze(0).cpu(),
                    "encoder_attention_mask": encoder_attention_mask.squeeze(0).cpu(),
                    "context_latents": context_latents.squeeze(0).cpu(),
                    "metadata": {
                        "audio_path": sample.audio_path,
                        "filename": sample.filename,
                        "caption": caption,
                        "lyrics": lyrics,
                        "duration": sample.duration,
                        "bpm": sample.bpm,
                        "keyscale": sample.keyscale,
                        "timesignature": sample.timesignature,
                        "language": sample.language,
                        "is_instrumental": sample.is_instrumental,
                        "preprocess_mode": mode,
                    },
                }

                output_path = os.path.join(output_dir, f"{sample.id}.pt")
                t0 = debug_start_verbose_for("dataset", f"torch.save[{i}]")
                torch.save(output_data, output_path)
                debug_end_verbose_for("dataset", f"torch.save[{i}]", t0)
                output_paths.append(output_path)
                success_count += 1

            except Exception as e:
                logger.exception(f"Error preprocessing {sample.filename}")
                fail_count += 1
                if progress_callback:
                    progress_callback(f"❌ Failed: {sample.filename}: {str(e)}")

        t0 = debug_start_verbose_for("dataset", "save_manifest")
        save_manifest(output_dir, self.metadata, output_paths)
        debug_end_verbose_for("dataset", "save_manifest", t0)

        status = f"✅ Preprocessed {success_count}/{len(labeled_samples)} samples to {output_dir}"
        if fail_count > 0:
            status += f" ({fail_count} failed)"

        return output_paths, status
