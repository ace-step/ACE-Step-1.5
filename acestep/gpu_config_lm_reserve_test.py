"""Tests for the duration-aware LM/DiT VRAM reserve in ``gpu_config``.

The LM initializes while the DiT is already resident and claims whatever is
free.  What it leaves behind is what the DiT pre-flight
(``core/generation/handler/generate_music.py``) later demands, and that demand
grows with track length -- these tests pin that both sides use the same
yardstick.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from acestep.gpu_config import (
    DIT_RESERVE_HEADROOM_GB,
    LM_DIT_RESERVE_DURATION_ENV,
    LM_GPU_MEMORY_RATIO_MAX,
    VRAM_SAFETY_MARGIN_GB,
    get_dit_inference_reserve_gb,
    get_dit_max_duration_for_free_vram_s,
    get_lm_gpu_memory_ratio,
    resolve_lm_dit_reserve_duration_s,
)

GB = 1024**3


class DitInferenceReserveTests(unittest.TestCase):
    """The reserve mirrors the pre-flight's demand plus fixed headroom."""

    def test_reserve_grows_with_track_length(self) -> None:
        """A 165s xl-turbo track reserves 2.75x the activations of a 60s one."""
        self.assertAlmostEqual(
            0.5 * 165 / 60 + VRAM_SAFETY_MARGIN_GB + DIT_RESERVE_HEADROOM_GB,
            get_dit_inference_reserve_gb("xl_turbo", 1, 165),
        )

    def test_reserve_scales_with_batch_size(self) -> None:
        """Two samples per forward pass need twice the activations."""
        single = get_dit_inference_reserve_gb("turbo", 1, 240)
        double = get_dit_inference_reserve_gb("turbo", 2, 240)
        fixed_gb = VRAM_SAFETY_MARGIN_GB + DIT_RESERVE_HEADROOM_GB
        self.assertAlmostEqual(2 * (single - fixed_gb), double - fixed_gb)

    def test_tracks_below_a_minute_reserve_like_a_full_minute(self) -> None:
        """The pre-flight's duration factor floors at 1.0, so the reserve does too."""
        self.assertEqual(
            get_dit_inference_reserve_gb("xl_turbo", 1, 60),
            get_dit_inference_reserve_gb("xl_turbo", 1, 20),
        )

    def test_xl_profile_reserves_more_than_the_standard_profile(self) -> None:
        """XL activations are larger, so the same track reserves more."""
        self.assertGreater(
            get_dit_inference_reserve_gb("xl_turbo", 1, 165),
            get_dit_inference_reserve_gb("turbo", 1, 165),
        )

    def test_max_duration_inverts_the_reserve(self) -> None:
        """The supported track length is the reserve formula solved for duration."""
        reserve_gb = get_dit_inference_reserve_gb("xl_turbo", 1, 240)
        self.assertAlmostEqual(
            240.0, get_dit_max_duration_for_free_vram_s("xl_turbo", 1, reserve_gb)
        )

    def test_no_track_fits_when_free_vram_is_below_the_fixed_margins(self) -> None:
        """Free VRAM smaller than the safety margins supports no track at all."""
        self.assertEqual(
            0.0, get_dit_max_duration_for_free_vram_s("xl_turbo", 1, 0.4)
        )


class ResolveReserveDurationTests(unittest.TestCase):
    """Where the reserve's track length comes from when no request exists yet."""

    def _with_tier_max(self, max_duration_with_lm: int) -> MagicMock:
        config = MagicMock()
        config.max_duration_with_lm = max_duration_with_lm
        return config

    def test_falls_back_to_the_tier_maximum(self) -> None:
        """Without an override, the LM reserves for the tier's longest track."""
        with patch.dict(os.environ, {}, clear=False), patch(
            "acestep.gpu_config.get_global_gpu_config",
            return_value=self._with_tier_max(480),
        ):
            os.environ.pop(LM_DIT_RESERVE_DURATION_ENV, None)
            self.assertEqual(480.0, resolve_lm_dit_reserve_duration_s())

    def test_environment_overrides_the_tier_maximum(self) -> None:
        """A deployment that knows its track lengths can reserve for them."""
        with patch.dict(os.environ, {LM_DIT_RESERVE_DURATION_ENV: "240"}), patch(
            "acestep.gpu_config.get_global_gpu_config",
            return_value=self._with_tier_max(480),
        ):
            self.assertEqual(240.0, resolve_lm_dit_reserve_duration_s())

    def test_unusable_override_falls_back_to_the_tier_maximum(self) -> None:
        """Garbage and non-positive overrides are reported, not obeyed."""
        for value in ("not-a-number", "0", "-30"):
            with self.subTest(value=value):
                with patch.dict(
                    os.environ, {LM_DIT_RESERVE_DURATION_ENV: value}
                ), patch(
                    "acestep.gpu_config.get_global_gpu_config",
                    return_value=self._with_tier_max(480),
                ):
                    self.assertEqual(480.0, resolve_lm_dit_reserve_duration_s())


class LmGpuMemoryRatioTests(unittest.TestCase):
    """The ratio hands the DiT the reserve the pre-flight will ask for."""

    def _ratio(
        self,
        *,
        free_gb: float,
        total_gb: float,
        allocated_gb: float,
        lm_model: str = "acestep-5Hz-lm-4B",
        dit_config_path: str = "acestep-v15-xl-turbo",
        duration_s: float = 165,
    ) -> float:
        """Run the ratio computation against a mocked CUDA device."""
        mock_cuda = MagicMock()
        mock_cuda.is_available.return_value = True
        mock_cuda.mem_get_info.return_value = (int(free_gb * GB), int(total_gb * GB))
        mock_cuda.memory_allocated.return_value = int(allocated_gb * GB)
        mock_torch = MagicMock()
        mock_torch.cuda = mock_cuda

        with patch.dict(sys.modules, {"torch": mock_torch}), patch.dict(
            os.environ, {}, clear=False
        ):
            os.environ.pop("MAX_CUDA_VRAM", None)
            ratio, _ = get_lm_gpu_memory_ratio(
                lm_model,
                total_gb,
                dit_config_path=dit_config_path,
                reserve_duration_s=duration_s,
            )
        return ratio

    def _free_after_lm_gb(
        self, ratio: float, total_gb: float, free_gb: float, allocated_gb: float
    ) -> float:
        """Device VRAM left free once nano-vllm has filled *ratio* of the card."""
        untracked_gb = (total_gb - free_gb) - allocated_gb
        return total_gb * (1 - ratio) - untracked_gb

    def test_ratio_leaves_the_duration_aware_reserve_free(self) -> None:
        """Measured RTX 3090 case: a 165s xl-turbo track keeps its reserve free."""
        total_gb, free_gb, allocated_gb = 23.53, 11.56, 10.55
        ratio = self._ratio(
            free_gb=free_gb, total_gb=total_gb, allocated_gb=allocated_gb
        )
        self.assertAlmostEqual(
            get_dit_inference_reserve_gb("xl_turbo", 1, 165),
            self._free_after_lm_gb(ratio, total_gb, free_gb, allocated_gb),
            places=6,
        )

    def test_longer_tracks_leave_more_room_for_the_dit(self) -> None:
        """Reserving for a longer track shrinks the LM's KV cache."""
        total_gb, free_gb, allocated_gb = 23.53, 11.56, 10.55
        short, long = (
            self._free_after_lm_gb(
                self._ratio(
                    free_gb=free_gb,
                    total_gb=total_gb,
                    allocated_gb=allocated_gb,
                    duration_s=duration_s,
                ),
                total_gb,
                free_gb,
                allocated_gb,
            )
            for duration_s in (120, 180)
        )
        self.assertLess(short, long)

    def test_lm_keeps_its_minimum_kv_cache_when_the_reserve_does_not_fit(self) -> None:
        """An unaffordable reserve shrinks the KV cache, never the LM weights."""
        total_gb, free_gb, allocated_gb = 23.53, 11.56, 10.55
        lm_weights_gb, minimum_kv_cache_gb = 8.0, 0.8
        ratio = self._ratio(
            free_gb=free_gb,
            total_gb=total_gb,
            allocated_gb=allocated_gb,
            duration_s=480,
        )
        self.assertAlmostEqual(
            free_gb - lm_weights_gb - minimum_kv_cache_gb,
            self._free_after_lm_gb(ratio, total_gb, free_gb, allocated_gb),
            places=6,
        )

    def test_lm_never_claims_more_than_it_needs(self) -> None:
        """An empty card leaves everything beyond the LM's own target free."""
        total_gb, free_gb, allocated_gb = 80.0, 79.0, 0.5
        lm_footprint_gb = 8.0 + 1.6
        self.assertAlmostEqual(
            free_gb - lm_footprint_gb,
            self._free_after_lm_gb(
                self._ratio(
                    free_gb=free_gb,
                    total_gb=total_gb,
                    allocated_gb=allocated_gb,
                    dit_config_path="acestep-v15-turbo",
                    duration_s=60,
                ),
                total_gb,
                free_gb,
                allocated_gb,
            ),
            places=6,
        )

    def test_capping_the_ratio_is_reported(self) -> None:
        """Silently capping hides that the LM did not get what it asked for."""
        with patch("acestep.gpu_config.logger") as mock_logger:
            ratio = self._ratio(
                free_gb=11.56,
                total_gb=23.53,
                allocated_gb=11.97,
                dit_config_path="acestep-v15-turbo",
                duration_s=60,
            )
        warnings = " ".join(
            str(call.args[0]) for call in mock_logger.warning.call_args_list
        )
        self.assertEqual(LM_GPU_MEMORY_RATIO_MAX, ratio)
        self.assertIn("Capping LM ratio", warnings)

    def test_unaffordable_reserve_is_reported_with_the_supported_duration(self) -> None:
        """The operator learns which track length the card actually supports."""
        with patch("acestep.gpu_config.logger") as mock_logger:
            self._ratio(
                free_gb=11.56, total_gb=23.53, allocated_gb=10.55, duration_s=480
            )
        warnings = " ".join(
            str(call.args[0]) for call in mock_logger.warning.call_args_list
        )
        self.assertIn("Cannot reserve", warnings)
        self.assertIn("supported up to", warnings)


if __name__ == "__main__":
    unittest.main()
