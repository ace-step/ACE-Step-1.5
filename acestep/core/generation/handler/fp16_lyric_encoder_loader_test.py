"""Tests that the model loader applies the lyric-encoder float32 fix only to float16 models."""

import os
import tempfile
import types
import unittest
from unittest.mock import patch

import torch
from torch import nn

from acestep.core.generation.handler import init_service_loader as LOADER


class _Host(LOADER.InitServiceLoaderMixin):
    """Just enough of the handler for _load_main_model_from_checkpoint."""

    def __init__(self, dtype: torch.dtype):
        """Store the dtype the loader should see."""
        self.dtype, self.model = dtype, None
        self.offload_to_cpu, self.offload_dit_to_cpu = False, False

    def is_flash_attention_available(self, _device: str) -> bool:
        """Flash attention is never available here."""
        return False

    def _sync_alignment_config(self):
        """No-op stub."""

    def _apply_cuda_bool_argsort_workaround(self):
        """No-op stub."""


class _LoadedModel(nn.Module):
    """What the mocked from_pretrained returns."""

    def __init__(self):
        """Give it the config attribute the loader sets."""
        super().__init__()
        self.config = types.SimpleNamespace(_attn_implementation="sdpa")


class LoaderAppliesTheFixOnlyInFloat16Tests(unittest.TestCase):
    """_load_main_model_from_checkpoint calls the fix for float16 models only."""

    def _load(self, dtype: torch.dtype):
        """Run the loader with a mocked model; return the host and the mocked fix."""
        host = _Host(dtype)
        with tempfile.TemporaryDirectory() as tmpdir:
            torch.save(torch.zeros(1, 1, 1), os.path.join(tmpdir, "silence_latent.pt"))
            with patch("torch.cuda.is_available", return_value=False), \
                    patch("transformers.AutoModel.from_pretrained", return_value=_LoadedModel()), \
                    patch.object(LOADER, "apply_float16_lyric_encoder_fix") as fix:
                host._load_main_model_from_checkpoint(
                    model_checkpoint_path=tmpdir, device="cpu", use_flash_attention=False,
                    compile_model=False, quantization=None,
                )
        return host, fix

    def test_float16_applies_it_to_the_model(self):
        """float16: called once, with the loaded model."""
        host, fix = self._load(torch.float16)
        fix.assert_called_once_with(host.model)

    def test_bfloat16_and_float32_do_not(self):
        """bfloat16 and float32: never called."""
        self.assertEqual(self._load(torch.bfloat16)[1].call_count, 0)
        self.assertEqual(self._load(torch.float32)[1].call_count, 0)


if __name__ == "__main__":
    unittest.main()
