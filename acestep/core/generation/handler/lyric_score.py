"""Lyric alignment scoring mixin for the main handler."""

from typing import Any, Dict, List, Optional

import torch
from loguru import logger

from acestep.core.generation.handler.lyric_alignment_common import LyricAlignmentCommonMixin


class LyricScoreMixin(LyricAlignmentCommonMixin):
    """Provide LM/DiT lyric alignment scoring from decoder attentions."""

    @torch.inference_mode()
    def get_lyric_score(
        self,
        pred_latent: torch.Tensor,
        encoder_hidden_states: torch.Tensor,
        encoder_attention_mask: torch.Tensor,
        context_latents: torch.Tensor,
        lyric_token_ids: torch.Tensor,
        vocal_language: str = "en",
        inference_steps: int = 8,
        seed: int = 42,
        custom_layers_config: Optional[Dict[int, List[int]]] = None,
    ) -> Dict[str, Any]:
        """Calculate lyric alignment scores for pure-noise and regressed-latent inputs.

        Args:
            pred_latent (torch.Tensor): Generated latent tensor shaped ``[B, T, D]``.
            encoder_hidden_states (torch.Tensor): Decoder conditioning states.
            encoder_attention_mask (torch.Tensor): Conditioning attention mask.
            context_latents (torch.Tensor): Context latents aligned to ``pred_latent``.
            lyric_token_ids (torch.Tensor): Tokenized lyric ids for alignment slicing.
            vocal_language (str): Language tag used to parse lyric header tokens.
            inference_steps (int): Positive diffusion step count for ``t_last``.
            seed (int): Noise seed used for deterministic score sampling.
            custom_layers_config (Optional[Dict[int, List[int]]]): Optional attention layer/head map.

        Returns:
            Dict[str, Any]: Score payload with ``lm_score``, ``dit_score``, ``success``, and ``error``.

        Raises:
            Exception: Unexpected runtime failures are re-raised after logging.
        """
        if self.model is None:
            return self._lyric_score_error("Model not initialized")

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
                raise ValueError(
                    f"inference_steps must be a positive non-zero integer, got {inference_steps!r}"
                )

            x0 = self._sample_noise_like(pred_latent, seed)
            t_last_val = 1.0 / inference_steps

            xt_lm = x0
            xt_dit = t_last_val * x0 + (1.0 - t_last_val) * pred_latent
            xt_in = torch.cat([xt_lm, xt_dit], dim=0)
            t_in = torch.cat(
                [
                    torch.tensor([1.0] * bsz, device=pred_latent.device, dtype=pred_latent.dtype),
                    torch.tensor([t_last_val] * bsz, device=pred_latent.device, dtype=pred_latent.dtype),
                ],
                dim=0,
            )
            encoder_hidden_states_in = torch.cat([encoder_hidden_states, encoder_hidden_states], dim=0)
            encoder_attention_mask_in = torch.cat([encoder_attention_mask, encoder_attention_mask], dim=0)
            context_latents_in = torch.cat([context_latents, context_latents], dim=0)
            attention_mask_in = torch.ones(
                2 * bsz,
                xt_in.shape[1],
                device=pred_latent.device,
                dtype=pred_latent.dtype,
            )

            with self._load_model_context("model"):
                decoder = self.model.decoder
                if hasattr(decoder, "eval"):
                    decoder.eval()
                decoder_outputs = decoder(
                    hidden_states=xt_in,
                    timestep=t_in,
                    timestep_r=t_in,
                    attention_mask=attention_mask_in,
                    encoder_hidden_states=encoder_hidden_states_in,
                    use_cache=False,
                    past_key_values=None,
                    encoder_attention_mask=encoder_attention_mask_in,
                    context_latents=context_latents_in,
                    output_attentions=True,
                    custom_layers_config=custom_layers_config,
                    enable_early_exit=True,
                )

            if decoder_outputs[2] is None:
                return self._lyric_score_error("Model did not return attentions")

            captured_layers = []
            for layer_attn in decoder_outputs[2]:
                if layer_attn is None:
                    continue
                captured_layers.append(layer_attn.transpose(-1, -2))
            if not captured_layers:
                return self._lyric_score_error("No valid attention layers returned")

            stacked = torch.stack(captured_layers)
            all_layers_matrix_lm = stacked[:, :bsz, ...]
            all_layers_matrix_dit = stacked[:, bsz:, ...]
            if bsz == 1:
                all_layers_matrix_lm = all_layers_matrix_lm.squeeze(1)
                all_layers_matrix_dit = all_layers_matrix_dit.squeeze(1)

            _, pure_lyric_ids, start_idx, end_idx = self._extract_lyric_segment(
                lyric_token_ids=lyric_token_ids,
                vocal_language=vocal_language,
            )
            if start_idx >= all_layers_matrix_lm.shape[-2]:
                return self._lyric_score_error("Lyrics indices out of bounds")

            pure_matrix_lm = all_layers_matrix_lm[..., start_idx:end_idx, :]
            pure_matrix_dit = all_layers_matrix_dit[..., start_idx:end_idx, :]

            from acestep.dit_alignment_score import MusicLyricScorer

            aligner = MusicLyricScorer(self.text_tokenizer)
            lm_score = self._calculate_single_lyric_score(
                aligner=aligner,
                matrix=pure_matrix_lm,
                pure_lyric_ids=pure_lyric_ids,
                custom_layers_config=custom_layers_config,
            )
            dit_score = self._calculate_single_lyric_score(
                aligner=aligner,
                matrix=pure_matrix_dit,
                pure_lyric_ids=pure_lyric_ids,
                custom_layers_config=custom_layers_config,
            )
            return {
                "lm_score": lm_score,
                "dit_score": dit_score,
                "success": True,
                "error": None,
            }
        except (ValueError, KeyError, RuntimeError, OSError) as exc:
            logger.exception("[get_lyric_score] Failed")
            return self._lyric_score_error(f"Error generating score: {exc}")
        except Exception:
            logger.exception("[get_lyric_score] Unexpected failure")
            raise

    def _calculate_single_lyric_score(
        self,
        aligner: Any,
        matrix: torch.Tensor,
        pure_lyric_ids: List[int],
        custom_layers_config: Dict[int, List[int]],
    ) -> float:
        """Run one alignment-score evaluation against one attention matrix."""
        info = aligner.lyrics_alignment_info(
            attention_matrix=matrix,
            token_ids=pure_lyric_ids,
            custom_config=custom_layers_config,
            return_matrices=False,
            medfilt_width=1,
        )
        if info.get("energy_matrix") is None:
            return 0.0
        res = aligner.calculate_score(
            energy_matrix=info["energy_matrix"],
            type_mask=info["type_mask"],
            path_coords=info["path_coords"],
        )
        return float(res.get("lyrics_score", res.get("final_score", 0.0)))
