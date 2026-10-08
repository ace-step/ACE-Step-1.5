"""Tests for keeping nano-vllm's Qwen3 LM inside float16's range.

Covers fp16_range.py and RMSNorm.add_rms_forward. ACE-Step's 5 Hz LM writes ~2,000,000 into its
residual stream at decoder layer 2 (the SwiGLU product feeding that layer's down_proj is ~85,000);
in float16 every sampled token became '!'. These tests use nano-vllm's real Qwen3MLP and RMSNorm
with tiny sizes, scaled up to overflow float16 the same way.

Run from acestep/third_parts/nano-vllm: python -m unittest nanovllm.layers.fp16_range_test
(nanovllm's subpackages have no __init__.py, so unittest discovery does not find these tests).
"""

import inspect
import unittest

import torch
from torch import nn

from nanovllm.engine import model_runner
from nanovllm.layers import fp16_range as FIX
from nanovllm.layers.layernorm import RMSNorm
from nanovllm.models.qwen3 import Qwen3MLP

FLOAT16_MAX = 65504.0


def _mlp(dtype: torch.dtype = torch.float32, boost: float = 1.0) -> Qwen3MLP:
    """A tiny real Qwen3MLP; ``boost`` makes its product and output overflow float16.

    The weights are drawn in float32 and then converted, so every dtype holds the same model.
    """
    torch.manual_seed(0)
    mlp = Qwen3MLP(hidden_size=16, intermediate_size=32, hidden_act="silu").float()
    with torch.no_grad():
        for p in mlp.parameters():
            p.normal_(0.0, 0.5)
        mlp.gate_up_proj.weight.mul_(boost)
    return mlp.to(dtype)


class MlpScaleTests(unittest.TestCase):
    """apply_fp16_mlp_scale on nano-vllm's Qwen3MLP."""

    def setUp(self):
        """A fixed input."""
        torch.manual_seed(1)
        self.x = torch.randn(3, 16)

    def test_output_is_unchanged(self):
        """Dividing 'up' by a power of two and multiplying back gives the same output."""
        mlp = _mlp()
        before = mlp(self.x)
        self.assertEqual(FIX.apply_fp16_mlp_scale(mlp), 1)
        after = mlp(self.x)
        self.assertEqual(after.dtype, torch.float32)
        self.assertTrue(torch.allclose(before, after, rtol=1e-6, atol=1e-6))

    def test_only_the_up_half_is_scaled(self):
        """gate_up_proj holds [gate; up]: gate stays, up is divided."""
        mlp = _mlp()
        w = mlp.gate_up_proj.weight.detach().clone()
        FIX.apply_fp16_mlp_scale(mlp, factor=128.0)
        half = w.shape[0] // 2
        self.assertTrue(torch.equal(mlp.gate_up_proj.weight[:half], w[:half]))
        self.assertTrue(torch.equal(mlp.gate_up_proj.weight[half:], w[half:] / 128.0))

    def test_float16_overflow_goes_away(self):
        """Control + fix: an MLP past 65,504 gives inf in float16, the right answer when fixed."""
        reference = _mlp(torch.float32, boost=60.0)(self.x)
        self.assertGreater(reference.abs().max().item(), FLOAT16_MAX)
        mlp = _mlp(torch.float16, boost=60.0)
        self.assertFalse(torch.isfinite(mlp(self.x.half()).float()).all())
        FIX.apply_fp16_mlp_scale(mlp)
        out = mlp(self.x.half())
        self.assertEqual(out.dtype, torch.float32)        # handed to the float32 residual stream
        self.assertTrue(torch.isfinite(out).all())
        self.assertLess(((out - reference).norm() / reference.norm()).item(), 1e-2)

    def test_the_real_models_worst_mlp_fits(self):
        """Pinned to the 5 Hz LM's layer 2: ~85,000 into down_proj, ~2.1 million out (float32)."""
        mlp = Qwen3MLP(hidden_size=16, intermediate_size=32, hidden_act="silu").float()
        with torch.no_grad():
            half = mlp.gate_up_proj.weight.shape[0] // 2
            mlp.gate_up_proj.weight[:half].fill_(300.0 / 16)     # gate = 300 on all-ones input
            mlp.gate_up_proj.weight[half:].fill_(285.0 / 16)     # up = 285: product ~85,500
            mlp.down_proj.weight.fill_(0.77)                     # 32 x 85,500 x 0.77 = 2.1M
        x = torch.ones(1, 16)
        reference = mlp(x)
        self.assertGreater(reference.abs().max().item(), 2.0e6)
        fp16 = mlp.half()
        self.assertFalse(torch.isfinite(fp16(x.half()).float()).all())
        FIX.apply_fp16_mlp_scale(fp16)
        out = fp16(x.half())
        self.assertTrue(torch.isfinite(out).all())
        self.assertLess(((out - reference).abs().max() / reference.abs().max()).item(), 1e-2)

    def test_factor_must_be_a_power_of_two(self):
        """Only a power of two divides and multiplies back without changing any value."""
        with self.assertRaises(ValueError):
            FIX.apply_fp16_mlp_scale(_mlp(), factor=1.5)

    def test_float16_models_get_it_and_others_do_not(self):
        """maybe_apply_fp16_range: float16 changes every MLP; bfloat16 and float32 change none."""
        both = nn.ModuleList([_mlp(), _mlp()])
        self.assertEqual(FIX.maybe_apply_fp16_range(both, torch.float16), 2)
        for dtype in (torch.bfloat16, torch.float32):
            mlp = _mlp()
            w = mlp.gate_up_proj.weight.detach().clone()
            self.assertEqual(FIX.maybe_apply_fp16_range(mlp, dtype), 0)
            self.assertTrue(torch.equal(w, mlp.gate_up_proj.weight))

    def test_the_model_runner_applies_it_after_loading(self):
        """ModelRunner calls it with the model and its dtype right after load_model."""
        source = inspect.getsource(model_runner.ModelRunner.__init__)
        load = source.index("load_model(self.model, config.model)")
        call = source.index("maybe_apply_fp16_range(self.model, self.dtype)")
        self.assertLess(load, call)
        self.assertLess(call, source.index("self.warmup_model()"))

    def test_applying_twice_scales_once(self):
        """A second call changes nothing."""
        mlp = _mlp()
        FIX.apply_fp16_mlp_scale(mlp)
        w = mlp.gate_up_proj.weight.detach().clone()
        self.assertEqual(FIX.apply_fp16_mlp_scale(mlp), 0)
        self.assertTrue(torch.equal(w, mlp.gate_up_proj.weight))

    def test_counts_every_mlp_and_skips_other_modules(self):
        """Every Qwen3MLP in a model is changed; other modules are left alone."""
        other = nn.Linear(4, 4)
        w = other.weight.detach().clone()
        model = nn.ModuleList([_mlp(), _mlp(), other])
        self.assertEqual(FIX.apply_fp16_mlp_scale(model), 2)
        self.assertTrue(torch.equal(w, other.weight))

    def test_unscaled_mlp_keeps_its_dtype(self):
        """Without the fix (bfloat16 / float32 models) the MLP output keeps the model dtype."""
        self.assertEqual(_mlp(torch.bfloat16)(self.x.bfloat16()).dtype, torch.bfloat16)


class ResidualStreamTests(unittest.TestCase):
    """RMSNorm.add_rms_forward carries the residual in float32 for float16 models only."""

    def test_float16_model_keeps_a_float32_residual(self):
        """A residual past 65,504 survives exactly; the normalised output is float16."""
        norm = RMSNorm(8).half()
        x = torch.full((2, 8), 3.0, dtype=torch.float32)                 # e.g. a scaled MLP output
        residual = torch.full((2, 8), 2_000_000.0, dtype=torch.float32)
        out, new_residual = norm(x, residual)
        self.assertEqual(new_residual.dtype, torch.float32)
        self.assertTrue(torch.equal(new_residual, torch.full((2, 8), 2_000_003.0)))
        self.assertEqual(out.dtype, torch.float16)
        self.assertTrue(torch.isfinite(out).all())

    def test_bfloat16_model_is_unchanged(self):
        """bfloat16 models keep a bfloat16 residual, as before."""
        norm = RMSNorm(8).bfloat16()
        x = torch.randn(2, 8).bfloat16()
        out, residual = norm(x, torch.randn(2, 8).bfloat16())
        self.assertEqual((out.dtype, residual.dtype), (torch.bfloat16, torch.bfloat16))


if __name__ == "__main__":
    unittest.main()
