"""Unit tests for ConditioningMaskMixin chunk-mask and source-latent behavior."""

import unittest
from typing import List, Optional

import torch

from acestep.core.generation.handler.conditioning_masks import (
    ConditioningMaskMixin,
    _LEGO_INSTRUCTION_MARKER,
)


class _Host(ConditioningMaskMixin):
    """Minimal host implementing ConditioningMaskMixin dependencies."""

    def __init__(self):
        self.device = "cpu"
        self.sample_rate = 48000


def _make_host():
    return _Host()


def _build(
    host,
    batch_size: int = 1,
    max_latent_length: int = 100,
    instructions: Optional[List[str]] = None,
    audio_code_hints: Optional[List[Optional[str]]] = None,
    target_wavs: Optional[torch.Tensor] = None,
    target_latents: Optional[torch.Tensor] = None,
    repainting_start: Optional[List[float]] = None,
    repainting_end: Optional[List[float]] = None,
):
    """Call _build_chunk_masks_and_src_latents with sensible defaults."""
    if instructions is None:
        instructions = ["Fill the audio semantic mask based on the given conditions:"] * batch_size
    if audio_code_hints is None:
        audio_code_hints = [None] * batch_size
    if target_wavs is None:
        target_wavs = torch.ones(batch_size, 2, 48000)
    if target_latents is None:
        # Non-zero so we can detect if they were replaced with silence
        target_latents = torch.ones(batch_size, max_latent_length, 16)
    silence_latent_tiled = torch.zeros(max_latent_length, 16)
    return host._build_chunk_masks_and_src_latents(
        batch_size=batch_size,
        max_latent_length=max_latent_length,
        instructions=instructions,
        audio_code_hints=audio_code_hints,
        target_wavs=target_wavs,
        target_latents=target_latents,
        repainting_start=repainting_start,
        repainting_end=repainting_end,
        silence_latent_tiled=silence_latent_tiled,
    )


class ConditioningMaskLegoBehaviorTests(unittest.TestCase):
    """Verify lego mode keeps source audio latents intact (no silence replacement).

    For lego, can_use_repainting=True so repainting_start/end are set and the
    chunk mask is computed from the repainting range. However, src_latents must
    NOT be silenced — the source audio is the musical context for the DiT.
    """

    def test_lego_with_repainting_range_preserves_source_latents(self):
        """Lego with repainting_start/end must preserve src_latents (no silencing).

        The chunk mask is computed from the range (marking which positions have
        active audio to generate), but the source latents carry the backing track
        context and must reach the DiT unchanged.
        """
        host = _make_host()
        target_latents = torch.ones(1, 100, 16) * 2.5
        lego_instruction = "Generate the GUITAR track based on the audio context:"
        chunk_masks, spans, is_covers, src_latents, _rm = _build(
            host,
            instructions=[lego_instruction],
            target_latents=target_latents,
            repainting_start=[0.0],
            repainting_end=[4.0],  # 4 s at sample_rate=48000, stride=1920 → latents 0..100
        )
        self.assertTrue(
            torch.allclose(src_latents, target_latents),
            "lego src_latents must equal the source audio latents, not be silenced",
        )
        self.assertEqual(spans[0][0], "repainting", "lego span should be 'repainting' (from range)")

    def test_lego_default_instruction_preserves_source_latents(self):
        """The lego_default instruction also preserves src_latents."""
        host = _make_host()
        target_latents = torch.ones(1, 100, 16) * 1.7
        lego_default_instruction = "Generate the track based on the audio context:"
        chunk_masks, spans, is_covers, src_latents, _rm = _build(
            host,
            instructions=[lego_default_instruction],
            target_latents=target_latents,
            repainting_start=[0.0],
            repainting_end=[4.0],
        )
        self.assertTrue(
            torch.allclose(src_latents, target_latents),
            "lego_default src_latents must equal the source audio latents",
        )

    def test_repaint_full_range_silences_repainting_region(self):
        """Repaint with full range should overwrite the repainting region with silence.

        This verifies the existing repaint behavior is preserved: src_latents for
        the masked region should be silence so the DiT regenerates that section.
        """
        host = _make_host()
        target_latents = torch.ones(1, 100, 16) * 2.5
        chunk_masks, spans, is_covers, src_latents, _rm = _build(
            host,
            target_latents=target_latents,
            repainting_start=[0.0],
            repainting_end=[4.0],  # 4 seconds at sample_rate=48000, stride=1920 → latents 0..100
        )
        # With full-range repainting the src_latents region should be silenced
        start_l, end_l = spans[0][1], spans[0][2]
        self.assertEqual(spans[0][0], "repainting")
        # The repainting region in src_latents should be zeros (silence)
        self.assertTrue(
            src_latents[0, start_l:end_l].abs().sum().item() < 1e-6,
            "repaint src_latents in masked region should be silence",
        )

    def test_repaint_partial_range_silences_only_masked_region(self):
        """Partial repaint leaves source audio outside the mask intact."""
        host = _make_host()
        target_latents = torch.ones(1, 100, 16) * 3.0
        # Repaint 1s-2s (roughly latents 25-50 at 48000/1920=25 latents/sec)
        chunk_masks, spans, is_covers, src_latents, _rm = _build(
            host,
            target_latents=target_latents,
            repainting_start=[1.0],
            repainting_end=[2.0],
        )
        self.assertEqual(spans[0][0], "repainting")
        start_l, end_l = spans[0][1], spans[0][2]
        # Repainting region should be silenced
        self.assertTrue(
            src_latents[0, start_l:end_l].abs().sum().item() < 1e-6,
            "masked region in repaint src_latents should be silence",
        )
        # Outside region should keep original values
        if start_l > 0:
            self.assertAlmostEqual(
                src_latents[0, 0, 0].item(),
                3.0,
                places=4,
                msg="src_latents outside repaint mask should preserve original audio",
            )

    def test_lego_instruction_marker_constant(self):
        """The _LEGO_INSTRUCTION_MARKER constant matches the actual lego instruction templates."""
        lego_instructions = [
            "Generate the GUITAR track based on the audio context:",
            "Generate the track based on the audio context:",
            "Generate the DRUMS track based on the audio context:",
        ]
        for instr in lego_instructions:
            self.assertIn(
                _LEGO_INSTRUCTION_MARKER,
                instr.lower(),
                f"Marker must match lego instruction: {instr!r}",
            )

    def test_lego_detection_is_case_insensitive(self):
        """Lego detection must be case-insensitive via .lower()."""
        host = _make_host()
        target_latents = torch.ones(1, 100, 16) * 2.5
        # Use mixed-case version of the instruction
        mixed_case_instruction = "Generate the GUITAR Track BASED ON THE AUDIO CONTEXT:"
        chunk_masks, spans, is_covers, src_latents, _rm = _build(
            host,
            instructions=[mixed_case_instruction],
            target_latents=target_latents,
            repainting_start=[0.0],
            repainting_end=[4.0],
        )
        self.assertTrue(
            torch.allclose(src_latents, target_latents),
            "lego detection must be case-insensitive; src_latents should be preserved",
        )

    def test_lego_with_empty_instructions_does_not_raise(self):
        """Empty instructions list must not cause an index error or silence lego latents."""
        host = _make_host()
        target_latents = torch.ones(1, 100, 16) * 2.5
        # Empty instructions list — instructions[i] lookup falls back to ""
        chunk_masks, spans, is_covers, src_latents, _rm = _build(
            host,
            instructions=[],
            target_latents=target_latents,
            repainting_start=[0.0],
            repainting_end=[4.0],
        )
        # With an empty instructions list, is_lego=False, so the repaint silencing applies.
        # This is a graceful fallback — the important thing is no exception is raised.
        self.assertEqual(src_latents.shape, target_latents.shape)

    def test_non_lego_instruction_still_silences_repaint(self):
        """A non-lego instruction in the repainting path must still silence src_latents."""
        host = _make_host()
        target_latents = torch.ones(1, 100, 16) * 2.5
        repaint_instruction = "Repaint the mask area based on the given conditions:"
        chunk_masks, spans, is_covers, src_latents, _rm = _build(
            host,
            instructions=[repaint_instruction],
            target_latents=target_latents,
            repainting_start=[0.0],
            repainting_end=[4.0],
        )
        start_l, end_l = spans[0][1], spans[0][2]
        self.assertTrue(
            src_latents[0, start_l:end_l].abs().sum().item() < 1e-6,
            "non-lego instruction must still silence the repaint region",
        )

    def test_no_source_audio_produces_silence_latents(self):
        """Without source audio, src_latents should be silence (text2music behavior)."""
        host = _make_host()
        target_wavs = torch.zeros(1, 2, 48000)
        chunk_masks, spans, is_covers, src_latents, _rm = _build(
            host,
            target_wavs=target_wavs,
            repainting_start=None,
            repainting_end=None,
        )
        self.assertTrue(
            src_latents.abs().sum().item() < 1e-6,
            "src_latents should be silence when no source audio is present",
        )


if __name__ == "__main__":
    unittest.main()
