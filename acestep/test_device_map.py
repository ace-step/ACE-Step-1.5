"""Unit tests for multi-GPU device map parsing and resolution."""

import os
import unittest
from unittest.mock import patch

from acestep.device_map import (
    ComponentDeviceMap,
    DeviceMapError,
    GpuInfo,
    LayoutError,
    LayoutRequest,
    compute_auto_device_map,
    cuda_device_index,
    device_type,
    estimate_dit_peak_gb,
    estimate_lm_total_gb,
    is_cuda_device,
    normalize_component_device,
    parse_gpu_mapping,
    resolve_component_device_map,
)


class DeviceMapParsingTests(unittest.TestCase):
    """Tests for mapping string parsing and validation."""

    def test_normalize_component_device_expands_bare_cuda(self):
        self.assertEqual(normalize_component_device("cuda"), "cuda:0")

    def test_normalize_component_device_preserves_cuda_index(self):
        self.assertEqual(normalize_component_device("cuda:2"), "cuda:2")

    def test_parse_gpu_mapping_returns_none_for_empty_and_auto(self):
        self.assertIsNone(parse_gpu_mapping(None, default_device="cuda:0"))
        self.assertIsNone(parse_gpu_mapping("", default_device="cuda:0"))
        self.assertIsNone(parse_gpu_mapping("auto", default_device="cuda:0"))

    def test_parse_gpu_mapping_single_places_all_components_on_index(self):
        device_map = parse_gpu_mapping("single:1", default_device="cuda:0")
        self.assertIsNotNone(device_map)
        assert device_map is not None
        self.assertEqual(device_map.dit, "cuda:1")
        self.assertEqual(device_map.vae, "cuda:1")
        self.assertEqual(device_map.text_encoder, "cuda:1")
        self.assertEqual(device_map.lm, "cuda:1")

    def test_parse_gpu_mapping_explicit_components(self):
        device_map = parse_gpu_mapping(
            "dit:0,vae:0,text_encoder:0,lm:1",
            default_device="cuda:0",
        )
        self.assertIsNotNone(device_map)
        assert device_map is not None
        self.assertEqual(device_map.dit, "cuda:0")
        self.assertEqual(device_map.lm, "cuda:1")
        self.assertTrue(device_map.is_multi_device())

    def test_parse_gpu_mapping_defaults_aux_components_to_dit(self):
        device_map = parse_gpu_mapping("dit:2", default_device="cuda:0")
        self.assertIsNotNone(device_map)
        assert device_map is not None
        self.assertEqual(device_map.dit, "cuda:2")
        self.assertEqual(device_map.vae, "cuda:2")
        self.assertEqual(device_map.text_encoder, "cuda:2")
        self.assertIsNone(device_map.lm)

    def test_parse_gpu_mapping_rejects_unknown_component(self):
        with self.assertRaises(DeviceMapError):
            parse_gpu_mapping("decoder:0", default_device="cuda:0")

    def test_parse_gpu_mapping_rejects_missing_dit(self):
        with self.assertRaises(DeviceMapError):
            parse_gpu_mapping("vae:0,lm:1", default_device="cuda:0")

    def test_parse_gpu_mapping_rejects_unsupported_default_device(self):
        with self.assertRaises(DeviceMapError):
            parse_gpu_mapping("single:0", default_device="unknown-backend")

    def test_parse_gpu_mapping_reads_env_when_argument_missing(self):
        with patch.dict(os.environ, {"ACESTEP_GPU_MAPPING": "single:3"}, clear=False):
            device_map = parse_gpu_mapping(None, default_device="cuda:0")
        self.assertIsNotNone(device_map)
        assert device_map is not None
        self.assertEqual(device_map.dit, "cuda:3")


class DeviceMapResolutionTests(unittest.TestCase):
    """Tests for legacy and explicit device map resolution."""

    def test_resolve_component_device_map_legacy_single_device(self):
        device_map = resolve_component_device_map(
            requested_device="cuda",
            gpu_mapping=None,
        )
        self.assertEqual(device_map.dit, "cuda:0")
        self.assertFalse(device_map.is_multi_device())

    def test_resolve_component_device_map_preserves_requested_index(self):
        device_map = resolve_component_device_map(
            requested_device="cuda:1",
            gpu_mapping=None,
        )
        self.assertEqual(device_map.dit, "cuda:1")
        self.assertEqual(device_map.lm, "cuda:1")

    def test_resolve_component_device_map_auto_uses_multi_gpu_layout(self):
        gpus = [
            GpuInfo(0, "GPU0", 24.0, 22.0),
            GpuInfo(1, "GPU1", 24.0, 23.0),
        ]
        with patch("acestep.device_map.resolve.discover_gpus", return_value=gpus):
            device_map = resolve_component_device_map(
                requested_device="cuda:0",
                gpu_mapping="auto",
                config_path="acestep-v15-xl-sft",
                lm_model_path="acestep-5Hz-lm-4B",
            )
        self.assertEqual(device_map.dit, "cuda:1")
        self.assertEqual(device_map.lm, "cuda:0")
        self.assertTrue(device_map.is_multi_device())

    def test_resolve_component_device_map_auto_falls_back_on_single_gpu(self):
        with patch("acestep.device_map.resolve.discover_gpus", return_value=[GpuInfo(0, "GPU0", 24.0, 22.0)]):
            device_map = resolve_component_device_map(
                requested_device="cuda:0",
                gpu_mapping="auto",
            )
        self.assertEqual(device_map.dit, "cuda:0")
        self.assertFalse(device_map.is_multi_device())


class AutoLayoutTests(unittest.TestCase):
    """Tests for VRAM-aware automatic layout selection."""

    def test_compute_auto_device_map_splits_dit_and_lm(self):
        gpus = [
            GpuInfo(0, "GPU0", 24.0, 10.0),
            GpuInfo(1, "GPU1", 24.0, 23.0),
        ]
        layout = compute_auto_device_map(
            LayoutRequest(
                gpus=gpus,
                dit_type="xl_base",
                lm_model_path="acestep-5Hz-lm-4B",
            )
        )
        self.assertIsInstance(layout, ComponentDeviceMap)
        self.assertEqual(layout.dit, "cuda:1")
        self.assertEqual(layout.lm, "cuda:0")

    def test_compute_auto_device_map_returns_error_when_dit_does_not_fit(self):
        gpus = [GpuInfo(0, "GPU0", 8.0, 2.0)]
        layout = compute_auto_device_map(
            LayoutRequest(gpus=gpus, dit_type="xl_base")
        )
        self.assertIsInstance(layout, LayoutError)
        self.assertIn("No GPU has", layout.message)

    def test_compute_auto_device_map_rejects_same_gpu_lm_without_headroom(self):
        """Co-located LM fallback must reserve the DiT footprint on the shared GPU."""
        gpus = [GpuInfo(0, "GPU0", 24.0, 22.0)]
        layout = compute_auto_device_map(
            LayoutRequest(
                gpus=gpus,
                dit_type="xl_base",
                lm_model_path="acestep-5Hz-lm-4B",
            )
        )
        self.assertIsInstance(layout, LayoutError)
        self.assertIn("No GPU has", layout.message)

    def test_estimate_helpers_use_config_profiles(self):
        self.assertGreater(estimate_dit_peak_gb("xl_base", batch_size=2), estimate_dit_peak_gb("turbo", 1))
        self.assertGreater(
            estimate_lm_total_gb("acestep-5Hz-lm-4B"),
            estimate_lm_total_gb("acestep-5Hz-lm-0.6B"),
        )


class DeviceAliasTests(unittest.TestCase):
    """Tests for CUDA alias helpers."""

    def test_device_for_maps_model_alias_to_dit(self):
        device_map = ComponentDeviceMap.from_single_device("cuda:0")
        self.assertEqual(device_map.device_for("model"), "cuda:0")

    def test_cuda_device_index_helpers(self):
        self.assertTrue(is_cuda_device("cuda:2"))
        self.assertEqual(device_type("cuda:2"), "cuda")
        self.assertEqual(cuda_device_index("cuda"), 0)
        self.assertEqual(cuda_device_index("cuda:2"), 2)


if __name__ == "__main__":
    unittest.main()
