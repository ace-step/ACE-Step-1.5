"""Top-level ``generate_music`` orchestration mixin.

This module provides the public ``generate_music`` entry point extracted from
``AceStepHandler`` so orchestration stays separate from lower-level helpers.
"""

import gc
import traceback
from typing import Any, Dict, List, Optional, Union

import torch
from loguru import logger

from acestep.constants import DEFAULT_DIT_INSTRUCTION
from acestep.core.generation.handler.repaint_waveform_splice import (
    apply_repaint_waveform_splice,
)
from acestep.gpu_config import (
    DIT_INFERENCE_VRAM_PER_BATCH,
    VRAM_SAFETY_MARGIN_GB,
    get_effective_free_vram_gb,
)


def _resolve_repaint_config(
    mode: str = "balanced",
    strength: float = 0.5,
) -> tuple:
    """Convert repaint mode and strength into concrete numeric parameters.

    Higher *strength* means more aggressive repainting (less source preservation).

    Args:
        mode: One of ``"conservative"``, ``"balanced"``, or ``"aggressive"``.
        strength: 0.0 = conservative (max preservation), 1.0 = aggressive
            (pure diffusion).  Only effective in balanced mode.

    Returns:
        Tuple of ``(injection_ratio, crossfade_frames, wav_crossfade_sec)``.
    """
    strength = max(0.0, min(1.0, strength))
    if mode == "aggressive":
        return 0.0, 0, 0.0
    if mode == "conservative":
        return 1.0, 25, 0.05
    inv = 1.0 - strength
    return inv, round(25 * inv), 0.05 * inv


class GenerateMusicMixin:
    """Coordinate request prep, service execution, decode, and payload assembly.

    The host class is expected to implement helper methods invoked by this
    orchestration flow.
    """

    def _verify_decoder_device_dtype(self) -> None:
        """Ensure all decoder parameters are on ``self.device`` and ``self.dtype``.

        CPU-offload round-trips can leave PEFT/LoRA adapter weights on the
        wrong device or in the wrong dtype, which silently produces NaN/Inf
        during the diffusion forward pass.  This method detects and fixes
        such mismatches before generation begins.
        """
        decoder = getattr(self.model, "decoder", None)
        if decoder is None:
            return

        wrong_device = []
        wrong_dtype = []
        for name, param in decoder.named_parameters():
            if not self._is_on_target_device(param, self.device):
                wrong_device.append(name)
            if param.is_floating_point() and param.dtype != self.dtype:
                wrong_dtype.append(name)

        if wrong_device or wrong_dtype:
            if wrong_device:
                logger.warning(
                    f"[generate_music] LoRA sanity check: {len(wrong_device)} decoder "
                    f"parameters on wrong device (expected {self.device}), fixing: "
                    f"{wrong_device[:5]}{'...' if len(wrong_device) > 5 else ''}"
                )
            if wrong_dtype:
                logger.warning(
                    f"[generate_music] LoRA sanity check: {len(wrong_dtype)} decoder "
                    f"parameters have wrong dtype (expected {self.dtype}), fixing: "
                    f"{wrong_dtype[:5]}{'...' if len(wrong_dtype) > 5 else ''}"
                )
            decoder.to(device=self.device, dtype=self.dtype)

        # Final verification — use recursive move if simple .to() wasn't enough
        still_wrong = [
            name for name, p in decoder.named_parameters()
            if not self._is_on_target_device(p, self.device)
        ]
        if still_wrong:
            logger.warning(
                f"[generate_music] {len(still_wrong)} params still on wrong device "
                f"after decoder.to(), using recursive move"
            )
            self._recursive_to_device(decoder, self.device, self.dtype)

    def _vram_preflight_check(
        self,
        actual_batch_size: int,
        audio_duration: Optional[float],
        guidance_scale: float,
    ) -> Optional[Dict[str, Any]]:
        """Check free VRAM headroom before attempting service_generate.

        Model weights are already resident in GPU memory at this point.  We
        only need to verify there is enough room for the diffusion-pass
        activations (intermediate attention maps, FFN buffers, noise tensors)
        plus a project-standard safety margin.

        Args:
            actual_batch_size: Number of samples being generated.
            audio_duration: Requested audio length in seconds, or None for default.
            guidance_scale: CFG guidance value; values > 1.0 indicate CFG is active
                and the DiT runs two forward passes per step (doubling activation memory).

        Returns:
            An error payload dict when VRAM is insufficient, or None when the
            check passes or no CUDA device is present (CPU/MPS/XPU fall through).
        """
        if not torch.cuda.is_available():
            return None

        if getattr(self, "offload_to_cpu", False):
            logger.debug(
                "[generate_music] VRAM pre-flight: skipping check "
                "(offload_to_cpu=True, models loaded one-at-a-time)"
            )
            return None

        duration_s = audio_duration or 60.0
        # CFG doubles forward-pass memory: two DiT evaluations per step.
        dit_key = "base" if guidance_scale > 1.0 else "turbo"
        per_batch_gb = DIT_INFERENCE_VRAM_PER_BATCH.get(dit_key, 0.6)
        # Longer audio = more latent frames (5 Hz rate) = more memory.
        duration_factor = max(1.0, duration_s / 60.0)
        needed_gb = per_batch_gb * actual_batch_size * duration_factor + VRAM_SAFETY_MARGIN_GB

        free_gb = get_effective_free_vram_gb()
        logger.info(
            "[generate_music] VRAM pre-flight: {:.2f} GB free, ~{:.2f} GB needed "
            "(batch={}, duration={:.0f}s, mode={}).",
            free_gb, needed_gb, actual_batch_size, duration_s, dit_key,
        )

        if free_gb >= needed_gb:
            return None

        msg = (
            f"Insufficient free VRAM: need ~{needed_gb:.1f} GB, "
            f"only {free_gb:.1f} GB available. "
            f"Reduce batch size (currently {actual_batch_size}) "
            f"or audio duration (currently {duration_s:.0f}s)."
        )
        logger.warning("[generate_music] VRAM pre-flight failed: {}", msg)
        return {
            "audios": [],
            "status_message": f"Error: {msg}",
            "extra_outputs": {},
            "success": False,
            "error": msg,
        }

    def generate_music(
        self,
        captions: str,
        global_caption: str = "",
        lyrics: str = "",
        bpm: Optional[int] = None,
        key_scale: str = "",
        time_signature: str = "",
        vocal_language: str = "en",
        inference_steps: int = 8,
        guidance_scale: float = 7.0,
        use_random_seed: bool = True,
        seed: Optional[Union[str, float, int]] = -1,
        reference_audio=None,
        audio_duration: Optional[float] = None,
        batch_size: Optional[int] = None,
        src_audio=None,
        audio_code_string: Union[str, List[str]] = "",
        repainting_start: float = 0.0,
        repainting_end: Optional[float] = None,
        instruction: str = DEFAULT_DIT_INSTRUCTION,
        audio_cover_strength: float = 1.0,
        cover_noise_strength: float = 0.0,
        task_type: str = "text2music",
        use_adg: bool = False,
        cfg_interval_start: float = 0.0,
        cfg_interval_end: float = 1.0,
        shift: float = 1.0,
        infer_method: str = "ode",
        use_tiled_decode: bool = True,
        timesteps: Optional[List[float]] = None,
        latent_shift: float = 0.0,
        latent_rescale: float = 1.0,
        chunk_mask_mode: str = "auto",
        repaint_latent_crossfade_frames: int = 10,
        repaint_wav_crossfade_sec: float = 0.0,
        repaint_mode: str = "balanced",
        repaint_strength: float = 0.5,
        progress=None,
    ) -> Dict[str, Any]:
        """Generate audio from text/reference inputs and return response payload.

        Args:
            captions: Text prompt describing requested music.
            lyrics: Lyric text used for conditioning.
            reference_audio: Optional reference-audio payload.
            src_audio: Optional source audio for repaint/cover.
            inference_steps: Diffusion step count.
            guidance_scale: CFG guidance value.
            seed: Optional explicit seed from caller/UI.
            infer_method: Diffusion method name.
            timesteps: Optional custom timestep schedule.
            use_tiled_decode: Whether tiled VAE decode is used.
            latent_shift: Additive latent post-processing value.
            latent_rescale: Multiplicative latent post-processing value.
            progress: Optional callback taking ``(ratio, desc=...)``.

        Returns:
            Dict[str, Any]: Standard payload with generated audio tensors, status,
            intermediate outputs, success flag, and optional error text.

        Raises:
            No exceptions are re-raised. Runtime failures are converted into the
            returned error payload.
        """
        progress = self._resolve_generate_music_progress(progress)
        if self.model is None or self.vae is None or self.text_tokenizer is None or self.text_encoder is None:
            readiness_error = self._validate_generate_music_readiness()
            return readiness_error

        task_type, instruction = self._resolve_generate_music_task(
            task_type=task_type,
            audio_code_string=audio_code_string,
            instruction=instruction,
        )

        # Turbo models bake guidance into the distillation process and do not
        # use CFG.  Forcing guidance_scale to 1.0 avoids double-application of
        # guidance that produces noise or NaN/Inf on float16 (see issue #927).
        if self.is_turbo_model() and guidance_scale != 1.0:
            logger.info(
                "[generate_music] Turbo model detected: overriding "
                "guidance_scale {:.1f} -> 1.0 (turbo does not use CFG).",
                guidance_scale,
            )
            guidance_scale = 1.0

        # When LoRA is active, verify all decoder parameters are on the
        # expected device and dtype.  CPU-offload round-trips can leave PEFT
        # adapter weights on the wrong device, causing NaN in the diffusion
        # forward pass.  The check is cheap and prevents a hard-to-debug
        # generation failure.
        if getattr(self, "lora_loaded", False) and getattr(self, "use_lora", False):
            self._verify_decoder_device_dtype()

        logger.info("[generate_music] Starting generation...")
        if progress:
            progress(0.51, desc="Preparing inputs...")
        logger.info("[generate_music] Preparing inputs...")

        runtime = self._prepare_generate_music_runtime(
            batch_size=batch_size,
            audio_duration=audio_duration,
            repainting_end=repainting_end,
            seed=seed,
            use_random_seed=use_random_seed,
        )
        actual_batch_size = runtime["actual_batch_size"]
        actual_seed_list = runtime["actual_seed_list"]
        seed_value_for_ui = runtime["seed_value_for_ui"]
        audio_duration = runtime["audio_duration"]
        repainting_end = runtime["repainting_end"]

        try:
            refer_audios, processed_src_audio, audio_error = self._prepare_reference_and_source_audio(
                reference_audio=reference_audio,
                src_audio=src_audio,
                audio_code_string=audio_code_string,
                actual_batch_size=actual_batch_size,
                task_type=task_type,
            )
            if audio_error is not None:
                return audio_error

            service_inputs = self._prepare_generate_music_service_inputs(
                actual_batch_size=actual_batch_size,
                processed_src_audio=processed_src_audio,
                audio_duration=audio_duration,
                captions=captions,
                global_caption=global_caption,
                lyrics=lyrics,
                vocal_language=vocal_language,
                instruction=instruction,
                bpm=bpm,
                key_scale=key_scale,
                time_signature=time_signature,
                task_type=task_type,
                audio_code_string=audio_code_string,
                repainting_start=repainting_start,
                repainting_end=repainting_end,
                chunk_mask_mode=chunk_mask_mode,
            )
            vram_error = self._vram_preflight_check(
                actual_batch_size=actual_batch_size,
                audio_duration=audio_duration,
                guidance_scale=guidance_scale,
            )
            if vram_error is not None:
                return vram_error

            injection_ratio, resolved_cf_frames, resolved_wav_cf = (
                _resolve_repaint_config(repaint_mode, repaint_strength)
            )

            service_run = self._run_generate_music_service_with_progress(
                progress=progress,
                actual_batch_size=actual_batch_size,
                audio_duration=audio_duration,
                inference_steps=inference_steps,
                timesteps=timesteps,
                service_inputs=service_inputs,
                refer_audios=refer_audios,
                guidance_scale=guidance_scale,
                actual_seed_list=actual_seed_list,
                audio_cover_strength=audio_cover_strength,
                cover_noise_strength=cover_noise_strength,
                use_adg=use_adg,
                cfg_interval_start=cfg_interval_start,
                cfg_interval_end=cfg_interval_end,
                shift=shift,
                infer_method=infer_method,
                repaint_crossfade_frames=resolved_cf_frames,
                repaint_injection_ratio=injection_ratio,
            )
            outputs = service_run["outputs"]
            infer_steps_for_progress = service_run["infer_steps_for_progress"]

            pred_latents, time_costs = self._prepare_generate_music_decode_state(
                outputs=outputs,
                infer_steps_for_progress=infer_steps_for_progress,
                actual_batch_size=actual_batch_size,
                audio_duration=audio_duration,
                latent_shift=latent_shift,
                latent_rescale=latent_rescale,
            )
            pred_wavs, pred_latents_cpu, time_costs = self._decode_generate_music_pred_latents(
                pred_latents=pred_latents,
                progress=progress,
                use_tiled_decode=use_tiled_decode,
                time_costs=time_costs,
            )
            repainting_start_batch = service_inputs.get("repainting_start_batch")
            repainting_end_batch = service_inputs.get("repainting_end_batch")
            do_wav_splice = (
                repaint_mode != "aggressive"
                and repainting_start_batch is not None
                and repainting_end_batch is not None
            )
            if do_wav_splice:
                pred_wavs = apply_repaint_waveform_splice(
                    pred_wavs=pred_wavs,
                    src_wavs=service_inputs["target_wavs_tensor"],
                    repainting_starts=repainting_start_batch,
                    repainting_ends=repainting_end_batch,
                    sample_rate=self.sample_rate,
                    crossfade_duration=resolved_wav_cf,
                )
            result = self._build_generate_music_success_payload(
                outputs=outputs,
                pred_wavs=pred_wavs,
                pred_latents_cpu=pred_latents_cpu,
                time_costs=time_costs,
                seed_value_for_ui=seed_value_for_ui,
                actual_batch_size=actual_batch_size,
                progress=progress,
            )
            # Clear GPU tensor references from the mutable outputs dict so
            # accelerator memory is reclaimable before the next generation.
            _gpu_keys = (
                "src_latents", "target_latents_input", "chunk_masks",
                "latent_masks", "encoder_hidden_states",
                "encoder_attention_mask", "context_latents",
                "lyric_token_idss",
            )
            for _k in _gpu_keys:
                outputs.pop(_k, None)
            del outputs, pred_wavs, pred_latents_cpu
            gc.collect()
            self._empty_cache()
            return result
        except Exception as exc:
            error_msg = f"Error: {exc!s}\n{traceback.format_exc()}"
            logger.exception("[generate_music] Generation failed")
            return {
                "audios": [],
                "status_message": error_msg,
                "extra_outputs": {},
                "success": False,
                "error": f"{exc!s}",
            }
