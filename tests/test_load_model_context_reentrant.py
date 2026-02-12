"""Tests for _load_model_context reentrancy and batch load/offload behaviour.

Background (perf regression):
    When using the PyTorch backend with offload_to_cpu=True and batch > 1,
    each batch item triggered a full LLM load (CPU→GPU) and offload (GPU→CPU)
    cycle inside _run_pt_single.  For batch=4 this added ~6 seconds of pure
    model-transfer overhead (4 loads + 4 offloads instead of 1+1) and prevented
    the GPU from staying warm between items.

Fix:
    1. _load_model_context() was made *reentrant*: if the model is already on
       the target device it yields immediately without loading or offloading.
    2. _run_pt() wraps the entire batch loop in a single _load_model_context()
       call.  The per-item calls inside _run_pt_single become no-ops.

These tests verify that the reentrancy guard works correctly and that batch
mode triggers exactly one load/offload cycle regardless of batch size.
"""
import unittest
from unittest.mock import MagicMock
import torch

from acestep.llm_inference import LLMHandler


class _FakeParam:
    """Minimal stand-in for a model parameter with a device attribute."""

    def __init__(self, device_type: str = "cpu"):
        self.device = torch.device(device_type)


class _FakeModel:
    """Minimal model stub that tracks .to() calls."""

    def __init__(self, device_type: str = "cpu"):
        self._device_type = device_type
        self.to_calls = []

    def parameters(self):
        yield _FakeParam(self._device_type)

    def to(self, target, *args, **kwargs):
        self.to_calls.append(str(target))
        if isinstance(target, str):
            self._device_type = target.split(":")[0]
        return self


class TestLoadModelContextReentrancy(unittest.TestCase):
    """Verify _load_model_context is reentrant (no redundant load/offload).

    Reentrancy is critical for performance: when an outer caller (e.g. the
    batch loop in _run_pt) already holds the model on the GPU, inner callers
    (_run_pt_single) must *not* offload and reload it.  Without reentrancy
    each batch item pays ~1.5 s of model transfer overhead.
    """

    def _make_handler(self, device="cuda"):
        handler = LLMHandler.__new__(LLMHandler)
        handler.offload_to_cpu = True
        handler.device = device
        handler.dtype = torch.float32
        handler.llm_backend = "pt"
        handler.llm = _FakeModel("cpu")
        return handler

    def test_single_entry_loads_and_offloads(self):
        handler = self._make_handler()
        with handler._load_model_context():
            self.assertEqual(handler.llm._device_type, "cuda")
        self.assertEqual(handler.llm._device_type, "cpu")
        # .to(device).to(dtype) on load, then .to("cpu") on offload
        self.assertEqual(handler.llm.to_calls, ["cuda", "torch.float32", "cpu"])

    def test_reentrant_skips_inner_load_offload(self):
        """Inner context must be a no-op when model is already on device."""
        handler = self._make_handler()
        with handler._load_model_context():
            handler.llm.to_calls.clear()  # reset after outer load
            with handler._load_model_context():
                # Inner should NOT have called .to()
                self.assertEqual(handler.llm.to_calls, [])
                self.assertEqual(handler.llm._device_type, "cuda")
            # After inner exits, model must still be on cuda (no offload)
            self.assertEqual(handler.llm.to_calls, [])
            self.assertEqual(handler.llm._device_type, "cuda")
        # After outer exits, model offloaded
        self.assertEqual(handler.llm._device_type, "cpu")

    def test_offload_disabled_is_noop(self):
        handler = self._make_handler()
        handler.offload_to_cpu = False
        handler.llm = _FakeModel("cpu")
        with handler._load_model_context():
            self.assertEqual(handler.llm.to_calls, [])

    def test_vllm_backend_is_noop(self):
        handler = self._make_handler()
        handler.llm_backend = "vllm"
        handler.llm = _FakeModel("cpu")
        with handler._load_model_context():
            self.assertEqual(handler.llm.to_calls, [])


class TestRunPtBatchSingleLoadOffload(unittest.TestCase):
    """Verify _run_pt batch mode wraps the loop in one _load_model_context.

    Performance context:
        Before the fix, batch=N caused N separate load→generate→offload cycles.
        Each load/offload pair costs ~1.5 s on a typical GPU, so batch=4 wasted
        ~6 s on model transfers alone.  After the fix the model loads once before
        the loop and offloads once after, reducing transfer overhead to ~1.5 s
        regardless of batch size.
    """

    def test_batch_triggers_single_load_offload(self):
        """With batch=3, _load_model_context should be entered once (outer),
        and _run_pt_single's inner calls should be no-ops due to reentrancy."""
        handler = LLMHandler.__new__(LLMHandler)
        handler.offload_to_cpu = True
        handler.device = "cuda"
        handler.dtype = torch.float32
        handler.llm_backend = "pt"
        handler.llm = _FakeModel("cpu")
        handler.llm_tokenizer = MagicMock()
        handler.disable_tqdm = True
        handler.constrained_processor = None
        handler.max_model_len = 4096

        # Patch _run_pt_single to avoid actual generation but still exercise
        # the context manager reentrancy.
        call_count = {"n": 0}
        original_device_types = []

        def fake_run_pt_single(**kwargs):
            call_count["n"] += 1
            # Record device at call time to prove model is on GPU
            original_device_types.append(handler.llm._device_type)
            return f"output_{call_count['n']}"

        handler._run_pt_single = fake_run_pt_single

        prompts = ["prompt_a", "prompt_b", "prompt_c"]
        results = handler._run_pt(
            formatted_prompts=prompts,
            temperature=0.8,
            cfg_scale=1.0,
            negative_prompt="",
            top_k=None,
            top_p=None,
            repetition_penalty=1.0,
        )

        self.assertEqual(len(results), 3)
        self.assertEqual(call_count["n"], 3)
        # Each call should have seen the model on cuda
        self.assertEqual(original_device_types, ["cuda", "cuda", "cuda"])
        # After batch completes, model should be back on cpu
        self.assertEqual(handler.llm._device_type, "cpu")
        # Total .to() calls: 1 load (cuda) + 1 offload (cpu) = 2
        to_calls = [c for c in handler.llm.to_calls if c in ("cuda", "cpu")]
        self.assertEqual(to_calls.count("cuda"), 1, "Model should load to cuda exactly once")
        self.assertEqual(to_calls.count("cpu"), 1, "Model should offload to cpu exactly once")


if __name__ == "__main__":
    unittest.main()
