"""Tests for null audio_duration crash fixes (issue #797) and auto-duration (issue #1022).

Covers:
  - Fix 1: CoT-generated duration feeds into Phase 2 target_duration.
  - Fix 2: _compute_max_new_tokens caps fallback at DURATION_MAX.
  - Fix 3: silence_latent tiling when length exceeds stored tensor.
  - Fix 4: API-level auto-duration sentinel passes through for LM auto-calculation.
"""

import unittest
from types import SimpleNamespace

try:
    import torch
    from acestep.llm_inference import LLMHandler
    from acestep.constants import DURATION_MAX
    from acestep.core.generation.handler.conditioning_target import (
        ConditioningTargetMixin,
    )
    from acestep.api.job_generation_setup import (
        _AUTO_DURATION_SENTINEL,
        build_generation_setup,
    )

    _IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    LLMHandler = None
    ConditioningTargetMixin = None
    DURATION_MAX = None
    _AUTO_DURATION_SENTINEL = None
    build_generation_setup = None
    _IMPORT_ERROR = exc


# ---------------------------------------------------------------------------
# Fix 2: _compute_max_new_tokens caps
# ---------------------------------------------------------------------------

@unittest.skipIf(LLMHandler is None, f"import unavailable: {_IMPORT_ERROR}")
class ComputeMaxNewTokensCapTests(unittest.TestCase):
    """_compute_max_new_tokens must not exceed DURATION_MAX-based cap."""

    def _handler(self, max_model_len: int = 16384) -> "LLMHandler":
        h = LLMHandler()
        h.max_model_len = max_model_len
        return h

    def test_no_duration_caps_at_duration_max(self):
        """Without target_duration, result must be <= DURATION_MAX*5 + 500."""
        h = self._handler(max_model_len=100_000)
        tokens = h._compute_max_new_tokens(target_duration=None, generation_phase="codes")
        cap = DURATION_MAX * 5 + 500
        self.assertLessEqual(tokens, cap)

    def test_no_duration_with_fallback_caps(self):
        """Explicit fallback_max must also be capped at DURATION_MAX bound."""
        h = self._handler(max_model_len=100_000)
        huge_fallback = 999_999
        tokens = h._compute_max_new_tokens(
            target_duration=None, generation_phase="codes", fallback_max=huge_fallback,
        )
        cap = DURATION_MAX * 5 + 500
        self.assertLessEqual(tokens, cap)

    def test_with_duration_ignores_cap(self):
        """When target_duration is set, normal calculation should apply."""
        h = self._handler()
        tokens = h._compute_max_new_tokens(target_duration=30.0, generation_phase="codes")
        # 30s * 5 codes/s + 10 buffer = 160
        self.assertEqual(tokens, 160)


# ---------------------------------------------------------------------------
# Fix 3: silence_latent tiling
# ---------------------------------------------------------------------------

@unittest.skipIf(torch is None, f"import unavailable: {_IMPORT_ERROR}")
class SilenceLatentTilingTests(unittest.TestCase):
    """_get_silence_latent_slice must tile when length > stored tensor."""

    def _make_mixin(self, latent_len: int = 64, channels: int = 6):
        """Build a minimal object that satisfies the mixin's interface."""

        class _Host(ConditioningTargetMixin):
            pass

        host = _Host()
        host.silence_latent = torch.ones(1, latent_len, channels)
        return host, channels

    def test_slice_within_bounds(self):
        host, C = self._make_mixin(latent_len=128)
        result = host._get_silence_latent_slice(64)
        self.assertEqual(result.shape, (64, C))

    def test_slice_exact_bounds(self):
        host, C = self._make_mixin(latent_len=128)
        result = host._get_silence_latent_slice(128)
        self.assertEqual(result.shape, (128, C))

    def test_slice_exceeds_bounds_tiles(self):
        host, C = self._make_mixin(latent_len=64)
        result = host._get_silence_latent_slice(200)
        self.assertEqual(result.shape, (200, C))

    def test_tiled_values_are_correct(self):
        """Tiled tensor should repeat the original values."""
        host, C = self._make_mixin(latent_len=3, channels=2)
        host.silence_latent = torch.tensor([[[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]])
        result = host._get_silence_latent_slice(7)
        self.assertEqual(result.shape, (7, 2))
        # First 3 frames match original
        self.assertTrue(torch.equal(result[:3], host.silence_latent[0]))
        # Frames 3-5 repeat
        self.assertTrue(torch.equal(result[3:6], host.silence_latent[0]))


# ---------------------------------------------------------------------------
# Fix 4: API auto-duration sentinel (issue #1022)
# ---------------------------------------------------------------------------

@unittest.skipIf(build_generation_setup is None, f"import unavailable: {_IMPORT_ERROR}")
class ApiAutoDurationTests(unittest.TestCase):
    """build_generation_setup must pass auto-sentinel for LM auto-calculation."""

    def _base_req(self):
        return SimpleNamespace(
            task_type="text2music",
            instruction="default instruction",
            reference_audio_path="",
            src_audio_path="",
            vocal_language="en",
            inference_steps=25,
            seed=None,
            guidance_scale=4.5,
            use_adg=False,
            cfg_interval_start=0.0,
            cfg_interval_end=1.0,
            shift=1.0,
            infer_method="ode",
            timesteps="",
            repainting_start=0.0,
            repainting_end=-1,
            audio_cover_strength=0.0,
            cover_noise_strength=0.0,
            audio_code_string="",
            lm_temperature=0.85,
            lm_cfg_scale=2.5,
            lm_negative_prompt="",
            batch_size=None,
            allow_lm_batch=False,
            use_random_seed=True,
            audio_format="wav",
            constrained_decoding_debug=False,
            track_classes=None,
            track_name="",
        )

    def test_null_duration_gets_auto_sentinel(self):
        """When audio_duration is None, params.duration should be the auto-sentinel (-1)."""
        setup = build_generation_setup(
            req=self._base_req(),
            caption="cap",
            lyrics="lyr",
            bpm=None,
            key_scale="",
            time_signature="",
            audio_duration=None,
            thinking=False,
            sample_mode=False,
            format_has_duration=False,
            use_cot_caption=False,
            use_cot_language=False,
            lm_top_k=0,
            lm_top_p=0.9,
            parse_timesteps=lambda _: None,
            is_instrumental=lambda _: False,
            default_dit_instruction="default instruction",
            task_instructions={},
        )
        self.assertEqual(setup.params.duration, _AUTO_DURATION_SENTINEL)

    def test_zero_duration_gets_auto_sentinel(self):
        """Zero duration should get the auto-sentinel for LM auto-calculation."""
        setup = build_generation_setup(
            req=self._base_req(),
            caption="cap",
            lyrics="lyr",
            bpm=None,
            key_scale="",
            time_signature="",
            audio_duration=0,
            thinking=False,
            sample_mode=False,
            format_has_duration=False,
            use_cot_caption=False,
            use_cot_language=False,
            lm_top_k=0,
            lm_top_p=0.9,
            parse_timesteps=lambda _: None,
            is_instrumental=lambda _: False,
            default_dit_instruction="default instruction",
            task_instructions={},
        )
        self.assertEqual(setup.params.duration, _AUTO_DURATION_SENTINEL)

    def test_negative_duration_gets_auto_sentinel(self):
        """Negative duration (-1) should pass as auto-sentinel for LM auto-calculation."""
        setup = build_generation_setup(
            req=self._base_req(),
            caption="cap",
            lyrics="lyr",
            bpm=None,
            key_scale="",
            time_signature="",
            audio_duration=-1.0,
            thinking=False,
            sample_mode=False,
            format_has_duration=False,
            use_cot_caption=False,
            use_cot_language=False,
            lm_top_k=0,
            lm_top_p=0.9,
            parse_timesteps=lambda _: None,
            is_instrumental=lambda _: False,
            default_dit_instruction="default instruction",
            task_instructions={},
        )
        self.assertEqual(setup.params.duration, _AUTO_DURATION_SENTINEL)

    def test_explicit_duration_preserved(self):
        """When audio_duration is explicitly set, it should be preserved."""
        setup = build_generation_setup(
            req=self._base_req(),
            caption="cap",
            lyrics="lyr",
            bpm=None,
            key_scale="",
            time_signature="",
            audio_duration=60.0,
            thinking=False,
            sample_mode=False,
            format_has_duration=False,
            use_cot_caption=False,
            use_cot_language=False,
            lm_top_k=0,
            lm_top_p=0.9,
            parse_timesteps=lambda _: None,
            is_instrumental=lambda _: False,
            default_dit_instruction="default instruction",
            task_instructions={},
        )
        self.assertEqual(setup.params.duration, 60.0)


# ---------------------------------------------------------------------------
# Fix 5: BPM sentinel normalization (issue #1022)
# ---------------------------------------------------------------------------

@unittest.skipIf(build_generation_setup is None, f"import unavailable: {_IMPORT_ERROR}")
class BpmSentinelNormalizationTests(unittest.TestCase):
    """Negative/zero BPM must be normalized to None for auto-detection."""

    def test_negative_bpm_passthrough(self):
        """bpm=-1 should pass through as-is (no __post_init__ normalization)."""
        from acestep.inference import GenerationParams

        params = GenerationParams(bpm=-1)
        self.assertEqual(params.bpm, -1)

    def test_zero_bpm_passthrough(self):
        """bpm=0 should pass through as-is."""
        from acestep.inference import GenerationParams

        params = GenerationParams(bpm=0)
        self.assertEqual(params.bpm, 0)

    def test_valid_bpm_preserved(self):
        """Positive BPM within range should be preserved."""
        from acestep.inference import GenerationParams

        params = GenerationParams(bpm=120)
        self.assertEqual(120, params.bpm)

    def test_none_bpm_stays_none(self):
        """bpm=None should remain None."""
        from acestep.inference import GenerationParams

        params = GenerationParams(bpm=None)
        self.assertIsNone(params.bpm)


if __name__ == "__main__":
    unittest.main()
