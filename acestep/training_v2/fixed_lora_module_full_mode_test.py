"""Tests for full fine-tuning mode in FixedLoRAModule."""

from __future__ import annotations

import unittest

import torch
import torch.nn as nn

from acestep.training_v2.configs import LoRAConfigV2, TrainingConfigV2
from acestep.training_v2.fixed_lora_module import FixedLoRAModule


class _DummyModel(nn.Module):
    """Minimal ACE-Step-like model with decoder and null condition embedding."""

    def __init__(self) -> None:
        super().__init__()
        self.decoder = nn.Sequential(nn.Linear(4, 4), nn.Linear(4, 4))
        self.encoder = nn.Linear(4, 4)
        self.null_condition_emb = nn.Parameter(torch.zeros(1, 1, 4))
        self.config = type("Cfg", (), {})()


class FixedLoRAModuleFullModeTest(unittest.TestCase):
    """Verifies full-mode freezing and optimizer grouping behavior."""

    def test_full_mode_trains_decoder_only(self) -> None:
        """Only decoder parameters should remain trainable in full mode."""
        model = _DummyModel()
        cfg = TrainingConfigV2(
            dataset_dir=".",
            checkpoint_dir=".",
            output_dir=".",
            training_mode="full",
        )
        module = FixedLoRAModule(
            model=model,
            adapter_config=LoRAConfigV2(),
            training_config=cfg,
            device=torch.device("cpu"),
            dtype=torch.float32,
        )

        decoder_trainable = all(p.requires_grad for p in module.model.decoder.parameters())
        encoder_trainable = any(p.requires_grad for p in module.model.encoder.parameters())

        self.assertTrue(decoder_trainable)
        self.assertFalse(encoder_trainable)

    def test_full_mode_param_groups_include_all_trainable_params(self) -> None:
        """Param groups should cover every trainable decoder parameter once."""
        model = _DummyModel()
        cfg = TrainingConfigV2(
            dataset_dir=".",
            checkpoint_dir=".",
            output_dir=".",
            training_mode="full",
            full_lr_mult_attn=1.1,
            full_lr_mult_ffn=0.9,
            full_lr_mult_other=1.0,
        )
        module = FixedLoRAModule(
            model=model,
            adapter_config=LoRAConfigV2(),
            training_config=cfg,
            device=torch.device("cpu"),
            dtype=torch.float32,
        )

        groups = module.build_full_mode_param_groups()
        grouped = {id(p) for group in groups for p in group["params"]}
        trainable = {id(p) for p in module.model.parameters() if p.requires_grad}
        self.assertSetEqual(grouped, trainable)


if __name__ == "__main__":
    unittest.main()
