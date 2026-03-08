"""
vLLM backend mixin for LLMHandler.

Provides the _initialize_5hz_lm_vllm and _run_vllm methods that handle
model initialization and text generation via the nano-vllm (vLLM) backend.
This mixin is intended to be combined with other mixins and a base class
that supply shared attributes (self.llm, self.llm_initialized, etc.) and
helper methods (self.get_gpu_memory_utilization, self._normalize_batch_input,
self._setup_constrained_processor, self._compute_max_new_tokens,
self._build_unconditional_prompt, self._cleanup_torch_distributed_state).
"""

import time
import traceback
from typing import Dict, List, Optional, Union

import torch
from loguru import logger

from acestep.gpu_config import get_lm_model_size
from acestep.llm.constants import BYTES_PER_GB, LOW_GPU_MAX_MODEL_LEN, DEFAULT_MAX_MODEL_LEN


class VllmBackendMixin:
    """Mixin that adds vLLM backend support to LLMHandler."""

    def _initialize_5hz_lm_vllm(self, model_path: str, enforce_eager: bool = False) -> str:
        """Initialize 5Hz LM model using vllm backend. When enforce_eager is True, CUDA graph
        capture is disabled (required when LoRA training may run in the same process)."""
        if not torch.cuda.is_available():
            self.llm_initialized = False
            logger.error("CUDA/ROCm is not available. Please check your GPU setup.")
            return "❌ CUDA/ROCm is not available. Please check your GPU setup."
        try:
            from nanovllm import LLM, SamplingParams
        except ImportError:
            self.llm_initialized = False
            logger.error("nano-vllm is not installed. Please install it using 'cd acestep/third_parts/nano-vllm && pip install .")
            return "❌ nano-vllm is not installed. Please install it using 'cd acestep/third_parts/nano-vllm && pip install ."

        try:
            current_device = torch.cuda.current_device()
            device_name = torch.cuda.get_device_name(current_device)

            torch.cuda.empty_cache()
            self._cleanup_torch_distributed_state()

            # Use adaptive GPU memory utilization based on model size
            gpu_memory_utilization, low_gpu_memory_mode = self.get_gpu_memory_utilization(
                model_path=model_path,
                minimal_gpu=3,
                min_ratio=0.1,
                max_ratio=0.9
            )

            if low_gpu_memory_mode:
                self.max_model_len = LOW_GPU_MAX_MODEL_LEN
            else:
                self.max_model_len = DEFAULT_MAX_MODEL_LEN

            logger.info(f"Initializing 5Hz LM with model: {model_path}, enforce_eager: {enforce_eager}, tensor_parallel_size: 1, max_model_len: {self.max_model_len}, gpu_memory_utilization: {gpu_memory_utilization:.3f}")
            start_time = time.time()
            self.llm = LLM(
                model=model_path,
                enforce_eager=enforce_eager,
                tensor_parallel_size=1,
                max_model_len=self.max_model_len,
                gpu_memory_utilization=gpu_memory_utilization,
                tokenizer=self.llm_tokenizer,
            )
            logger.info(f"5Hz LM initialized successfully in {time.time() - start_time:.2f} seconds")
            self.llm_initialized = True
            self.llm_backend = "vllm"
            return f"✅ 5Hz LM initialized successfully\nModel: {model_path}\nDevice: {device_name}\nGPU Memory Utilization: {gpu_memory_utilization:.3f}\nLow GPU Memory Mode: {low_gpu_memory_mode}"
        except Exception as e:
            self.llm_initialized = False
            return f"❌ Error initializing 5Hz LM: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"

    def _run_vllm(
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
        metadata_temperature: Optional[float] = None,
        codes_temperature: Optional[float] = None,
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
        Unified vllm generation function supporting both single and batch modes.
        Accepts either a single formatted prompt (str) or a list of formatted prompts (List[str]).
        Returns a single string for single mode, or a list of strings for batch mode.
        """
        from nanovllm import SamplingParams

        # Determine if batch mode
        formatted_prompt_list, is_batch = self._normalize_batch_input(formatted_prompts)
        batch_size = len(formatted_prompt_list)

        # Determine effective temperature for sampler
        # Batch mode doesn't support phase temperatures, so use simple temperature
        # Single mode supports phase temperatures
        use_phase_temperatures = not is_batch and (metadata_temperature is not None or codes_temperature is not None)
        effective_sampler_temp = 1.0 if use_phase_temperatures else temperature

        # Setup constrained processor
        constrained_processor = self._setup_constrained_processor(
            use_constrained_decoding=use_constrained_decoding or use_phase_temperatures,
            constrained_decoding_debug=constrained_decoding_debug,
            target_duration=target_duration,
            user_metadata=user_metadata,
            stop_at_reasoning=stop_at_reasoning,
            skip_genres=skip_genres,
            skip_caption=skip_caption,
            skip_language=skip_language,
            generation_phase=generation_phase,
            is_batch=is_batch,
            metadata_temperature=metadata_temperature,
            codes_temperature=codes_temperature,
        )

        # Calculate max_tokens based on target_duration and generation phase
        max_tokens = self._compute_max_new_tokens(
            target_duration=target_duration,
            generation_phase=generation_phase,
            fallback_max=self.max_model_len - 64,
        )

        sampling_params = SamplingParams(
            max_tokens=max_tokens,
            temperature=effective_sampler_temp,
            cfg_scale=cfg_scale,
            top_k=top_k,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
            logits_processor=constrained_processor,
            logits_processor_update_state=constrained_processor.update_state if constrained_processor else None,
        )

        if cfg_scale > 1.0:
            # Build unconditional prompt based on generation phase
            formatted_unconditional_prompt = self._build_unconditional_prompt(
                caption=caption,
                lyrics=lyrics,
                cot_text=cot_text,
                negative_prompt=negative_prompt,
                generation_phase=generation_phase,
                is_batch=is_batch,
            )
            unconditional_prompts = [formatted_unconditional_prompt] * batch_size

            outputs = self.llm.generate(
                formatted_prompt_list,
                sampling_params,
                unconditional_prompts=unconditional_prompts,
            )
        else:
            outputs = self.llm.generate(formatted_prompt_list, sampling_params)

        # Extract text from outputs
        output_texts = []
        for output in outputs:
            if hasattr(output, "outputs") and len(output.outputs) > 0:
                output_texts.append(output.outputs[0].text)
            elif hasattr(output, "text"):
                output_texts.append(output.text)
            elif isinstance(output, dict) and "text" in output:
                output_texts.append(output["text"])
            else:
                output_texts.append(str(output))

        # Return single string for single mode, list for batch mode
        return output_texts[0] if not is_batch else output_texts
