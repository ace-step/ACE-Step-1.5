"""Tests for computing the lyric encoder's last projection in float32 on float16 models.

On a Tesla V100 the lyric encoder's last layer (layers.7.mlp.down_proj) reaches |x| ~ 505,000 on
ordinary lyrics -- past float16's 65,504 -- so every latent becomes NaN (issue #1055). These tests
use the real AceStepLyricEncoder (turbo; the other five model files carry identical copies) with a
tiny config and a last MLP scaled up to overflow the same way.
"""

import copy
import pickle
import unittest
from unittest.mock import patch

import torch
from torch import nn

from acestep.core.generation.handler import fp16_lyric_encoder as FIX
from acestep.models.common.configuration_acestep_v15 import AceStepConfig
from acestep.models.turbo.modeling_acestep_v15_turbo import AceStepLyricEncoder

FLOAT16_MAX = 65504.0


def _encoder() -> AceStepLyricEncoder:
    """Build a tiny real lyric encoder whose last MLP overflows float16 like the real one."""
    config = AceStepConfig(
        hidden_size=64, intermediate_size=128, num_attention_heads=2, num_key_value_heads=2,
        head_dim=32, text_hidden_dim=16, num_lyric_encoder_hidden_layers=2,
        layer_types=["full_attention", "full_attention"], use_sliding_window=False,
    )
    config._attn_implementation = "eager"
    torch.manual_seed(0)
    enc = AceStepLyricEncoder(config).eval()
    with torch.no_grad():
        # ~1.7K into the last projection, ~150K out -- like the real one's ~11.5K in, ~505K out.
        mlp = enc.layers[-1].mlp
        mlp.gate_proj.weight.mul_(100.0)
        mlp.up_proj.weight.mul_(100.0)
        mlp.down_proj.weight.mul_(1000.0)
    return enc


class _Model(nn.Module):
    """A model with ``encoder.lyric_encoder`` and an unrelated float16 submodule."""

    def __init__(self):
        """Create the tiny encoder and a stand-in decoder."""
        super().__init__()
        self.encoder = nn.Module()
        self.encoder.lyric_encoder = _encoder()
        self.decoder = nn.Linear(4, 4)


def _run(enc: nn.Module, dtype: torch.dtype) -> torch.Tensor:
    """Run the encoder on a fixed random input in ``dtype``."""
    torch.manual_seed(1)
    x = torch.randn(1, 7, 16).to(dtype)
    mask = torch.ones(1, 7, dtype=torch.long)
    return enc(inputs_embeds=x, attention_mask=mask).last_hidden_state


class LyricEncoderTailFloat32Tests(unittest.TestCase):
    """compute_lyric_encoder_tail_in_float32 on the real (tiny) lyric encoder."""

    def setUp(self):
        """Build the model and a float32 reference, and check the reference really overflows."""
        self.model = _Model()
        peak = []
        down = self.model.encoder.lyric_encoder.layers[-1].mlp.down_proj
        handle = down.register_forward_hook(lambda m, i, o: peak.append(o.abs().max().item()))
        self.reference = _run(self.model.encoder.lyric_encoder, torch.float32)
        handle.remove()
        self.assertGreater(peak[0], FLOAT16_MAX)
        self.assertTrue(torch.isfinite(self.reference).all())

    def test_without_the_fix_float16_overflows(self):
        """Control: the tiny encoder really does overflow in float16."""
        out = _run(self.model.half().encoder.lyric_encoder, torch.float16)
        self.assertFalse(torch.isfinite(out).all())

    def test_float16_output_is_finite_close_and_float16(self):
        """With the fix the output is finite, float16, close to float32, and no copy is kept."""
        model = self.model.half()
        self.assertTrue(FIX.compute_lyric_encoder_tail_in_float32(model))
        out = _run(model.encoder.lyric_encoder, torch.float16)
        self.assertEqual(out.dtype, torch.float16)
        self.assertTrue(torch.isfinite(out).all())
        error = (out.float() - self.reference).norm() / self.reference.norm()
        self.assertLess(error.item(), 2e-2)
        down = model.encoder.lyric_encoder.layers[-1].mlp.down_proj
        self.assertEqual(down.weight.dtype, torch.float16)

    def test_survives_a_later_dtype_move(self):
        """CPU offload moves the model with .to(device, dtype=float16); the fix must hold."""
        model = self.model.half()
        FIX.compute_lyric_encoder_tail_in_float32(model)
        model.float()
        model.to(dtype=torch.float16)
        self.assertTrue(torch.isfinite(_run(model.encoder.lyric_encoder, torch.float16)).all())

    def test_survives_autocast_to_float16(self):
        """A float16 autocast context (the trainer uses one) must not undo the fix."""
        model = self.model.half()
        FIX.compute_lyric_encoder_tail_in_float32(model)
        with torch.autocast(device_type="cpu", dtype=torch.float16):
            out = _run(model.encoder.lyric_encoder, torch.float16)
        self.assertTrue(torch.isfinite(out).all())

    def test_deepcopy_and_pickle_keep_working(self):
        """A deep copy uses its own weights, and the patched model still pickles."""
        model = self.model.half()
        FIX.compute_lyric_encoder_tail_in_float32(model)
        clone = copy.deepcopy(model)
        with torch.no_grad():
            clone.encoder.lyric_encoder.layers[-1].mlp.down_proj.weight.zero_()
        self.assertFalse(torch.equal(_run(clone.encoder.lyric_encoder, torch.float16),
                                     _run(model.encoder.lyric_encoder, torch.float16)))
        restored = pickle.loads(pickle.dumps(model))
        self.assertTrue(torch.isfinite(_run(restored.encoder.lyric_encoder, torch.float16)).all())

    def test_float32_model_is_unchanged(self):
        """On a float32 model the patched projection gives the same output."""
        FIX.compute_lyric_encoder_tail_in_float32(self.model)
        out = _run(self.model.encoder.lyric_encoder, torch.float32)
        self.assertEqual(out.dtype, torch.float32)
        self.assertTrue(torch.allclose(out, self.reference, atol=1e-5))

    def test_applying_twice_hooks_once(self):
        """A second call reports success and adds no second hook."""
        model = self.model.half()
        self.assertTrue(FIX.compute_lyric_encoder_tail_in_float32(model))
        self.assertTrue(FIX.compute_lyric_encoder_tail_in_float32(model))
        self.assertEqual(len(model.encoder.lyric_encoder.norm._forward_hooks), 1)

    def test_patches_the_last_layer_that_runs(self):
        """AceStepLyricEncoder.forward runs layers[: config.num_hidden_layers]."""
        enc = self.model.encoder.lyric_encoder
        enc.config.num_hidden_layers = 1
        self.assertTrue(FIX.compute_lyric_encoder_tail_in_float32(self.model))
        self.assertIsInstance(enc.layers[0].mlp.down_proj, FIX.Float32Linear)
        self.assertNotIsInstance(enc.layers[1].mlp.down_proj, FIX.Float32Linear)
        other = _Model()
        other.encoder.lyric_encoder.config.num_hidden_layers = 0      # nothing runs
        self.assertFalse(FIX.compute_lyric_encoder_tail_in_float32(other))

    def test_a_replaced_linear_is_left_alone(self):
        """A Linear subclass in that place (e.g. a quantized layer) is not swapped."""
        class _OtherLinear(nn.Linear):
            """Stand-in for a Linear replaced by another library."""

        mlp = self.model.encoder.lyric_encoder.layers[-1].mlp
        mlp.down_proj.__class__ = _OtherLinear
        self.assertFalse(FIX.compute_lyric_encoder_tail_in_float32(self.model))
        self.assertIs(type(mlp.down_proj), _OtherLinear)

    def test_models_without_a_lyric_encoder_are_left_alone(self):
        """A model without encoder.lyric_encoder is not touched."""
        self.assertFalse(FIX.compute_lyric_encoder_tail_in_float32(nn.Linear(4, 4)))

    def test_apply_warns_when_not_recognised(self):
        """apply_float16_lyric_encoder_fix logs a warning if nothing could be patched."""
        with patch.object(FIX.logger, "warning") as warning, patch.object(FIX.logger, "info"):
            FIX.apply_float16_lyric_encoder_fix(nn.Linear(4, 4))
            FIX.apply_float16_lyric_encoder_fix(_Model().half())
        self.assertEqual(warning.call_count, 1)


if __name__ == "__main__":
    unittest.main()
