"""Lyric timestamp generation mixin for the main handler."""

from typing import Any, Dict, List, Optional

import torch
from loguru import logger

from acestep.core.generation.handler.lyric_alignment_common import LyricAlignmentCommonMixin


class LyricTimestampMixin(LyricAlignmentCommonMixin):
    """Provide cross-attention based lyric timestamp generation."""

    @torch.inference_mode()
    def get_lyric_timestamp(
        self,
        pred_latent: torch.Tensor,
        encoder_hidden_states: torch.Tensor,
        encoder_attention_mask: torch.Tensor,
        context_latents: torch.Tensor,
        lyric_token_ids: torch.Tensor,
        total_duration_seconds: float,
        vocal_language: str = "en",
        inference_steps: int = 8,
        seed: int = 42,
        custom_layers_config: Optional[Dict[int, List[int]]] = None,
    ) -> Dict[str, Any]:
        """Generate LRC timestamps by aligning decoder cross-attention to lyric tokens.

        Args:
            pred_latent (torch.Tensor): Generated latent tensor shaped ``[B, T, D]``.
            encoder_hidden_states (torch.Tensor): Decoder conditioning states.
            encoder_attention_mask (torch.Tensor): Conditioning attention mask.
            context_latents (torch.Tensor): Context latents aligned to ``pred_latent``.
            lyric_token_ids (torch.Tensor): Tokenized lyric sequence including header tokens.
            total_duration_seconds (float): Audio duration used to scale timestamp output.
            vocal_language (str): Language tag used to locate lyric header boundary.
            inference_steps (int): Positive diffusion step count for ``t_last``.
            seed (int): Noise seed used for deterministic timestamp sampling.
            custom_layers_config (Optional[Dict[int, List[int]]]): Optional attention layer/head map.

        Returns:
            Dict[str, Any]: Timestamp payload with ``lrc_text``, token/sentence timestamps, ``success``, and ``error``.

        Raises:
            Exception: Unexpected runtime failures are re-raised after logging.
        """
        if self.model is None:
            return self._lyric_timestamp_error("Model not initialized")

        custom_layers_config = self._resolve_custom_layers_config(custom_layers_config)

        try:
            (
                pred_latent,
                encoder_hidden_states,
                encoder_attention_mask,
                context_latents,
            ) = self._move_alignment_inputs_to_runtime(
                pred_latent=pred_latent,
                encoder_hidden_states=encoder_hidden_states,
                encoder_attention_mask=encoder_attention_mask,
                context_latents=context_latents,
            )
            bsz = pred_latent.shape[0]
            if not isinstance(inference_steps, int) or inference_steps <= 0:
                return self._lyric_timestamp_error(
                    f"inference_steps must be a positive non-zero integer, got {inference_steps!r}"
                )

            t_last_val = 1.0 / inference_steps
            t_tensor = torch.tensor([t_last_val] * bsz, device=pred_latent.device, dtype=pred_latent.dtype)
            noise = self._sample_noise_like(pred_latent, seed)
            xt = t_last_val * noise + (1.0 - t_last_val) * pred_latent
            attention_mask = torch.ones(bsz, pred_latent.shape[1], device=pred_latent.device, dtype=pred_latent.dtype)

            with self._load_model_context("model"):
                decoder_outputs = self.model.decoder(
                    hidden_states=xt,
                    timestep=t_tensor,
                    timestep_r=t_tensor,
                    attention_mask=attention_mask,
                    encoder_hidden_states=encoder_hidden_states,
                    use_cache=False,
                    past_key_values=None,
                    encoder_attention_mask=encoder_attention_mask,
                    context_latents=context_latents,
                    output_attentions=True,
                    custom_layers_config=custom_layers_config,
                    enable_early_exit=True,
                )

            if decoder_outputs[2] is None:
                return self._lyric_timestamp_error("Model did not return attentions")

            captured_layers = []
            for layer_attn in decoder_outputs[2]:
                if layer_attn is None:
                    continue
                captured_layers.append(layer_attn[:bsz].transpose(-1, -2))
            if not captured_layers:
                return self._lyric_timestamp_error("No valid attention layers returned")

            stacked = torch.stack(captured_layers)
            all_layers_matrix = stacked.squeeze(1) if bsz == 1 else stacked

            _, pure_lyric_ids, start_idx, end_idx = self._extract_lyric_segment(
                lyric_token_ids=lyric_token_ids,
                vocal_language=vocal_language,
            )
            pure_lyric_matrix = all_layers_matrix[:, :, start_idx:end_idx, :]

            from acestep.dit_alignment_score import MusicStampsAligner

            aligner = MusicStampsAligner(self.text_tokenizer)
            align_info = aligner.stamps_align_info(
                attention_matrix=pure_lyric_matrix,
                lyrics_tokens=pure_lyric_ids,
                total_duration_seconds=total_duration_seconds,
                custom_config=custom_layers_config,
                return_matrices=False,
                violence_level=2.0,
                medfilt_width=1,
            )
            if align_info.get("calc_matrix") is None:
                return self._lyric_timestamp_error(
                    align_info.get("error", "Failed to process attention matrix")
                )

            result = aligner.get_timestamps_and_lrc(
                calc_matrix=align_info["calc_matrix"],
                lyrics_tokens=pure_lyric_ids,
                total_duration_seconds=total_duration_seconds,
            )
            return {
                "lrc_text": result["lrc_text"],
                "sentence_timestamps": result["sentence_timestamps"],
                "token_timestamps": result["token_timestamps"],
                "success": True,
                "error": None,
            }
        except (ValueError, KeyError, RuntimeError, OSError) as exc:
            logger.exception("[get_lyric_timestamp] Failed")
            return self._lyric_timestamp_error(f"Error generating timestamps: {exc}")
        except Exception:
            logger.exception("[get_lyric_timestamp] Unexpected failure")
            raise
