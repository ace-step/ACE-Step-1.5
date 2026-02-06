import os
import pickle
import torch
import torch.distributed as dist
from multiprocessing.synchronize import Event
from multiprocessing.shared_memory import SharedMemory
import sys

from nanovllm.config import Config

# Debug logging - enable with NANOVLLM_DEBUG=1
_DEBUG = os.environ.get("NANOVLLM_DEBUG", "0") == "1"

def _debug_log(msg: str):
    """Print debug message if NANOVLLM_DEBUG is enabled"""
    if _DEBUG:
        print(f"[nanovllm DEBUG] {msg}", flush=True)
from nanovllm.engine.sequence import Sequence
from nanovllm.models.qwen3 import Qwen3ForCausalLM
from nanovllm.layers.sampler import Sampler
from nanovllm.utils.context import set_context, get_context, reset_context
from nanovllm.utils.loader import load_model

import socket


def find_available_port(start_port: int = 2333, max_attempts: int = 100) -> int:
    """Find an available port starting from start_port.
    
    Args:
        start_port: The starting port number to check
        max_attempts: Maximum number of ports to try
        
    Returns:
        An available port number
        
    Raises:
        RuntimeError: If no available port is found within max_attempts
    """
    for i in range(max_attempts):
        port = start_port + i
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('localhost', port))
                return port
        except OSError:
            # Port is in use, try next one
            continue
    raise RuntimeError(f"Could not find an available port starting from {start_port} after {max_attempts} attempts")


class ModelRunner:

    def __init__(self, config: Config, rank: int, event: Event | list[Event]):
        # Enable capturing scalar outputs to avoid graph breaks from Tensor.item() calls
        torch._dynamo.config.capture_scalar_outputs = True
        
        self.config = config
        hf_config = config.hf_config
        self.block_size = config.kvcache_block_size
        self.enforce_eager = config.enforce_eager
        self.world_size = config.tensor_parallel_size
        self.rank = rank
        self.event = event
        dist_port = find_available_port()
        print(f"[debug]dist_port: {dist_port}")
        # Use gloo backend on Windows, nccl on Linux/other platforms
        backend = "gloo" if sys.platform == "win32" else "nccl"
        dist.init_process_group(backend, f"tcp://127.0.0.1:{dist_port}", world_size=self.world_size, rank=rank)
        torch.cuda.set_device(rank)
        default_dtype = torch.get_default_dtype()
        # Use dtype instead of deprecated torch_dtype
        config_dtype = getattr(hf_config, 'dtype', getattr(hf_config, 'torch_dtype', torch.bfloat16))

        # Validate and convert config_dtype to a valid torch floating-point dtype
        # Default to bfloat16 for CUDA (required for Flash Attention 2)
        if config_dtype is None:
            config_dtype = torch.bfloat16
        elif isinstance(config_dtype, str):
            # Convert string dtype to torch dtype
            dtype_map = {
                'float32': torch.float32,
                'float16': torch.float16,
                'bfloat16': torch.bfloat16,
                'float64': torch.float64,
                'torch.float32': torch.float32,
                'torch.float16': torch.float16,
                'torch.bfloat16': torch.bfloat16,
                'torch.float64': torch.float64,
            }
            config_dtype = dtype_map.get(config_dtype.lower(), torch.bfloat16)
        elif not isinstance(config_dtype, torch.dtype) or not config_dtype.is_floating_point:
            # If not a valid floating-point torch dtype, default to bfloat16
            config_dtype = torch.bfloat16

        self.dtype = config_dtype  # Save for later use
        torch.set_default_dtype(config_dtype)
        torch.set_default_device("cuda")
        self.model = Qwen3ForCausalLM(hf_config)
        load_model(self.model, config.model)
        self.sampler = Sampler()
        
        # Pre-allocate buffers for sampling (optimization: avoid repeated tensor creation)
        # Must be called before warmup_model() since it uses these buffers
        self._allocate_sample_buffers()
        
        self.warmup_model()
        self.allocate_kv_cache()
        if not self.enforce_eager:
            self.capture_cudagraph()
        
        torch.set_default_device("cpu")
        torch.set_default_dtype(default_dtype)

        if self.world_size > 1:
            if rank == 0:
                self.shm = SharedMemory(name="nanovllm", create=True, size=2**20)
                dist.barrier()
            else:
                dist.barrier()
                self.shm = SharedMemory(name="nanovllm")
                self.loop()

    def _allocate_sample_buffers(self):
        """Pre-allocate reusable buffers for sampling to avoid repeated tensor creation."""
        max_bs = self.config.max_num_seqs
        max_tokens = self.config.max_num_batched_tokens
        max_num_blocks = (self.config.max_model_len + self.block_size - 1) // self.block_size
        
        # Pre-allocate pinned memory buffers on CPU for fast transfer
        # Must explicitly specify device="cpu" since default device may be "cuda"
        self._cpu_temperatures = torch.zeros(max_bs, dtype=torch.float32, device="cpu", pin_memory=True)
        self._cpu_cfg_scales = torch.zeros(max_bs, dtype=torch.float32, device="cpu", pin_memory=True)
        self._cpu_top_ks = torch.zeros(max_bs, dtype=torch.int32, device="cpu", pin_memory=True)
        self._cpu_top_ps = torch.zeros(max_bs, dtype=torch.float32, device="cpu", pin_memory=True)
        self._cpu_repetition_penalties = torch.zeros(max_bs, dtype=torch.float32, device="cpu", pin_memory=True)
        
        # Pre-allocate decode buffers on CPU with pinned memory
        self._cpu_input_ids = torch.zeros(max_bs, dtype=torch.int64, device="cpu", pin_memory=True)
        self._cpu_positions = torch.zeros(max_bs, dtype=torch.int64, device="cpu", pin_memory=True)
        self._cpu_slot_mapping = torch.zeros(max_bs, dtype=torch.int32, device="cpu", pin_memory=True)
        self._cpu_context_lens = torch.zeros(max_bs, dtype=torch.int32, device="cpu", pin_memory=True)
        
        # Pre-allocate prefill buffers on CPU with pinned memory (optimization to avoid repeated tensor creation)
        self._cpu_prefill_input_ids = torch.zeros(max_tokens, dtype=torch.int64, device="cpu", pin_memory=True)
        self._cpu_prefill_positions = torch.zeros(max_tokens, dtype=torch.int64, device="cpu", pin_memory=True)
        self._cpu_prefill_cu_seqlens = torch.zeros(max_bs + 1, dtype=torch.int32, device="cpu", pin_memory=True)
        self._cpu_prefill_slot_mapping = torch.zeros(max_tokens, dtype=torch.int32, device="cpu", pin_memory=True)
        
        # Pre-allocate block tables buffer (shared by both decode and prefill)
        self._cpu_block_tables = torch.zeros(max_bs, max_num_blocks, dtype=torch.int32, device="cpu", pin_memory=True)
        
        # Pre-allocate buffer for sequence token IDs (used in logits processor and sampler)
        # Max length is max_model_len since sequences can be that long
        self._seq_token_ids_buffer = torch.zeros(max_bs, self.config.max_model_len, dtype=torch.int64, device="cpu", pin_memory=True)

    def exit(self):
        if self.world_size > 1:
            self.shm.close()
            dist.barrier()
            if self.rank == 0:
                self.shm.unlink()
        if not self.enforce_eager:
            del self.graphs, self.graph_pool
        torch.cuda.synchronize()
        dist.destroy_process_group()

    def loop(self):
        while True:
            method_name, args = self.read_shm()
            self.call(method_name, *args)
            if method_name == "exit":
                break

    def read_shm(self):
        assert self.world_size > 1 and self.rank > 0
        self.event.wait()
        n = int.from_bytes(self.shm.buf[0:4], "little")
        method_name, *args = pickle.loads(self.shm.buf[4:n+4])
        self.event.clear()
        return method_name, args

    def write_shm(self, method_name, *args):
        assert self.world_size > 1 and self.rank == 0
        data = pickle.dumps([method_name, *args])
        n = len(data)
        self.shm.buf[0:4] = n.to_bytes(4, "little")
        self.shm.buf[4:n+4] = data
        for event in self.event:
            event.set()

    def call(self, method_name, *args):
        if self.world_size > 1 and self.rank == 0:
            self.write_shm(method_name, *args)
        method = getattr(self, method_name, None)
        return method(*args)

    def warmup_model(self):
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        max_num_batched_tokens, max_model_len = self.config.max_num_batched_tokens, self.config.max_model_len
        num_seqs = min(max_num_batched_tokens // max_model_len, self.config.max_num_seqs)
        seqs = [Sequence([0] * max_model_len) for _ in range(num_seqs)]
        self.run(seqs, True)
        torch.cuda.empty_cache()

    def allocate_kv_cache(self):
        config = self.config
        hf_config = config.hf_config
        free, total = torch.cuda.mem_get_info()
        current = torch.cuda.memory_stats()["allocated_bytes.all.current"]
        num_kv_heads = hf_config.num_key_value_heads // self.world_size
        head_dim = getattr(hf_config, "head_dim", hf_config.hidden_size // hf_config.num_attention_heads)
        block_bytes = 2 * hf_config.num_hidden_layers * self.block_size * num_kv_heads * head_dim * self.dtype.itemsize
        
        # Calculate available memory for KV cache
        # After warmup_model, empty_cache has been called, so current represents model memory only
        # Use free memory but respect the gpu_memory_utilization limit
        target_total_usage = total * config.gpu_memory_utilization
        available_for_kv_cache = min(free * 0.9, target_total_usage - current)
        
        # Ensure we have positive memory available
        if available_for_kv_cache <= 0:
            available_for_kv_cache = free * 0.5  # Fallback to 50% of free memory
        
        config.num_kvcache_blocks = max(1, int(available_for_kv_cache) // block_bytes)
        if config.num_kvcache_blocks <= 0:
            raise RuntimeError(
                f"Insufficient GPU memory for KV cache. "
                f"Free: {free / 1024**3:.2f} GB, Current: {current / 1024**3:.2f} GB, "
                f"Available for KV: {available_for_kv_cache / 1024**3:.2f} GB, "
                f"Block size: {block_bytes / 1024**2:.2f} MB"
            )
        max_tokens_capacity = config.num_kvcache_blocks * self.block_size
        kv_cache_size_gb = config.num_kvcache_blocks * block_bytes / 1024**3
        print(
            f"[nanovllm] KV cache allocated: {config.num_kvcache_blocks} blocks × {self.block_size} tokens = "
            f"{max_tokens_capacity} tokens capacity, {kv_cache_size_gb:.2f} GB "
            f"(free: {free / 1024**3:.2f} GB, used: {current / 1024**3:.2f} GB, "
            f"target: {target_total_usage / 1024**3:.2f} GB, block: {block_bytes / 1024**2:.2f} MB)"
        )
        self.kv_cache = torch.empty(2, hf_config.num_hidden_layers, config.num_kvcache_blocks, self.block_size, num_kv_heads, head_dim)
        layer_id = 0
        for module in self.model.modules():
            if hasattr(module, "k_cache") and hasattr(module, "v_cache"):
                module.k_cache = self.kv_cache[0, layer_id]
                module.v_cache = self.kv_cache[1, layer_id]
                layer_id += 1

    def prepare_block_tables(self, seqs: list[Sequence]):
        max_len = max(len(seq.block_table) for seq in seqs)
        block_tables = [seq.block_table + [-1] * (max_len - len(seq.block_table)) for seq in seqs]
        block_tables = torch.tensor(block_tables, dtype=torch.int32, pin_memory=True).cuda(non_blocking=True)
        return block_tables

    def prepare_prefill(self, seqs: list[Sequence]):
        input_ids = []
        positions = []
        cu_seqlens_q = [0]
        cu_seqlens_k = [0]
        max_seqlen_q = 0
        max_seqlen_k = 0
        slot_mapping = []
        block_tables = None
        for seq in seqs:
            seqlen = len(seq)
            input_ids.extend(seq[seq.num_cached_tokens:])
            positions.extend(list(range(seq.num_cached_tokens, seqlen)))
            seqlen_q = seqlen - seq.num_cached_tokens
            seqlen_k = seqlen
            cu_seqlens_q.append(cu_seqlens_q[-1] + seqlen_q)
            cu_seqlens_k.append(cu_seqlens_k[-1] + seqlen_k)
            max_seqlen_q = max(seqlen_q, max_seqlen_q)
            max_seqlen_k = max(seqlen_k, max_seqlen_k)
            if not seq.block_table:    # warmup
                continue
            for i in range(seq.num_cached_blocks, seq.num_blocks):
                start = seq.block_table[i] * self.block_size
                if i != seq.num_blocks - 1:
                    end = start + self.block_size
                else:
                    end = start + seq.last_block_num_tokens
                slot_mapping.extend(list(range(start, end)))
        if cu_seqlens_k[-1] > cu_seqlens_q[-1]:    # prefix cache
            block_tables = self.prepare_block_tables(seqs)
        input_ids = torch.tensor(input_ids, dtype=torch.int64, pin_memory=True).cuda(non_blocking=True)
        positions = torch.tensor(positions, dtype=torch.int64, pin_memory=True).cuda(non_blocking=True)
        cu_seqlens_q = torch.tensor(cu_seqlens_q, dtype=torch.int32, pin_memory=True).cuda(non_blocking=True)
        cu_seqlens_k = torch.tensor(cu_seqlens_k, dtype=torch.int32, pin_memory=True).cuda(non_blocking=True)
        slot_mapping = torch.tensor(slot_mapping, dtype=torch.int32, pin_memory=True).cuda(non_blocking=True)
        set_context(True, cu_seqlens_q, cu_seqlens_k, max_seqlen_q, max_seqlen_k, slot_mapping, None, block_tables)
        return input_ids, positions

    def prepare_decode(self, seqs: list[Sequence]):
        """Optimized decode preparation using pre-allocated buffers."""
        bs = len(seqs)
        
        # Use pre-allocated CPU buffers
        for i, seq in enumerate(seqs):
            self._cpu_input_ids[i] = seq.last_token
            self._cpu_positions[i] = len(seq) - 1
            self._cpu_context_lens[i] = len(seq)
            self._cpu_slot_mapping[i] = seq.block_table[-1] * self.block_size + seq.last_block_num_tokens - 1
        
        # Transfer to GPU using sliced views
        input_ids = self._cpu_input_ids[:bs].cuda(non_blocking=True)
        positions = self._cpu_positions[:bs].cuda(non_blocking=True)
        slot_mapping = self._cpu_slot_mapping[:bs].cuda(non_blocking=True)
        context_lens = self._cpu_context_lens[:bs].cuda(non_blocking=True)
        block_tables = self.prepare_block_tables(seqs)
        set_context(False, slot_mapping=slot_mapping, context_lens=context_lens, block_tables=block_tables)
        return input_ids, positions

    def prepare_sample(self, seqs: list[Sequence], is_cfg_batch: bool = False):
        """Optimized sample preparation using pre-allocated buffers."""
        if is_cfg_batch:
            num_seqs = len(seqs) // 2
            target_seqs = seqs[:num_seqs]
        else:
            num_seqs = len(seqs)
            target_seqs = seqs
        
        # Fill pre-allocated CPU buffers
        top_ks_is_zero = True
        top_ps_is_one = True
        repetition_penalties_is_one = True
        for i, seq in enumerate(target_seqs):
            self._cpu_temperatures[i] = seq.temperature
            self._cpu_cfg_scales[i] = seq.cfg_scale
            self._cpu_top_ks[i] = seq.top_k if seq.top_k is not None else 0
            if seq.top_k is not None and seq.top_k > 0:
                top_ks_is_zero = False
            self._cpu_top_ps[i] = seq.top_p if seq.top_p is not None else 1.0
            if seq.top_p is not None and seq.top_p == 1.0:
                top_ps_is_one = False
            self._cpu_repetition_penalties[i] = seq.repetition_penalty if seq.repetition_penalty is not None else 1.0
            if seq.repetition_penalty is not None and seq.repetition_penalty == 1.0:
                repetition_penalties_is_one = False
        
        # Transfer to GPU using sliced views (single batched transfer)
        temperatures = self._cpu_temperatures[:num_seqs].cuda(non_blocking=True)
        cfg_scales = self._cpu_cfg_scales[:num_seqs].cuda(non_blocking=True)
        top_ks = self._cpu_top_ks[:num_seqs].cuda(non_blocking=True) if not top_ks_is_zero else None
        top_ps = self._cpu_top_ps[:num_seqs].cuda(non_blocking=True) if not top_ps_is_one else None
        repetition_penalties = self._cpu_repetition_penalties[:num_seqs].cuda(non_blocking=True) if not repetition_penalties_is_one else None
        
        return temperatures, cfg_scales, top_ks, top_ps, repetition_penalties

    @torch.inference_mode()
    def run_model(self, input_ids: torch.Tensor, positions: torch.Tensor, is_prefill: bool):
        if is_prefill or self.enforce_eager or input_ids.size(0) > 512:
            _debug_log(f"run_model: eager mode, is_prefill={is_prefill}, bs={input_ids.size(0)}")
            return self.model.compute_logits(self.model(input_ids, positions))
        else:
            bs = input_ids.size(0)
            context = get_context()
            
            _debug_log(f"run_model: decode mode, bs={bs}")
            _debug_log(f"  context.block_tables.shape={context.block_tables.shape}")
            _debug_log(f"  context.slot_mapping.shape={context.slot_mapping.shape}")
            _debug_log(f"  context.context_lens.shape={context.context_lens.shape}")
            _debug_log(f"  context.slot_mapping={context.slot_mapping.tolist()}")
            _debug_log(f"  context.context_lens={context.context_lens.tolist()}")
            
            # Check if block_tables size exceeds pre-allocated buffer size
            # This can happen when conditional and unconditional sequences have different lengths
            # in CFG mode, causing block_tables to have more columns than expected
            max_num_blocks = self.graph_vars["block_tables"].size(1)
            if context.block_tables.size(1) > max_num_blocks:
                # Fall back to eager mode when block_tables is too large for CUDA graph
                _debug_log(f"  fallback: block_tables cols {context.block_tables.size(1)} > max {max_num_blocks}")
                return self.model.compute_logits(self.model(input_ids, positions))
            
            # Fix: Also check if block_tables row count matches batch size
            # Dimension mismatch can cause CUDA illegal memory access during graph replay
            if context.block_tables.size(0) != bs:
                # Fall back to eager mode when block_tables row count doesn't match batch size
                _debug_log(f"  fallback: block_tables rows {context.block_tables.size(0)} != bs {bs}")
                return self.model.compute_logits(self.model(input_ids, positions))
            
            # Fix: Verify slot_mapping and context_lens dimensions match batch size
            if context.slot_mapping.size(0) != bs or context.context_lens.size(0) != bs:
                # Fall back to eager mode when dimensions don't match
                _debug_log(f"  fallback: slot_mapping/context_lens size mismatch")
                return self.model.compute_logits(self.model(input_ids, positions))
            
            # Validate block_tables values
            if _DEBUG:
                max_block_id = context.block_tables.max().item()
                min_block_id = context.block_tables[context.block_tables >= 0].min().item() if (context.block_tables >= 0).any() else -1
                _debug_log(f"  block_tables range: [{min_block_id}, {max_block_id}]")
                _debug_log(f"  num_kvcache_blocks: {self.config.num_kvcache_blocks}")
                if max_block_id >= self.config.num_kvcache_blocks:
                    _debug_log(f"  WARNING: block_table contains invalid block_id {max_block_id} >= {self.config.num_kvcache_blocks}")
            
            graph = self.graphs[next(x for x in self.graph_bs if x >= bs)]
            graph_vars = self.graph_vars
            graph_vars["input_ids"][:bs] = input_ids
            graph_vars["positions"][:bs] = positions
            graph_vars["slot_mapping"].fill_(-1)
            graph_vars["slot_mapping"][:bs] = context.slot_mapping
            graph_vars["context_lens"].zero_()
            graph_vars["context_lens"][:bs] = context.context_lens
            # Clear block_tables first to ensure no stale data from previous runs
            graph_vars["block_tables"][:bs].fill_(-1)
            graph_vars["block_tables"][:bs, :context.block_tables.size(1)] = context.block_tables
            
            _debug_log(f"  executing CUDA graph replay for bs={bs}")
            graph.replay()
            return self.model.compute_logits(graph_vars["outputs"][:bs])

    def run(self, seqs: list[Sequence], is_prefill: bool) -> list[int]:
        """Run model forward and sampling. For CFG sequences, batch is structured as:
        [cond_seq1, cond_seq2, ..., uncond_seq1, uncond_seq2, ...]
        where uncond_seqi is the paired unconditional sequence of cond_seqi."""
        _debug_log(f"run: num_seqs={len(seqs)}, is_prefill={is_prefill}")
        for i, seq in enumerate(seqs):
            _debug_log(f"  seq[{i}]: len={len(seq)}, num_blocks={seq.num_blocks}, "
                      f"cfg_scale={seq.cfg_scale}, is_uncond={seq.is_unconditional}, "
                      f"block_table={seq.block_table}")
        
        # Check if this is a CFG batch (contains paired conditional and unconditional sequences)
        is_cfg_batch = seqs[0].cfg_scale > 1.0 and seqs[0].paired_seq is not None
        _debug_log(f"  is_cfg_batch={is_cfg_batch}")
        if is_cfg_batch:
            # CFG batch: seqs = [cond_seq1, cond_seq2, ..., uncond_seq1, uncond_seq2, ...]
            num_cond = len(seqs) // 2
            cond_seqs = seqs[:num_cond]
            # uncond_seqs = seqs[num_cond:]
            
            # Prepare inputs for both conditional and unconditional (they're already in the batch)
            input_ids, positions = (self.prepare_prefill(seqs) if is_prefill else self.prepare_decode(seqs))
            sample_params = self.prepare_sample(seqs, is_cfg_batch=True) if self.rank == 0 else None
            if sample_params is not None:
                temperatures, cfg_scales, top_ks, top_ps, repetition_penalties = sample_params
            else:
                temperatures = cfg_scales = top_ks = top_ps = repetition_penalties = None
            
            # Run model forward (processes entire batch: cond + uncond)
            logits_all = self.run_model(input_ids, positions, is_prefill)
            reset_context()
            
            if self.rank == 0:
                # Split logits: first half is conditional, second half is unconditional
                logits_cond = logits_all[:num_cond]
                logits_uncond = logits_all[num_cond:]
                
                # Apply repetition penalty to conditional logits (before CFG)
                if repetition_penalties is not None:
                    for i, seq in enumerate(cond_seqs):
                        penalty = repetition_penalties[i].item()
                        if penalty != 1.0:
                            # Only penalize completion tokens (not prompt tokens)
                            completion_tokens = torch.tensor(seq.completion_token_ids, device=logits_cond.device)
                            if len(completion_tokens) > 0:
                                # Create token mask: mark tokens that appeared in completion
                                token_mask = torch.zeros(logits_cond.shape[1], dtype=torch.bool, device=logits_cond.device)
                                token_mask[completion_tokens] = True
                                
                                # Apply standard repetition penalty formula (matching transformers implementation):
                                # For tokens in completion: if score < 0 then score * penalty, else score / penalty
                                penalty_scores = torch.where(
                                    logits_cond[i] < 0,
                                    logits_cond[i] * penalty,
                                    logits_cond[i] / penalty
                                )
                                # Only apply penalty to tokens that appeared in completion
                                logits_cond[i] = torch.where(token_mask, penalty_scores, logits_cond[i])
                
                # Apply CFG formula: logits_cfg = logits_uncond + cfg_scale * (logits_cond - logits_uncond)
                cfg_scales_tensor = cfg_scales.unsqueeze(1)  # [num_cond, 1]
                logits_cfg = logits_uncond + cfg_scales_tensor * (logits_cond - logits_uncond)
                
                # Apply logits processor for constrained decoding (if any sequence has one)
                for i, seq in enumerate(cond_seqs):
                    if seq.logits_processor is not None:
                        # Create input_ids tensor for this sequence
                        seq_input_ids = torch.tensor([seq.token_ids], device=logits_cfg.device)
                        # Apply processor to this sequence's logits
                        logits_cfg[i:i+1] = seq.logits_processor(seq_input_ids, logits_cfg[i:i+1])
                
                # Prepare input_ids for sampler (for repetition penalty, though we already applied it)
                # cond_input_ids = torch.tensor([seq.token_ids for seq in cond_seqs], device=logits_cfg.device)
                
                # Sample from CFG logits
                token_ids_cfg = self.sampler(
                    logits_cfg, 
                    temperatures,
                    top_ks=top_ks if top_ks is not None else None,
                    top_ps=top_ps if top_ps is not None else None,
                    repetition_penalties=None,  # Already applied above
                    # input_ids=cond_input_ids,
                ).tolist()
                
                # Update logits processor state after sampling
                # NOTE: Only update for the first sequence since all sequences share the same processor
                # Updating multiple times would cause duplicate state updates (e.g., codes_count += N instead of += 1)
                if cond_seqs and cond_seqs[0].logits_processor_update_state is not None:
                    cond_seqs[0].logits_processor_update_state(token_ids_cfg[0])
                
                # Return token_ids (will be applied to both conditional and unconditional sequences)
                return token_ids_cfg
            else:
                return None
        else:
            # Normal batch (non-CFG)
            input_ids, positions = (self.prepare_prefill(seqs) if is_prefill 
                                   else self.prepare_decode(seqs))
            sample_params = self.prepare_sample(seqs, is_cfg_batch=False) if self.rank == 0 else None
            if sample_params is not None:
                temperatures, cfg_scales, top_ks, top_ps, repetition_penalties = sample_params
            else:
                temperatures = cfg_scales = top_ks = top_ps = repetition_penalties = None
            logits = self.run_model(input_ids, positions, is_prefill)
            reset_context()
            
            if self.rank == 0:
                # Apply repetition penalty to logits
                if repetition_penalties is not None:
                    for i, seq in enumerate(seqs):
                        penalty = repetition_penalties[i].item()
                        if penalty != 1.0:
                            # Only penalize completion tokens (not prompt tokens)
                            completion_tokens = torch.tensor(seq.completion_token_ids, device=logits.device)
                            if len(completion_tokens) > 0:
                                # Create token mask: mark tokens that appeared in completion
                                token_mask = torch.zeros(logits.shape[1], dtype=torch.bool, device=logits.device)
                                token_mask[completion_tokens] = True
                                
                                # Apply standard repetition penalty formula (matching transformers implementation):
                                # For tokens in completion: if score < 0 then score * penalty, else score / penalty
                                penalty_scores = torch.where(
                                    logits[i] < 0,
                                    logits[i] * penalty,
                                    logits[i] / penalty
                                )
                                # Only apply penalty to tokens that appeared in completion
                                logits[i] = torch.where(token_mask, penalty_scores, logits[i])
                
                # Apply logits processor for constrained decoding (if any sequence has one)
                # Clone logits to avoid in-place update issues in inference mode
                logits = logits.clone()
                for i, seq in enumerate(seqs):
                    if seq.logits_processor is not None:
                        # Create input_ids tensor for this sequence
                        seq_input_ids = torch.tensor([seq.token_ids], device=logits.device)
                        # Apply processor to this sequence's logits (clone to avoid inference mode issues)
                        processed = seq.logits_processor(seq_input_ids, logits[i:i+1].clone())
                        logits[i] = processed[0]
                
                # Prepare input_ids for sampler
                # seq_input_ids = torch.tensor([seq.token_ids for seq in seqs], device=logits.device)
                
                token_ids = self.sampler(
                    logits, 
                    temperatures,
                    top_ks=top_ks if top_ks is not None else None,
                    top_ps=top_ps if top_ps is not None else None,
                    repetition_penalties=None,  # Already applied above
                    # input_ids=seq_input_ids,
                ).tolist()
                
                # Update logits processor state after sampling
                # NOTE: Only update for the first sequence since all sequences may share the same processor
                # (when using a single SamplingParams for batch generation)
                # Updating multiple times would cause duplicate state updates (e.g., codes_count += N instead of += 1)
                if seqs and seqs[0].logits_processor_update_state is not None:
                    seqs[0].logits_processor_update_state(token_ids[0])
                
                return token_ids
            else:
                return None

    @torch.inference_mode()
    def capture_cudagraph(self):
        config = self.config
        hf_config = config.hf_config
        max_bs = min(self.config.max_num_seqs, 512)
        max_num_blocks = (config.max_model_len + self.block_size - 1) // self.block_size
        input_ids = torch.zeros(max_bs, dtype=torch.int64)
        positions = torch.zeros(max_bs, dtype=torch.int64)
        slot_mapping = torch.zeros(max_bs, dtype=torch.int32)
        context_lens = torch.zeros(max_bs, dtype=torch.int32)
        block_tables = torch.zeros(max_bs, max_num_blocks, dtype=torch.int32)
        outputs = torch.zeros(max_bs, hf_config.hidden_size)
        self.graph_bs = [1, 2, 4, 8] + list(range(16, max_bs + 1, 16))
        self.graphs = {}
        self.graph_pool = None

        for bs in reversed(self.graph_bs):
            graph = torch.cuda.CUDAGraph()
            set_context(False, slot_mapping=slot_mapping[:bs], context_lens=context_lens[:bs], block_tables=block_tables[:bs])
            outputs[:bs] = self.model(input_ids[:bs], positions[:bs])    # warmup
            with torch.cuda.graph(graph, self.graph_pool):
                outputs[:bs] = self.model(input_ids[:bs], positions[:bs])    # capture
            if self.graph_pool is None:
                self.graph_pool = graph.pool()
            self.graphs[bs] = graph
            torch.cuda.synchronize()
            reset_context()

        self.graph_vars = dict(
            input_ids=input_ids,
            positions=positions,
            slot_mapping=slot_mapping,
            context_lens=context_lens,
            block_tables=block_tables,
            outputs=outputs,
        )
