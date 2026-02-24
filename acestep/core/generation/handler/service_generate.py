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
        lyrics: Union[str, List[str]],
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
    ) -> Dict[str, Any]:
        """Generate music latents and metadata from text/audio conditioning inputs.

        Args:
            captions: Caption string(s) describing the target generation.
            lyrics: Lyric string(s) aligned with each requested sample.
            keys: Optional sample identifiers.
            target_wavs: Optional target audio tensor for repaint/cover flows.
            refer_audios: Optional nested reference-audio tensors for style conditioning.
            metas: Optional metadata payload(s) for each sample.
            vocal_languages: Optional per-sample vocal language code(s).
            infer_steps: Number of diffusion steps to run.
            guidance_scale: CFG guidance strength.
            seed: Optional scalar or per-sample seed list.
            return_intermediate: Whether to include intermediate tensors in outputs.
            repainting_start: Optional repaint start time(s) in seconds.
            repainting_end: Optional repaint end time(s) in seconds.
            instructions: Optional per-sample instruction string(s).
            audio_cover_strength: Cover blend strength.
            cover_noise_strength: Cover noise blend strength.
            use_adg: Whether adaptive diffusion guidance is enabled.
            cfg_interval_start: CFG schedule start ratio.
            cfg_interval_end: CFG schedule end ratio.
            shift: Diffusion shift parameter.
            audio_code_hints: Optional serialized audio-code hints.
            infer_method: Diffusion inference method selector.
            timesteps: Optional explicit diffusion timestep sequence.

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
        )
        outputs, encoder_hidden_states, encoder_attention_mask, context_latents = (
            self._execute_service_generate_diffusion(
                payload=payload,
                generate_kwargs=generate_kwargs,
                seed_param=seed_param,
                infer_method=infer_method,
                shift=shift,
                audio_cover_strength=audio_cover_strength,
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
