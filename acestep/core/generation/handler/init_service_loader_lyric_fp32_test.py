"""Unit tests for ``InitServiceLoaderMixin._keep_lyric_encoder_fp32``."""

import unittest
from types import SimpleNamespace

import torch

from acestep.core.generation.handler.init_service_loader import InitServiceLoaderMixin


class _FakeLyricEncoder(torch.nn.Module):
    """Tiny stand-in that records the dtypes it actually computes in."""

    def __init__(self):
        super().__init__()
        self.proj = torch.nn.Linear(4, 4)
        self.seen = []

    def forward(self, inputs_embeds, attention_mask=None):
        self.seen.append((inputs_embeds.dtype, self.proj.weight.dtype))
        return SimpleNamespace(last_hidden_state=self.proj(inputs_embeds))


class _Host(InitServiceLoaderMixin):
    """Minimal host exposing only what ``_keep_lyric_encoder_fp32`` reads."""

    def __init__(self, dtype, lyric_encoder):
        self.dtype = dtype
        self.model = SimpleNamespace(encoder=SimpleNamespace(lyric_encoder=lyric_encoder))


def _make_encoder(dtype):
    encoder = _FakeLyricEncoder()
    encoder.to(dtype)
    return encoder


class KeepLyricEncoderFp32Test(unittest.TestCase):
    """Verify the fp16 overflow guard only affects the fp16 path."""

    def test_computes_in_fp32_and_returns_fp16(self):
        """Inputs and weights are fp32 during forward; weights and output are fp16 afterwards."""
        encoder = _make_encoder(torch.float16)
        _Host(torch.float16, encoder)._keep_lyric_encoder_fp32()

        out = encoder(torch.randn(2, 3, 4, dtype=torch.float16), attention_mask=torch.ones(2, 3))

        self.assertEqual(encoder.seen[-1], (torch.float32, torch.float32))
        self.assertEqual(out.last_hidden_state.dtype, torch.float16)
        self.assertEqual(encoder.proj.weight.dtype, torch.float16)

    def test_survives_offload_recast_between_calls(self):
        """A later ``model.to(float16)`` (CPU-offload reload) must not break the next call."""
        encoder = _make_encoder(torch.float16)
        _Host(torch.float16, encoder)._keep_lyric_encoder_fp32()
        encoder(torch.randn(1, 2, 4, dtype=torch.float16))

        encoder.to(torch.float16)  # what _recursive_to_device(model, device, dtype) does
        encoder(torch.randn(1, 2, 4, dtype=torch.float16))

        self.assertEqual(encoder.seen[-1], (torch.float32, torch.float32))

    def test_restores_fp16_weights_when_forward_raises(self):
        """An exception inside forward must not leave the weights stuck in fp32."""
        encoder = _make_encoder(torch.float16)
        _Host(torch.float16, encoder)._keep_lyric_encoder_fp32()

        with self.assertRaises(TypeError):
            encoder(torch.randn(1, 2, 4, dtype=torch.float16), unexpected_kwarg=1)

        self.assertEqual(encoder.proj.weight.dtype, torch.float16)

    def test_idempotent(self):
        """Calling the patch twice must not wrap the encoder twice."""
        encoder = _make_encoder(torch.float16)
        host = _Host(torch.float16, encoder)
        host._keep_lyric_encoder_fp32()
        wrapped = encoder.forward
        host._keep_lyric_encoder_fp32()

        self.assertIs(encoder.forward, wrapped)

    def test_noop_for_non_fp16_dtypes(self):
        """bf16 / fp32 paths (Ampere+, CPU, MPS, XPU) are left untouched."""
        for dtype in (torch.bfloat16, torch.float32):
            with self.subTest(dtype=dtype):
                encoder = _make_encoder(dtype)
                original_forward = encoder.forward
                _Host(dtype, encoder)._keep_lyric_encoder_fp32()

                self.assertEqual(encoder.forward, original_forward)
                self.assertFalse(getattr(encoder, "_fp32_forward_patched", False))
                self.assertEqual(encoder.proj.weight.dtype, dtype)

    def test_noop_when_model_has_no_lyric_encoder(self):
        """Models without ``encoder.lyric_encoder`` are ignored instead of raising."""
        host = _Host(torch.float16, None)
        host.model = SimpleNamespace()
        host._keep_lyric_encoder_fp32()  # must not raise


if __name__ == "__main__":
    unittest.main()
