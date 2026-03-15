"""Chunk-mask and source-latent helpers for batch conditioning."""

from typing import Dict, List, Optional, Tuple

import torch

# Phrase unique to lego task instructions — used to detect lego items from instruction text.
# Matches both TASK_INSTRUCTIONS["lego"] and TASK_INSTRUCTIONS["lego_default"].
_LEGO_INSTRUCTION_MARKER = "based on the audio context"


class ConditioningMaskMixin:
    """Mixin containing repaint mask/span and source-latent builders.

    Depends on host members:
    - Attributes: ``device``, ``sample_rate``.
    """

    def _build_chunk_masks_and_src_latents(
        self,
        batch_size: int,
        max_latent_length: int,
        instructions: List[str],
        audio_code_hints: List[Optional[str]],
        target_wavs: torch.Tensor,
        target_latents: torch.Tensor,
        repainting_start: Optional[List[float]],
        repainting_end: Optional[List[float]],
        silence_latent_tiled: torch.Tensor,
        chunk_mask_modes: Optional[List[str]] = None,
    ) -> Tuple[
        torch.Tensor,
        List[Tuple[str, int, int]],
        torch.Tensor,
        torch.Tensor,
        Optional[torch.Tensor],
    ]:
        """Create chunk masks/spans, source latents, and repaint injection mask.

        Returns:
            Tuple of (chunk_masks, spans, is_covers, src_latents, repaint_mask).
            ``repaint_mask`` is a boolean ``[B, T]`` tensor (True = generate,
            False = preserve source) when any item uses repainting, else ``None``.
        """
        chunk_masks = []
        spans = []
        is_covers = []
        repainting_ranges: Dict[int, Tuple[int, int]] = {}

        for i in range(batch_size):
            has_code_hint = audio_code_hints[i] is not None
            if repainting_start is not None and repainting_end is not None:
                start_sec = repainting_start[i] if repainting_start[i] is not None else 0.0
                end_sec = repainting_end[i]
                if end_sec is not None and end_sec > start_sec:
                    left_padding_sec = max(0, -start_sec)
                    adjusted_start_sec = start_sec + left_padding_sec
                    adjusted_end_sec = end_sec + left_padding_sec
                    start_latent = int(adjusted_start_sec * self.sample_rate // 1920)
                    end_latent = int(adjusted_end_sec * self.sample_rate // 1920)
                    start_latent = max(0, min(start_latent, max_latent_length - 1))
                    end_latent = max(start_latent + 1, min(end_latent, max_latent_length))

                    mask = torch.zeros(max_latent_length, dtype=torch.bool, device=self.device)
                    mask[start_latent:end_latent] = True
                    chunk_masks.append(mask)
                    spans.append(("repainting", start_latent, end_latent))
                    repainting_ranges[i] = (start_latent, end_latent)
                    is_covers.append(False)
                    continue

            chunk_masks.append(torch.ones(max_latent_length, dtype=torch.bool, device=self.device))
            spans.append(("full", 0, max_latent_length))
            instruction_i = instructions[i] if instructions and i < len(instructions) else ""
            instruction_lower = instruction_i.lower()
            is_cover = (
                "generate audio semantic tokens" in instruction_lower
                and "based on the given conditions" in instruction_lower
            ) or has_code_hint
            is_covers.append(is_cover)

        chunk_masks_tensor = torch.stack(chunk_masks)
        if chunk_mask_modes:
            for i, mode in enumerate(chunk_mask_modes):
                if mode == "auto":
                    chunk_masks_tensor[i] = 2.0
        is_covers_tensor = torch.BoolTensor(is_covers).to(self.device)

        src_latents_list = []
        for i in range(batch_size):
            has_code_hint = audio_code_hints[i] is not None
            has_target_audio = has_code_hint or (target_wavs is not None and target_wavs[i].abs().sum() > 1e-6)
            if has_target_audio:
                if i in repainting_ranges:
                    src_latent = target_latents[i].clone()
                    start_latent, end_latent = repainting_ranges[i]
                    instruction_i = instructions[i] if instructions and i < len(instructions) else ""
                    is_lego = _LEGO_INSTRUCTION_MARKER in instruction_i.lower()
                    if not is_lego:
                        src_latent[start_latent:end_latent] = silence_latent_tiled[start_latent:end_latent]
                    src_latents_list.append(src_latent)
                else:
                    src_latents_list.append(target_latents[i].clone())
            else:
                src_latents_list.append(silence_latent_tiled.clone())
        src_latents = torch.stack(src_latents_list)

        repaint_mask: Optional[torch.Tensor] = None
        if repainting_ranges:
            repaint_mask = torch.ones(
                batch_size, max_latent_length, dtype=torch.bool, device=self.device,
            )
            for i, (start_latent, end_latent) in repainting_ranges.items():
                repaint_mask[i] = False
                repaint_mask[i, start_latent:end_latent] = True

        return chunk_masks_tensor, spans, is_covers_tensor, src_latents, repaint_mask
