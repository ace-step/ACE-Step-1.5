"""Regression tests for cover-noise-strength forwarding in generation."""

import contextlib
import types
import unittest
from unittest.mock import MagicMock, Mock

import torch

try:
    from acestep.handler import AceStepHandler
except ModuleNotFoundError:
    AceStepHandler = None


@unittest.skipIf(AceStepHandler is None, "AceStepHandler dependencies are unavailable in this test environment.")
class CoverNoiseStrengthForwardingTests(unittest.TestCase):
    """Verify `cover_noise_strength` survives the service-generation flow."""

    def test_service_generate_forwards_cover_noise_strength(self) -> None:
        """Preserve cover strength forwarding to the PyTorch backend."""
        self._assert_cover_noise_strength_forwarded(use_mlx_dit=False)

    def test_service_generate_forwards_cover_noise_strength_to_mlx(self) -> None:
        """Forward cover strength to MLX without silently falling back to PyTorch."""
        self._assert_cover_noise_strength_forwarded(use_mlx_dit=True)

    def _assert_cover_noise_strength_forwarded(self, use_mlx_dit: bool) -> None:
        """Check the selected backend receives the service's cover strength."""
        handler = AceStepHandler.__new__(AceStepHandler)

        handler.config = types.SimpleNamespace(is_turbo=False)
        handler.device = "cpu"
        handler.dtype = torch.float32
        handler.use_mlx_dit = use_mlx_dit
        handler.mlx_decoder = object() if use_mlx_dit else None
        handler.silence_latent = torch.zeros(1, 16, 4, dtype=torch.float32)

        handler._normalize_instructions = lambda instructions, _batch, _default: instructions
        handler._normalize_audio_code_hints = lambda hints, _batch: hints
        handler._ensure_silence_latent_on_device = lambda: None
        handler._load_model_context = lambda _name: contextlib.nullcontext()

        prepare_batch_mock = Mock(return_value={"latent_masks": torch.ones(1, 4, dtype=torch.long)})
        handler._prepare_batch = prepare_batch_mock

        src_latents = torch.zeros(1, 4, 4, dtype=torch.float32)
        tensor_2d = torch.ones(1, 4, dtype=torch.float32)
        bool_mask = torch.ones(1, 4, dtype=torch.bool)
        handler.preprocess_batch = Mock(
            return_value=(
                ["k1"],
                ["text"],
                src_latents,
                src_latents.clone(),
                tensor_2d.clone(),
                bool_mask.clone(),
                tensor_2d.clone(),
                bool_mask.clone(),
                bool_mask.clone(),
                tensor_2d.clone(),
                torch.tensor([0], dtype=torch.long),
                bool_mask.clone(),
                [("full", 0, 4)],
                torch.tensor([True]),
                None,
                torch.ones(1, 2, dtype=torch.long),
                None,
                None,
                None,
                None,
            )
        )

        model = Mock()
        model.prepare_condition = Mock(
            return_value=(tensor_2d.clone(), bool_mask.clone(), tensor_2d.clone())
        )
        model.generate_audio = Mock(return_value={"target_latents": src_latents.clone()})
        handler.model = model
        handler._mlx_run_diffusion = MagicMock(
            return_value={"target_latents": src_latents.clone()}
        )

        cover_noise_strength = 0.42
        handler.service_generate(
            captions="caption",
            lyrics="lyrics",
            cover_noise_strength=cover_noise_strength,
            target_wavs=torch.zeros(1, 2, 1920, dtype=torch.float32),
            refer_audios=[[torch.zeros(2, 1920, dtype=torch.float32)]],
        )

        self.assertEqual(
            prepare_batch_mock.call_args.kwargs.get("cover_noise_strength"),
            cover_noise_strength,
        )
        generate = handler._mlx_run_diffusion if use_mlx_dit else model.generate_audio
        unused = model.generate_audio if use_mlx_dit else handler._mlx_run_diffusion
        generate.assert_called_once()
        unused.assert_not_called()
        self.assertEqual(generate.call_args.kwargs["cover_noise_strength"], cover_noise_strength)
        self.assertIs(generate.call_args.kwargs["src_latents"], src_latents)


if __name__ == "__main__":
    unittest.main()
