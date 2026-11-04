"""Tests for acestep.training_v2.adapter_resume.load_adapter_state_dict.

Uses a tiny real PEFT LoRA model so the key naming of ``save_pretrained``
(adapter name stripped) is exercised exactly as in a Side-Step checkpoint.
"""

import os
import tempfile
import unittest

try:
    import torch
    import torch.nn as nn
    from peft import LoraConfig, get_peft_model
    from safetensors.torch import load_file

    _HAS_DEPS = True
except ImportError:  # pragma: no cover - depends on the environment
    _HAS_DEPS = False

from acestep.training_v2.adapter_resume import AdapterResumeError, load_adapter_state_dict


def _make_peft_model(seed: int) -> "nn.Module":
    """Return a small PEFT LoRA model with non-zero, seed-dependent adapter weights."""

    class Block(nn.Module):
        """Minimal block with attention- and MLP-like projections."""

        def __init__(self) -> None:
            super().__init__()
            self.q_proj = nn.Linear(8, 8)
            self.gate_proj = nn.Linear(8, 8)

        def forward(self, x):
            return self.gate_proj(self.q_proj(x))

    torch.manual_seed(0)
    model = get_peft_model(
        Block(), LoraConfig(r=4, lora_alpha=8, target_modules=["q_proj", "gate_proj"])
    )
    torch.manual_seed(seed)
    for name, param in model.named_parameters():
        if "lora_" in name:
            nn.init.normal_(param)
    return model


def _lora_tensors(model: "nn.Module") -> dict:
    """Return a copy of the adapter tensors keyed by parameter name."""
    return {n: p.detach().clone() for n, p in model.named_parameters() if "lora_" in n}


@unittest.skipUnless(_HAS_DEPS, "torch, peft and safetensors are required")
class LoadAdapterStateDictTest(unittest.TestCase):
    """Resume must restore the trained adapter, never silently skip it."""

    def setUp(self) -> None:
        self.trained = _make_peft_model(seed=1)
        self.tmp = tempfile.TemporaryDirectory()
        self.trained.save_pretrained(self.tmp.name)
        self.saved = load_file(os.path.join(self.tmp.name, "adapter_model.safetensors"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_restores_peft_weights_saved_by_save_pretrained(self) -> None:
        fresh = _make_peft_model(seed=2)
        loaded = load_adapter_state_dict(fresh, self.saved)
        self.assertEqual(loaded, len(self.saved))
        expected = _lora_tensors(self.trained)
        for name, tensor in _lora_tensors(fresh).items():
            self.assertTrue(torch.equal(tensor, expected[name]), name)

    def test_plain_strict_false_load_matches_nothing(self) -> None:
        """Regression: the previous loader applied none of the saved tensors."""
        fresh = _make_peft_model(seed=2)
        result = fresh.load_state_dict(self.saved, strict=False)
        self.assertEqual(len(result.unexpected_keys), len(self.saved))

    def test_raises_when_no_tensor_matches(self) -> None:
        fresh = _make_peft_model(seed=2)
        wrong = {"base_model.model.other.lora_A.weight": torch.zeros(4, 8)}
        with self.assertRaises(AdapterResumeError):
            load_adapter_state_dict(fresh, wrong)

    def test_raises_on_empty_file(self) -> None:
        with self.assertRaises(AdapterResumeError):
            load_adapter_state_dict(_make_peft_model(seed=2), {})

    def test_non_peft_module_uses_plain_state_dict(self) -> None:
        plain = nn.Linear(4, 4)
        weights = {"weight": torch.ones(4, 4), "bias": torch.zeros(4)}
        self.assertEqual(load_adapter_state_dict(plain, weights), 2)
        self.assertTrue(torch.equal(plain.weight, torch.ones(4, 4)))


if __name__ == "__main__":
    unittest.main()
