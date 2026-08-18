"""Regression tests for the direct-conditioning task gate in ``generate_music``.

``complete`` and ``lego`` condition on source audio.  Running the LM for them
made it emit audio codes from text alone, and those codes then pre-empted real
``src_audio`` processing downstream (the "Audio codes provided, ignoring
src_audio" branch in ``_prepare_reference_and_source_audio``).  Both halves of
the fix are asserted here, because either one alone is silently wrong:

1. the LM must not run — ``llm_handler.generate_with_stop_condition`` uncalled;
2. conditioning must come from ``params`` instead — ``src_audio``, ``caption``
   and ``lyrics`` must reach ``dit_handler.generate_music``.

The two task types are asserted separately: they share a code path, but only
``complete`` has been behaviour-verified upstream, so a future divergence in
``lego`` should fail on its own line rather than hide behind a loop.
"""

import unittest
from unittest.mock import MagicMock

from acestep.inference import (
    DIRECT_CONDITIONING_TASKS,
    GenerationConfig,
    GenerationParams,
    generate_music,
)


class RecordingDitHandler:
    """Minimal stand-in that captures the kwargs ``generate_music`` passes on.

    ``generate_music`` filters its kwargs through
    ``inspect.signature(dit_handler.generate_music)``, so the parameters under
    test have to be named explicitly here rather than swallowed by ``**kwargs``.
    Returning ``success=False`` stops the orchestrator right after the call, so
    no model or file I/O is needed.
    """

    def __init__(self):
        """Initialize with no captured call; ``generate_kwargs`` stays None until called."""
        self.generate_kwargs = None
        self.lora_loaded = False
        self.use_lora = False
        self.lora_scale = 1.0

    def prepare_seeds(self, batch_size, seed, use_random_seed):
        """Return a fixed seed list so the run is deterministic.

        Args:
            batch_size: Number of seeds the caller expects.
            seed: Ignored; the real handler parses a comma-separated string here.
            use_random_seed: Ignored; seeds are fixed regardless.

        Returns:
            ``(seeds, None)`` — a list of ``batch_size`` identical seeds, and the
            padding info the real handler returns and ``generate_music`` discards.
        """
        return [1234] * batch_size, None

    def generate_music(
        self,
        captions=None,
        lyrics=None,
        src_audio=None,
        task_type=None,
        audio_code_string=None,
        **kwargs,
    ):
        """Record the conditioning kwargs and stop the pipeline.

        Args:
            captions: Caption reaching the DiT — ``params.caption`` on a
                direct-conditioning task, LM-generated otherwise.
            lyrics: Lyrics reaching the DiT, same origin as ``captions``.
            src_audio: Source audio path; the value under test.
            task_type: Task the orchestrator resolved.
            audio_code_string: LM-generated codes. Non-empty here means codes
                pre-empted ``src_audio`` downstream.
            **kwargs: Remaining DiT arguments, captured but not asserted on.

        Returns:
            A failure result (``success=False``), which makes ``generate_music``
            return early — so no model runs and nothing is written to disk.
            The captured kwargs are left on ``self.generate_kwargs``.
        """
        self.generate_kwargs = {
            "captions": captions,
            "lyrics": lyrics,
            "src_audio": src_audio,
            "task_type": task_type,
            "audio_code_string": audio_code_string,
            **kwargs,
        }
        return {
            "success": False,
            "status_message": "stub handler — stopped after capturing conditioning",
            "error": "stub",
            "audios": [],
            "extra_outputs": {},
        }


def _make_llm_handler():
    """LLM handler that looks fully initialized, so skipping is a real decision."""
    llm_handler = MagicMock()
    llm_handler.llm_initialized = True
    llm_handler.generate_with_stop_condition.return_value = {
        "success": False,
        "error": "stub LM should not have been reached",
    }
    return llm_handler


def _run(task_type, **param_overrides):
    """Drive ``generate_music`` once with LM-enabling defaults left on."""
    dit_handler = RecordingDitHandler()
    llm_handler = _make_llm_handler()
    params = GenerationParams(
        task_type=task_type,
        src_audio="/tmp/source.wav",
        caption="warm analog drums and bass",
        lyrics="[Instrumental]",
        # thinking and the three CoT flags default to True; leaving them alone
        # is the point — the gate must hold without the caller disabling them.
        **param_overrides,
    )
    generate_music(dit_handler, llm_handler, params, GenerationConfig(batch_size=1))
    return dit_handler, llm_handler, params


class CompleteTaskSkipsLmTests(unittest.TestCase):
    """``complete`` must reach the DiT with source conditioning, not LM codes."""

    def test_lm_is_not_invoked(self):
        """An initialized LM with every CoT flag on must still be skipped."""
        _, llm_handler, _ = _run("complete")
        llm_handler.generate_with_stop_condition.assert_not_called()

    def test_dit_receives_source_audio_and_params_conditioning(self):
        """With no LM run, src_audio and params caption/lyrics must reach the DiT."""
        dit_handler, _, params = _run("complete")
        self.assertIsNotNone(dit_handler.generate_kwargs, "DiT handler was never called")
        self.assertEqual(params.src_audio, dit_handler.generate_kwargs["src_audio"])
        self.assertEqual(params.caption, dit_handler.generate_kwargs["captions"])
        self.assertEqual(params.lyrics, dit_handler.generate_kwargs["lyrics"])

    def test_no_audio_codes_pre_empt_source_audio(self):
        """Empty codes are what keep the source-audio branch reachable downstream."""
        dit_handler, _, _ = _run("complete")
        self.assertFalse((dit_handler.generate_kwargs["audio_code_string"] or "").strip())


class LegoTaskSkipsLmTests(unittest.TestCase):
    """``lego`` shares the path but is asserted independently on purpose."""

    def test_lm_is_not_invoked(self):
        """Asserted separately from ``complete``: only that one is behaviour-verified."""
        _, llm_handler, _ = _run("lego")
        llm_handler.generate_with_stop_condition.assert_not_called()

    def test_dit_receives_source_audio_and_params_conditioning(self):
        """With no LM run, src_audio and params caption/lyrics must reach the DiT."""
        dit_handler, _, params = _run("lego")
        self.assertIsNotNone(dit_handler.generate_kwargs, "DiT handler was never called")
        self.assertEqual(params.src_audio, dit_handler.generate_kwargs["src_audio"])
        self.assertEqual(params.caption, dit_handler.generate_kwargs["captions"])
        self.assertEqual(params.lyrics, dit_handler.generate_kwargs["lyrics"])

    def test_no_audio_codes_pre_empt_source_audio(self):
        """Empty codes are what keep the source-audio branch reachable downstream."""
        dit_handler, _, _ = _run("lego")
        self.assertFalse((dit_handler.generate_kwargs["audio_code_string"] or "").strip())


class DirectConditioningTaskSetTests(unittest.TestCase):
    """The LM gate and the params fallback must not be able to diverge."""

    def test_every_direct_conditioning_task_skips_the_lm(self):
        """Membership in the set must imply the LM gate, for every task in it."""
        for task_type in sorted(DIRECT_CONDITIONING_TASKS):
            with self.subTest(task_type=task_type):
                _, llm_handler, _ = _run(task_type)
                llm_handler.generate_with_stop_condition.assert_not_called()

    def test_every_direct_conditioning_task_conditions_from_params(self):
        """And must imply the params fallback — the half the LM gate would otherwise strand."""
        for task_type in sorted(DIRECT_CONDITIONING_TASKS):
            with self.subTest(task_type=task_type):
                dit_handler, _, params = _run(task_type)
                self.assertEqual(params.caption, dit_handler.generate_kwargs["captions"])
                self.assertEqual(params.lyrics, dit_handler.generate_kwargs["lyrics"])

    def test_text2music_still_runs_the_lm(self):
        """Control: proves the assertions above can actually observe an LM call."""
        _, llm_handler, _ = _run("text2music")
        llm_handler.generate_with_stop_condition.assert_called_once()


if __name__ == "__main__":
    unittest.main()
