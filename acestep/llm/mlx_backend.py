"""
MLX backend mixin for LLMHandler.

Provides Apple Silicon native acceleration via the MLX framework and mlx-lm.
All methods reference ``self.*`` attributes that are supplied by the combined
LLMHandler class (e.g. ``self._mlx_model``, ``self.llm_tokenizer``,
``self.llm_backend``, ``self.llm_initialized``).
"""

import time
from typing import Dict, List, Optional, Tuple, Union

import torch
from loguru import logger
from tqdm import tqdm

from acestep.llm.constants import CODES_PER_SECOND, DEFAULT_MAX_MODEL_LEN


class MlxBackendMixin:
    """Mixin supplying MLX (Apple Silicon) backend methods for LLMHandler."""

    @staticmethod
    def _is_mlx_available() -> bool:
        """Check if MLX framework is available (Apple Silicon).

        Delegates to the cached ``mlx_available()`` helper to avoid
        re-importing ``mlx.core`` when the native extension failed on
        first load (which causes a fatal nanobind duplicate-enum crash).
        """
        try:
            from acestep.models.mlx import mlx_available
            if not mlx_available():
                return False
            import mlx_lm
            return True
        except Exception:
            return False

    def _load_mlx_model(self, model_path: str) -> Tuple[bool, str]:
        """
        Load the 5Hz LM model using mlx-lm for native Apple Silicon acceleration.

        Args:
            model_path: Path to the HuggingFace model directory

        Returns:
            Tuple of (success, status_message)
        """
        try:
            import mlx.core as mx
            from mlx_lm.utils import load as mlx_load

            logger.info(f"Loading MLX model from {model_path}")
            start_time = time.time()

            # Try standard mlx-lm load first
            try:
                self._mlx_model, _ = mlx_load(model_path)
            except Exception as first_err:
                # The ACE-Step 5Hz LM checkpoints store safetensors keys without
                # the "model." prefix (e.g. "layers.0.xxx" instead of
                # "model.layers.0.xxx") which is what mlx-lm's Qwen3 model
                # expects.  When the standard load fails we retry with the
                # prefix remapped.
                logger.info(
                    f"Standard MLX load failed ({first_err}), "
                    "retrying with 'model.' prefix remapping..."
                )
                import glob as _glob
                from pathlib import Path
                from mlx_lm.utils import load_model, load_config, load_tokenizer, _get_classes

                _model_path = Path(model_path)
                config = load_config(_model_path)

                # Load raw weights from safetensors
                weight_files = _glob.glob(str(_model_path / "model*.safetensors"))
                if not weight_files:
                    raise FileNotFoundError(f"No safetensors found in {model_path}") from first_err

                weights = {}
                for wf in weight_files:
                    weights.update(mx.load(wf))

                # Check if keys need "model." prefix by inspecting first key
                sample_key = next(iter(weights))
                if not sample_key.startswith("model."):
                    logger.info("Adding 'model.' prefix to weight keys for MLX compatibility")
                    weights = {f"model.{k}": v for k, v in weights.items()}

                # Build model from config
                model_class, model_args_class = _get_classes(config=config)
                model_args = model_args_class.from_dict(config)
                model = model_class(model_args)

                if hasattr(model, "sanitize"):
                    weights = model.sanitize(weights)

                model.load_weights(list(weights.items()), strict=True)
                mx.eval(model.parameters())
                model.eval()
                self._mlx_model = model

            mx.eval(self._mlx_model.parameters())
            # Store model path for get_hf_model_for_scoring
            self._mlx_model_path = model_path

            load_time = time.time() - start_time
            logger.info(f"MLX model loaded successfully in {load_time:.2f}s")

            self.llm_backend = "mlx"
            self.llm_initialized = True
            status_msg = (
                f"✅ 5Hz LM initialized successfully\n"
                f"Model: {model_path}\n"
                f"Backend: MLX (Apple Silicon native)\n"
                f"Device: Apple Silicon GPU"
            )
            return True, status_msg

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            logger.warning(f"Failed to load MLX model: {e}\n{error_detail}")
            return False, f"❌ MLX load failed: {str(e)}"

    def _make_mlx_cache(self):
        """Create a KV cache for the MLX model."""
        import mlx.core as mx
        try:
            from mlx_lm.models.cache import make_prompt_cache
            return make_prompt_cache(self._mlx_model)
        except (ImportError, AttributeError):
            # Fallback: try model's own cache creation
            try:
                return self._mlx_model.make_cache()
            except AttributeError:
                raise RuntimeError(
                    "Cannot create MLX KV cache. Ensure mlx-lm version >= 0.20.0"
                )

    def _run_mlx_batch_native(
        self,
        formatted_prompt: str,
        batch_size: int,
        temperature: float,
        cfg_scale: float,
        negative_prompt: str,
        top_k: Optional[int],
        top_p: Optional[float],
        repetition_penalty: float,
        use_constrained_decoding: bool,
        constrained_decoding_debug: bool,
        target_duration: Optional[float],
        caption: str,
        lyrics: str,
        cot_text: str,
        seeds: Optional[List[int]] = None,
    ) -> List[str]:
        """
        Optimized native MLX batch generation for codes phase.

        Strategy: shared prefill + clone cache + interleaved B=1 decode.

        On Apple Silicon, LLM decode is memory-bandwidth-bound. Batching the
        forward pass (B>1) doubles the KV cache reads per step and actually
        *slows down* throughput for 1.7B-class models. Instead, we:

        1. Prefill ONCE with B=1, then clone the KV caches for each item.
           This saves ~50% of prefill time vs sequential generation.
        2. Interleave B=1 forward passes across items within each step.
           Each item gets its own cache, constrained state, and seed.

        This achieves ~1.25x speedup over fully sequential generation while
        maintaining the full ~44 tok/s per-item decode speed.

        Only used for codes generation phase where all prompts are identical.
        Raises on failure so the caller can fall back to sequential mode.
        """
        import mlx.core as mx
        import numpy as np
        from mlx_lm.models.cache import make_prompt_cache, KVCache
        from mlx_lm.sample_utils import make_sampler

        # ---- Tokenize (single prompt, shared by all items) ----
        inputs = self.llm_tokenizer(
            formatted_prompt,
            return_tensors="np",
            padding=False,
            truncation=True,
        )
        input_ids_np = inputs["input_ids"]  # [1, seq_len]
        prompt_length = input_ids_np.shape[1]
        prompt = mx.array(input_ids_np[0])  # 1D [seq_len]

        # ---- Calculate max_new_tokens ----
        # Batch native is always codes phase
        max_new_tokens = self._compute_max_new_tokens(
            target_duration=target_duration,
            generation_phase="codes",
        )

        # ---- EOS tokens ----
        eos_token_id = self.llm_tokenizer.eos_token_id
        pad_token_id = self.llm_tokenizer.pad_token_id or eos_token_id

        # ---- Native MLX sampler ----
        sampler = make_sampler(
            temp=temperature if temperature > 0 else 0.0,
            top_p=top_p if top_p is not None and 0.0 < top_p < 1.0 else 1.0,
            top_k=top_k if top_k is not None and top_k > 0 else 0,
        )

        # ---- Repetition penalty config ----
        use_rep_penalty = repetition_penalty != 1.0
        rep_penalty_val = float(repetition_penalty)

        use_cfg = cfg_scale > 1.0
        cfg_label = "CFG " if use_cfg else ""
        prefill_step_size = 2048

        # ---- Pre-convert constrained masks to MLX (shared by all items) ----
        from acestep.constrained_logits_processor import FSMState
        _mlx_non_audio_mask = None
        _mlx_eos_id = None
        _target_codes = None

        # Setup a temporary constrained processor to get masks
        constrained_processor = self._setup_constrained_processor(
            use_constrained_decoding=use_constrained_decoding,
            constrained_decoding_debug=constrained_decoding_debug,
            target_duration=target_duration,
            user_metadata=None,
            stop_at_reasoning=False,
            skip_genres=True,
            skip_caption=True,
            skip_language=True,
            generation_phase="codes",
            is_batch=True,
        )

        if constrained_processor is not None:
            if hasattr(constrained_processor, 'non_audio_code_mask') and constrained_processor.non_audio_code_mask is not None:
                _mlx_non_audio_mask = mx.array(constrained_processor.non_audio_code_mask.float().numpy())
            if hasattr(constrained_processor, 'eos_token_id') and constrained_processor.eos_token_id is not None:
                _mlx_eos_id = int(constrained_processor.eos_token_id)
            if hasattr(constrained_processor, 'target_codes'):
                _target_codes = constrained_processor.target_codes

            # Pre-transition FSM to CODES_GENERATION
            if constrained_processor.state == FSMState.THINK_TAG:
                if "</think>" in formatted_prompt:
                    constrained_processor.state = FSMState.CODES_GENERATION
                    constrained_processor.codes_count = 0

        # ===== SHARED PREFILL PHASE (done ONCE for all batch items) =====
        prefill_start = time.time()
        logger.info(f"MLX batch native: prefilling once for {batch_size} items (shared prompt)")

        def _clone_cache_list(cache_list):
            """Deep-copy a list of KVCache objects so each batch item gets independent state."""
            cloned = []
            for c in cache_list:
                new_c = KVCache()
                if c.keys is not None:
                    # mx.array(...) on an existing array creates a copy
                    new_c.keys = mx.array(c.keys)
                    new_c.values = mx.array(c.values)
                    new_c.offset = c.offset
                cloned.append(new_c)
            return cloned

        if use_cfg:
            # Build unconditional prompt
            uncond_text = self._build_unconditional_prompt(
                caption=caption, lyrics=lyrics, cot_text=cot_text,
                negative_prompt=negative_prompt, generation_phase="codes", is_batch=True,
            )
            uncond_inputs = self.llm_tokenizer(
                uncond_text, return_tensors="np", padding=False, truncation=True,
            )
            uncond_prompt = mx.array(uncond_inputs["input_ids"][0])
            uncond_length = len(uncond_prompt)

            # Create single KV caches and prefill once
            base_cond_cache = make_prompt_cache(self._mlx_model)
            base_uncond_cache = make_prompt_cache(self._mlx_model)

            # Chunked prefill for conditional prompt
            cond_remaining = prompt
            while len(cond_remaining) > 1:
                chunk_size = min(prefill_step_size, len(cond_remaining) - 1)
                self._mlx_model(cond_remaining[:chunk_size][None], cache=base_cond_cache)
                mx.eval([c.state for c in base_cond_cache])
                cond_remaining = cond_remaining[chunk_size:]
                mx.clear_cache()

            # Chunked prefill for unconditional prompt
            uncond_remaining = uncond_prompt
            while len(uncond_remaining) > 1:
                chunk_size = min(prefill_step_size, len(uncond_remaining) - 1)
                self._mlx_model(uncond_remaining[:chunk_size][None], cache=base_uncond_cache)
                mx.eval([c.state for c in base_uncond_cache])
                uncond_remaining = uncond_remaining[chunk_size:]
                mx.clear_cache()

            # Process last tokens of both prompts to get initial logits
            base_cond_logits = self._mlx_model(cond_remaining[None], cache=base_cond_cache)
            base_uncond_logits = self._mlx_model(uncond_remaining[None], cache=base_uncond_cache)
            mx.eval(base_cond_logits, base_uncond_logits)

            # Clone caches for each batch item (item 0 reuses the base cache)
            item_cond_caches = [base_cond_cache]
            item_uncond_caches = [base_uncond_cache]
            for i in range(1, batch_size):
                item_cond_caches.append(_clone_cache_list(base_cond_cache))
                item_uncond_caches.append(_clone_cache_list(base_uncond_cache))
            # Eval cloned caches
            for i in range(1, batch_size):
                mx.eval(*[c.keys for c in item_cond_caches[i] if c.keys is not None])
                mx.eval(*[c.keys for c in item_uncond_caches[i] if c.keys is not None])

            # Initial logits for each item (same values, but we need separate references)
            item_last_cond = [base_cond_logits[:, -1:, :]] * batch_size
            item_last_uncond = [base_uncond_logits[:, -1:, :]] * batch_size

            prefill_time = time.time() - prefill_start
            total_prefill_tokens = prompt_length + uncond_length
            prefill_tps = total_prefill_tokens / prefill_time if prefill_time > 0 else 0
            logger.info(
                f"MLX batch native prefill: {total_prefill_tokens} tokens "
                f"(cond={prompt_length}, uncond={uncond_length}) "
                f"in {prefill_time:.2f}s ({prefill_tps:.1f} tok/s) "
                f"[shared across {batch_size} items, saved {(batch_size-1)*total_prefill_tokens} redundant tokens]"
            )
        else:
            # Non-CFG mode
            base_cache = make_prompt_cache(self._mlx_model)
            remaining = prompt
            while len(remaining) > 1:
                chunk_size = min(prefill_step_size, len(remaining) - 1)
                self._mlx_model(remaining[:chunk_size][None], cache=base_cache)
                mx.eval([c.state for c in base_cache])
                remaining = remaining[chunk_size:]
                mx.clear_cache()

            base_logits = self._mlx_model(remaining[None], cache=base_cache)
            mx.eval(base_logits)

            item_caches = [base_cache]
            for i in range(1, batch_size):
                item_caches.append(_clone_cache_list(base_cache))
            for i in range(1, batch_size):
                mx.eval(*[c.keys for c in item_caches[i] if c.keys is not None])

            item_last_logits = [base_logits[:, -1:, :]] * batch_size

            prefill_time = time.time() - prefill_start
            prefill_tps = prompt_length / prefill_time if prefill_time > 0 else 0
            logger.info(
                f"MLX batch native prefill: {prompt_length} tokens "
                f"in {prefill_time:.2f}s ({prefill_tps:.1f} tok/s) "
                f"[shared across {batch_size} items]"
            )

        # ===== INTERLEAVED AUTOREGRESSIVE GENERATION LOOP =====
        # Each item has independent: tokens, codes_count, finished flag, KV cache, random key
        # But they share: model weights, masks, sampler
        #
        # Why interleaved B=1 instead of true batch B=N?
        # On Apple Silicon, LLM decode is memory-bandwidth-bound.
        # B=2 doubles KV cache reads per step, causing ~3x slowdown per step
        # for 1.7B models. Interleaved B=1 keeps the full ~44 tok/s speed
        # while still sharing the prefill computation.
        base_token_ids = list(input_ids_np[0])
        item_all_token_ids = [list(base_token_ids) for _ in range(batch_size)]
        item_new_tokens = [[] for _ in range(batch_size)]
        item_codes_count = [0] * batch_size
        item_finished = [False] * batch_size

        # Pre-compute per-item seed bases (large primes to avoid correlation)
        item_seed_bases = []
        for i in range(batch_size):
            if seeds and i < len(seeds):
                item_seed_bases.append(seeds[i])
            else:
                item_seed_bases.append(42 + i * 1000003)

        decode_start = time.time()
        pbar = tqdm(total=max_new_tokens, desc=f"MLX {cfg_label}Batch Gen (native, n={batch_size})", unit="tok")

        for step in range(max_new_tokens):
            # Check if all items are done
            if all(item_finished):
                break

            # Process each active item (interleaved B=1 forward passes)
            for i in range(batch_size):
                if item_finished[i]:
                    continue

                # ---- Set deterministic per-item seed for this step ----
                # This ensures reproducibility: item i at step s always uses the same seed
                mx.random.seed(item_seed_bases[i] + step * 1000003)

                # ---- Combine logits (CFG) ----
                if use_cfg:
                    step_logits = item_last_uncond[i] + cfg_scale * (item_last_cond[i] - item_last_uncond[i])
                else:
                    step_logits = item_last_logits[i]

                step_logits = step_logits.reshape(1, -1)  # [1, vocab_size]

                # ---- Repetition penalty ----
                if use_rep_penalty and len(item_all_token_ids[i]) > 0:
                    token_indices = mx.array(item_all_token_ids[i])
                    selected = step_logits[:, token_indices]
                    modified = mx.where(
                        selected > 0,
                        selected / rep_penalty_val,
                        selected * rep_penalty_val,
                    )
                    step_logits[:, token_indices] = modified

                # ---- Constrained decoding (native MLX fast path) ----
                if _mlx_non_audio_mask is not None:
                    step_logits = step_logits + _mlx_non_audio_mask
                if _target_codes is not None and _mlx_eos_id is not None:
                    if item_codes_count[i] < _target_codes:
                        step_logits = mx.concatenate([
                            step_logits[:, :_mlx_eos_id],
                            mx.array([[float('-inf')]]),
                            step_logits[:, _mlx_eos_id + 1:],
                        ], axis=1)
                    else:
                        eos_val = step_logits[:, _mlx_eos_id:_mlx_eos_id + 1]
                        step_logits = mx.full(step_logits.shape, float('-inf'))
                        step_logits = mx.concatenate([
                            step_logits[:, :_mlx_eos_id],
                            eos_val,
                            step_logits[:, _mlx_eos_id + 1:],
                        ], axis=1)

                # ---- Sample ----
                logprobs = step_logits - mx.logsumexp(step_logits, keepdims=True)
                token_arr = sampler(logprobs)
                mx.eval(token_arr)
                token_id = token_arr.item()

                item_new_tokens[i].append(token_id)
                item_all_token_ids[i].append(token_id)

                # Update codes count
                item_codes_count[i] += 1

                # Check EOS
                if token_id == eos_token_id:
                    item_finished[i] = True
                    continue
                if pad_token_id is not None and pad_token_id != eos_token_id and token_id == pad_token_id:
                    item_finished[i] = True
                    continue

                # ---- Next forward step (B=1 per item) ----
                next_input = mx.array([[token_id]])
                if use_cfg:
                    cond_logits = self._mlx_model(next_input, cache=item_cond_caches[i])
                    uncond_logits = self._mlx_model(next_input, cache=item_uncond_caches[i])
                    item_last_cond[i] = cond_logits[:, -1:, :]
                    item_last_uncond[i] = uncond_logits[:, -1:, :]
                else:
                    logits_out = self._mlx_model(next_input, cache=item_caches[i])
                    item_last_logits[i] = logits_out[:, -1:, :]

            pbar.update(1)

            # Periodic memory cleanup
            if step % 256 == 0 and step > 0:
                mx.clear_cache()

        pbar.close()

        # ---- Log generation summary ----
        decode_time = time.time() - decode_start
        total_tokens = sum(len(t) for t in item_new_tokens)
        avg_tokens = total_tokens / batch_size if batch_size > 0 else 0
        decode_tps = total_tokens / decode_time if decode_time > 0 else 0
        total_time = prefill_time + decode_time
        logger.info(
            f"MLX batch native generation complete: {batch_size} items, "
            f"{total_tokens} total tokens ({avg_tokens:.0f} avg) in {decode_time:.2f}s "
            f"({decode_tps:.1f} tok/s) | prefill {prefill_time:.2f}s + decode {decode_time:.2f}s = {total_time:.2f}s total"
        )

        # Decode each item's tokens
        output_texts = []
        for i in range(batch_size):
            output_text = self.llm_tokenizer.decode(item_new_tokens[i], skip_special_tokens=False)
            output_texts.append(output_text)

        return output_texts

    def _run_mlx_single_native(
        self,
        formatted_prompt: str,
        temperature: float,
        cfg_scale: float,
        negative_prompt: str,
        top_k: Optional[int],
        top_p: Optional[float],
        repetition_penalty: float,
        use_constrained_decoding: bool,
        constrained_decoding_debug: bool,
        target_duration: Optional[float],
        user_metadata: Optional[Dict[str, Optional[str]]],
        stop_at_reasoning: bool,
        skip_genres: bool,
        skip_caption: bool,
        skip_language: bool,
        generation_phase: str,
        caption: str,
        lyrics: str,
        cot_text: str,
    ) -> str:
        """
        Optimized native MLX generation using mlx-lm infrastructure.

        Key improvements over the hybrid approach:
        1. Native MLX sampling (temperature, top-k, top-p) via mlx-lm make_sampler
           - Eliminates numpy/PyTorch round-trip for EVERY generated token
        2. Native MLX repetition penalty (no per-step PyTorch conversion)
        3. Chunked prefill for memory-efficient long prompt processing
        4. Periodic memory cleanup (mx.clear_cache) matching mlx-lm patterns
        5. Bridges to PyTorch ONLY for constrained decoding FSM when active

        Raises on failure so the caller can fall back to the legacy hybrid method.
        """
        import mlx.core as mx
        import numpy as np
        from mlx_lm.models.cache import make_prompt_cache
        from mlx_lm.sample_utils import make_sampler

        # ---- Tokenize ----
        inputs = self.llm_tokenizer(
            formatted_prompt,
            return_tensors="np",
            padding=False,
            truncation=True,
        )
        input_ids_np = inputs["input_ids"]  # [1, seq_len]
        prompt_length = input_ids_np.shape[1]
        prompt = mx.array(input_ids_np[0])  # 1D [seq_len]

        # ---- Setup constrained processor ----
        constrained_processor = self._setup_constrained_processor(
            use_constrained_decoding=use_constrained_decoding,
            constrained_decoding_debug=constrained_decoding_debug,
            target_duration=target_duration,
            user_metadata=user_metadata,
            stop_at_reasoning=stop_at_reasoning,
            skip_genres=skip_genres,
            skip_caption=skip_caption,
            skip_language=skip_language,
            generation_phase=generation_phase,
            is_batch=False,
        )

        # ---- Calculate max_new_tokens ----
        max_new_tokens = self._compute_max_new_tokens(
            target_duration=target_duration,
            generation_phase=generation_phase,
        )

        # ---- EOS tokens ----
        eos_token_id = self.llm_tokenizer.eos_token_id
        pad_token_id = self.llm_tokenizer.pad_token_id or eos_token_id

        # ---- Native MLX sampler (replaces PyTorch top-k/top-p/temperature) ----
        sampler = make_sampler(
            temp=temperature if temperature > 0 else 0.0,
            top_p=top_p if top_p is not None and 0.0 < top_p < 1.0 else 1.0,
            top_k=top_k if top_k is not None and top_k > 0 else 0,
        )

        # ---- Repetition penalty config ----
        use_rep_penalty = repetition_penalty != 1.0
        rep_penalty_val = float(repetition_penalty)

        use_cfg = cfg_scale > 1.0
        cfg_label = "CFG " if use_cfg else ""
        tqdm_desc = f"MLX {cfg_label}Gen (native)"
        prefill_step_size = 2048

        # ---- Pre-convert constrained processor masks to MLX (one-time) ----
        # This enables native MLX fast-path for CODES_GENERATION state,
        # eliminating the PyTorch bridge for 99%+ of Phase 2 tokens.
        from acestep.constrained_logits_processor import FSMState
        _mlx_non_audio_mask = None
        _mlx_eos_id = None
        _target_codes = None
        _use_native_codes_path = False

        if constrained_processor is not None:
            # Pre-convert the non-audio-code mask to MLX (blocks everything except audio codes + EOS)
            if hasattr(constrained_processor, 'non_audio_code_mask') and constrained_processor.non_audio_code_mask is not None:
                _mlx_non_audio_mask = mx.array(constrained_processor.non_audio_code_mask.float().numpy())
            if hasattr(constrained_processor, 'eos_token_id') and constrained_processor.eos_token_id is not None:
                _mlx_eos_id = int(constrained_processor.eos_token_id)
            if hasattr(constrained_processor, 'target_codes'):
                _target_codes = constrained_processor.target_codes

            # For codes phase, the prompt already contains </think>.
            # Pre-transition FSM to CODES_GENERATION so the native fast path
            # activates from the very first generated token.
            if generation_phase == "codes" and constrained_processor.state == FSMState.THINK_TAG:
                if "</think>" in formatted_prompt:
                    constrained_processor.state = FSMState.CODES_GENERATION
                    constrained_processor.codes_count = 0
                    _use_native_codes_path = True
                    logger.info("MLX native: pre-transitioned FSM to CODES_GENERATION (native fast path)")

        # ===== PREFILL PHASE =====
        prefill_start = time.time()

        if use_cfg:
            # Build unconditional prompt
            uncond_text = self._build_unconditional_prompt(
                caption=caption,
                lyrics=lyrics,
                cot_text=cot_text,
                negative_prompt=negative_prompt,
                generation_phase=generation_phase,
                is_batch=False,
            )
            uncond_inputs = self.llm_tokenizer(
                uncond_text,
                return_tensors="np",
                padding=False,
                truncation=True,
            )
            uncond_prompt = mx.array(uncond_inputs["input_ids"][0])
            uncond_length = len(uncond_prompt)

            # Create KV caches via mlx-lm infrastructure
            cond_cache = make_prompt_cache(self._mlx_model)
            uncond_cache = make_prompt_cache(self._mlx_model)

            # Chunked prefill for conditional prompt
            cond_remaining = prompt
            while len(cond_remaining) > 1:
                chunk_size = min(prefill_step_size, len(cond_remaining) - 1)
                self._mlx_model(cond_remaining[:chunk_size][None], cache=cond_cache)
                mx.eval([c.state for c in cond_cache])
                cond_remaining = cond_remaining[chunk_size:]
                mx.clear_cache()

            # Chunked prefill for unconditional prompt
            uncond_remaining = uncond_prompt
            while len(uncond_remaining) > 1:
                chunk_size = min(prefill_step_size, len(uncond_remaining) - 1)
                self._mlx_model(uncond_remaining[:chunk_size][None], cache=uncond_cache)
                mx.eval([c.state for c in uncond_cache])
                uncond_remaining = uncond_remaining[chunk_size:]
                mx.clear_cache()

            # Process last tokens of both prompts
            cond_logits = self._mlx_model(cond_remaining[None], cache=cond_cache)
            uncond_logits = self._mlx_model(uncond_remaining[None], cache=uncond_cache)
            mx.eval(cond_logits, uncond_logits)

            last_cond = cond_logits[:, -1:, :]
            last_uncond = uncond_logits[:, -1:, :]

            prefill_time = time.time() - prefill_start
            total_prefill_tokens = prompt_length + uncond_length
            prefill_tps = total_prefill_tokens / prefill_time if prefill_time > 0 else 0
            logger.info(
                f"MLX native prefill: {total_prefill_tokens} tokens "
                f"(cond={prompt_length}, uncond={uncond_length}) "
                f"in {prefill_time:.2f}s ({prefill_tps:.1f} tok/s)"
            )
        else:
            # Non-CFG: single cache
            cache = make_prompt_cache(self._mlx_model)

            # Chunked prefill
            remaining = prompt
            while len(remaining) > 1:
                chunk_size = min(prefill_step_size, len(remaining) - 1)
                self._mlx_model(remaining[:chunk_size][None], cache=cache)
                mx.eval([c.state for c in cache])
                remaining = remaining[chunk_size:]
                mx.clear_cache()

            logits_out = self._mlx_model(remaining[None], cache=cache)
            mx.eval(logits_out)
            last_logits = logits_out[:, -1:, :]

            prefill_time = time.time() - prefill_start
            prefill_tps = prompt_length / prefill_time if prefill_time > 0 else 0
            logger.info(
                f"MLX native prefill: {prompt_length} tokens "
                f"in {prefill_time:.2f}s ({prefill_tps:.1f} tok/s)"
            )

        # ===== AUTOREGRESSIVE GENERATION LOOP =====
        all_token_ids = list(input_ids_np[0])
        new_tokens = []
        decode_start = time.time()

        pbar = tqdm(total=max_new_tokens, desc=tqdm_desc, unit="tok")
        for step in range(max_new_tokens):
            # ---- Combine logits (CFG formula in MLX, lazy) ----
            if use_cfg:
                step_logits = last_uncond + cfg_scale * (last_cond - last_uncond)
            else:
                step_logits = last_logits

            step_logits = step_logits.reshape(1, -1)  # [1, vocab_size]

            # ---- Native MLX repetition penalty (lazy) ----
            if use_rep_penalty and len(all_token_ids) > 0:
                token_indices = mx.array(all_token_ids)
                selected = step_logits[:, token_indices]
                modified = mx.where(
                    selected > 0,
                    selected / rep_penalty_val,
                    selected * rep_penalty_val,
                )
                step_logits[:, token_indices] = modified

            # ---- Constrained decoding: native MLX fast path vs PyTorch bridge ----
            if constrained_processor is not None:
                _cp_state = constrained_processor.state

                if _cp_state == FSMState.CODES_GENERATION:
                    # === NATIVE MLX FAST PATH (no PyTorch bridge!) ===
                    # Apply non-audio-code mask (blocks everything except audio codes + EOS)
                    if _mlx_non_audio_mask is not None:
                        step_logits = step_logits + _mlx_non_audio_mask
                    # Duration constraint: block or force EOS
                    if _target_codes is not None and _mlx_eos_id is not None:
                        if constrained_processor.codes_count < _target_codes:
                            # Block EOS until target codes reached
                            step_logits = mx.concatenate([
                                step_logits[:, :_mlx_eos_id],
                                mx.array([[float('-inf')]]),
                                step_logits[:, _mlx_eos_id + 1:],
                            ], axis=1)
                        else:
                            # Force EOS when target reached
                            eos_val = step_logits[:, _mlx_eos_id:_mlx_eos_id + 1]
                            step_logits = mx.full(step_logits.shape, float('-inf'))
                            step_logits = mx.concatenate([
                                step_logits[:, :_mlx_eos_id],
                                eos_val,
                                step_logits[:, _mlx_eos_id + 1:],
                            ], axis=1)

                elif _cp_state == FSMState.COMPLETED:
                    # No-op: COMPLETED state in codes/cot phase is passthrough
                    pass

                else:
                    # === PYTORCH BRIDGE (metadata states during CoT phase) ===
                    step_logits_f32 = step_logits.astype(mx.float32)
                    np_logits = np.array(step_logits_f32, copy=True)
                    t_logits = torch.from_numpy(np_logits)
                    t_ids = torch.tensor([all_token_ids], dtype=torch.long)
                    t_logits = constrained_processor(t_ids, t_logits)
                    step_logits = mx.array(t_logits.numpy())

            # ---- Native MLX sampling (temperature + top-k + top-p) ----
            logprobs = step_logits - mx.logsumexp(step_logits, keepdims=True)
            token_arr = sampler(logprobs)
            mx.eval(token_arr)  # SINGLE sync point per token
            token_id = token_arr.item()

            new_tokens.append(token_id)
            all_token_ids.append(token_id)
            pbar.update(1)

            # Update constrained processor FSM state
            if constrained_processor is not None:
                constrained_processor.update_state(token_id)

            # Check EOS
            if token_id == eos_token_id:
                break
            if pad_token_id is not None and pad_token_id != eos_token_id and token_id == pad_token_id:
                break

            # ---- Next forward step in MLX (LAZY - no eval!) ----
            # By deferring evaluation, the entire pipeline (forward + CFG + mask + sample)
            # executes as one fused graph when mx.eval(token_arr) is called next iteration.
            next_input = mx.array([[token_id]])
            if use_cfg:
                cond_logits = self._mlx_model(next_input, cache=cond_cache)
                uncond_logits = self._mlx_model(next_input, cache=uncond_cache)
                last_cond = cond_logits[:, -1:, :]
                last_uncond = uncond_logits[:, -1:, :]
            else:
                logits_out = self._mlx_model(next_input, cache=cache)
                last_logits = logits_out[:, -1:, :]

            # Periodic memory cleanup (every 256 tokens, matching mlx-lm pattern)
            if step % 256 == 0 and step > 0:
                mx.clear_cache()

        pbar.close()

        # ---- Log generation summary ----
        decode_time = time.time() - decode_start
        num_generated = len(new_tokens)
        decode_tps = num_generated / decode_time if decode_time > 0 else 0
        total_time = prefill_time + decode_time
        logger.info(
            f"MLX native generation complete: {num_generated} tokens in {decode_time:.2f}s "
            f"({decode_tps:.1f} tok/s) | prefill {prefill_time:.2f}s + decode {decode_time:.2f}s = {total_time:.2f}s total"
        )

        # Decode new tokens only
        output_text = self.llm_tokenizer.decode(new_tokens, skip_special_tokens=False)
        return output_text

    def _run_mlx_single(
        self,
        formatted_prompt: str,
        temperature: float,
        cfg_scale: float,
        negative_prompt: str,
        top_k: Optional[int],
        top_p: Optional[float],
        repetition_penalty: float,
        use_constrained_decoding: bool,
        constrained_decoding_debug: bool,
        target_duration: Optional[float],
        user_metadata: Optional[Dict[str, Optional[str]]],
        stop_at_reasoning: bool,
        skip_genres: bool,
        skip_caption: bool,
        skip_language: bool,
        generation_phase: str,
        caption: str,
        lyrics: str,
        cot_text: str,
    ) -> str:
        """
        MLX-accelerated single-item generation.

        Tries optimized native MLX generation first (using mlx-lm infrastructure
        for sampling, repetition penalty, and chunked prefill). Falls back to
        hybrid MLX/PyTorch approach if native generation fails.
        """
        # ---- Try optimized native MLX generation ----
        try:
            return self._run_mlx_single_native(
                formatted_prompt=formatted_prompt,
                temperature=temperature,
                cfg_scale=cfg_scale,
                negative_prompt=negative_prompt,
                top_k=top_k,
                top_p=top_p,
                repetition_penalty=repetition_penalty,
                use_constrained_decoding=use_constrained_decoding,
                constrained_decoding_debug=constrained_decoding_debug,
                target_duration=target_duration,
                user_metadata=user_metadata,
                stop_at_reasoning=stop_at_reasoning,
                skip_genres=skip_genres,
                skip_caption=skip_caption,
                skip_language=skip_language,
                generation_phase=generation_phase,
                caption=caption,
                lyrics=lyrics,
                cot_text=cot_text,
            )
        except Exception as _native_err:
            logger.warning(
                f"Native MLX generation failed ({type(_native_err).__name__}: {_native_err}), "
                f"falling back to hybrid mode"
            )

        # ---- Fallback: Legacy hybrid MLX/PyTorch generation ----
        import mlx.core as mx
        import numpy as np

        # Tokenize prompt
        inputs = self.llm_tokenizer(
            formatted_prompt,
            return_tensors="np",
            padding=False,
            truncation=True,
        )
        input_ids_np = inputs["input_ids"]  # [1, seq_len]
        prompt_length = input_ids_np.shape[1]
        prompt = mx.array(input_ids_np)

        # Setup constrained processor
        constrained_processor = self._setup_constrained_processor(
            use_constrained_decoding=use_constrained_decoding,
            constrained_decoding_debug=constrained_decoding_debug,
            target_duration=target_duration,
            user_metadata=user_metadata,
            stop_at_reasoning=stop_at_reasoning,
            skip_genres=skip_genres,
            skip_caption=skip_caption,
            skip_language=skip_language,
            generation_phase=generation_phase,
            is_batch=False,
        )

        # Calculate max_new_tokens
        max_new_tokens = self._compute_max_new_tokens(
            target_duration=target_duration,
            generation_phase=generation_phase,
        )

        # EOS token
        eos_token_id = self.llm_tokenizer.eos_token_id
        pad_token_id = self.llm_tokenizer.pad_token_id or eos_token_id

        use_cfg = cfg_scale > 1.0
        cfg_label = "CFG " if use_cfg else ""
        tqdm_desc = f"MLX {cfg_label}Generation"

        # ---- Prefill phase ----
        prefill_start = time.time()
        if use_cfg:
            # Build unconditional prompt
            uncond_text = self._build_unconditional_prompt(
                caption=caption,
                lyrics=lyrics,
                cot_text=cot_text,
                negative_prompt=negative_prompt,
                generation_phase=generation_phase,
                is_batch=False,
            )
            uncond_inputs = self.llm_tokenizer(
                uncond_text,
                return_tensors="np",
                padding=False,
                truncation=True,
            )
            uncond_prompt = mx.array(uncond_inputs["input_ids"])
            uncond_length = uncond_prompt.shape[1]

            # Create separate caches for conditional and unconditional
            cond_cache = self._make_mlx_cache()
            uncond_cache = self._make_mlx_cache()

            # Prefill both prompts
            cond_logits = self._mlx_model(prompt, cache=cond_cache)
            uncond_logits = self._mlx_model(uncond_prompt, cache=uncond_cache)
            mx.eval(cond_logits, uncond_logits)

            last_cond = cond_logits[:, -1:, :]
            last_uncond = uncond_logits[:, -1:, :]

            prefill_time = time.time() - prefill_start
            total_prefill_tokens = prompt_length + uncond_length
            prefill_tps = total_prefill_tokens / prefill_time if prefill_time > 0 else 0
            logger.info(
                f"MLX prefill: {total_prefill_tokens} tokens "
                f"(cond={prompt_length}, uncond={uncond_length}) "
                f"in {prefill_time:.2f}s ({prefill_tps:.1f} tok/s)"
            )
        else:
            cache = self._make_mlx_cache()
            logits_out = self._mlx_model(prompt, cache=cache)
            mx.eval(logits_out)
            last_logits = logits_out[:, -1:, :]

            prefill_time = time.time() - prefill_start
            prefill_tps = prompt_length / prefill_time if prefill_time > 0 else 0
            logger.info(
                f"MLX prefill: {prompt_length} tokens "
                f"in {prefill_time:.2f}s ({prefill_tps:.1f} tok/s)"
            )

        # ---- Autoregressive generation loop ----
        # Track all token IDs for constrained processor context
        all_token_ids = list(input_ids_np[0])
        new_tokens = []
        decode_start = time.time()

        pbar = tqdm(total=max_new_tokens, desc=tqdm_desc, unit="tok")
        for step in range(max_new_tokens):
            # Apply CFG formula in MLX
            if use_cfg:
                step_logits = last_uncond + cfg_scale * (last_cond - last_uncond)
            else:
                step_logits = last_logits

            step_logits = step_logits.reshape(1, -1)  # [1, vocab_size]

            # Bridge to PyTorch for logits processing and sampling
            # This reuses all existing tested code (constrained decoding, top-k/p, etc.)
            # Cast to float32 in MLX first: numpy doesn't support bfloat16
            step_logits_f32 = step_logits.astype(mx.float32)
            np_logits = np.array(step_logits_f32, copy=True)
            t_logits = torch.from_numpy(np_logits)
            t_ids = torch.tensor([all_token_ids], dtype=torch.long)

            # Apply constrained processor
            if constrained_processor is not None:
                t_logits = constrained_processor(t_ids, t_logits)

            # Apply repetition penalty
            if repetition_penalty != 1.0:
                from transformers.generation.logits_process import RepetitionPenaltyLogitsProcessor
                rep_proc = RepetitionPenaltyLogitsProcessor(penalty=repetition_penalty)
                t_logits = rep_proc(t_ids, t_logits)

            # Apply top-k and top-p filtering (reuse existing methods)
            t_logits = self._apply_top_k_filter(t_logits, top_k)
            t_logits = self._apply_top_p_filter(t_logits, top_p)

            # Sample token (reuse existing method)
            t_token = self._sample_tokens(t_logits, temperature)
            token_id = t_token.item()

            new_tokens.append(token_id)
            all_token_ids.append(token_id)
            pbar.update(1)

            # Update constrained processor state
            if constrained_processor is not None:
                constrained_processor.update_state(token_id)

            # Check EOS
            if token_id == eos_token_id:
                break
            if pad_token_id is not None and pad_token_id != eos_token_id and token_id == pad_token_id:
                break

            # Next forward step in MLX (fast)
            next_input = mx.array([[token_id]])
            if use_cfg:
                cond_logits = self._mlx_model(next_input, cache=cond_cache)
                uncond_logits = self._mlx_model(next_input, cache=uncond_cache)
                mx.eval(cond_logits, uncond_logits)
                last_cond = cond_logits[:, -1:, :]
                last_uncond = uncond_logits[:, -1:, :]
            else:
                logits_out = self._mlx_model(next_input, cache=cache)
                mx.eval(logits_out)
                last_logits = logits_out[:, -1:, :]

        pbar.close()

        # Log generation summary
        decode_time = time.time() - decode_start
        num_generated = len(new_tokens)
        decode_tps = num_generated / decode_time if decode_time > 0 else 0
        total_time = prefill_time + decode_time
        logger.info(
            f"MLX generation complete: {num_generated} tokens in {decode_time:.2f}s "
            f"({decode_tps:.1f} tok/s) | prefill {prefill_time:.2f}s + decode {decode_time:.2f}s = {total_time:.2f}s total"
        )

        # Decode new tokens only
        output_text = self.llm_tokenizer.decode(new_tokens, skip_special_tokens=False)
        return output_text

    def _run_mlx(
        self,
        formatted_prompts: Union[str, List[str]],
        temperature: float,
        cfg_scale: float,
        negative_prompt: str,
        top_k: Optional[int],
        top_p: Optional[float],
        repetition_penalty: float,
        use_constrained_decoding: bool = True,
        constrained_decoding_debug: bool = False,
        target_duration: Optional[float] = None,
        user_metadata: Optional[Dict[str, Optional[str]]] = None,
        stop_at_reasoning: bool = False,
        skip_genres: bool = True,
        skip_caption: bool = False,
        skip_language: bool = False,
        generation_phase: str = "cot",
        caption: str = "",
        lyrics: str = "",
        cot_text: str = "",
        seeds: Optional[List[int]] = None,
    ) -> Union[str, List[str]]:
        """
        Unified MLX generation function supporting both single and batch modes.

        For batch mode in codes generation phase, uses optimized batch native path
        that shares prefill across all items (saving ~50% prefill time).
        Falls back to sequential processing if batch native fails.
        """
        import mlx.core as mx

        # Normalize input
        formatted_prompt_list, is_batch = self._normalize_batch_input(formatted_prompts)

        if is_batch:
            batch_size = len(formatted_prompt_list)

            # ---- Try optimized batch native path ----
            # Conditions: codes generation phase + all prompts identical (which they are in batch codes phase)
            all_prompts_identical = len(set(formatted_prompt_list)) == 1
            can_use_batch_native = (
                generation_phase == "codes"
                and all_prompts_identical
                and batch_size > 1
                and hasattr(self, '_mlx_model')
                and self._mlx_model is not None
            )

            if can_use_batch_native:
                try:
                    logger.info(
                        f"MLX batch: using optimized batch native path "
                        f"(batch_size={batch_size}, shared prefill)"
                    )
                    return self._run_mlx_batch_native(
                        formatted_prompt=formatted_prompt_list[0],
                        batch_size=batch_size,
                        temperature=temperature,
                        cfg_scale=cfg_scale,
                        negative_prompt=negative_prompt,
                        top_k=top_k,
                        top_p=top_p,
                        repetition_penalty=repetition_penalty,
                        use_constrained_decoding=use_constrained_decoding,
                        constrained_decoding_debug=constrained_decoding_debug,
                        target_duration=target_duration,
                        caption=caption,
                        lyrics=lyrics,
                        cot_text=cot_text,
                        seeds=seeds,
                    )
                except Exception as e:
                    logger.warning(
                        f"MLX batch native failed ({type(e).__name__}: {e}), "
                        f"falling back to sequential mode"
                    )

            # ---- Fallback: sequential processing ----
            logger.info(f"MLX batch: using sequential mode (batch_size={batch_size})")
            output_texts = []
            for i, formatted_prompt in enumerate(formatted_prompt_list):
                # Set MLX seed for reproducibility
                if seeds and i < len(seeds):
                    mx.random.seed(seeds[i])

                output_text = self._run_mlx_single(
                    formatted_prompt=formatted_prompt,
                    temperature=temperature,
                    cfg_scale=cfg_scale,
                    negative_prompt=negative_prompt,
                    top_k=top_k,
                    top_p=top_p,
                    repetition_penalty=repetition_penalty,
                    use_constrained_decoding=use_constrained_decoding,
                    constrained_decoding_debug=constrained_decoding_debug,
                    target_duration=target_duration,
                    user_metadata=None,
                    stop_at_reasoning=False,
                    skip_genres=True,
                    skip_caption=True,
                    skip_language=True,
                    generation_phase=generation_phase,
                    caption=caption,
                    lyrics=lyrics,
                    cot_text=cot_text,
                )
                output_texts.append(output_text)
            return output_texts

        # Single mode
        formatted_prompt = formatted_prompt_list[0]
        return self._run_mlx_single(
            formatted_prompt=formatted_prompt,
            temperature=temperature,
            cfg_scale=cfg_scale,
            negative_prompt=negative_prompt,
            top_k=top_k,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
            use_constrained_decoding=use_constrained_decoding,
            constrained_decoding_debug=constrained_decoding_debug,
            target_duration=target_duration,
            user_metadata=user_metadata,
            stop_at_reasoning=stop_at_reasoning,
            skip_genres=skip_genres,
            skip_caption=skip_caption,
            skip_language=skip_language,
            generation_phase=generation_phase,
            caption=caption,
            lyrics=lyrics,
            cot_text=cot_text,
        )
