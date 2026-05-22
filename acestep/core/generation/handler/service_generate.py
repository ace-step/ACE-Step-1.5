"""Service-generate orchestration entrypoint for handler decomposition.

This module provides the top-level generation flow used by service callers.
It coordinates request normalization, batch preparation, diffusion execution,
and output attachment without owning model internals.
"""

from typing import Any, Dict, List, Optional, Union

import torch


class ServiceGenerateMixin:
    """Run the high-level service-generation pipeline over prepared helper APIs.

    Implementing hosts are expected to provide request-normalization, batch
    preparation, diffusion, and output-attachment helper methods.
    """

    @torch.inference_mode()
    def service_generate(
        self,
        captions: Union[str, List[str]],
        global_captions: Optional[List[str]] = None,
        lyrics: Union[str, List[str]] = "",
        keys: Optional[Union[str, List[str]]] = None,
        target_wavs: Optional[torch.Tensor] = None,
        refer_audios: Optional[List[List[torch.Tensor]]] = None,
        metas: Optional[Union[str, Dict[str, Any], List[Union[str, Dict[str, Any]]]]] = None,
        vocal_languages: Optional[Union[str, List[str]]] = None,
        infer_steps: int = 60,
        guidance_scale: float = 7.0,
        seed: Optional[Union[int, List[int]]] = None,
        return_intermediate: bool = False,
        repainting_start: Optional[Union[float, List[float]]] = None,
        repainting_end: Optional[Union[float, List[float]]] = None,
        instructions: Optional[Union[str, List[str]]] = None,
        audio_cover_strength: float = 1.0,
        cover_noise_strength: float = 0.0,
        use_adg: bool = False,
        cfg_interval_start: float = 0.0,
        cfg_interval_end: float = 1.0,
        shift: float = 1.0,
        audio_code_hints: Optional[Union[str, List[str]]] = None,
        infer_method: str = "ode",
        timesteps: Optional[List[float]] = None,
        chunk_mask_modes: Optional[List[str]] = None,
        repaint_crossfade_frames: int = 10,
        repaint_injection_ratio: float = 0.5,
        source_repaint_latents: Optional[torch.Tensor] = None,
        sampler_mode: str = "euler",
        velocity_norm_threshold: float = 0.0,
        velocity_ema_factor: float = 0.0,
        dcw_enabled: bool = True,
        dcw_mode: str = "double",
        dcw_scaler: float = 0.05,
        dcw_high_scaler: float = 0.02,
        dcw_wavelet: str = "haar",
        task_type: str = "",
        retake_seed: Optional[Union[int, List[int]]] = None,
        retake_variance: float = 0.0,
        flow_edit_morph: bool = False,
        flow_edit_source_caption: str = "",
        flow_edit_source_lyrics: str = "",
        flow_edit_n_min: float = 0.0,
        flow_edit_n_max: float = 1.0,
        flow_edit_n_avg: int = 1,
    ) -> Dict[str, Any]:
        """Generate music latents and metadata from text/audio conditioning inputs.

        See :class:`ServiceGenerateRequestMixin` and the per-handler call sites for
        the contract on each input.  Notable groups:
        ``captions``/``lyrics``/``metas``/``vocal_languages`` are per-sample
        conditioning; ``cfg_interval_*`` / ``sampler_mode`` /
        ``velocity_*`` / ``dcw_*`` are sampler tweaks; ``flow_edit_morph``
        layers the V_delta overlay on top of cover/cover-nofsq dispatch.

        Returns:
            Dict[str, Any]: Service output payload containing generated latents,
            timing fields, and optionally intermediate conditioning tensors.

        Raises:
            Exception: Propagates exceptions raised by downstream helper methods
                (e.g., normalization, diffusion execution, output assembly).
        """
        normalized = self._normalize_service_generate_inputs(
            captions=captions,
            lyrics=lyrics,
            keys=keys,
            metas=metas,
            vocal_languages=vocal_languages,
            repainting_start=repainting_start,
            repainting_end=repainting_end,
            instructions=instructions,
            audio_code_hints=audio_code_hints,
            infer_steps=infer_steps,
            seed=seed,
            return_intermediate=return_intermediate,
        )
        batch = self._prepare_batch(
            captions=normalized["captions"],
            global_captions=global_captions,
            lyrics=normalized["lyrics"],
            keys=normalized["keys"],
            target_wavs=target_wavs,
            refer_audios=refer_audios,
            metas=normalized["metas"],
            vocal_languages=normalized["vocal_languages"],
            repainting_start=normalized["repainting_start"],
            repainting_end=normalized["repainting_end"],
            instructions=normalized["instructions"],
            audio_code_hints=normalized["audio_code_hints"],
            audio_cover_strength=audio_cover_strength,
            cover_noise_strength=cover_noise_strength,
            chunk_mask_modes=chunk_mask_modes,
            task_type=task_type,
            source_repaint_latents=source_repaint_latents,
        )
        payload = self._unpack_service_processed_data(self.preprocess_batch(batch))
        seed_param = self._resolve_service_seed_param(normalized["seed_list"])
        self._ensure_silence_latent_on_device()
        generate_kwargs = self._build_service_generate_kwargs(
            payload=payload,
            seed_param=seed_param,
            infer_steps=normalized["infer_steps"],
            guidance_scale=guidance_scale,
            audio_cover_strength=audio_cover_strength,
            cover_noise_strength=cover_noise_strength,
            infer_method=infer_method,
            use_adg=use_adg,
            cfg_interval_start=cfg_interval_start,
            cfg_interval_end=cfg_interval_end,
            shift=shift,
            timesteps=timesteps,
            repaint_crossfade_frames=repaint_crossfade_frames,
            repaint_injection_ratio=repaint_injection_ratio,
            sampler_mode=sampler_mode,
            velocity_norm_threshold=velocity_norm_threshold,
            velocity_ema_factor=velocity_ema_factor,
            dcw_enabled=dcw_enabled,
            dcw_mode=dcw_mode,
            dcw_scaler=dcw_scaler,
            dcw_high_scaler=dcw_high_scaler,
            dcw_wavelet=dcw_wavelet,
            retake_seed=retake_seed,
            retake_variance=retake_variance,
        )
        # flow_edit_ctx activates the V_delta overlay.  Supported on
        # text2music (silence-derived context, clean text-driven V_delta)
        # and cover / cover-nofsq (cover's LM-codes context shared by both
        # branches, V_delta still text-driven because the codes are the
        # same on both sides). Repaint / extract / lego have task-shape-
        # specific conditioning that needs paired-CFG derivation — left
        # for follow-up.
        flow_edit_ctx = {
            "morph": flow_edit_morph and task_type in ("text2music", "cover", "cover-nofsq"),
            "task_type": task_type,
            "source_caption": flow_edit_source_caption,
            "source_lyrics": flow_edit_source_lyrics,
            "n_min": flow_edit_n_min,
            "n_max": flow_edit_n_max,
            "n_avg": flow_edit_n_avg,
            "vocal_languages": normalized.get("vocal_languages"),
            "metas": normalized.get("metas"),
            "instructions": normalized.get("instructions"),
        }
        outputs, encoder_hidden_states, encoder_attention_mask, context_latents = (
            self._execute_service_generate_diffusion(
                payload=payload, generate_kwargs=generate_kwargs, seed_param=seed_param,
                infer_method=infer_method, shift=shift, audio_cover_strength=audio_cover_strength,
                retake_seed=retake_seed, retake_variance=retake_variance,
                flow_edit_ctx=flow_edit_ctx,
            )
        )
        return self._attach_service_generate_outputs(
            outputs=outputs,
            payload=payload,
            batch=batch,
            encoder_hidden_states=encoder_hidden_states,
            encoder_attention_mask=encoder_attention_mask,
            context_latents=context_latents,
            return_intermediate=normalized["return_intermediate"],
        )
