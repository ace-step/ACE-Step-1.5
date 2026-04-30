"""Unit tests for explicit component device mapping helpers."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from acestep.core.generation.device_mapping import (
    ComponentDeviceMap,
    format_component_gpu_hint_text,
    resolve_component_device_map,
    validate_component_device_map,
)


class DeviceMappingTests(unittest.TestCase):
    """Behavior tests for dynamic CUDA mapping and index validation."""

    @patch("torch.cuda.is_available", return_value=True)
    @patch("torch.cuda.device_count", return_value=3)
    @patch("torch.cuda.mem_get_info")
    def test_resolve_component_device_map_auto_populates_when_blank(self, mock_mem_get_info, *_mocks) -> None:
        """Blank mapping should auto-distribute components across discovered CUDA devices."""
        mock_mem_get_info.side_effect = [
            (3 * 1024**3, 4 * 1024**3),  # cuda:0
            (6 * 1024**3, 8 * 1024**3),  # cuda:1
            (4 * 1024**3, 6 * 1024**3),  # cuda:2
        ]
        mapping = resolve_component_device_map()
        self.assertEqual("cuda:1", mapping.dit)
        self.assertEqual("cuda:2", mapping.vae)
        self.assertEqual("cuda:0", mapping.lm)

    @patch("torch.cuda.is_available", return_value=True)
    @patch("torch.cuda.device_count", return_value=1)
    @patch("torch.cuda.mem_get_info", return_value=(8 * 1024**3, 8 * 1024**3))
    def test_resolve_component_device_map_single_gpu_collapses_to_cuda_zero(self, *_mocks) -> None:
        """Single visible GPU should resolve all components onto cuda:0."""
        mapping = resolve_component_device_map()
        self.assertEqual("cuda:0", mapping.dit)
        self.assertEqual("cuda:0", mapping.vae)
        self.assertEqual("cuda:0", mapping.lm)

    @patch("torch.cuda.is_available", return_value=False)
    def test_format_component_gpu_hint_text_hides_hint_without_multi_device(self, *_mocks) -> None:
        """Hint text should be hidden when all components collapse to one device."""
        self.assertEqual("", format_component_gpu_hint_text())

    @patch("torch.cuda.is_available", return_value=True)
    @patch("torch.cuda.device_count", return_value=3)
    @patch("torch.cuda.mem_get_info")
    def test_format_component_gpu_hint_text_includes_mapping_for_multi_gpu(
        self, mock_mem_get_info, *_mocks
    ) -> None:
        """Hint text should show per-component mapping when devices differ."""
        mock_mem_get_info.side_effect = [
            (8 * 1024**3, 8 * 1024**3),  # cuda:0
            (6 * 1024**3, 8 * 1024**3),  # cuda:1
            (4 * 1024**3, 8 * 1024**3),  # cuda:2
        ]
        hint = format_component_gpu_hint_text(label="Mapped GPUs")
        self.assertIn("Mapped GPUs:", hint)
        self.assertIn("DiT=cuda:0", hint)
        self.assertIn("VAE=cuda:1", hint)
        self.assertIn("LM=cuda:2", hint)

    @patch("torch.cuda.is_available", return_value=True)
    @patch("torch.cuda.device_count", return_value=2)
    @patch("torch.cuda.mem_get_info")
    def test_resolve_component_device_map_two_gpu_shares_second_for_vae_and_lm(
        self, mock_mem_get_info, *_mocks
    ) -> None:
        """Two GPUs should assign DiT to top VRAM and share second GPU for VAE/LM."""
        mock_mem_get_info.side_effect = [
            (6 * 1024**3, 8 * 1024**3),  # cuda:0
            (4 * 1024**3, 8 * 1024**3),  # cuda:1
        ]
        mapping = resolve_component_device_map()
        self.assertEqual("cuda:0", mapping.dit)
        self.assertEqual("cuda:1", mapping.vae)
        self.assertEqual("cuda:1", mapping.lm)

    @patch("torch.cuda.is_available", return_value=False)
    def test_resolve_component_device_map_no_cuda_returns_empty(self, *_mocks) -> None:
        """No CUDA availability should keep mapping empty when no explicit map is supplied."""
        self.assertEqual(resolve_component_device_map(), ComponentDeviceMap())

    @patch("torch.cuda.is_available", return_value=True)
    @patch("torch.cuda.device_count", return_value=2)
    def test_validate_component_device_map_accepts_in_range_cuda_index(self, *_mocks) -> None:
        """CUDA device mappings within detected range should pass validation."""
        validate_component_device_map(ComponentDeviceMap(dit="cuda:1"))

    @patch("torch.cuda.is_available", return_value=True)
    @patch("torch.cuda.device_count", return_value=1)
    def test_validate_component_device_map_raises_for_out_of_range_index(self, *_mocks) -> None:
        """Out-of-range CUDA mappings should fail fast with a ValueError."""
        with self.assertRaises(ValueError):
            validate_component_device_map(ComponentDeviceMap(lm="cuda:1"))

    @patch("torch.cuda.is_available", return_value=True)
    @patch("torch.cuda.device_count", return_value=2)
    def test_validate_component_device_map_raises_for_non_integer_index(self, *_mocks) -> None:
        """Malformed CUDA mapping should raise contextual ValueError."""
        with self.assertRaises(ValueError):
            validate_component_device_map(ComponentDeviceMap(lm="cuda:abc"))


if __name__ == "__main__":
    unittest.main()
