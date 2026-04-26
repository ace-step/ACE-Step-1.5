"""Shared helpers for lyric alignment and scoring mixins."""

from typing import Any, Dict, List, Optional, Sequence, Tuple

import torch
from loguru import logger

# Default lyric alignment attention layers config for the 2B DiT model.
# XL (4B) models MUST provide ``lyric_alignment_layers_config`` in their
# config.json — this default will produce incorrect alignment for XL
# because XL has 32 layers / 32 heads vs 24 layers / 16 heads in 2B.
_DEFAULT_LAYERS_CONFIG: Dict[int, List[int]] = {2: [6], 3: [10, 11], 4: [3], 5: [8, 9], 6: [8]}


class LyricAlignmentCommonMixin:
    """Provide shared data preparation helpers for lyric alignment methods."""

    def _sync_alignment_config(self) -> None:
        """Load lyric alignment layers config from model config if available.

        Called after ``self.config`` is set during model initialization.
        The model's ``lyric_alignment_layers_config`` (stored as
        ``{"layer_idx": [head_indices]}`` with string keys in JSON) takes
        precedence over the built-in 2B default.  When the field is absent
        or invalid the default is always restored so that re-initialization
        with a different model never leaves stale values behind.
        """
        raw = getattr(self.config, "lyric_alignment_layers_config", None) if self.config else None
        if not raw or not isinstance(raw, dict):
            if raw is not None:
                logger.warning(
                    "[lyric_alignment] Ignoring invalid lyric_alignment_layers_config "
                    "type: {}", type(raw).__name__,
                )
            self.custom_layers_config = dict(_DEFAULT_LAYERS_CONFIG)
            return
        # HuggingFace config JSON serializes dict keys as strings — convert to int.
        try:
            self.custom_layers_config = {int(k): [int(h) for h in v] for k, v in raw.items()}
        except (TypeError, ValueError) as exc:
            logger.warning(
                "[lyric_alignment] Ignoring malformed lyric_alignment_layers_config: {}", exc,
            )
            self.custom_layers_config = dict(_DEFAULT_LAYERS_CONFIG)

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
