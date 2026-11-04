"""Backend tests for ``task_type="extract"`` in service diffusion execution.

Covers two things:
- Routing: extract/lego/complete run on the PyTorch DiT (with a warning) even
  when MLX DiT is available; other tasks still use MLX.
- Parity: when the MLX branch runs on an extract-shaped payload it receives the
  same conditioning (source latents, full chunk mask, ``is_covers=False``) and
  CFG guidance inputs as the PyTorch ``generate_audio`` path.
"""

import unittest
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import torch

from acestep.core.generation.handler.mlx_dit_task_routing import logger as routing_logger
from acestep.core.generation.handler.mlx_dit_task_routing import should_use_mlx_dit
from acestep.core.generation.handler.service_generate_execute import ServiceGenerateExecuteMixin

_B, _T, _C, _ENC_L, _D = 1, 6, 4, 3, 8


class _Host(ServiceGenerateExecuteMixin):
    """Minimal host with mocked PyTorch model and MLX runner."""

    def __init__(self, use_mlx: bool):
        """Build mocks for the heavy model and the MLX diffusion runner."""
        self.device = "cpu"
        self.config = MagicMock(is_turbo=False)
        self.silence_latent = torch.zeros(1, _T, _C)
        self.use_mlx_dit = use_mlx
        self.mlx_decoder = object() if use_mlx else None
        self.context_latents = torch.randn(_B, _T, 2 * _C)
        self.encoder_hidden_states = torch.randn(_B, _ENC_L, _D)
        self.model = MagicMock()
        self.model.null_condition_emb = torch.randn(1, 1, _D)
        self.model.prepare_condition.return_value = (
            self.encoder_hidden_states, torch.ones(_B, _ENC_L), self.context_latents,
        )
        self.model.generate_audio.return_value = {"target_latents": torch.zeros(_B, _T, _C)}
        self._mlx_run_diffusion = MagicMock(
            return_value={"target_latents": torch.zeros(_B, _T, _C), "time_costs": {}}
        )

    def _load_model_context(self, _name):
        """Return a no-op model-loading context."""
        return nullcontext()


def _extract_payload() -> dict:
    """Return an extract-shaped payload: real source latents, full chunk, no cover."""
    src = torch.randn(_B, _T, _C)
    return {
        "text_hidden_states": torch.randn(_B, 5, _D),
        "text_attention_mask": torch.ones(_B, 5),
        "lyric_hidden_states": torch.randn(_B, 2, _D),
        "lyric_attention_mask": torch.ones(_B, 2),
        "refer_audio_acoustic_hidden_states_packed": torch.zeros(1, 1, _C),
        "refer_audio_order_mask": torch.zeros(1, dtype=torch.long),
        "src_latents": src,
        "target_latents": src.clone(),
        "chunk_mask": torch.ones(_B, _T, dtype=torch.bool),
        "is_covers": torch.tensor([False]),
        "non_cover_text_hidden_states": None,
        "non_cover_text_attention_masks": None,
        "precomputed_lm_hints_25Hz": None,
        "repaint_mask": None,
    }


def _run(host: _Host, payload: dict, task_type: str = "") -> dict:
    """Build kwargs like the service does and execute diffusion."""
    kwargs = host._build_service_generate_kwargs(
        payload=payload, seed_param=777, infer_steps=50, guidance_scale=7.0,
        audio_cover_strength=1.0, cover_noise_strength=0.0, infer_method="ode",
        use_adg=False, cfg_interval_start=0.0, cfg_interval_end=1.0, shift=1.0,
        timesteps=None,
    )
    host._execute_service_generate_diffusion(
        payload=payload, generate_kwargs=kwargs, seed_param=777, infer_method="ode",
        shift=1.0, audio_cover_strength=1.0, task_type=task_type,
    )
    return kwargs


class MlxTaskRoutingTests(unittest.TestCase):
    """Tasks without MLX parity must be routed to the PyTorch DiT."""

    def test_extract_lego_complete_route_to_pytorch_with_warning(self):
        """MLX is available, but these tasks must call PyTorch generate_audio."""
        for task in ("extract", "lego", "complete"):
            with self.subTest(task=task):
                host = _Host(use_mlx=True)
                with patch.object(routing_logger, "warning") as warn:
                    _run(host, _extract_payload(), task_type=task)
                host._mlx_run_diffusion.assert_not_called()
                host.model.generate_audio.assert_called_once()
                warn.assert_called_once()
                self.assertEqual(warn.call_args.args[1], task)

    def test_other_tasks_still_use_mlx(self):
        """Non-target check: text2music/cover/cover-nofsq/repaint keep the MLX backend."""
        for task in ("text2music", "cover", "cover-nofsq", "repaint"):
            with self.subTest(task=task):
                host = _Host(use_mlx=True)
                _run(host, _extract_payload(), task_type=task)
                host._mlx_run_diffusion.assert_called_once()
                host.model.generate_audio.assert_not_called()

    def test_should_use_mlx_dit_false_when_mlx_not_ready(self):
        """No MLX decoder means PyTorch regardless of task, without a warning."""
        with patch.object(routing_logger, "warning") as warn:
            self.assertFalse(should_use_mlx_dit(False, "text2music"))
            self.assertFalse(should_use_mlx_dit(False, "extract"))
        warn.assert_not_called()


class ExtractBackendParityTests(unittest.TestCase):
    """MLX and PyTorch backends must see identical extract conditioning."""

    def test_mlx_receives_extract_conditioning_and_guidance(self):
        """MLX gets prepare_condition's outputs plus the CFG settings PyTorch uses.

        ``task_type`` is left unset so the MLX branch runs on the extract payload.
        """
        payload = _extract_payload()
        host = _Host(use_mlx=True)
        kwargs = _run(host, payload)

        host.model.generate_audio.assert_not_called()
        cond = host.model.prepare_condition.call_args.kwargs
        self.assertIs(cond["src_latents"], payload["src_latents"])
        self.assertIs(cond["chunk_masks"], payload["chunk_mask"])
        self.assertIs(cond["is_covers"], payload["is_covers"])

        mlx = host._mlx_run_diffusion.call_args.kwargs
        self.assertIs(mlx["context_latents"], host.context_latents)
        self.assertIs(mlx["encoder_hidden_states"], host.encoder_hidden_states)
        self.assertIs(mlx["null_condition_emb"], host.model.null_condition_emb)
        self.assertEqual(mlx["guidance_scale"], kwargs["diffusion_guidance_scale"])
        self.assertEqual(mlx["infer_steps"], kwargs["infer_steps"])
        self.assertEqual(mlx["cfg_interval_start"], kwargs["cfg_interval_start"])
        self.assertEqual(mlx["cfg_interval_end"], kwargs["cfg_interval_end"])
        self.assertEqual(mlx["dcw_enabled"], False)
        self.assertIsNone(mlx["repaint_mask"])
        self.assertIsNone(mlx["context_latents_non_cover"])

    def test_pytorch_receives_same_extract_inputs(self):
        """Non-target check: the PyTorch path gets the same source/chunk/cover inputs."""
        payload = _extract_payload()
        host = _Host(use_mlx=False)
        _run(host, payload, task_type="extract")

        host._mlx_run_diffusion.assert_not_called()
        gen = host.model.generate_audio.call_args.kwargs
        self.assertIs(gen["src_latents"], payload["src_latents"])
        self.assertIs(gen["chunk_masks"], payload["chunk_mask"])
        self.assertIs(gen["is_covers"], payload["is_covers"])
        self.assertEqual(gen["diffusion_guidance_scale"], 7.0)
        self.assertFalse(gen["dcw_enabled"])
        self.assertIsNone(gen["repaint_mask"])


if __name__ == "__main__":
    unittest.main()
