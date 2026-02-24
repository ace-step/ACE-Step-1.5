"""Tests for LoRA/LoKr runtime controls (toggle, scale)."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from acestep.core.generation.handler.lora.controls import (
    _toggle_lokr,
    set_lora_scale,
    set_use_lora,
)


class _DummyHandler:
    """Handler stub exposing the attributes used by ``set_use_lora`` / ``set_lora_scale``."""

    def __init__(self, adapter_type=None) -> None:
        self.model = SimpleNamespace(decoder=SimpleNamespace())
        self.lora_loaded = True
        self.use_lora = True
        self.lora_scale = 1.0
        self._adapter_type = adapter_type
        self._lora_active_adapter = "default"
        self._active_loras = {"default": 1.0}
        self._lora_service = SimpleNamespace(
            registry={"default": {}},
            scale_state={},
            active_adapter="default",
            last_scale_report={},
            synthetic_default_mode=False,
        )

    def _ensure_lora_registry(self):
        return None

    def _rebuild_lora_registry(self, lora_path=None):
        return 0, list(self._active_loras.keys())

    def _sync_lora_state_from_service(self):
        return None

    def _apply_scale_to_adapter(self, name, scale):
        return 1

    def set_lora_scale(self, adapter_name_or_scale, scale=None):
        return set_lora_scale(self, adapter_name_or_scale, scale)


class ToggleLokrTests(unittest.TestCase):
    """Unit tests for the ``_toggle_lokr`` helper."""

    def test_disable_sets_multiplier_to_zero(self):
        """Disabling should call set_multiplier(0.0)."""
        lycoris_net = SimpleNamespace(set_multiplier=Mock())
        decoder = SimpleNamespace(_lycoris_net=lycoris_net)
        result = _toggle_lokr(decoder, enable=False)
        self.assertTrue(result)
        lycoris_net.set_multiplier.assert_called_once_with(0.0)

    def test_enable_sets_multiplier_to_scale(self):
        """Enabling should call set_multiplier with the given scale."""
        lycoris_net = SimpleNamespace(set_multiplier=Mock())
        decoder = SimpleNamespace(_lycoris_net=lycoris_net)
        result = _toggle_lokr(decoder, enable=True, scale=0.75)
        self.assertTrue(result)
        lycoris_net.set_multiplier.assert_called_once_with(0.75)

    def test_returns_false_when_no_lycoris_net(self):
        """Should return False when decoder has no _lycoris_net."""
        decoder = SimpleNamespace()
        result = _toggle_lokr(decoder, enable=False)
        self.assertFalse(result)

    def test_returns_false_when_no_set_multiplier(self):
        """Should return False when _lycoris_net lacks set_multiplier."""
        decoder = SimpleNamespace(_lycoris_net=SimpleNamespace())
        result = _toggle_lokr(decoder, enable=True)
        self.assertFalse(result)


class SetUseLokrTests(unittest.TestCase):
    """Tests for set_use_lora with LoKr adapter type."""

    def test_disable_lokr_zeros_multiplier(self):
        """Unchecking use_lora should set LoKr multiplier to 0."""
        handler = _DummyHandler(adapter_type="lokr")
        lycoris_net = SimpleNamespace(set_multiplier=Mock())
        handler.model.decoder._lycoris_net = lycoris_net

        result = set_use_lora(handler, False)

        self.assertFalse(handler.use_lora)
        lycoris_net.set_multiplier.assert_called_once_with(0.0)
        self.assertIn("LoKr", result)
        self.assertIn("disabled", result)

    def test_enable_lokr_restores_multiplier(self):
        """Re-checking use_lora should restore LoKr multiplier to saved scale."""
        handler = _DummyHandler(adapter_type="lokr")
        handler.use_lora = False
        handler._active_loras = {"default": 0.8}
        lycoris_net = SimpleNamespace(set_multiplier=Mock())
        handler.model.decoder._lycoris_net = lycoris_net

        result = set_use_lora(handler, True)

        self.assertTrue(handler.use_lora)
        lycoris_net.set_multiplier.assert_called_once_with(0.8)
        self.assertIn("LoKr", result)
        self.assertIn("enabled", result)

    def test_enable_lokr_uses_lora_scale_fallback(self):
        """When no active adapter, should fall back to self.lora_scale."""
        handler = _DummyHandler(adapter_type="lokr")
        handler.use_lora = False
        handler._lora_active_adapter = None
        handler.lora_scale = 0.5
        lycoris_net = SimpleNamespace(set_multiplier=Mock())
        handler.model.decoder._lycoris_net = lycoris_net

        set_use_lora(handler, True)

        lycoris_net.set_multiplier.assert_called_once_with(0.5)


class SetUsePeftLoraTests(unittest.TestCase):
    """Tests for set_use_lora with PEFT LoRA adapter type (non-regression)."""

    def test_disable_peft_lora_calls_disable_adapter_layers(self):
        """Unchecking use_lora should call disable_adapter_layers for PEFT."""
        handler = _DummyHandler(adapter_type="lora")
        handler.model.decoder.disable_adapter_layers = Mock()

        result = set_use_lora(handler, False)

        self.assertFalse(handler.use_lora)
        handler.model.decoder.disable_adapter_layers.assert_called_once()
        self.assertIn("LoRA", result)
        self.assertIn("disabled", result)

    def test_enable_peft_lora_calls_enable_adapter_layers(self):
        """Re-checking use_lora should call enable_adapter_layers for PEFT."""
        handler = _DummyHandler(adapter_type="lora")
        handler.use_lora = False
        handler.model.decoder.enable_adapter_layers = Mock()
        handler.model.decoder.disable_adapter_layers = Mock()
        handler.model.decoder.set_adapter = Mock()

        result = set_use_lora(handler, True)

        self.assertTrue(handler.use_lora)
        handler.model.decoder.enable_adapter_layers.assert_called_once()
        self.assertIn("LoRA", result)
        self.assertIn("enabled", result)

    def test_no_adapter_loaded_returns_error(self):
        """Enabling with no adapter loaded should return error."""
        handler = _DummyHandler()
        handler.lora_loaded = False
        handler.use_lora = False

        result = set_use_lora(handler, True)
        self.assertIn("❌", result)


class SetLokrScaleTests(unittest.TestCase):
    """Tests for set_lora_scale with LoKr adapter type."""

    def test_scale_lokr_sets_multiplier(self):
        """Setting scale on LoKr should call set_multiplier with the value."""
        handler = _DummyHandler(adapter_type="lokr")
        lycoris_net = SimpleNamespace(set_multiplier=Mock())
        handler.model.decoder._lycoris_net = lycoris_net

        result = set_lora_scale(handler, 0.6)

        lycoris_net.set_multiplier.assert_called_once_with(0.6)
        self.assertIn("0.60", result)
        self.assertIn("LoKr", result)
        self.assertAlmostEqual(handler.lora_scale, 0.6)

    def test_scale_lokr_when_disabled_stores_but_does_not_apply(self):
        """Scale change while disabled should store value but not call multiplier."""
        handler = _DummyHandler(adapter_type="lokr")
        handler.use_lora = False
        lycoris_net = SimpleNamespace(set_multiplier=Mock())
        handler.model.decoder._lycoris_net = lycoris_net

        result = set_lora_scale(handler, 0.3)

        lycoris_net.set_multiplier.assert_not_called()
        self.assertIn("disabled", result)
        self.assertAlmostEqual(handler.lora_scale, 0.3)


if __name__ == "__main__":
    unittest.main()
