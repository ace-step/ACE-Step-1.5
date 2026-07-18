"""Unit tests for multi-GPU component device mapping."""

import os
import unittest
from unittest import mock

from acestep.core.generation import device_mapping as dm
from acestep.core.generation.device_mapping import ComponentDeviceMap

_ENV_KEYS = ("ACESTEP_DIT_DEVICE", "ACESTEP_VAE_DEVICE", "ACESTEP_LM_DEVICE")


class _FakeCuda:
    def __init__(self, count, free_by_idx):
        self._count = count
        self._free = free_by_idx

    def is_available(self):
        return True

    def device_count(self):
        return self._count

    def mem_get_info(self, idx=0):
        return (self._free[idx], 16 * 1024 ** 3)


class _FakeTorch:
    def __init__(self, count, free_by_idx):
        self.cuda = _FakeCuda(count, free_by_idx)


def _clear_env():
    for k in _ENV_KEYS:
        os.environ.pop(k, None)


class DeviceMappingTest(unittest.TestCase):
    def setUp(self):
        _clear_env()

    def tearDown(self):
        _clear_env()

    def test_env_overrides_take_precedence_over_ranking(self):
        fake = _FakeTorch(2, {0: 5 * 1024 ** 3, 1: 10 * 1024 ** 3})
        with mock.patch.object(dm, "torch", fake):
            os.environ["ACESTEP_DIT_DEVICE"] = "cuda:0"
            os.environ["ACESTEP_VAE_DEVICE"] = "cuda:0"
            os.environ["ACESTEP_LM_DEVICE"] = "cuda:1"
            m = dm.resolve_component_device_map()
        self.assertEqual(m.dit, "cuda:0")
        self.assertEqual(m.vae, "cuda:0")
        self.assertEqual(m.lm, "cuda:1")

    def test_auto_ranking_by_free_vram(self):
        # idx 1 has more free VRAM -> DiT; idx 0 -> VAE and LM (2 GPUs).
        fake = _FakeTorch(2, {0: 5 * 1024 ** 3, 1: 10 * 1024 ** 3})
        with mock.patch.object(dm, "torch", fake):
            m = dm.resolve_component_device_map()
        self.assertEqual(m.dit, "cuda:1")
        self.assertEqual(m.vae, "cuda:0")
        self.assertEqual(m.lm, "cuda:0")

    def test_single_gpu_maps_all_to_same_device(self):
        fake = _FakeTorch(1, {0: 8 * 1024 ** 3})
        with mock.patch.object(dm, "torch", fake):
            m = dm.resolve_component_device_map()
        self.assertEqual(m.dit, "cuda:0")
        self.assertEqual(m.vae, "cuda:0")
        self.assertEqual(m.lm, "cuda:0")

    def test_no_cuda_returns_empty_map_without_env(self):
        with mock.patch.object(dm, "torch", None):
            m = dm.resolve_component_device_map()
        self.assertEqual(m, ComponentDeviceMap())

    def test_validate_raises_on_out_of_range_index(self):
        fake = _FakeTorch(2, {0: 1, 1: 1})
        with mock.patch.object(dm, "torch", fake):
            with self.assertRaises(ValueError):
                dm.validate_component_device_map(ComponentDeviceMap(dit="cuda:5"))

    def test_validate_passes_on_valid_indices(self):
        fake = _FakeTorch(2, {0: 1, 1: 1})
        with mock.patch.object(dm, "torch", fake):
            dm.validate_component_device_map(
                ComponentDeviceMap(dit="cuda:0", vae="cuda:0", lm="cuda:1")
            )

    def test_hint_is_empty_when_single_device(self):
        fake = _FakeTorch(1, {0: 8 * 1024 ** 3})
        with mock.patch.object(dm, "torch", fake):
            self.assertEqual(dm.format_component_gpu_hint_text(), "")

    def test_hint_non_empty_when_components_differ(self):
        fake = _FakeTorch(2, {0: 5 * 1024 ** 3, 1: 10 * 1024 ** 3})
        with mock.patch.object(dm, "torch", fake):
            hint = dm.format_component_gpu_hint_text(label="GPU map")
        self.assertIn("DiT=cuda:1", hint)
        self.assertIn("LM=cuda:0", hint)


if __name__ == "__main__":
    unittest.main()
