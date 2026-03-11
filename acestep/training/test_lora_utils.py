"""Unit tests for acestep.training.lora_injection and acestep.training.lora_utils modules."""

import unittest
from unittest.mock import MagicMock, patch
import torch
import torch.nn as nn

from acestep.training.lora_injection import (
    _unwrap_decoder,
    freeze_non_lora_parameters,
)
from acestep.training.lora_utils import check_peft_available


class TestUnwrapDecoder(unittest.TestCase):
    """Test cases for _unwrap_decoder function."""

    def test_returns_module_directly(self):
        """If module has no wrappers, return it unchanged."""
        mock_module = MagicMock(spec=nn.Module)
        result = _unwrap_decoder(mock_module)
        self.assertIs(result, mock_module)

    def test_unwraps_forward_module(self):
        """Unwrap _forward_module chain."""
        inner = MagicMock(spec=nn.Module)
        wrapper = MagicMock(spec_set=["_forward_module"])
        wrapper._forward_module = inner

        result = _unwrap_decoder(wrapper)
        self.assertIs(result, inner)

    def test_unwraps_peft_base_model(self):
        """Unwrap PEFT base_model with .model attribute."""
        inner = MagicMock(spec=nn.Module)
        base = MagicMock(spec_set=["model"])
        base.model = inner

        result = _unwrap_decoder(base)
        self.assertIs(result, inner)

    def test_unwraps_peft_base_model_no_inner_model(self):
        """Unwrap PEFT base_model without .model attribute."""
        base = MagicMock(spec=nn.Module)

        result = _unwrap_decoder(base)
        self.assertIs(result, base)

    def test_unwraps_nested_wrappers(self):
        """Handle multiple wrapper layers."""
        inner = MagicMock(spec=nn.Module)
        wrapper1 = MagicMock(spec_set=["_forward_module"])
        wrapper1._forward_module = inner
        wrapper2 = MagicMock(spec_set=["_forward_module"])
        wrapper2._forward_module = wrapper1

        result = _unwrap_decoder(wrapper2)
        self.assertIs(result, inner)

    def test_unwraps_complex_peft_chain(self):
        """Unwrap complex chain: wrapper -> _forward_module -> base_model -> .model."""
        inner = MagicMock(spec=nn.Module)
        base = MagicMock(spec_set=["model"])
        base.model = inner
        mid = MagicMock(spec_set=["_forward_module"])
        mid._forward_module = base
        wrapper = MagicMock(spec_set=["_forward_module"])
        wrapper._forward_module = mid

        result = _unwrap_decoder(wrapper)
        self.assertIs(result, inner)


class TestCheckPeftAvailable(unittest.TestCase):
    """Test cases for check_peft_available function."""

    def test_returns_boolean(self):
        """check_peft_available should return a boolean."""
        result = check_peft_available()
        self.assertIsInstance(result, bool)


class TestFreezeNonLoraParameters(unittest.TestCase):
    """Test cases for freeze_non_lora_parameters function."""

    def _create_mock_model(self, param_names_requires_grad=None):
        """Create a mock model with named parameters."""
        mock_model = MagicMock(spec=nn.Module)
        params = []
        for name, requires_grad in param_names_requires_grad or []:
            mock_param = MagicMock()
            mock_param.requires_grad = requires_grad
            mock_param.numel.return_value = 100
            params.append((name, mock_param))
        mock_model.named_parameters.return_value = params
        return mock_model

    def test_lora_params_remain_trainable(self):
        """LoRA parameters should remain trainable regardless of freeze_encoder."""
        mock_model = self._create_mock_model(
            [
                ("decoder.layer.q_proj.lora_A.weight", True),
                ("decoder.layer.k_proj.lora_B.weight", True),
            ]
        )
        freeze_non_lora_parameters(mock_model, freeze_encoder=True)
        for name, param in mock_model.named_parameters():
            if "lora_" in name:
                self.assertTrue(
                    param.requires_grad, f"LoRA param {name} should be trainable"
                )

    def test_non_lora_non_encoder_frozen_when_freeze_encoder_true(self):
        """Non-LoRA, non-encoder params should be frozen when freeze_encoder=True."""
        mock_model = self._create_mock_model(
            [
                ("decoder.layer.fc.weight", True),
            ]
        )
        freeze_non_lora_parameters(mock_model, freeze_encoder=True)
        for name, param in mock_model.named_parameters():
            self.assertFalse(
                param.requires_grad, f"Non-LoRA param {name} should be frozen"
            )

    def test_encoder_frozen_when_freeze_encoder_true(self):
        """Encoder parameters should be frozen when freeze_encoder=True."""
        mock_model = self._create_mock_model(
            [
                ("encoder.layer.0.weight", True),
                ("text_encoder.embed.weight", True),
                ("vision_encoder.conv.weight", True),
                ("model.encoder.block.0.weight", True),
            ]
        )
        freeze_non_lora_parameters(mock_model, freeze_encoder=True)
        for name, param in mock_model.named_parameters():
            self.assertFalse(
                param.requires_grad, f"Encoder param {name} should be frozen"
            )

    def test_encoder_trainable_when_freeze_encoder_false(self):
        """Encoder parameters should remain trainable when freeze_encoder=False."""
        mock_model = self._create_mock_model(
            [
                ("encoder.layer.0.weight", True),
                ("text_encoder.embed.weight", True),
                ("vision_encoder.conv.weight", True),
                ("model.encoder.block.0.weight", True),
                ("decoder.layer.fc.weight", True),
            ]
        )
        freeze_non_lora_parameters(mock_model, freeze_encoder=False)
        encoder_params = [
            "encoder.layer.0.weight",
            "text_encoder.embed.weight",
            "vision_encoder.conv.weight",
            "model.encoder.block.0.weight",
        ]
        for name, param in mock_model.named_parameters():
            if name in encoder_params:
                self.assertTrue(
                    param.requires_grad, f"Encoder param {name} should be trainable"
                )
            else:
                self.assertFalse(
                    param.requires_grad, f"Non-encoder param {name} should be frozen"
                )

    def test_mixed_params_freeze_encoder_true(self):
        """Test mixed LoRA and encoder params with freeze_encoder=True."""
        mock_model = self._create_mock_model(
            [
                ("encoder.layer.0.weight", True),
                ("decoder.layer.q_proj.lora_A.weight", True),
                ("decoder.layer.fc.weight", True),
            ]
        )
        freeze_non_lora_parameters(mock_model, freeze_encoder=True)
        for name, param in mock_model.named_parameters():
            if "lora_" in name:
                self.assertTrue(
                    param.requires_grad, f"LoRA param {name} should be trainable"
                )
            else:
                self.assertFalse(
                    param.requires_grad, f"Non-LoRA param {name} should be frozen"
                )

    def test_mixed_params_freeze_encoder_false(self):
        """Test mixed LoRA and encoder params with freeze_encoder=False."""
        mock_model = self._create_mock_model(
            [
                ("encoder.layer.0.weight", True),
                ("decoder.layer.q_proj.lora_A.weight", True),
                ("decoder.layer.fc.weight", True),
            ]
        )
        freeze_non_lora_parameters(mock_model, freeze_encoder=False)
        for name, param in mock_model.named_parameters():
            if "lora_" in name:
                self.assertTrue(
                    param.requires_grad, f"LoRA param {name} should be trainable"
                )
            elif (
                name.startswith("encoder")
                or name.startswith("text_encoder")
                or name.startswith("vision_encoder")
                or name.startswith("model.encoder")
            ):
                self.assertTrue(
                    param.requires_grad, f"Encoder param {name} should be trainable"
                )
            else:
                self.assertFalse(
                    param.requires_grad,
                    f"Non-LoRA/non-encoder param {name} should be frozen",
                )


if __name__ == "__main__":
    unittest.main()
