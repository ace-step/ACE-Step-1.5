"""Regression coverage for progress estimator thread lifecycle."""

import unittest

from acestep.core.generation.handler.generate_music_execute import GenerateMusicExecuteMixin


class _Host(GenerateMusicExecuteMixin):
    """Minimal host for exercising estimator shutdown behavior."""

    def __init__(self):
        self.stop_calls = 0
        self.thread = None

    def _start_diffusion_progress_estimator(self, **kwargs):
        class _Stop:
            def __init__(self, host):
                self.host = host

            def set(self):
                self.host.stop_calls += 1

        class _Thread:
            def __init__(self):
                self.join_calls = 0
                self._alive = True

            def join(self, timeout=None):
                _ = timeout
                self.join_calls += 1
                if self.join_calls >= 2:
                    self._alive = False

            def is_alive(self):
                return self._alive

        self.thread = _Thread()
        return _Stop(self), self.thread

    def service_generate(self, **kwargs):
        progress_callback = kwargs["progress_callback"]
        progress_callback(1, 4, "DiT diffusion...")
        return {"target_latents": "ok"}


class GenerateMusicExecuteThreadLifecycleTests(unittest.TestCase):
    """Ensure estimator thread handles survive timed joins until actual shutdown."""

    def test_runtime_progress_keeps_estimator_thread_handle_until_thread_exits(self):
        host = _Host()
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

        self.assertEqual(out["outputs"]["target_latents"], "ok")
        self.assertEqual(host.stop_calls, 2)
        self.assertIsNotNone(host.thread)
        self.assertEqual(host.thread.join_calls, 2)
        self.assertFalse(host.thread.is_alive())
        self.assertTrue(any(desc == "DiT diffusion..." for _, desc in updates))


if __name__ == "__main__":
    unittest.main()
