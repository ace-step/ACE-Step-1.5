"""Tests for the duration-aware LM/DiT VRAM reserve in ``gpu_config``.

The LM initializes while the DiT is already resident and claims whatever is
free.  What it leaves behind is what the DiT pre-flight
(``core/generation/handler/generate_music.py``) later demands, and that demand
grows with track length -- these tests pin that both sides use the same
yardstick.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from acestep.gpu_config import (
    DIT_RESERVE_HEADROOM_GB,
    LM_CFG_SEQUENCE_COUNT,
    LM_DIT_RESERVE_BATCH_ENV,
    LM_DIT_RESERVE_DEFAULT_BATCH,
    LM_DIT_RESERVE_DURATION_ENV,
    LM_GPU_MEMORY_RATIO_MAX,
    LM_MAX_MODEL_LEN_TOKENS,
    NANO_VLLM_KV_FRACTION,
    NANO_VLLM_MIN_RESERVE_GB,
    VRAM_SAFETY_MARGIN_GB,
    LmKvCacheTooSmallError,
    get_dit_inference_reserve_gb,
    get_dit_max_duration_for_free_vram_s,
    get_lm_gpu_memory_ratio,
    get_lm_kv_cache_bytes_per_token,
    get_lm_kv_cache_floor_gb,
    resolve_lm_dit_reserve_batch,
    resolve_lm_dit_reserve_duration_s,
)

GB = 1024**3

# Shape of the shipped acestep-5Hz-lm-4B checkpoint (Qwen3-4B).
LM_4B_LAYERS, LM_4B_KV_HEADS, LM_4B_HEAD_DIM = 36, 8, 128


def write_lm_checkpoint(
    root: str,
    name: str = "acestep-5Hz-lm-4B",
    num_hidden_layers: int = LM_4B_LAYERS,
    num_key_value_heads: int = LM_4B_KV_HEADS,
    head_dim: int = LM_4B_HEAD_DIM,
    dtype: str = "bfloat16",
) -> str:
    """Write a checkpoint directory with the config fields the KV math reads."""
    path = Path(root) / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "config.json").write_text(
        json.dumps(
            {
                "num_hidden_layers": num_hidden_layers,
                "num_key_value_heads": num_key_value_heads,
                "head_dim": head_dim,
                "dtype": dtype,
            }
        ),
        encoding="utf-8",
    )
    return str(path)


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


class ResolveReserveBatchTests(unittest.TestCase):
    """Deployments that generate several samples per request size for that."""

    def test_defaults_to_a_single_sample(self) -> None:
        """The common case is one sample per request."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(LM_DIT_RESERVE_BATCH_ENV, None)
            self.assertEqual(LM_DIT_RESERVE_DEFAULT_BATCH, resolve_lm_dit_reserve_batch())

    def test_environment_sets_the_reserved_batch_size(self) -> None:
        """A batch deployment can reserve for its real batch size."""
        with patch.dict(os.environ, {LM_DIT_RESERVE_BATCH_ENV: "4"}):
            self.assertEqual(4, resolve_lm_dit_reserve_batch())

    def test_unusable_override_falls_back_to_one_sample(self) -> None:
        """Garbage and non-positive batch sizes are reported, not obeyed."""
        for value in ("not-a-number", "0", "-2", "1.5"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {LM_DIT_RESERVE_BATCH_ENV: value}):
                    self.assertEqual(
                        LM_DIT_RESERVE_DEFAULT_BATCH, resolve_lm_dit_reserve_batch()
                    )


class LmKvCacheFloorTests(unittest.TestCase):
    """The KV cache floor is what nano-vllm's scheduler actually needs."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.checkpoint = write_lm_checkpoint(self._tmp.name)

    def test_bytes_per_token_follows_the_checkpoint_shape(self) -> None:
        """Key and value, for every layer and key/value head, in the model dtype."""
        self.assertEqual(
            2 * LM_4B_LAYERS * LM_4B_KV_HEADS * LM_4B_HEAD_DIM * 2,
            get_lm_kv_cache_bytes_per_token(self.checkpoint),
        )

    def test_float32_checkpoints_cost_twice_as_much_per_token(self) -> None:
        """The KV cache is stored in the checkpoint's dtype."""
        wide = write_lm_checkpoint(
            self._tmp.name, name="acestep-5Hz-lm-4B-fp32", dtype="float32"
        )
        self.assertEqual(
            2 * get_lm_kv_cache_bytes_per_token(self.checkpoint),
            get_lm_kv_cache_bytes_per_token(wide),
        )

    def test_floor_covers_a_cfg_pair_of_full_context_windows(self) -> None:
        """CFG schedules the conditional and unconditional sequence together."""
        bytes_per_token = get_lm_kv_cache_bytes_per_token(self.checkpoint)
        expected_gb = (
            LM_CFG_SEQUENCE_COUNT * LM_MAX_MODEL_LEN_TOKENS * bytes_per_token / GB
        )
        self.assertAlmostEqual(
            expected_gb, get_lm_kv_cache_floor_gb(self.checkpoint, 24.0), places=6
        )

    def test_unreadable_checkpoint_falls_back_to_the_empirical_estimate(self) -> None:
        """A missing config.json must not make the floor silently zero."""
        self.assertEqual(
            0.8, get_lm_kv_cache_floor_gb("acestep-5Hz-lm-4B", 24.0)
        )


class LmGpuMemoryRatioTests(unittest.TestCase):
    """The ratio hands the DiT the reserve the pre-flight will ask for."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.checkpoint = write_lm_checkpoint(self._tmp.name)
        self.kv_cache_floor_gb = get_lm_kv_cache_floor_gb(self.checkpoint, 24.0)

    def _ratio(
        self,
        *,
        free_gb: float,
        total_gb: float,
        allocated_gb: float,
        dit_config_path: str = "acestep-v15-xl-turbo",
        duration_s: float = 165,
        batch_size: int | None = 1,
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
                self.checkpoint,
                total_gb,
                dit_config_path=dit_config_path,
                batch_size=batch_size,
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
        """An unaffordable reserve shrinks the KV cache to its floor, never the weights."""
        total_gb, free_gb, allocated_gb = 23.53, 11.56, 10.55
        lm_weights_gb = 8.0
        ratio = self._ratio(
            free_gb=free_gb,
            total_gb=total_gb,
            allocated_gb=allocated_gb,
            duration_s=480,
        )
        self.assertAlmostEqual(
            free_gb - lm_weights_gb - self.kv_cache_floor_gb,
            self._free_after_lm_gb(ratio, total_gb, free_gb, allocated_gb),
            places=6,
        )

    def test_lm_init_fails_when_the_kv_cache_floor_does_not_fit(self) -> None:
        """Better a clear refusal now than `Insufficient KV cache` mid-generation."""
        with self.assertRaises(LmKvCacheTooSmallError) as raised:
            self._ratio(
                free_gb=8.5, total_gb=23.53, allocated_gb=14.5, duration_s=165
            )
        self.assertIn("KV cache", str(raised.exception))

    def test_lm_init_fails_when_nano_vllm_caps_undercut_the_floor(self) -> None:
        """nano-vllm keeps its own reserve, so raw headroom over the floor is not enough."""
        lm_weights_gb = 8.0
        # Headroom above the floor, but below what nano-vllm will hand out.
        free_gb = lm_weights_gb + self.kv_cache_floor_gb + 0.5
        deliverable_gb = (
            free_gb - lm_weights_gb - NANO_VLLM_MIN_RESERVE_GB
        ) * NANO_VLLM_KV_FRACTION
        self.assertGreater(free_gb - lm_weights_gb, self.kv_cache_floor_gb)
        self.assertLess(deliverable_gb, self.kv_cache_floor_gb)

        with self.assertRaises(LmKvCacheTooSmallError) as raised:
            self._ratio(
                free_gb=free_gb, total_gb=23.53, allocated_gb=12.0, duration_s=165
            )
        self.assertIn("nano-vllm can spend", str(raised.exception))

    def test_reserving_for_a_batch_shrinks_the_lm_further(self) -> None:
        """A batch deployment reserves activations for every sample."""
        total_gb, free_gb, allocated_gb = 23.53, 11.56, 10.55
        single, paired = (
            self._free_after_lm_gb(
                self._ratio(
                    free_gb=free_gb,
                    total_gb=total_gb,
                    allocated_gb=allocated_gb,
                    duration_s=60,
                    batch_size=batch_size,
                ),
                total_gb,
                free_gb,
                allocated_gb,
            )
            for batch_size in (1, 2)
        )
        self.assertAlmostEqual(
            get_dit_inference_reserve_gb("xl_turbo", 2, 60), paired, places=6
        )
        self.assertGreater(paired, single)

    def test_batch_size_comes_from_the_environment_when_unset(self) -> None:
        """The reserve lever applies without every caller passing a batch size."""
        total_gb, free_gb, allocated_gb = 23.53, 11.56, 10.55
        with patch.dict(os.environ, {LM_DIT_RESERVE_BATCH_ENV: "2"}):
            free_after_gb = self._free_after_lm_gb(
                self._ratio(
                    free_gb=free_gb,
                    total_gb=total_gb,
                    allocated_gb=allocated_gb,
                    duration_s=60,
                    batch_size=None,
                ),
                total_gb,
                free_gb,
                allocated_gb,
            )
        self.assertAlmostEqual(
            get_dit_inference_reserve_gb("xl_turbo", 2, 60), free_after_gb, places=6
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
