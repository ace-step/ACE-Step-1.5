"""Success payload builders for ``generate_music`` orchestration."""

from typing import Any, Dict

from loguru import logger


class GenerateMusicPayloadMixin:
    """Build audio/metadata payload structures returned by ``generate_music``."""

    def _build_generate_music_success_payload(
        self,
        outputs: Dict[str, Any],
        pred_wavs,
        pred_latents_cpu,
        time_costs: Dict[str, Any],
        seed_value_for_ui: int,
        actual_batch_size: int,
        progress: Any,
    ) -> Dict[str, Any]:
        """Assemble final success response from decoded tensors and model outputs.

        Args:
            outputs: Service output payload containing intermediate generation tensors.
            pred_wavs: Decoded waveform tensor shaped ``[batch, channels, samples]``.
            pred_latents_cpu: CPU latent tensor preserved for extra outputs.
            time_costs: Updated time-cost payload including decode/offload timings.
            seed_value_for_ui: Seed value displayed in UI outputs.
            actual_batch_size: Effective generation batch size.
            progress: Optional progress callback.

        Returns:
            Dict[str, Any]: Standard success payload returned by ``generate_music``.
        """
        logger.info("[generate_music] VAE decode completed. Preparing audio tensors...")
        if progress:
            progress(0.99, desc="Preparing audio data...")

        audio_tensors = []
        for index in range(actual_batch_size):
            audio_tensor = pred_wavs[index].cpu()
            audio_tensors.append(audio_tensor)

        status_message = "Generation completed successfully!"
        logger.info(f"[generate_music] Done! Generated {len(audio_tensors)} audio tensors.")

        src_latents = outputs.get("src_latents")
        target_latents_input = outputs.get("target_latents_input")
        chunk_masks = outputs.get("chunk_masks")
        spans = outputs.get("spans", [])
        latent_masks = outputs.get("latent_masks")

        encoder_hidden_states = outputs.get("encoder_hidden_states")
        encoder_attention_mask = outputs.get("encoder_attention_mask")
        context_latents = outputs.get("context_latents")
        lyric_token_idss = outputs.get("lyric_token_idss")

        extra_outputs = {
            "pred_latents": pred_latents_cpu,
            "target_latents": target_latents_input.detach().cpu() if target_latents_input is not None else None,
            "src_latents": src_latents.detach().cpu() if src_latents is not None else None,
            "chunk_masks": chunk_masks.detach().cpu() if chunk_masks is not None else None,
            "latent_masks": latent_masks.detach().cpu() if latent_masks is not None else None,
            "spans": spans,
            "time_costs": time_costs,
            "seed_value": seed_value_for_ui,
            "encoder_hidden_states": (
                encoder_hidden_states.detach().cpu()
                if encoder_hidden_states is not None
                else None
            ),
            "encoder_attention_mask": (
                encoder_attention_mask.detach().cpu()
                if encoder_attention_mask is not None
                else None
            ),
            "context_latents": context_latents.detach().cpu() if context_latents is not None else None,
            "lyric_token_idss": lyric_token_idss.detach().cpu() if lyric_token_idss is not None else None,
        }

        audios = []
        for audio_tensor in audio_tensors:
            audios.append({"tensor": audio_tensor, "sample_rate": self.sample_rate})

        return {
            "audios": audios,
            "status_message": status_message,
            "extra_outputs": extra_outputs,
            "success": True,
            "error": None,
        }
