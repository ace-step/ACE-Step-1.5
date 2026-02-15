"""Test UUID generation includes LoRA state to prevent file reuse."""
import unittest

from acestep.audio_utils import generate_uuid_from_params


class UuidGenerationTest(unittest.TestCase):
    """Test that UUID generation correctly differentiates LoRA states."""

    def test_different_lora_states_produce_different_uuids(self):
        """Different LoRA states with same other params should produce different UUIDs."""
        base_params = {
            "seed": 3631605787,
            "caption": "A beautiful melody",
            "lyrics": "[Instrumental]",
            "inference_steps": 8,
        }

        # Generate UUID with LoRA disabled
        params_lora_off = base_params.copy()
        params_lora_off["lora_loaded"] = False
        params_lora_off["use_lora"] = False
        params_lora_off["lora_scale"] = 1.0
        uuid_lora_off = generate_uuid_from_params(params_lora_off)

        # Generate UUID with LoRA enabled
        params_lora_on = base_params.copy()
        params_lora_on["lora_loaded"] = True
        params_lora_on["use_lora"] = True
        params_lora_on["lora_scale"] = 1.0
        uuid_lora_on = generate_uuid_from_params(params_lora_on)

        # UUIDs should be different
        self.assertNotEqual(
            uuid_lora_off,
            uuid_lora_on,
            "UUIDs should differ when only LoRA state changes",
        )

    def test_different_lora_scale_produces_different_uuids(self):
        """Different LoRA scales should produce different UUIDs."""
        base_params = {
            "seed": 3631605787,
            "caption": "A beautiful melody",
            "lora_loaded": True,
            "use_lora": True,
        }

        params_scale_0_5 = base_params.copy()
        params_scale_0_5["lora_scale"] = 0.5
        uuid_scale_0_5 = generate_uuid_from_params(params_scale_0_5)

        params_scale_1_0 = base_params.copy()
        params_scale_1_0["lora_scale"] = 1.0
        uuid_scale_1_0 = generate_uuid_from_params(params_scale_1_0)

        # UUIDs should be different
        self.assertNotEqual(
            uuid_scale_0_5,
            uuid_scale_1_0,
            "UUIDs should differ when only LoRA scale changes",
        )

    def test_same_params_produce_same_uuid(self):
        """Same params should always produce the same UUID (deterministic)."""
        params = {
            "seed": 3631605787,
            "caption": "A beautiful melody",
            "lora_loaded": True,
            "use_lora": True,
            "lora_scale": 1.0,
        }

        uuid1 = generate_uuid_from_params(params)
        uuid2 = generate_uuid_from_params(params)

        # UUIDs should be identical
        self.assertEqual(uuid1, uuid2, "Same params should produce same UUID")

    def test_uuid_format_is_valid(self):
        """Generated UUID should follow standard format."""
        params = {
            "seed": 3631605787,
            "lora_loaded": False,
            "use_lora": False,
            "lora_scale": 1.0,
        }

        uuid = generate_uuid_from_params(params)

        # Check format: 8-4-4-4-12
        parts = uuid.split("-")
        self.assertEqual(len(parts), 5, "UUID should have 5 parts")
        self.assertEqual(len(parts[0]), 8, "First part should be 8 chars")
        self.assertEqual(len(parts[1]), 4, "Second part should be 4 chars")
        self.assertEqual(len(parts[2]), 4, "Third part should be 4 chars")
        self.assertEqual(len(parts[3]), 4, "Fourth part should be 4 chars")
        self.assertEqual(len(parts[4]), 12, "Fifth part should be 12 chars")


if __name__ == "__main__":
    unittest.main()
