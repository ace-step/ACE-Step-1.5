"""Unit tests for generation setup assembly helpers."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from acestep.api.job_generation_setup import build_generation_setup


def _base_req() -> SimpleNamespace:
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


class JobGenerationSetupTests(unittest.TestCase):
    """Behavioral tests for generation setup decomposition."""

    def test_build_generation_setup_applies_complete_instruction_template(self) -> None:
        """Complete task should inject uppercased track classes into instruction."""

        req = _base_req()
        req.task_type = "complete"
        req.track_classes = ["Drums", "Bass"]
        task_instructions = {
            "complete": "Complete with {TRACK_CLASSES}",
            "complete_default": "Complete default",
        }
        setup = build_generation_setup(
            req=req,
            caption="cap",
            lyrics="lyr",
            bpm=120,
            key_scale="C major",
            time_signature="4/4",
            audio_duration=10.0,
            thinking=False,
            sample_mode=False,
            format_has_duration=False,
            use_cot_caption=True,
            use_cot_language=True,
            lm_top_k=0,
            lm_top_p=0.9,
            parse_timesteps=lambda _value: None,
            is_instrumental=lambda _lyrics: False,
            default_dit_instruction="default instruction",
            task_instructions=task_instructions,
        )

        self.assertEqual("Complete with DRUMS | BASS", setup.params.instruction)
        self.assertTrue(setup.params.use_cot_metas)

    def test_build_generation_setup_applies_track_name_template(self) -> None:
        """Extract/lego style template should inject uppercased track name."""

        req = _base_req()
        req.task_type = "extract"
        req.track_name = "vocals"
        task_instructions = {"extract": "Extract {TRACK_NAME}"}
        setup = build_generation_setup(
            req=req,
            caption="cap",
            lyrics="lyr",
            bpm=None,
            key_scale="",
            time_signature="",
            audio_duration=None,
            thinking=True,
            sample_mode=True,
            format_has_duration=True,
            use_cot_caption=False,
            use_cot_language=False,
            lm_top_k=10,
            lm_top_p=0.8,
            parse_timesteps=lambda _value: [0.1, 0.5],
            is_instrumental=lambda _lyrics: True,
            default_dit_instruction="default instruction",
            task_instructions=task_instructions,
        )

        self.assertEqual("Extract VOCALS", setup.params.instruction)
        self.assertFalse(setup.params.use_cot_metas)
        self.assertEqual([0.1, 0.5], setup.params.timesteps)
        # When audio_duration is None, the auto-sentinel (-1.0) is passed
        # so the LM CoT phase can auto-calculate duration from lyrics.
        from acestep.api.job_generation_setup import _AUTO_DURATION_SENTINEL
        self.assertEqual(_AUTO_DURATION_SENTINEL, setup.params.duration)

    def test_build_generation_setup_resolves_seed_list_from_string(self) -> None:
        """Seed strings should keep valid values and drop invalid or sentinel values."""

        req = _base_req()
        req.use_random_seed = False
        req.seed = "12, -1, 13.0, bad"
        setup = build_generation_setup(
            req=req,
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
            parse_timesteps=lambda _value: None,
            is_instrumental=lambda _lyrics: False,
            default_dit_instruction="default instruction",
            task_instructions={},
        )

        self.assertEqual([12, 13], setup.config.seeds)

    def test_build_generation_setup_forwards_audio_codes_and_cover_noise_strength(self) -> None:
        """Audio code hints and cover-noise strength should be forwarded unchanged."""

        req = _base_req()
        req.audio_code_string = "<|audio_code_42|>"
        req.cover_noise_strength = 0.42
        setup = build_generation_setup(
            req=req,
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
            parse_timesteps=lambda _value: None,
            is_instrumental=lambda _lyrics: False,
            default_dit_instruction="default instruction",
            task_instructions={},
        )

        self.assertEqual("<|audio_code_42|>", setup.params.audio_codes)
        self.assertAlmostEqual(0.42, setup.params.cover_noise_strength)


    def test_auto_duration_sentinel_passes_through(self) -> None:
        """duration=-1 or None should pass auto-sentinel, not hardcoded 120s."""

        from acestep.api.job_generation_setup import _AUTO_DURATION_SENTINEL

        for duration_input in (None, -1, -1.0, 0):
            with self.subTest(duration_input=duration_input):
                req = _base_req()
                setup = build_generation_setup(
                    req=req,
                    caption="cap",
                    lyrics="lyr",
                    bpm=None,
                    key_scale="",
                    time_signature="",
                    audio_duration=duration_input,
                    thinking=False,
                    sample_mode=False,
                    format_has_duration=False,
                    use_cot_caption=True,
                    use_cot_language=True,
                    lm_top_k=0,
                    lm_top_p=0.9,
                    parse_timesteps=lambda _value: None,
                    is_instrumental=lambda _lyrics: False,
                    default_dit_instruction="default instruction",
                    task_instructions={},
                )
                self.assertEqual(_AUTO_DURATION_SENTINEL, setup.params.duration)
                # use_cot_metas must be True so the LM can auto-calculate
                self.assertTrue(setup.params.use_cot_metas)

    def test_explicit_duration_passes_through(self) -> None:
        """Explicit positive duration should be forwarded unchanged."""

        req = _base_req()
        setup = build_generation_setup(
            req=req,
            caption="cap",
            lyrics="lyr",
            bpm=120,
            key_scale="C major",
            time_signature="4",
            audio_duration=45.0,
            thinking=False,
            sample_mode=False,
            format_has_duration=False,
            use_cot_caption=True,
            use_cot_language=True,
            lm_top_k=0,
            lm_top_p=0.9,
            parse_timesteps=lambda _value: None,
            is_instrumental=lambda _lyrics: False,
            default_dit_instruction="default instruction",
            task_instructions={},
        )
        self.assertEqual(45.0, setup.params.duration)

    def test_use_cot_metas_enabled_when_format_has_duration(self) -> None:
        """use_cot_metas should remain True even when format produced duration,
        so the LM can still fill missing bpm/key_scale/time_signature."""

        req = _base_req()
        setup = build_generation_setup(
            req=req,
            caption="cap",
            lyrics="lyr",
            bpm=None,
            key_scale="",
            time_signature="",
            audio_duration=30.0,
            thinking=False,
            sample_mode=False,
            format_has_duration=True,
            use_cot_caption=True,
            use_cot_language=True,
            lm_top_k=0,
            lm_top_p=0.9,
            parse_timesteps=lambda _value: None,
            is_instrumental=lambda _lyrics: False,
            default_dit_instruction="default instruction",
            task_instructions={},
        )
        # Even with format_has_duration=True, use_cot_metas should be True
        # so LM can fill missing bpm/key/time_signature
        self.assertTrue(setup.params.use_cot_metas)


if __name__ == "__main__":
    unittest.main()
