"""Unit tests for explicit component device mapping helpers."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from acestep.core.generation.device_mapping import (
    ComponentDeviceMap,
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
    def test_resolve_component_device_map_single_gpu_collapses_to_cuda_zero(self, *_mocks) -> None:
        """Single visible GPU should resolve all components onto cuda:0."""
        mapping = resolve_component_device_map()
        self.assertEqual("cuda:0", mapping.dit)
        self.assertEqual("cuda:0", mapping.vae)
        self.assertEqual("cuda:0", mapping.lm)

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


if __name__ == "__main__":
    unittest.main()
