"""Unit tests for acestep.training_v2.trainer_helpers.save_adapter_flat.

These tests use only stdlib and unittest.mock so that torch is not required.
The save_adapter_flat function only needs attribute-level duck-typing, so
plain MagicMock objects work as stand-ins for nn.Module subclasses.
"""

import unittest
from unittest.mock import MagicMock, patch


def _make_fabric_wrapper(inner: MagicMock) -> MagicMock:
    """Return a mock that looks like a Fabric _FabricModule wrapping *inner*."""
    wrapper = MagicMock(spec_set=["_forward_module"])
    wrapper._forward_module = inner
    return wrapper


def _make_peft_decoder() -> MagicMock:
    """Return a mock that looks like a PEFT PeftModel-wrapped decoder."""
    decoder = MagicMock(spec=["save_pretrained"])
    return decoder


def _make_base_decoder() -> MagicMock:
    """Return a mock with no save_pretrained (raw non-PEFT decoder fallback)."""
    return MagicMock(spec=[])  # no save_pretrained attribute


def _make_full_model(decoder: MagicMock) -> MagicMock:
    """Return a mock that looks like AceStepConditionGenerationModel.

    The full model also has save_pretrained (inherits from HF PreTrainedModel)
    -- that method must NOT be invoked; only the decoder's save_pretrained
    should be called.
    """
    model = MagicMock(spec=["decoder", "save_pretrained"])
    model.decoder = decoder
    model.save_pretrained = MagicMock()
    return model


def _make_trainer(decoder: MagicMock, adapter_type: str = "lora") -> MagicMock:
    """Build a minimal trainer mock with the given decoder embedded."""
    full_model = _make_full_model(decoder)
    module = MagicMock()
    module.model = full_model
    trainer = MagicMock()
    trainer.adapter_type = adapter_type
    trainer.module = module
    return trainer


class TestSaveAdapterFlatLora(unittest.TestCase):
    """save_adapter_flat must write adapter files (not the full model) for LoRA."""

    def test_calls_save_pretrained_on_peft_decoder_not_full_model(self):
        """save_pretrained() must be called on the PeftModel decoder, not the full model."""
        peft_decoder = _make_peft_decoder()
        trainer = _make_trainer(peft_decoder)

        from acestep.training_v2.trainer_helpers import save_adapter_flat

        with patch("os.makedirs"):
            save_adapter_flat(trainer, "/tmp/out")

        # The PeftModel's save_pretrained must have been invoked.
        peft_decoder.save_pretrained.assert_called_once_with("/tmp/out")
        # The full model's save_pretrained must NOT have been called.
        trainer.module.model.save_pretrained.assert_not_called()

    def test_unwraps_fabric_wrapper_before_saving(self):
        """When Fabric wraps the decoder, save_pretrained is still called on the PeftModel."""
        peft_decoder = _make_peft_decoder()
        fabric_wrapped = _make_fabric_wrapper(peft_decoder)
        trainer = _make_trainer(fabric_wrapped)

        from acestep.training_v2.trainer_helpers import save_adapter_flat

        with patch("os.makedirs"):
            save_adapter_flat(trainer, "/tmp/out")

        peft_decoder.save_pretrained.assert_called_once_with("/tmp/out")
        trainer.module.model.save_pretrained.assert_not_called()

    def test_doubly_wrapped_fabric_still_reaches_peft_decoder(self):
        """Handles two layers of Fabric _FabricModule wrapping."""
        peft_decoder = _make_peft_decoder()
        fabric_inner = _make_fabric_wrapper(peft_decoder)
        fabric_outer = _make_fabric_wrapper(fabric_inner)
        trainer = _make_trainer(fabric_outer)

        from acestep.training_v2.trainer_helpers import save_adapter_flat

        with patch("os.makedirs"):
            save_adapter_flat(trainer, "/tmp/out")

        peft_decoder.save_pretrained.assert_called_once_with("/tmp/out")

    def test_fallback_to_save_lora_weights_when_no_save_pretrained(self):
        """If the decoder has no save_pretrained, save_lora_weights is used as fallback."""
        raw_decoder = _make_base_decoder()
        trainer = _make_trainer(raw_decoder)

        from acestep.training_v2.trainer_helpers import save_adapter_flat

        with (
            patch("os.makedirs"),
            patch(
                "acestep.training_v2.trainer_helpers.save_lora_weights"
            ) as mock_slw,
        ):
            save_adapter_flat(trainer, "/tmp/out")

        mock_slw.assert_called_once_with(trainer.module.model, "/tmp/out")

    def test_regression_full_model_save_pretrained_not_called_for_lora(self):
        """Regression: the full AceStep model's save_pretrained must never be called.

        Previously, _unwrap_decoder(module.model) returned the full
        AceStepConditionGenerationModel (which also has save_pretrained), causing
        model.safetensors + config.json to be written instead of adapter files.
        """
        peft_decoder = _make_peft_decoder()
        trainer = _make_trainer(peft_decoder)

        from acestep.training_v2.trainer_helpers import save_adapter_flat

        with patch("os.makedirs"):
            save_adapter_flat(trainer, "/tmp/out")

        # Critically, the full model's save_pretrained must not have been called.
        trainer.module.model.save_pretrained.assert_not_called()


if __name__ == "__main__":
    unittest.main()
