"""Output assembly helpers for service generation."""

from typing import Any, Dict

import torch


class ServiceGenerateOutputsMixin:
    """Attach service-generation intermediates required by downstream flows."""

    def _attach_service_generate_outputs(
        self,
        outputs: Dict[str, Any],
        payload: Dict[str, Any],
        batch: Dict[str, Any],
        encoder_hidden_states: torch.Tensor,
        encoder_attention_mask: torch.Tensor,
        context_latents: torch.Tensor,
    ) -> Dict[str, Any]:
        """Attach intermediate tensors required by downstream consumers."""
        outputs["src_latents"] = payload["src_latents"]
        outputs["target_latents_input"] = payload["target_latents"]
        outputs["chunk_masks"] = payload["chunk_mask"]
        outputs["spans"] = payload["spans"]
        outputs["latent_masks"] = batch.get("latent_masks")
        outputs["encoder_hidden_states"] = encoder_hidden_states
        outputs["encoder_attention_mask"] = encoder_attention_mask
        outputs["context_latents"] = context_latents
        outputs["lyric_token_idss"] = payload["lyric_token_idss"]
        return outputs
