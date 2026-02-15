"""Test UUID generation includes LoRA state to prevent file reuse."""
import os
import tempfile
import unittest

from acestep.audio_utils import generate_uuid_from_params, get_lora_weights_hash


# ---------------------------------------------------------------------------
# Lightweight stub for dit_handler used by get_lora_weights_hash tests
# ---------------------------------------------------------------------------

class _FakeLoraService:
    """Minimal stand-in for LoraService with a registry dict."""

    def __init__(self, registry=None):
        self.registry = registry or {}


class _FakeHandler:
    """Minimal stand-in for a DiT handler with LoRA attributes."""

    def __init__(self, lora_loaded=False, use_lora=False, registry=None):
        self.lora_loaded = lora_loaded
        self.use_lora = use_lora
        self._lora_service = _FakeLoraService(registry)


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

    # ------------------------------------------------------------------
    # get_lora_weights_hash tests
    # ------------------------------------------------------------------

    def test_lora_weights_hash_empty_when_no_lora(self):
        """Hash should be empty when no LoRA is loaded."""
        handler = _FakeHandler(lora_loaded=False, use_lora=False)
        self.assertEqual(get_lora_weights_hash(handler), "")

    def test_lora_weights_hash_empty_when_use_lora_false(self):
        """Hash should be empty when use_lora is False even if loaded."""
        handler = _FakeHandler(lora_loaded=True, use_lora=False)
        self.assertEqual(get_lora_weights_hash(handler), "")

    def test_different_lora_files_produce_different_hashes(self):
        """Two different weight files should yield different hashes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path_a = os.path.join(tmpdir, "lora_a")
            path_b = os.path.join(tmpdir, "lora_b")
            os.makedirs(path_a)
            os.makedirs(path_b)

            # Write distinct fake weight files
            with open(os.path.join(path_a, "adapter_model.safetensors"), "wb") as f:
                f.write(b"weights_A_content_1234")
            with open(os.path.join(path_b, "adapter_model.safetensors"), "wb") as f:
                f.write(b"weights_B_content_5678")

            handler_a = _FakeHandler(
                lora_loaded=True,
                use_lora=True,
                registry={"adapter": {"path": path_a, "targets": []}},
            )
            handler_b = _FakeHandler(
                lora_loaded=True,
                use_lora=True,
                registry={"adapter": {"path": path_b, "targets": []}},
            )

            hash_a = get_lora_weights_hash(handler_a)
            hash_b = get_lora_weights_hash(handler_b)

            self.assertTrue(hash_a, "Hash A should be non-empty")
            self.assertTrue(hash_b, "Hash B should be non-empty")
            self.assertNotEqual(
                hash_a,
                hash_b,
                "Different LoRA weight files must produce different hashes",
            )

    def test_same_lora_file_produces_same_hash(self):
        """Same weight file should produce identical hash on repeated calls."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "lora")
            os.makedirs(path)
            with open(os.path.join(path, "adapter_model.safetensors"), "wb") as f:
                f.write(b"consistent_weights")

            handler = _FakeHandler(
                lora_loaded=True,
                use_lora=True,
                registry={"adapter": {"path": path, "targets": []}},
            )

            self.assertEqual(
                get_lora_weights_hash(handler),
                get_lora_weights_hash(handler),
                "Same LoRA file should produce identical hash",
            )

    def test_lora_weights_hash_differentiates_uuids(self):
        """UUID should differ when only lora_weights_hash changes."""
        base = {"seed": 42, "lora_loaded": True, "use_lora": True, "lora_scale": 1.0}

        params_a = {**base, "lora_weights_hash": "aaa"}
        params_b = {**base, "lora_weights_hash": "bbb"}

        self.assertNotEqual(
            generate_uuid_from_params(params_a),
            generate_uuid_from_params(params_b),
            "UUIDs should differ when lora_weights_hash differs",
        )


class AudioCodesPreservationTest(unittest.TestCase):
    """Test that user-provided audio_codes are not overwritten by empty LM codes.

    Reproduces the logic from inference.py lines 654-658 where
    lm_generated_audio_codes_list may contain empty strings (from
    infer_type='dit') that would incorrectly overwrite user-provided codes.
    """

    @staticmethod
    def _build_audio_params(base_params, lm_codes_list, idx):
        """Replicate the audio_params building logic from inference.py."""
        audio_params = base_params.copy()
        if lm_codes_list and idx < len(lm_codes_list):
            lm_code = lm_codes_list[idx]
            if lm_code and str(lm_code).strip():
                audio_params["audio_codes"] = lm_code
        return audio_params

    def test_user_codes_preserved_when_lm_returns_empty(self):
        """User-provided audio_codes must survive when LM returns empty codes."""
        user_codes = "<|audio_code_1|><|audio_code_2|>"
        base = {"audio_codes": user_codes, "seed": 42}
        # LM ran in "dit" mode → empty string in list
        result = self._build_audio_params(base, [""], 0)
        self.assertEqual(result["audio_codes"], user_codes)

    def test_lm_codes_overwrite_when_non_empty(self):
        """LM-generated codes should overwrite when non-empty."""
        lm_codes = "<|audio_code_99|>"
        base = {"audio_codes": "", "seed": 42}
        result = self._build_audio_params(base, [lm_codes], 0)
        self.assertEqual(result["audio_codes"], lm_codes)

    def test_user_codes_preserved_when_lm_list_empty(self):
        """User codes preserved when lm_generated list is empty."""
        user_codes = "<|audio_code_1|>"
        base = {"audio_codes": user_codes, "seed": 42}
        result = self._build_audio_params(base, [], 0)
        self.assertEqual(result["audio_codes"], user_codes)


if __name__ == "__main__":
    unittest.main()
