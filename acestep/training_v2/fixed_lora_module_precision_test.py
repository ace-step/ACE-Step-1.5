"""Unit tests for training_v2 precision selection."""

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch
import torch.nn as nn

from acestep.training_v2.fixed_lora_module import (
    FixedLoRAModule,
    _select_compute_dtype,
    _select_fabric_precision,
)


class TestPrecisionSelection(unittest.TestCase):
    """Tests for compute dtype and Fabric precision mapping."""

    def test_explicit_fp32_on_mps_selects_true_fp32(self) -> None:
        """MPS honors explicit fp32 instead of falling back to mixed precision."""
        self.assertEqual(_select_compute_dtype("mps", "fp32"), torch.float32)
        self.assertEqual(_select_fabric_precision("mps", "fp32"), "32-true")

    def test_explicit_fp16_on_mps_selects_mixed_fp16(self) -> None:
        """MPS honors explicit fp16 mixed precision."""
        self.assertEqual(_select_compute_dtype("mps", "fp16"), torch.float16)
        self.assertEqual(_select_fabric_precision("mps", "fp16"), "16-mixed")

    def test_explicit_bf16_selects_mixed_bf16(self) -> None:
        """Accelerator devices honor explicit bf16 mixed precision."""
        for device_type in ("cuda", "xpu", "mps", "cpu"):
            with self.subTest(device_type=device_type):
                self.assertEqual(
                    _select_compute_dtype(device_type, "bf16"),
                    torch.bfloat16,
                )
                self.assertEqual(
                    _select_fabric_precision(device_type, "bf16"),
                    "bf16-mixed",
                )

    def test_auto_preserves_device_defaults(self) -> None:
        """Auto precision keeps the existing per-device defaults."""
        expected = {
            "cuda": (torch.bfloat16, "bf16-mixed"),
            "xpu": (torch.bfloat16, "bf16-mixed"),
            "mps": (torch.float16, "16-mixed"),
            "cpu": (torch.float32, "32-true"),
        }

        for device_type, (dtype, fabric_precision) in expected.items():
            with self.subTest(device_type=device_type):
                self.assertEqual(_select_compute_dtype(device_type), dtype)
                self.assertEqual(_select_fabric_precision(device_type), fabric_precision)

    def test_invalid_precision_raises(self) -> None:
        """Unsupported precision tokens fail instead of using device defaults."""
        with self.assertRaises(ValueError):
            _select_compute_dtype("mps", "fp64")
        with self.assertRaises(ValueError):
            _select_fabric_precision("mps", "fp64")


class _DummyModel(nn.Module):
    """Minimal model stand-in for FixedLoRAModule construction."""

    def __init__(self) -> None:
        super().__init__()
        self.config = SimpleNamespace()


class _ZeroDecoder(nn.Module):
    """Decoder stand-in that returns a tensor compatible with flow loss."""

    def forward(self, hidden_states: torch.Tensor, **_: torch.Tensor) -> tuple[torch.Tensor]:
        """Return a zero prediction with the same shape as hidden states."""
        return (torch.zeros_like(hidden_states),)


class TestFixedLoRAModulePrecision(unittest.TestCase):
    """Tests for dtype usage inside FixedLoRAModule."""

    def test_init_uses_selected_dtype(self) -> None:
        """Constructor keeps the dtype selected by the trainer."""
        training_config = SimpleNamespace(
            adapter_type="lora",
            cfg_ratio=0.0,
            data_proportion=1.0,
            timestep_mu=0.0,
            timestep_sigma=1.0,
        )

        def inject_lora(module: FixedLoRAModule, model: nn.Module, _: object) -> None:
            """Skip real adapter injection and attach the dummy model."""
            module.model = model
            module.adapter_info = {}

        with patch.object(FixedLoRAModule, "_inject_lora", inject_lora):
            module = FixedLoRAModule(
                model=_DummyModel(),
                adapter_config=SimpleNamespace(),
                training_config=training_config,
                device=torch.device("mps"),
                dtype=torch.float32,
            )

        self.assertEqual(module.dtype, torch.float32)

    def test_training_step_skips_autocast_for_fp32(self) -> None:
        """fp32 training avoids autocast even on an MPS device type."""
        module = FixedLoRAModule.__new__(FixedLoRAModule)
        nn.Module.__init__(module)
        module.device = torch.device("cpu")
        module.device_type = "mps"
        module.dtype = torch.float32
        module.transfer_non_blocking = False
        module.model = SimpleNamespace(decoder=_ZeroDecoder())
        module._null_cond_emb = None
        module._cfg_ratio = 0.0
        module._data_proportion = 1.0
        module._timestep_mu = 0.0
        module._timestep_sigma = 1.0
        module.force_input_grads_for_checkpointing = False
        module.training_losses = []

        batch = {
            "target_latents": torch.ones(2, 3, 4),
            "attention_mask": torch.ones(2, 3, 4),
            "encoder_hidden_states": torch.ones(2, 3, 4),
            "encoder_attention_mask": torch.ones(2, 3, 4),
            "context_latents": torch.ones(2, 3, 4),
        }

        with patch("torch.autocast") as autocast:
            loss = module.training_step(batch)

        autocast.assert_not_called()
        self.assertEqual(loss.dtype, torch.float32)


class TestTrainerPrecisionThreading(unittest.TestCase):
    """Source-inspection tests for FixedLoRATrainer precision wiring."""

    def _call_arg_sources(self, function_name: str) -> list[list[str]]:
        """Return source text for positional args passed to the named helper."""
        source_path = Path(__file__).with_name("trainer_fixed.py")
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls: list[list[str]] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != function_name:
                continue
            calls.append([
                ast.get_source_segment(source, arg) or ""
                for arg in node.args
            ])

        return calls

    def test_train_passes_config_precision_to_compute_dtype(self) -> None:
        """Trainer threads cfg.precision into compute dtype selection."""
        calls = self._call_arg_sources("_select_compute_dtype")
        self.assertIn('getattr(cfg, "precision", "auto")', calls[0])

    def test_train_fabric_passes_config_precision_to_fabric_precision(self) -> None:
        """Fabric setup threads cfg.precision into precision selection."""
        calls = self._call_arg_sources("_select_fabric_precision")
        self.assertIn('getattr(cfg, "precision", "auto")', calls[0])


if __name__ == "__main__":
    unittest.main()
