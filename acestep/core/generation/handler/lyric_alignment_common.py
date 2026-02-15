"""Shared helpers for lyric alignment and scoring mixins."""

from typing import Any, Dict, List, Optional, Sequence, Tuple

import torch


class LyricAlignmentCommonMixin:
    """Provide shared data preparation helpers for lyric alignment methods."""

    def _resolve_custom_layers_config(
        self, custom_layers_config: Optional[Dict[int, List[int]]]
    ) -> Dict[int, List[int]]:
        """Return caller config when provided, otherwise host default config."""
        if custom_layers_config is not None:
            return custom_layers_config
        return self.custom_layers_config

    def _move_alignment_inputs_to_runtime(
        self,
        pred_latent: torch.Tensor,
        encoder_hidden_states: torch.Tensor,
        encoder_attention_mask: torch.Tensor,
        context_latents: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Move alignment tensors to the handler runtime device and dtype."""
        device = self.device
        dtype = self.dtype
        return (
            pred_latent.to(device=device, dtype=dtype),
            encoder_hidden_states.to(device=device, dtype=dtype),
            encoder_attention_mask.to(device=device, dtype=dtype),
            context_latents.to(device=device, dtype=dtype),
        )

    def _sample_noise_like(self, reference: torch.Tensor, seed: Optional[int]) -> torch.Tensor:
        """Sample deterministic noise for a tensor shape, including MPS-safe seeding."""
        if seed is None:
            return torch.randn_like(reference)

        device = reference.device
        dtype = reference.dtype
        is_mps = (isinstance(device, str) and device == "mps") or (
            hasattr(device, "type") and device.type == "mps"
        )
        gen_device = "cpu" if is_mps else device
        generator = torch.Generator(device=gen_device).manual_seed(int(seed))
        return torch.randn(reference.shape, generator=generator, device=gen_device, dtype=dtype).to(device)

    def _extract_lyric_segment(
        self,
        lyric_token_ids: torch.Tensor,
        vocal_language: str,
    ) -> Tuple[Sequence[int], List[int], int, int]:
        """Split token ids into header and lyric ranges."""
        raw_lyric_ids: Sequence[int]
        if isinstance(lyric_token_ids, torch.Tensor):
            raw_lyric_ids = lyric_token_ids[0].tolist()
        else:
            raw_lyric_ids = lyric_token_ids

        header_str = f"# Languages\n{vocal_language}\n\n# Lyric\n"
        header_ids = self.text_tokenizer.encode(header_str, add_special_tokens=False)
        start_idx = len(header_ids)
        try:
            end_idx = raw_lyric_ids.index(151643)  # <|endoftext|>
        except ValueError:
            end_idx = len(raw_lyric_ids)

        pure_lyric_ids = list(raw_lyric_ids[start_idx:end_idx])
        return raw_lyric_ids, pure_lyric_ids, start_idx, end_idx

    def _lyric_timestamp_error(self, message: str) -> Dict[str, Any]:
        """Build the standard timestamp error payload."""
        return {
            "lrc_text": "",
            "sentence_timestamps": [],
            "token_timestamps": [],
            "success": False,
            "error": message,
        }

    def _lyric_score_error(self, message: str) -> Dict[str, Any]:
        """Build the standard lyric-score error payload."""
        return {
            "lm_score": 0.0,
            "dit_score": 0.0,
            "success": False,
            "error": message,
        }
