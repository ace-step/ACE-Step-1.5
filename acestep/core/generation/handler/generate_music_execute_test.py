"""Unit tests for ``generate_music`` execution helper mixin."""

import unittest
from unittest.mock import patch

from acestep.core.generation.handler import generate_music_execute as execute_module
from acestep.core.generation.handler.generate_music_execute import GenerateMusicExecuteMixin


class _Host(GenerateMusicExecuteMixin):
    """Minimal host implementing progress/service stubs for execute helper tests."""

    def __init__(self):
        """Capture calls for assertions."""
        self.started = False
        self.stopped = False
        self.service_calls = 0

    def _start_diffusion_progress_estimator(self, **kwargs):
        """Return fake stop event/thread handles used by helper lifecycle."""
        _ = kwargs
        self.started = True

        class _Stop:
            """Minimal stop-event stand-in used by the test host."""

            def __init__(self, host):
                """Bind host state so ``set`` can mark stop lifecycle completion."""
                self.host = host

            def set(self):
                """Mark progress lifecycle as stopped."""
                self.host.stopped = True

        class _Thread:
            """Minimal thread stand-in exposing a ``join`` method."""

            def join(self, timeout=None):
                """Accept join calls without background threading."""
                _ = timeout

        return _Stop(self), _Thread()

    def service_generate(self, **kwargs):
        """Record service invocation and return minimal output payload."""
        _ = kwargs
        self.service_calls += 1
        return {"target_latents": "ok"}


class GenerateMusicExecuteMixinTests(unittest.TestCase):
    """Verify progress lifecycle and service forwarding behavior."""

    def test_run_service_with_progress_invokes_service_and_stops_estimator(self):
        """Helper should call service once and always stop progress estimator."""
        host = _Host()
        out = host._run_generate_music_service_with_progress(
            progress=lambda *args, **kwargs: None,
            actual_batch_size=1,
            audio_duration=10.0,
            inference_steps=8,
            timesteps=None,
            service_inputs={
                "captions_batch": ["c"],
                "lyrics_batch": ["l"],
                "metas_batch": ["m"],
                "vocal_languages_batch": ["en"],
                "target_wavs_tensor": None,
                "repainting_start_batch": [0.0],
                "repainting_end_batch": [1.0],
                "instructions_batch": ["i"],
                "audio_code_hints_batch": None,
                "should_return_intermediate": True,
            },
            refer_audios=None,
            guidance_scale=7.0,
            actual_seed_list=[1],
            audio_cover_strength=1.0,
            cover_noise_strength=0.0,
            use_adg=False,
            cfg_interval_start=0.0,
            cfg_interval_end=1.0,
            shift=1.0,
            infer_method="ode",
        )
        self.assertTrue(host.started)
        self.assertTrue(host.stopped)
        self.assertEqual(host.service_calls, 1)
        self.assertEqual(out["outputs"]["target_latents"], "ok")

    def test_run_service_with_progress_raises_timeout_and_stops_estimator(self):
        """A service call still running at the deadline raises TimeoutError and stops progress."""
        host = _Host()
        with patch.object(execute_module, "run_on_service_thread", return_value=False):
            with self.assertRaises(TimeoutError):
                host._run_generate_music_service_with_progress(
                    progress=lambda *args, **kwargs: None,
                    actual_batch_size=1,
                    audio_duration=10.0,
                    inference_steps=8,
                    timesteps=None,
                    service_inputs={},
                    refer_audios=None,
                    guidance_scale=7.0,
                    actual_seed_list=[1],
                    audio_cover_strength=1.0,
                    cover_noise_strength=0.0,
                    use_adg=False,
                    cfg_interval_start=0.0,
                    cfg_interval_end=1.0,
                    shift=1.0,
                    infer_method="ode",
                )
        self.assertTrue(host.stopped)


if __name__ == "__main__":
    unittest.main()
