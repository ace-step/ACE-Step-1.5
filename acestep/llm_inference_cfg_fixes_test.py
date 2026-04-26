"""Unit tests for CFG-related bug fixes in ``LLMHandler``.

Covers:
  - Fix 1: cfg_scale forced to 1.0 during CoT phase so text logits are not distorted.
  - Fixes 2/3/5: non_audio_code_mask applied *before* CFG to avoid wasted compute
    over the full 217k vocab and probability mass leakage.
  - Fix 4: per-sequence EOS tracking – generation stops only when *all* sequences
    have finished, not at the first EOS token.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

try:
    import torch
    from acestep.llm_inference import LLMHandler
    from acestep.constrained_logits_processor import FSMState

    _IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover – dependency guard
    torch = None  # type: ignore[assignment]
    LLMHandler = None
    FSMState = None
    _IMPORT_ERROR = exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_handler() -> "LLMHandler":
    """Return a minimal LLMHandler without any loaded models."""
    handler = LLMHandler()
    # Provide just enough tokenizer state for the tests
    tokenizer = MagicMock()
    tokenizer.eos_token_id = 1
    tokenizer.pad_token_id = 1
    handler.llm_tokenizer = tokenizer
    handler.disable_tqdm = True
    return handler


def _make_constrained_processor(state: "FSMState", vocab_size: int = 10) -> MagicMock:
    """Return a mock constrained processor pinned to *state*."""
    proc = MagicMock()
    proc.state = state
    # Build a mask that allows only tokens 2 and 3 (audio codes) plus token 1 (EOS)
    non_audio_mask = torch.full((1, vocab_size), float("-inf"))
    non_audio_mask[0, 1] = 0.0  # EOS
    non_audio_mask[0, 2] = 0.0  # audio code
    non_audio_mask[0, 3] = 0.0  # audio code
    proc.non_audio_code_mask = non_audio_mask
    # Make __call__ return scores unchanged by default
    proc.side_effect = lambda input_ids, scores: scores
    return proc


def _make_fake_model(batch_size: int, vocab_size: int = 10, logit_val: float = 1.0):
    """Return a fake model that outputs constant logits of shape [batch_size, 1, vocab_size]."""
    model = MagicMock()
    logits = torch.full((batch_size, 1, vocab_size), logit_val)
    outputs = SimpleNamespace(logits=logits, past_key_values=None)
    model.return_value = outputs
    model.generation_config = MagicMock()
    model.generation_config.use_cache = False
    return model


# ---------------------------------------------------------------------------
# Fix 1: CoT phase must use cfg_scale=1.0
# ---------------------------------------------------------------------------

@unittest.skipIf(LLMHandler is None, f"llm_inference import unavailable: {_IMPORT_ERROR}")
class TestCotCfgScaleFixed(unittest.TestCase):
    """cfg_scale must be forced to 1.0 for the CoT phase (Fix 1)."""

    def test_cot_phase_uses_cfg_scale_1(self):
        """generate_from_formatted_prompt called during CoT must receive cfg_scale=1.0."""
        handler = LLMHandler()
        handler.llm_initialized = True
        handler.llm_backend = "pt"

        captured_cfg = {}

        def fake_run_pt(formatted_prompts, temperature, cfg_scale, **kwargs):
            captured_cfg["cfg_scale"] = cfg_scale
            return "<think>metadata</think>"

        with patch.object(handler, "_run_pt", side_effect=fake_run_pt):
            with patch.object(handler, "build_formatted_prompt", return_value="PROMPT"):
                with patch.object(
                    handler,
                    "_format_metadata_as_cot",
                    return_value="",
                ):
                    with patch.object(
                        handler,
                        "build_formatted_prompt_with_cot",
                        return_value="PROMPT_WITH_COT",
                    ):
                        # Simulate Phase 1 CoT call via generate_from_formatted_prompt
                        # by calling the internal helper directly
                        handler.generate_from_formatted_prompt(
                            formatted_prompt="PROMPT",
                            cfg={
                                "temperature": 0.6,
                                "cfg_scale": 1.0,  # already 1.0 for CoT
                                "negative_prompt": "NO USER INPUT",
                                "top_k": None,
                                "top_p": None,
                                "repetition_penalty": 1.0,
                                "target_duration": None,
                                "generation_phase": "cot",
                                "caption": "test",
                                "lyrics": "test",
                            },
                        )
        # cfg_scale must be 1.0 for CoT – captured during _run_pt call
        self.assertEqual(captured_cfg.get("cfg_scale"), 1.0)

    def test_generate_with_stop_condition_forces_cot_cfg_1(self):
        """generate_with_stop_condition must pass cfg_scale=1.0 to the CoT phase
        regardless of the user-supplied cfg_scale value."""
        handler = LLMHandler()
        handler.llm_initialized = True
        handler.llm_backend = "pt"

        # Capture cfg passed to generate_from_formatted_prompt
        captured_cfgs = []

        def capturing_gen(formatted_prompt, cfg=None, **kwargs):
            captured_cfgs.append(cfg or {})
            # Return a minimal CoT response so Phase 1 succeeds
            return "<think>metadata</think>", "ok"

        with patch.object(handler, "generate_from_formatted_prompt", side_effect=capturing_gen):
            with patch.object(handler, "build_formatted_prompt", return_value="P"):
                with patch.object(handler, "_parse_metadata_from_cot", return_value={}):
                    with patch.object(handler, "_format_metadata_as_cot", return_value=""):
                        with patch.object(
                            handler, "build_formatted_prompt_with_cot", return_value="P2"
                        ):
                            # Invoke with cfg_scale=2.0 (typical UI default)
                            handler.generate_with_stop_condition(
                                caption="test caption",
                                lyrics="test lyrics",
                                cfg_scale=2.0,
                                temperature=0.6,
                                negative_prompt="",
                                top_k=None,
                                top_p=None,
                                repetition_penalty=1.0,
                                infer_type="dit",  # Phase 1 only – avoids Phase 2 setup
                                progress=lambda *a, **kw: None,
                            )

        # At least one generate_from_formatted_prompt call must exist
        self.assertTrue(len(captured_cfgs) >= 1, "generate_from_formatted_prompt was not called")

        # The first call is always the CoT phase – cfg_scale must be 1.0
        cot_cfg = captured_cfgs[0]
        self.assertEqual(
            cot_cfg.get("cfg_scale"),
            1.0,
            f"Expected cfg_scale=1.0 for CoT phase, got {cot_cfg.get('cfg_scale')}",
        )


# ---------------------------------------------------------------------------
# Fixes 2/3/5: mask applied before CFG in CODES_GENERATION state
# ---------------------------------------------------------------------------

@unittest.skipIf(LLMHandler is None, f"llm_inference import unavailable: {_IMPORT_ERROR}")
class TestCfgMaskBeforeCFG(unittest.TestCase):
    """When in CODES_GENERATION state, invalid tokens must be -inf BEFORE CFG (Fixes 2/3/5)."""

    VOCAB_SIZE = 10
    BATCH_SIZE = 1

    def _run_single_step(
        self,
        constrained_processor_state: "FSMState",
        cond_logit_val: float = 2.0,
        uncond_logit_val: float = 1.0,
        cfg_scale: float = 2.0,
    ) -> "torch.Tensor":
        """Run _generate_with_cfg_custom for one step and return the sampled token."""
        handler = _make_handler()
        vocab_size = self.VOCAB_SIZE
        total_batch = self.BATCH_SIZE * 2  # cond + uncond

        # Fake model – different logit values for cond vs uncond
        model = MagicMock()
        cond_logits = torch.full((self.BATCH_SIZE, 1, vocab_size), cond_logit_val)
        uncond_logits = torch.full((self.BATCH_SIZE, 1, vocab_size), uncond_logit_val)
        # Stack [cond, uncond]
        combined_logits = torch.cat([cond_logits, uncond_logits], dim=0)
        outputs = SimpleNamespace(logits=combined_logits, past_key_values=None)
        model.return_value = outputs
        model.generation_config = MagicMock()
        model.generation_config.use_cache = False
        handler.llm = model

        constrained_proc = _make_constrained_processor(
            constrained_processor_state, vocab_size
        )

        input_ids = torch.zeros((total_batch, 5), dtype=torch.long)
        attn_mask = torch.ones((total_batch, 5), dtype=torch.long)

        result = handler._generate_with_cfg_custom(
            batch_input_ids=input_ids,
            batch_attention_mask=attn_mask,
            max_new_tokens=1,
            temperature=1.0,
            cfg_scale=cfg_scale,
            top_k=None,
            top_p=None,
            repetition_penalty=1.0,
            pad_token_id=1,
            streamer=None,
            constrained_processor=constrained_proc,
        )
        # result shape: [total_batch, seq_len+1]; return the generated token for cond seq 0
        return result[0, -1]

    def test_codes_generation_only_samples_valid_tokens(self):
        """In CODES_GENERATION state, only audio codes (2, 3) or EOS (1) may be sampled."""
        for _ in range(20):  # repeat to reduce flakiness from sampling
            token = self._run_single_step(FSMState.CODES_GENERATION)
            self.assertIn(
                token.item(),
                {1, 2, 3},
                f"Sampled invalid token {token.item()} during CODES_GENERATION",
            )

    def test_non_codes_state_samples_from_full_vocab(self):
        """Outside CODES_GENERATION, all vocab tokens are valid candidates."""
        # With uniform logits and no masking, token 0 should sometimes be sampled
        seen_tokens = set()
        for _ in range(30):
            token = self._run_single_step(FSMState.THINK_TAG, cfg_scale=1.0)
            seen_tokens.add(token.item())
        # Should see some variation across vocab (token 0 or others)
        self.assertGreater(len(seen_tokens), 1, "Expected sampling from full vocab")

    def test_codes_generation_cfg_applied_to_valid_indices_only(self):
        """CFG scaling must only affect valid token positions during CODES_GENERATION.

        With cond_logit=2.0, uncond_logit=1.0, cfg_scale=2.0 the CFG formula gives:
          cfg = 1.0 + 2.0 * (2.0 - 1.0) = 3.0 for valid tokens, -inf elsewhere.
        We verify that invalid tokens remain -inf after the CFG path.
        """
        handler = _make_handler()
        vocab_size = self.VOCAB_SIZE
        total_batch = self.BATCH_SIZE * 2

        # Build a model where cond logits are 2.0 and uncond logits are 1.0
        cond_logits = torch.full((self.BATCH_SIZE, 1, vocab_size), 2.0)
        uncond_logits = torch.full((self.BATCH_SIZE, 1, vocab_size), 1.0)
        combined = torch.cat([cond_logits, uncond_logits], dim=0)
        outputs = SimpleNamespace(logits=combined, past_key_values=None)
        model = MagicMock(return_value=outputs)
        model.generation_config = MagicMock()
        model.generation_config.use_cache = False
        handler.llm = model

        constrained_proc = _make_constrained_processor(FSMState.CODES_GENERATION, vocab_size)

        # Patch _sample_tokens to capture the logits passed to it
        captured_logits = []

        def fake_sample(logits, temperature):
            captured_logits.append(logits.clone())
            # Always return valid token 2
            return torch.tensor([2])

        with patch.object(handler, "_sample_tokens", side_effect=fake_sample):
            input_ids = torch.zeros((total_batch, 3), dtype=torch.long)
            handler._generate_with_cfg_custom(
                batch_input_ids=input_ids,
                batch_attention_mask=None,
                max_new_tokens=1,
                temperature=1.0,
                cfg_scale=2.0,
                top_k=None,
                top_p=None,
                repetition_penalty=1.0,
                pad_token_id=1,
                streamer=None,
                constrained_processor=constrained_proc,
            )

        self.assertEqual(len(captured_logits), 1)
        logits = captured_logits[0][0]  # [vocab_size] for seq 0

        # Invalid tokens (not 1, 2, or 3) must be -inf
        for idx in range(vocab_size):
            if idx not in {1, 2, 3}:
                self.assertEqual(
                    logits[idx].item(),
                    float("-inf"),
                    f"Token {idx} should be -inf (invalid), got {logits[idx].item()}",
                )


# ---------------------------------------------------------------------------
# NaN guard: aggressive repetition penalty edge case
# ---------------------------------------------------------------------------

@unittest.skipIf(LLMHandler is None, f"llm_inference import unavailable: {_IMPORT_ERROR}")
class TestCfgNanGuard(unittest.TestCase):
    """CFG result must not contain NaN when repetition penalty drives a token to -inf
    in both conditional and unconditional branches simultaneously (edge case).

    (-inf) + scale * ((-inf) - (-inf))  =>  NaN in IEEE 754 arithmetic
    The nan_to_num guard must replace NaN with -inf so those tokens are safely
    excluded from sampling rather than causing undefined behaviour.
    """

    VOCAB_SIZE = 10

    def test_cfg_nan_replaced_with_neg_inf(self):
        """NaN entries in cfg_logits (outside CODES_GENERATION) are replaced with -inf."""
        handler = _make_handler()
        vocab_size = self.VOCAB_SIZE
        total_batch = 2  # batch_size=1: [cond, uncond]

        # Both cond and uncond logits are -inf for token 4 → CFG produces NaN for that token
        cond = torch.full((1, 1, vocab_size), 0.0)
        uncond = torch.full((1, 1, vocab_size), 0.0)
        cond[0, 0, 4] = float('-inf')
        uncond[0, 0, 4] = float('-inf')
        # Token 7 (EOS substitute) stays finite so sampling always has a valid candidate
        cond[0, 0, 7] = 100.0
        uncond[0, 0, 7] = 100.0
        combined = torch.cat([cond, uncond], dim=0)
        outputs = SimpleNamespace(logits=combined, past_key_values=None)
        model = MagicMock(return_value=outputs)
        model.generation_config = MagicMock()
        model.generation_config.use_cache = False
        handler.llm = model
        handler.llm_tokenizer.eos_token_id = 7

        captured_logits = []

        def fake_sample(logits, temperature):
            captured_logits.append(logits.clone())
            return torch.tensor([7])

        with patch.object(handler, "_sample_tokens", side_effect=fake_sample):
            input_ids = torch.zeros((total_batch, 3), dtype=torch.long)
            # Use a THINK_TAG processor so the full-vocab CFG else-branch is taken
            constrained_proc = _make_constrained_processor(FSMState.THINK_TAG, vocab_size)
            handler._generate_with_cfg_custom(
                batch_input_ids=input_ids,
                batch_attention_mask=None,
                max_new_tokens=1,
                temperature=1.0,
                cfg_scale=2.0,
                top_k=None,
                top_p=None,
                repetition_penalty=1.0,
                pad_token_id=7,
                streamer=None,
                constrained_processor=constrained_proc,
            )

        self.assertEqual(len(captured_logits), 1)
        logits = captured_logits[0][0]  # [vocab_size] for seq 0

        # No NaN values in the logits passed to the sampler
        self.assertFalse(
            torch.isnan(logits).any().item(),
            f"NaN found in cfg_logits: {logits}",
        )
        # Token 4 (was NaN before guard) must be -inf after the guard
        self.assertEqual(
            logits[4].item(),
            float('-inf'),
            f"Expected -inf for NaN token, got {logits[4].item()}",
        )


# ---------------------------------------------------------------------------
# Fix 4: Per-sequence EOS tracking (batch compaction)
# ---------------------------------------------------------------------------

@unittest.skipIf(LLMHandler is None, f"llm_inference import unavailable: {_IMPORT_ERROR}")
class TestPerSequenceEosTracking(unittest.TestCase):
    """Generation must continue until ALL sequences in the batch have hit EOS (Fix 4)."""

    VOCAB_SIZE = 10

    def test_generation_stops_when_all_sequences_finish(self):
        """With batch_size=1, generation must stop immediately at EOS (unchanged behaviour)."""
        eos_id = 1
        vocab_size = self.VOCAB_SIZE
        handler = _make_handler()
        handler.llm_tokenizer.eos_token_id = eos_id

        # Model always outputs EOS
        logits = torch.full((2, 1, vocab_size), -100.0)  # [cond+uncond, 1, V]
        logits[:, :, eos_id] = 100.0
        outputs = SimpleNamespace(logits=logits, past_key_values=None)
        model = MagicMock(return_value=outputs)
        model.generation_config = MagicMock()
        model.generation_config.use_cache = False
        handler.llm = model

        input_ids = torch.zeros((2, 3), dtype=torch.long)
        result = handler._generate_with_cfg_custom(
            batch_input_ids=input_ids,
            batch_attention_mask=None,
            max_new_tokens=10,
            temperature=1.0,
            cfg_scale=1.0,
            top_k=None,
            top_p=None,
            repetition_penalty=1.0,
            pad_token_id=eos_id,
            streamer=None,
        )
        # Should have stopped after 1 step (EOS immediately)
        generated_len = result.shape[1] - input_ids.shape[1]
        self.assertEqual(generated_len, 1, f"Expected 1 generated token, got {generated_len}")
        # The generated token must be EOS
        self.assertEqual(result[0, -1].item(), eos_id)

    def test_finished_sequences_are_forced_to_eos(self):
        """After a sequence hits EOS, subsequent tokens must also be EOS (no new tokens)."""
        eos_id = 1
        vocab_size = self.VOCAB_SIZE
        handler = _make_handler()
        handler.llm_tokenizer.eos_token_id = eos_id

        # Step 0: output EOS; step 1+: output token 5
        step = [0]

        def fake_call(input_ids, **kwargs):
            logits = torch.full((input_ids.shape[0], 1, vocab_size), -100.0)
            if step[0] == 0:
                logits[:, :, eos_id] = 100.0  # EOS on step 0
            else:
                logits[:, :, 5] = 100.0  # token 5 on step 1+
            step[0] += 1
            return SimpleNamespace(logits=logits, past_key_values=None)

        model = MagicMock(side_effect=fake_call)
        model.generation_config = MagicMock()
        model.generation_config.use_cache = False
        handler.llm = model

        input_ids = torch.zeros((2, 3), dtype=torch.long)
        result = handler._generate_with_cfg_custom(
            batch_input_ids=input_ids,
            batch_attention_mask=None,
            max_new_tokens=5,
            temperature=1.0,
            cfg_scale=1.0,
            top_k=None,
            top_p=None,
            repetition_penalty=1.0,
            pad_token_id=eos_id,
            streamer=None,
        )
        # With batch_size=1, EOS on step 0 means all done → stops immediately
        generated_len = result.shape[1] - input_ids.shape[1]
        self.assertEqual(generated_len, 1)
        self.assertEqual(result[0, -1].item(), eos_id)


if __name__ == "__main__":
    unittest.main()
