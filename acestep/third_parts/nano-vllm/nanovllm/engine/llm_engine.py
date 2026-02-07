import atexit
import threading
from dataclasses import fields
from time import perf_counter
from tqdm.auto import tqdm
from transformers import AutoTokenizer
import torch.multiprocessing as mp

from nanovllm.config import Config
from nanovllm.sampling_params import SamplingParams
from nanovllm.engine.sequence import Sequence
from nanovllm.engine.scheduler import Scheduler
from nanovllm.engine.model_runner import ModelRunner


class LLMEngine:

    def __init__(self, model, **kwargs):
        config_fields = {field.name for field in fields(Config)}
        config_kwargs = {k: v for k, v in kwargs.items() if k in config_fields}
        config = Config(model, **config_kwargs)
        self.ps = []
        self.events = []
        # Thread-safety lock for generate().
        # The scheduler, block manager, model runner, and CUDA graph buffers are all
        # shared mutable state that is NOT thread-safe. In concurrent serving scenarios
        # (API server with ThreadPoolExecutor, multiple queue workers, Gradio with
        # concurrent requests), multiple threads can call generate() simultaneously.
        # Without this lock, concurrent access corrupts scheduler state, block tables,
        # and CUDA graph input buffers, leading to intermittent CUDA device-side
        # assertion failures (illegal memory access in KV cache).
        self._generate_lock = threading.Lock()
        ctx = mp.get_context("spawn")
        for i in range(1, config.tensor_parallel_size):
            event = ctx.Event()
            process = ctx.Process(target=ModelRunner, args=(config, i, event))
            process.start()
            self.ps.append(process)
            self.events.append(event)
        self.model_runner = ModelRunner(config, 0, self.events)
        tokenizer = kwargs.get("tokenizer", None)
        if tokenizer is not None:
            self.tokenizer = tokenizer
        else:
            self.tokenizer = AutoTokenizer.from_pretrained(config.model, use_fast=True)
        config.eos = self.tokenizer.eos_token_id
        self.scheduler = Scheduler(config)
        atexit.register(self.exit)

    def exit(self):
        self.model_runner.call("exit")
        del self.model_runner
        for p in self.ps:
            p.join()

    def add_request(self, prompt: str | list[int], sampling_params: SamplingParams, unconditional_prompt: str | list[int] | None = None):
        if isinstance(prompt, str):
            prompt = self.tokenizer.encode(prompt)
        # For CFG: if cfg_scale > 1.0, create both conditional and unconditional sequences
        if sampling_params.cfg_scale > 1.0:
            if unconditional_prompt is None:
                # Try to construct unconditional prompt by replacing user input with "NO USER INPUT"
                # This is a fallback - ideally users should provide unconditional_prompt
                if isinstance(prompt, list):
                    # For now, just use the same prompt (user should provide unconditional_prompt)
                    # TODO: Implement automatic "NO USER INPUT" replacement if possible
                    unconditional_prompt = prompt
                else:
                    unconditional_prompt = prompt
            if isinstance(unconditional_prompt, str):
                unconditional_prompt = self.tokenizer.encode(unconditional_prompt)
            # Create unconditional sequence first (so we can reference it from conditional)
            uncond_seq = Sequence(unconditional_prompt, sampling_params, is_unconditional=True)
            # Create conditional sequence with reference to unconditional
            cond_seq = Sequence(prompt, sampling_params, is_unconditional=False, conditional_seq=uncond_seq)
            uncond_seq.paired_seq = cond_seq  # Link them bidirectionally
            # Add both sequences to scheduler
            self.scheduler.add(cond_seq)
            self.scheduler.add(uncond_seq)
        else:
            seq = Sequence(prompt, sampling_params)
            self.scheduler.add(seq)

    def step(self):
        seqs, is_prefill = self.scheduler.schedule()
        token_ids = self.model_runner.call("run", seqs, is_prefill)
        self.scheduler.postprocess(seqs, token_ids)
        # Only output conditional sequences (unconditional sequences are just for CFG computation)
        output_seqs = [seq for seq in seqs if seq.is_finished and (seq.cfg_scale <= 1.0 or not seq.is_unconditional)]
        outputs = [(seq.seq_id, seq.completion_token_ids) for seq in output_seqs]
        num_tokens = sum(len(seq) for seq in seqs) if is_prefill else -len([s for s in seqs if not s.is_unconditional])
        return outputs, num_tokens

    def is_finished(self):
        return self.scheduler.is_finished()

    def reset(self):
        """
        Reset the scheduler state and release all allocated blocks.
        This should be called when an exception occurs during generation to prevent
        KV cache block leaks that can cause 'deque index out of range' errors.
        """
        # Deallocate all running sequences
        while self.scheduler.running:
            seq = self.scheduler.running.popleft()
            if seq.block_table:  # Only deallocate if blocks are allocated
                self.scheduler.block_manager.deallocate(seq)
        
        # Deallocate all waiting sequences (they might have blocks from preemption)
        while self.scheduler.waiting:
            seq = self.scheduler.waiting.popleft()
            if seq.block_table:
                self.scheduler.block_manager.deallocate(seq)

    def generate(
        self,
        prompts: list[str] | list[list[int]],
        sampling_params: SamplingParams | list[SamplingParams],
        use_tqdm: bool = True,
        unconditional_prompts: list[str] | list[list[int]] | None = None,
    ) -> list[str]:
        # Serialize access to the engine to prevent concurrent corruption of
        # scheduler state, block manager, CUDA graph buffers, and KV cache.
        # This is the primary defense against the intermittent CUDA device-side
        # assertion error that occurs in concurrent serving scenarios.
        with self._generate_lock:
            return self._generate_impl(prompts, sampling_params, use_tqdm, unconditional_prompts)

    def _generate_impl(
        self,
        prompts: list[str] | list[list[int]],
        sampling_params: SamplingParams | list[SamplingParams],
        use_tqdm: bool = True,
        unconditional_prompts: list[str] | list[list[int]] | None = None,
    ) -> list[str]:
        # Clean up any residual state from previous interrupted generations
        # This prevents 'deque index out of range' errors from accumulated block leaks
        if not self.is_finished():
            self.reset()
        
        if use_tqdm:
            pbar = tqdm(total=len(prompts), desc="Generating", dynamic_ncols=True)
        if not isinstance(sampling_params, list):
            sampling_params = [sampling_params] * len(prompts)
        if unconditional_prompts is None:
            unconditional_prompts = [None] * len(prompts)
        for prompt, sp, uncond_prompt in zip(prompts, sampling_params, unconditional_prompts):
            self.add_request(prompt, sp, uncond_prompt)
        outputs = {}
        prefill_throughput = decode_throughput = 0.
        try:
            while not self.is_finished():
                t = perf_counter()
                output, num_tokens = self.step()
                if use_tqdm:
                    if num_tokens > 0:
                        prefill_throughput = num_tokens / (perf_counter() - t)
                    else:
                        decode_throughput = -num_tokens / (perf_counter() - t)
                    pbar.set_postfix({
                        "Prefill": f"{int(prefill_throughput)}tok/s",
                        "Decode": f"{int(decode_throughput)}tok/s",
                    })
                for seq_id, token_ids in output:
                    outputs[seq_id] = token_ids
                    if use_tqdm:
                        pbar.update(1)
        except Exception:
            # Clean up on exception to prevent block leaks
            self.reset()
            raise
        finally:
            if use_tqdm:
                pbar.close()
        
        outputs = [outputs[seq_id] for seq_id in sorted(outputs.keys())]
        outputs = [{"text": self.tokenizer.decode(token_ids), "token_ids": token_ids} for token_ids in outputs]
        return outputs
