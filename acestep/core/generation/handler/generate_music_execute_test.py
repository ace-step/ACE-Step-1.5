"""Unit tests for ``generate_music`` execution helper mixin."""

import unittest
import time
import threading

from acestep.core.generation.handler.generate_music_execute import GenerateMusicExecuteMixin


class _Host(GenerateMusicExecuteMixin):
    """Minimal host implementing progress/service stubs for execute helper tests."""

    def __init__(self):
        """Capture calls for assertions."""
        self.started = False
        self.stopped = False
        self.stop_calls = 0
        self.service_calls = 0
        self.emit_runtime_progress = True
        self.estimator_progress_values = []
        self.service_delay_sec = 0.0

    def _start_diffusion_progress_estimator(self, **kwargs):
        """Return fake stop event/thread handles used by helper lifecycle."""
        self.started = True
        progress = kwargs["progress"]
        desc = kwargs["desc"]
        for value in self.estimator_progress_values:
            progress(value, desc=desc)

        class _Stop:
            """Minimal stop-event stand-in used by the test host."""

            def __init__(self, host):
                """Bind host state so ``set`` can mark stop lifecycle completion."""
                self.host = host

            def set(self):
                """Mark progress lifecycle as stopped."""
                self.host.stopped = True
                self.host.stop_calls += 1

        class _Thread:
            """Minimal thread stand-in exposing a ``join`` method."""

            def join(self, timeout=None):
                """Accept join calls without background threading."""
                _ = timeout

        return _Stop(self), _Thread()

    def service_generate(self, **kwargs):
        """Record service invocation and return minimal output payload."""
        callback = kwargs.get("progress_callback")
        self.service_calls += 1
        if self.service_delay_sec > 0:
            time.sleep(self.service_delay_sec)
        if callback is not None and self.emit_runtime_progress:
            callback(1, 4, "DiT diffusion...")
            callback(4, 4, "DiT diffusion...")
        return {"target_latents": "ok"}


class GenerateMusicExecuteMixinTests(unittest.TestCase):
    """Verify progress lifecycle and service forwarding behavior."""

    def test_run_service_with_progress_invokes_service_and_stops_estimator(self):
        """Helper should call service once and always stop progress estimator."""
        host = _Host()
        host.emit_runtime_progress = False
        host.estimator_progress_values = [0.63, 0.79]
        updates = []
        out = host._run_generate_music_service_with_progress(
            progress=lambda value, desc=None: updates.append((value, desc)),
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
        self.assertEqual(host.stop_calls, 1)
        self.assertEqual(host.service_calls, 1)
        self.assertEqual(out["outputs"]["target_latents"], "ok")
        self.assertAlmostEqual(updates[-1][0], 0.79, places=6)

    def test_runtime_progress_events_are_forwarded_to_ui_progress(self):
        """Step-level runtime progress should stop the estimator and reach phase completion."""
        host = _Host()
        updates = []

        host._run_generate_music_service_with_progress(
            progress=lambda value, desc=None: updates.append((value, desc)),
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

        self.assertTrue(any(desc == "DiT diffusion..." for _, desc in updates))
        self.assertEqual(host.stop_calls, 2)
        self.assertAlmostEqual(updates[-1][0], 0.79, places=6)

    def test_runtime_progress_handoff_stays_monotonic_after_estimator_advances(self):
        """Runtime callbacks should not drive the UI backwards after estimator progress."""
        host = _Host()
        host.estimator_progress_values = [0.68]
        updates = []

        host._run_generate_music_service_with_progress(
            progress=lambda value, desc=None: updates.append((value, desc)),
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

        progress_values = [value for value, _ in updates]
        self.assertEqual(progress_values, sorted(progress_values))
        self.assertGreaterEqual(progress_values[2], 0.68)

    def test_runtime_progress_does_not_publish_behind_blocked_estimator_callback(self):
        """A blocked estimator callback should not allow a stale publish after runtime progress."""

        class _AsyncEstimatorHost(_Host):
            def _start_diffusion_progress_estimator(self, **kwargs):
                self.started = True
                progress = kwargs["progress"]
                desc = kwargs["desc"]

                class _Stop:
                    def __init__(self, host):
                        self.host = host

                    def set(self):
                        self.host.stopped = True
                        self.host.stop_calls += 1

                thread = threading.Thread(
                    target=lambda: progress(0.63, desc=desc),
                    name="test-estimator",
                    daemon=True,
                )
                thread.start()
                return _Stop(self), thread

        host = _AsyncEstimatorHost()
        blocked_estimator = threading.Event()
        updates = []

        def progress(value, desc=None):
            if value == 0.63 and not blocked_estimator.is_set():
                blocked_estimator.set()
                time.sleep(0.05)
            updates.append((value, desc))

        host._run_generate_music_service_with_progress(
            progress=progress,
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

        progress_values = [value for value, _ in updates]
        self.assertEqual(progress_values, sorted(progress_values))


if __name__ == "__main__":
    unittest.main()
