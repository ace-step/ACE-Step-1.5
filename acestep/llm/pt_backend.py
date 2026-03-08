"""
PyTorch backend mixin for LLM inference.

Provides model loading and generation methods for the PyTorch backend,
extracted from LLMHandler to allow modular composition.
"""

import traceback
from typing import Optional, Dict, List, Tuple, Union

import torch
from loguru import logger
from transformers import AutoModelForCausalLM


class PytorchBackendMixin:
    """Mixin providing PyTorch model loading and generation methods.

    Expects the combined class to provide attributes such as:
        llm, llm_tokenizer, llm_backend, llm_initialized, offload_to_cpu,
        dtype, device, _load_model_context, _setup_constrained_processor,
        _compute_max_new_tokens, _build_logits_processor,
        _build_unconditional_prompt, _generate_with_cfg_custom,
        _generate_with_constrained_decoding, _normalize_batch_input.
    """

    def _load_pytorch_model(self, model_path: str, device: str) -> Tuple[bool, str]:
        """Load PyTorch model from path and return (success, status_message)"""
        try:
            self.llm = AutoModelForCausalLM.from_pretrained(model_path, trust_remote_code=True)
            if not self.offload_to_cpu:
                self.llm = self.llm.to(device).to(self.dtype)
            else:
                self.llm = self.llm.to("cpu").to(self.dtype)
            self.llm.eval()
            self.llm_backend = "pt"
            self.llm_initialized = True
            logger.info(f"5Hz LM initialized successfully using PyTorch backend on {device}")
            status_msg = f"✅ 5Hz LM initialized successfully\nModel: {model_path}\nBackend: PyTorch\nDevice: {device}"
            return True, status_msg
        except Exception as e:
            return False, f"❌ Error initializing 5Hz LM: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"

    def _run_pt_single(
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
        """Internal helper function for single-item PyTorch generation."""
        inputs = self.llm_tokenizer(
            formatted_prompt,
            return_tensors="pt",
            padding=False,
            truncation=True,
        )

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

        with self._load_model_context():
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Calculate max_new_tokens based on target_duration and generation phase
            max_new_tokens = self._compute_max_new_tokens(
                target_duration=target_duration,
                generation_phase=generation_phase,
                fallback_max=getattr(self.llm.config, "max_new_tokens", 4096),
            )

            # Build logits processor list (only for CFG and repetition penalty)
            logits_processor = self._build_logits_processor(repetition_penalty)

            if cfg_scale > 1.0:
                # Build unconditional prompt based on generation phase
                formatted_unconditional_prompt = self._build_unconditional_prompt(
                    caption=caption,
                    lyrics=lyrics,
                    cot_text=cot_text,
                    negative_prompt=negative_prompt,
                    generation_phase=generation_phase,
                    is_batch=False,
                )

                # Tokenize both prompts together to ensure same length (with left padding)
                # Left padding is important for generation tasks
                batch_texts = [formatted_prompt, formatted_unconditional_prompt]
                original_padding_side = self.llm_tokenizer.padding_side
                self.llm_tokenizer.padding_side = 'left'
                batch_inputs_tokenized = self.llm_tokenizer(
                    batch_texts,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                )
                self.llm_tokenizer.padding_side = original_padding_side
                batch_inputs_tokenized = {k: v.to(self.device) for k, v in batch_inputs_tokenized.items()}

                # Extract batch inputs
                batch_input_ids = batch_inputs_tokenized['input_ids']
                batch_attention_mask = batch_inputs_tokenized.get('attention_mask', None)

                # Use custom CFG generation loop with constrained decoding
                outputs = self._generate_with_cfg_custom(
                    batch_input_ids=batch_input_ids,
                    batch_attention_mask=batch_attention_mask,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    cfg_scale=cfg_scale,
                    top_k=top_k,
                    top_p=top_p,
                    repetition_penalty=repetition_penalty,
                    pad_token_id=self.llm_tokenizer.pad_token_id or self.llm_tokenizer.eos_token_id,
                    streamer=None,
                    constrained_processor=constrained_processor,
                )

                # Extract only the conditional output (first in batch)
                outputs = outputs[0:1]  # Keep only conditional output
            elif use_constrained_decoding:
                # Use custom constrained decoding loop for non-CFG
                outputs = self._generate_with_constrained_decoding(
                    input_ids=inputs["input_ids"],
                    attention_mask=inputs.get("attention_mask"),
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    top_k=top_k,
                    top_p=top_p,
                    repetition_penalty=repetition_penalty,
                    pad_token_id=self.llm_tokenizer.pad_token_id or self.llm_tokenizer.eos_token_id,
                    streamer=None,
                    constrained_processor=constrained_processor,
                )
            else:
                # Generate without CFG using native generate() parameters
                with torch.inference_mode():
                    outputs = self.llm.generate(
                        **inputs,
                        max_new_tokens=max_new_tokens,
                        temperature=temperature if temperature > 0 else 1.0,
                        do_sample=True if temperature > 0 else False,
                        top_k=top_k if top_k is not None and top_k > 0 else None,
                        top_p=top_p if top_p is not None and 0.0 < top_p < 1.0 else None,
                        logits_processor=logits_processor if len(logits_processor) > 0 else None,
                        pad_token_id=self.llm_tokenizer.pad_token_id or self.llm_tokenizer.eos_token_id,
                        streamer=None,
                    )

        # Decode the generated tokens
        # outputs is a tensor with shape [batch_size, seq_len], extract first sequence
        if isinstance(outputs, torch.Tensor):
            if outputs.dim() == 2:
                generated_ids = outputs[0]
            else:
                generated_ids = outputs
        else:
            generated_ids = outputs[0]

        # Only decode the newly generated tokens (skip the input prompt)
        # Use the original input length (before batch processing for CFG)
        if cfg_scale > 1.0:
            # In CFG case, we need to use the conditional input length from batch_inputs_tokenized
            # Both sequences have the same length due to padding
            input_length = batch_inputs_tokenized['input_ids'].shape[1]
        else:
            input_length = inputs["input_ids"].shape[1]

        generated_ids = generated_ids[input_length:]

        # Move to CPU for decoding (tokenizer needs CPU tensors)
        if generated_ids.device.type != "cpu":
            generated_ids = generated_ids.cpu()

        output_text = self.llm_tokenizer.decode(generated_ids, skip_special_tokens=False)
        return output_text

    def _run_pt(
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
        Unified PyTorch generation function supporting both single and batch modes.
        Accepts either a single formatted prompt (str) or a list of formatted prompts (List[str]).
        Returns a single string for single mode, or a list of strings for batch mode.
        Note: PyTorch backend processes batch items sequentially (doesn't support true batching efficiently).
        """
        # Determine if batch mode
        formatted_prompt_list, is_batch = self._normalize_batch_input(formatted_prompts)

        # For batch mode, process each item sequentially with different seeds.
        # Wrap the entire loop in a single _load_model_context() so the model
        # loads to GPU once and offloads once, instead of per-item.
        if is_batch:
            output_texts = []

            with self._load_model_context():
                for i, formatted_prompt in enumerate(formatted_prompt_list):
                    # Set seed for this item if provided
                    if seeds and i < len(seeds):
                        torch.manual_seed(seeds[i])
                        if torch.cuda.is_available():
                            torch.cuda.manual_seed_all(seeds[i])
                        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                            torch.mps.manual_seed(seeds[i])

                    # Generate using single-item method with batch-mode defaults
                    output_text = self._run_pt_single(
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

        # Single mode: process the formatted prompt
        formatted_prompt = formatted_prompt_list[0]

        return self._run_pt_single(
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
