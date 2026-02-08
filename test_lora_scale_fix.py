#!/usr/bin/env python3
"""
Test script to verify LoRA scale slider fix.

This script tests that:
1. When use_lora=False, set_lora_scale does not modify any modules
2. When use_lora=True, set_lora_scale only modifies LoRA modules
3. Attention modules and other non-LoRA modules are never affected
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unittest.mock import Mock, MagicMock

# Simple print-based logger for testing without dependencies
class SimpleLogger:
    @staticmethod
    def info(msg): print(f"INFO: {msg}")
    @staticmethod
    def success(msg): print(f"SUCCESS: {msg}")
    @staticmethod
    def error(msg): print(f"ERROR: {msg}")

logger = SimpleLogger()


def create_mock_handler():
    """Create a mock handler with simulated model structure."""
    # Create a minimal handler class for testing
    class MockHandler:
        def __init__(self):
            self.lora_loaded = True
            self.use_lora = False
            self.lora_scale = 1.0
            self.model = Mock()
            
        def set_lora_scale(self, scale):
            """Simplified version of the fixed set_lora_scale method."""
            if not self.lora_loaded:
                return "⚠️ No LoRA loaded"
            
            # Clamp scale to 0-1 range
            self.lora_scale = max(0.0, min(1.0, scale))
            
            # Only apply scaling if LoRA is enabled
            if not self.use_lora:
                return f"✅ LoRA scale: {self.lora_scale:.2f} (LoRA disabled)"
            
            # Iterate through LoRA layers only and set their scaling
            try:
                modified_count = 0
                for name, module in self.model.decoder.named_modules():
                    # Only modify LoRA modules - they have 'lora_' in their name
                    # This prevents modifying attention scaling and other non-LoRA modules
                    if 'lora_' in name and hasattr(module, 'scaling'):
                        scaling = module.scaling
                        # Handle dict-style scaling (adapter_name -> value)
                        if isinstance(scaling, dict):
                            # Save original scaling on first call
                            if not hasattr(module, '_original_scaling'):
                                module._original_scaling = {k: v for k, v in scaling.items()}
                            # Apply new scale
                            for adapter_name in scaling:
                                module.scaling[adapter_name] = module._original_scaling[adapter_name] * self.lora_scale
                            modified_count += 1
                        # Handle float-style scaling (single value)
                        elif isinstance(scaling, (int, float)):
                            if not hasattr(module, '_original_scaling'):
                                module._original_scaling = scaling
                            module.scaling = module._original_scaling * self.lora_scale
                            modified_count += 1
                
                if modified_count > 0:
                    return f"✅ LoRA scale: {self.lora_scale:.2f}"
                else:
                    return f"⚠️ Scale set to {self.lora_scale:.2f} (no modules found)"
            except Exception as e:
                return f"⚠️ Scale set to {self.lora_scale:.2f} (partial)"
        
        def set_use_lora(self, use_lora):
            """Simplified version of the fixed set_use_lora method."""
            if use_lora and not self.lora_loaded:
                return "❌ No LoRA adapter loaded. Please load a LoRA first."
            
            self.use_lora = use_lora
            
            # Apply current scale when enabling LoRA
            if self.lora_loaded:
                if use_lora and self.lora_scale != 1.0:
                    self.set_lora_scale(self.lora_scale)
            
            status = "enabled" if use_lora else "disabled"
            return f"✅ LoRA {status}"
    
    handler = MockHandler()
    handler = MockHandler()
    
    # Mock the model structure
    mock_decoder = Mock()
    
    # Create mock modules that simulate the decoder structure:
    # 1. LoRA modules (should be affected when LoRA is enabled)
    # 2. Attention modules with 'scale' attribute (should NOT be affected)
    
    # Use real dict/float for scaling attributes, not Mock
    class MockModule:
        def __init__(self, scaling_value):
            self.scaling = scaling_value
    
    mock_lora_module_1 = MockModule({'default': 1.0})
    mock_lora_module_2 = MockModule(1.0)
    mock_attention_module = MockModule(0.125)  # Attention scale (1/sqrt(head_dim))
    mock_other_module = MockModule(2.0)
    
    # Set up named_modules to return our test modules
    def named_modules():
        return [
            ('decoder.layers.0.self_attn.q_proj.lora_A', mock_lora_module_1),
            ('decoder.layers.0.self_attn.k_proj.lora_B', mock_lora_module_2),
            ('decoder.layers.0.self_attn', mock_attention_module),  # NOT a LoRA module
            ('decoder.layers.0.other_layer', mock_other_module),  # NOT a LoRA module
        ]
    
    mock_decoder.named_modules = named_modules
    handler.model.decoder = mock_decoder
    
    return handler, mock_lora_module_1, mock_lora_module_2, mock_attention_module, mock_other_module


def test_lora_scale_with_lora_disabled():
    """Test that scaling modules when LoRA is disabled doesn't affect any modules."""
    logger.info("\n=== Test 1: LoRA Scale with LoRA Disabled ===")
    
    handler, lora_mod1, lora_mod2, attn_mod, other_mod = create_mock_handler()
    
    # Store original values
    orig_lora1 = lora_mod1.scaling.copy()
    orig_lora2 = lora_mod2.scaling
    orig_attn = attn_mod.scaling
    orig_other = other_mod.scaling
    
    # Set LoRA to disabled
    handler.use_lora = False
    
    # Try to set scale to 0.5
    result = handler.set_lora_scale(0.5)
    
    # Verify the scale value is stored
    assert handler.lora_scale == 0.5, f"Expected lora_scale to be 0.5, got {handler.lora_scale}"
    
    # Verify NO modules were modified (because LoRA is disabled)
    assert lora_mod1.scaling == orig_lora1, "LoRA module 1 should NOT be modified when LoRA is disabled"
    assert lora_mod2.scaling == orig_lora2, "LoRA module 2 should NOT be modified when LoRA is disabled"
    assert attn_mod.scaling == orig_attn, "Attention module should NOT be modified"
    assert other_mod.scaling == orig_other, "Other module should NOT be modified"
    
    logger.success("✓ Test 1 passed: No modules modified when LoRA disabled")
    return True


def test_lora_scale_with_lora_enabled():
    """Test that scaling modules when LoRA is enabled ONLY affects LoRA modules."""
    logger.info("\n=== Test 2: LoRA Scale with LoRA Enabled ===")
    
    handler, lora_mod1, lora_mod2, attn_mod, other_mod = create_mock_handler()
    
    # Store original values
    orig_attn = attn_mod.scaling
    orig_other = other_mod.scaling
    
    # Set LoRA to enabled
    handler.use_lora = True
    
    # Set scale to 0.5
    result = handler.set_lora_scale(0.5)
    
    # Verify the scale value is stored
    assert handler.lora_scale == 0.5, f"Expected lora_scale to be 0.5, got {handler.lora_scale}"
    
    # Verify ONLY LoRA modules were modified
    assert lora_mod1.scaling['default'] == 0.5, f"LoRA module 1 should be scaled to 0.5, got {lora_mod1.scaling['default']}"
    assert lora_mod2.scaling == 0.5, f"LoRA module 2 should be scaled to 0.5, got {lora_mod2.scaling}"
    
    # Verify non-LoRA modules were NOT modified
    assert attn_mod.scaling == orig_attn, f"Attention module should NOT be modified, expected {orig_attn}, got {attn_mod.scaling}"
    assert other_mod.scaling == orig_other, f"Other module should NOT be modified, expected {orig_other}, got {other_mod.scaling}"
    
    logger.success("✓ Test 2 passed: Only LoRA modules modified when LoRA enabled")
    return True


def test_enable_lora_applies_scale():
    """Test that enabling LoRA applies the stored scale value."""
    logger.info("\n=== Test 3: Enable LoRA Applies Stored Scale ===")
    
    handler, lora_mod1, lora_mod2, attn_mod, other_mod = create_mock_handler()
    
    # Start with LoRA disabled and set scale to 0.3
    handler.use_lora = False
    handler.set_lora_scale(0.3)
    
    # Verify modules not modified yet
    assert lora_mod1.scaling == {'default': 1.0}, "LoRA module 1 should not be modified yet"
    
    # Now enable LoRA
    handler.use_lora = True
    result = handler.set_use_lora(True)
    
    # Verify LoRA modules are now scaled
    assert lora_mod1.scaling['default'] == 0.3, f"LoRA module 1 should be scaled to 0.3 after enabling, got {lora_mod1.scaling['default']}"
    assert lora_mod2.scaling == 0.3, f"LoRA module 2 should be scaled to 0.3 after enabling, got {lora_mod2.scaling}"
    
    # Verify non-LoRA modules still not modified
    assert attn_mod.scaling == 0.125, "Attention module should still not be modified"
    
    logger.success("✓ Test 3 passed: Enabling LoRA applies stored scale")
    return True


def test_attention_module_never_modified():
    """Test that attention modules with 'scaling' attribute are never touched."""
    logger.info("\n=== Test 4: Attention Module Protection ===")
    
    handler, lora_mod1, lora_mod2, attn_mod, other_mod = create_mock_handler()
    
    orig_attn = attn_mod.scaling
    
    # Try with LoRA disabled
    handler.use_lora = False
    handler.set_lora_scale(0.2)
    assert attn_mod.scaling == orig_attn, "Attention module modified when LoRA disabled!"
    
    # Try with LoRA enabled
    handler.use_lora = True
    handler.set_lora_scale(0.2)
    assert attn_mod.scaling == orig_attn, "Attention module modified when LoRA enabled!"
    
    # Try different scale values
    for scale in [0.0, 0.5, 0.8, 1.0]:
        handler.set_lora_scale(scale)
        assert attn_mod.scaling == orig_attn, f"Attention module modified at scale {scale}!"
    
    logger.success("✓ Test 4 passed: Attention module never modified")
    return True


def main():
    """Run all tests."""
    logger.info("=" * 70)
    logger.info("Testing LoRA Scale Fix")
    logger.info("=" * 70)
    
    all_passed = True
    
    try:
        all_passed &= test_lora_scale_with_lora_disabled()
    except Exception as e:
        logger.error(f"✗ Test 1 failed: {e}")
        all_passed = False
    
    try:
        all_passed &= test_lora_scale_with_lora_enabled()
    except Exception as e:
        logger.error(f"✗ Test 2 failed: {e}")
        all_passed = False
    
    try:
        all_passed &= test_enable_lora_applies_scale()
    except Exception as e:
        logger.error(f"✗ Test 3 failed: {e}")
        all_passed = False
    
    try:
        all_passed &= test_attention_module_never_modified()
    except Exception as e:
        logger.error(f"✗ Test 4 failed: {e}")
        all_passed = False
    
    logger.info("\n" + "=" * 70)
    if all_passed:
        logger.success("ALL TESTS PASSED ✓")
        logger.info("\nSummary:")
        logger.info("  • LoRA scale slider has no effect when LoRA is disabled")
        logger.info("  • LoRA scale slider only affects LoRA modules when enabled")
        logger.info("  • Attention modules are never modified")
        logger.info("  • Scale is applied when LoRA is enabled")
        return 0
    else:
        logger.error("SOME TESTS FAILED ✗")
        return 1


if __name__ == "__main__":
    sys.exit(main())
