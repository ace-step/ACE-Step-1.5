"""Execution helpers for service generation diffusion and output assembly."""

import random
from typing import Any, Dict, List, Optional, Tuple

import torch
from loguru import logger


class ServiceGenerateExecuteMixin:
    """Run diffusion execution for normalized service-generation requests."""

    def _unpack_service_processed_data(self, processed_data: Tuple[Any, ...]) -> Dict[str, Any]:
        """Convert batch preprocessing tuple into a keyed payload."""
        (
            keys,
            text_inputs,
            src_latents,
            target_latents,
            text_hidden_states,
            text_attention_mask,
            lyric_hidden_states,
            lyric_attention_mask,
            _audio_attention_mask,
            refer_audio_acoustic_hidden_states_packed,
            refer_audio_order_mask,
            chunk_mask,
            spans,
            is_covers,
            _audio_codes,
            lyric_token_idss,
            precomputed_lm_hints_25Hz,
            non_cover_text_hidden_states,
            non_cover_text_attention_masks,
        ) = processed_data
        return {
            "keys": keys,
            "text_inputs": text_inputs,
            "src_latents": src_latents,
            "target_latents": target_latents,
            "text_hidden_states": text_hidden_states,
            "text_attention_mask": text_attention_mask,
            "lyric_hidden_states": lyric_hidden_states,
            "lyric_attention_mask": lyric_attention_mask,
            "refer_audio_acoustic_hidden_states_packed": refer_audio_acoustic_hidden_states_packed,
            "refer_audio_order_mask": refer_audio_order_mask,
            "chunk_mask": chunk_mask,
            "spans": spans,
            "is_covers": is_covers,
            "lyric_token_idss": lyric_token_idss,
            "precomputed_lm_hints_25Hz": precomputed_lm_hints_25Hz,
            "non_cover_text_hidden_states": non_cover_text_hidden_states,
            "non_cover_text_attention_masks": non_cover_text_attention_masks,
        }

    def _resolve_service_seed_param(self, seed_list: Optional[List[int]]) -> Any:
        """Return model seed parameter: per-item seed list or random single seed."""
        if seed_list is not None:
            return seed_list
        return random.randint(0, 2**32 - 1)

    def _build_service_generate_kwargs(
        self,
        payload: Dict[str, Any],
        seed_param: Any,
        infer_steps: int,
        guidance_scale: float,
        audio_cover_strength: float,
        cover_noise_strength: float,
        infer_method: str,
        use_adg: bool,
        cfg_interval_start: float,
        cfg_interval_end: float,
        shift: float,
        timesteps: Optional[List[float]],
    ) -> Dict[str, Any]:
        """Build kwargs passed to model generation backends."""
        kwargs = {
            "text_hidden_states": payload["text_hidden_states"],
            "text_attention_mask": payload["text_attention_mask"],
            "lyric_hidden_states": payload["lyric_hidden_states"],
            "lyric_attention_mask": payload["lyric_attention_mask"],
            "refer_audio_acoustic_hidden_states_packed": payload["refer_audio_acoustic_hidden_states_packed"],
            "refer_audio_order_mask": payload["refer_audio_order_mask"],
            "src_latents": payload["src_latents"],
            "chunk_masks": payload["chunk_mask"],
            "is_covers": payload["is_covers"],
            "silence_latent": self.silence_latent,
            "seed": seed_param,
            "non_cover_text_hidden_states": payload["non_cover_text_hidden_states"],
            "non_cover_text_attention_mask": payload["non_cover_text_attention_masks"],
            "precomputed_lm_hints_25Hz": payload["precomputed_lm_hints_25Hz"],
            "audio_cover_strength": audio_cover_strength,
            "cover_noise_strength": cover_noise_strength,
            "infer_method": infer_method,
            "infer_steps": infer_steps,
            "diffusion_guidance_sale": guidance_scale,
            "use_adg": use_adg,
            "cfg_interval_start": cfg_interval_start,
            "cfg_interval_end": cfg_interval_end,
            "shift": shift,
        }
        if timesteps is not None:
            kwargs["timesteps"] = torch.tensor(timesteps, dtype=torch.float32, device=self.device)
        return kwargs

    def _execute_service_generate_diffusion(
        self,
        payload: Dict[str, Any],
        generate_kwargs: Dict[str, Any],
        seed_param: Any,
        infer_method: str,
        shift: float,
        audio_cover_strength: float,
    ) -> Tuple[Dict[str, Any], torch.Tensor, torch.Tensor, torch.Tensor]:
        """Execute condition preparation and diffusion using MLX or PyTorch backend."""
        dit_backend = (
            "MLX (native)" if (self.use_mlx_dit and self.mlx_decoder is not None) else f"PyTorch ({self.device})"
        )
        logger.info(f"[service_generate] Generating audio... (DiT backend: {dit_backend})")
        with torch.inference_mode():
            with self._load_model_context("model"):
                encoder_hidden_states, encoder_attention_mask, context_latents = self.model.prepare_condition(
                    text_hidden_states=payload["text_hidden_states"],
                    text_attention_mask=payload["text_attention_mask"],
                    lyric_hidden_states=payload["lyric_hidden_states"],
                    lyric_attention_mask=payload["lyric_attention_mask"],
                    refer_audio_acoustic_hidden_states_packed=payload["refer_audio_acoustic_hidden_states_packed"],
                    refer_audio_order_mask=payload["refer_audio_order_mask"],
                    hidden_states=payload["src_latents"],
                    attention_mask=torch.ones(
                        payload["src_latents"].shape[0],
                        payload["src_latents"].shape[1],
                        device=payload["src_latents"].device,
                        dtype=payload["src_latents"].dtype,
                    ),
                    silence_latent=self.silence_latent,
                    src_latents=payload["src_latents"],
                    chunk_masks=payload["chunk_mask"],
                    is_covers=payload["is_covers"],
                    precomputed_lm_hints_25Hz=payload["precomputed_lm_hints_25Hz"],
                )

                if self.use_mlx_dit and self.mlx_decoder is not None:
                    try:
                        enc_hs_nc, enc_am_nc, ctx_nc = None, None, None
                        if audio_cover_strength < 1.0 and payload["non_cover_text_hidden_states"] is not None:
                            non_is_covers = torch.zeros_like(payload["is_covers"])
                            sil_exp = self.silence_latent[:, :payload["src_latents"].shape[1], :].expand(
                                payload["src_latents"].shape[0], -1, -1
                            )
                            enc_hs_nc, enc_am_nc, ctx_nc = self.model.prepare_condition(
                                text_hidden_states=payload["non_cover_text_hidden_states"],
                                text_attention_mask=payload["non_cover_text_attention_masks"],
                                lyric_hidden_states=payload["lyric_hidden_states"],
                                lyric_attention_mask=payload["lyric_attention_mask"],
                                refer_audio_acoustic_hidden_states_packed=payload["refer_audio_acoustic_hidden_states_packed"],
                                refer_audio_order_mask=payload["refer_audio_order_mask"],
                                hidden_states=sil_exp,
                                attention_mask=torch.ones(
                                    sil_exp.shape[0], sil_exp.shape[1], device=sil_exp.device, dtype=sil_exp.dtype
                                ),
                                silence_latent=self.silence_latent,
                                src_latents=sil_exp,
                                chunk_masks=payload["chunk_mask"],
                                is_covers=non_is_covers,
                            )

                        outputs = self._mlx_run_diffusion(
                            encoder_hidden_states=encoder_hidden_states,
                            encoder_attention_mask=encoder_attention_mask,
                            context_latents=context_latents,
                            src_latents=payload["src_latents"],
                            seed=seed_param,
                            infer_method=infer_method,
                            shift=shift,
                            timesteps=generate_kwargs.get("timesteps"),
                            audio_cover_strength=audio_cover_strength,
                            encoder_hidden_states_non_cover=enc_hs_nc,
                            encoder_attention_mask_non_cover=enc_am_nc,
                            context_latents_non_cover=ctx_nc,
                        )
                        _tc = outputs.get("time_costs", {})
                        logger.info(
                            "[service_generate] DiT diffusion complete via MLX (%.2fs total, %.3fs/step).",
                            _tc.get("diffusion_time_cost", 0),
                            _tc.get("diffusion_per_step_time_cost", 0),
                        )
                    except Exception as exc:
                        logger.warning("[service_generate] MLX diffusion failed (%s); falling back to PyTorch.", exc)
                        outputs = self.model.generate_audio(**generate_kwargs)
                else:
                    logger.info("[service_generate] DiT diffusion via PyTorch ({})...", self.device)
                    outputs = self.model.generate_audio(**generate_kwargs)

        return outputs, encoder_hidden_states, encoder_attention_mask, context_latents
