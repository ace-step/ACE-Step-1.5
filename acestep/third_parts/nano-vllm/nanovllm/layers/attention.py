import os
import torch
from torch import nn
import torch.nn.functional as F

from nanovllm.utils.context import get_context

# Debug logging - enable with NANOVLLM_DEBUG=1
_DEBUG = os.environ.get("NANOVLLM_DEBUG", "0") == "1"

def _debug_log(msg: str):
    """Print debug message if NANOVLLM_DEBUG is enabled"""
    if _DEBUG:
        print(f"[nanovllm attention DEBUG] {msg}", flush=True)

# Optional dependencies: Triton (for KV cache kernel) and Flash Attention
_HAS_TRITON = False
_HAS_FLASH_ATTN = False

try:
    import triton
    import triton.language as tl
    _HAS_TRITON = True
except ImportError:
    pass

try:
    from flash_attn import flash_attn_varlen_func, flash_attn_with_kvcache
    _HAS_FLASH_ATTN = True
except ImportError:
    pass


# ============================================================
# Triton KV cache store kernel (original, used when available)
# ============================================================

if _HAS_TRITON:
    @triton.jit
    def store_kvcache_kernel(
        key_ptr,
        key_stride,
        value_ptr,
        value_stride,
        k_cache_ptr,
        v_cache_ptr,
        slot_mapping_ptr,
        D: tl.constexpr,
    ):
        idx = tl.program_id(0)
        slot = tl.load(slot_mapping_ptr + idx)
        if slot == -1: return
        key_offsets = idx * key_stride + tl.arange(0, D)
        value_offsets = idx * value_stride + tl.arange(0, D)
        key = tl.load(key_ptr + key_offsets)
        value = tl.load(value_ptr + value_offsets)
        cache_offsets = slot * D + tl.arange(0, D)
        tl.store(k_cache_ptr + cache_offsets, key)
        tl.store(v_cache_ptr + cache_offsets, value)


# ============================================================
# Pure PyTorch KV cache store (fallback when Triton unavailable)
# ============================================================

def _store_kvcache_pytorch(
    key: torch.Tensor,
    value: torch.Tensor,
    k_cache: torch.Tensor,
    v_cache: torch.Tensor,
    slot_mapping: torch.Tensor,
):
    """Store key/value into paged KV cache using pure PyTorch ops.

    Args:
        key: [N, num_kv_heads, head_dim]
        value: [N, num_kv_heads, head_dim]
        k_cache: [num_blocks, block_size, num_kv_heads, head_dim] (per-layer view)
        v_cache: [num_blocks, block_size, num_kv_heads, head_dim]
        slot_mapping: [N] - flat slot indices into cache
    """
    N, num_kv_heads, head_dim = key.shape
    D = num_kv_heads * head_dim

    # View cache as flat [total_slots, D]
    k_flat = k_cache.reshape(-1, D)
    v_flat = v_cache.reshape(-1, D)

    # View keys/values as [N, D]
    key_flat = key.reshape(N, D)
    value_flat = value.reshape(N, D)

    # Filter out padding slots (slot == -1)
    valid_mask = slot_mapping != -1
    valid_slots = slot_mapping[valid_mask]
    k_flat[valid_slots] = key_flat[valid_mask]
    v_flat[valid_slots] = value_flat[valid_mask]


def store_kvcache(
    key: torch.Tensor,
    value: torch.Tensor,
    k_cache: torch.Tensor,
    v_cache: torch.Tensor,
    slot_mapping: torch.Tensor,
):
    """Store key/value into paged KV cache. Uses Triton kernel when available."""
    if _HAS_TRITON:
        N, num_heads, head_dim = key.shape
        D = num_heads * head_dim
        assert key.stride(-1) == 1 and value.stride(-1) == 1
        assert key.stride(1) == head_dim and value.stride(1) == head_dim
        assert k_cache.stride(1) == D and v_cache.stride(1) == D
        assert slot_mapping.numel() == N
        store_kvcache_kernel[(N,)](key, key.stride(0), value, value.stride(0), k_cache, v_cache, slot_mapping, D)
    else:
        _store_kvcache_pytorch(key, value, k_cache, v_cache, slot_mapping)


# ============================================================
# SDPA-based attention (fallback when Flash Attention unavailable)
# ============================================================

def _sdpa_varlen_prefill(
    q: torch.Tensor,
    k: torch.Tensor,
    v: torch.Tensor,
    cu_seqlens_q: torch.Tensor,
    cu_seqlens_k: torch.Tensor,
    scale: float,
    num_heads: int,
    num_kv_heads: int,
) -> torch.Tensor:
    """SDPA replacement for flash_attn_varlen_func during prefill.

    Splits packed sequences, runs SDPA per sequence with causal masking,
    then re-packs. Handles GQA via enable_gqa when heads differ.

    Args:
        q: [total_q_tokens, num_heads, head_dim]
        k: [total_k_tokens, num_kv_heads, head_dim]
        v: [total_k_tokens, num_kv_heads, head_dim]
        cu_seqlens_q: [num_seqs + 1] cumulative sequence lengths for queries
        cu_seqlens_k: [num_seqs + 1] cumulative sequence lengths for keys
        scale: attention scale factor
        num_heads: number of query heads
        num_kv_heads: number of KV heads

    Returns:
        output: [total_q_tokens, num_heads, head_dim]
    """
    num_seqs = cu_seqlens_q.shape[0] - 1
    outputs = []
    enable_gqa = num_heads != num_kv_heads

    for i in range(num_seqs):
        q_start = cu_seqlens_q[i].item()
        q_end = cu_seqlens_q[i + 1].item()
        k_start = cu_seqlens_k[i].item()
        k_end = cu_seqlens_k[i + 1].item()

        # [seq_len, heads, dim] -> [1, heads, seq_len, dim]
        qi = q[q_start:q_end].unsqueeze(0).transpose(1, 2)
        ki = k[k_start:k_end].unsqueeze(0).transpose(1, 2)
        vi = v[k_start:k_end].unsqueeze(0).transpose(1, 2)

        oi = F.scaled_dot_product_attention(
            qi, ki, vi, scale=scale, is_causal=True, enable_gqa=enable_gqa
        )

        # [1, heads, seq_len, dim] -> [seq_len, heads, dim]
        outputs.append(oi.transpose(1, 2).squeeze(0))

    return torch.cat(outputs, dim=0)


def _sdpa_prefill_with_paged_cache(
    q: torch.Tensor,
    k_cache: torch.Tensor,
    v_cache: torch.Tensor,
    cu_seqlens_q: torch.Tensor,
    cu_seqlens_k: torch.Tensor,
    block_tables: torch.Tensor,
    scale: float,
    num_heads: int,
    num_kv_heads: int,
) -> torch.Tensor:
    """SDPA prefill with paged KV cache (prefix caching case).

    Args:
        q: [total_q_tokens, num_heads, head_dim]
        k_cache: [num_blocks, block_size, num_kv_heads, head_dim]
        v_cache: [num_blocks, block_size, num_kv_heads, head_dim]
        cu_seqlens_q: [num_seqs + 1]
        cu_seqlens_k: [num_seqs + 1]
        block_tables: [num_seqs, max_blocks_per_seq]
        scale: attention scale factor
        num_heads: number of query heads
        num_kv_heads: number of KV heads

    Returns:
        output: [total_q_tokens, num_heads, head_dim]
    """
    block_size = k_cache.shape[1]
    num_seqs = cu_seqlens_q.shape[0] - 1
    outputs = []
    enable_gqa = num_heads != num_kv_heads

    for i in range(num_seqs):
        q_start = cu_seqlens_q[i].item()
        q_end = cu_seqlens_q[i + 1].item()
        k_len = cu_seqlens_k[i + 1].item() - cu_seqlens_k[i].item()

        # Gather k/v from paged cache
        num_blocks_needed = (k_len + block_size - 1) // block_size
        block_indices = block_tables[i, :num_blocks_needed]
        ki = k_cache[block_indices].reshape(-1, num_kv_heads, k_cache.shape[-1])[:k_len]
        vi = v_cache[block_indices].reshape(-1, num_kv_heads, v_cache.shape[-1])[:k_len]

        # [seq, heads, dim] -> [1, heads, seq, dim]
        qi = q[q_start:q_end].unsqueeze(0).transpose(1, 2)
        ki = ki.unsqueeze(0).transpose(1, 2)
        vi = vi.unsqueeze(0).transpose(1, 2)

        oi = F.scaled_dot_product_attention(
            qi, ki, vi, scale=scale, is_causal=True, enable_gqa=enable_gqa
        )
        outputs.append(oi.transpose(1, 2).squeeze(0))

    return torch.cat(outputs, dim=0)


def _sdpa_decode_with_paged_cache(
    q: torch.Tensor,
    k_cache: torch.Tensor,
    v_cache: torch.Tensor,
    context_lens: torch.Tensor,
    block_tables: torch.Tensor,
    scale: float,
    num_heads: int,
    num_kv_heads: int,
) -> torch.Tensor:
    """SDPA replacement for flash_attn_with_kvcache during decode.

    For each sequence, gathers KV from paged cache and runs SDPA
    for the single new query token against the full context.

    Args:
        q: [batch, 1, num_heads, head_dim] (already unsqueezed)
        k_cache: [num_blocks, block_size, num_kv_heads, head_dim]
        v_cache: [num_blocks, block_size, num_kv_heads, head_dim]
        context_lens: [batch] - number of tokens in context for each sequence
        block_tables: [batch, max_blocks_per_seq]
        scale: attention scale factor
        num_heads: number of query heads
        num_kv_heads: number of KV heads

    Returns:
        output: [batch, 1, num_heads, head_dim]
    """
    batch_size = q.shape[0]
    block_size = k_cache.shape[1]
    outputs = []
    enable_gqa = num_heads != num_kv_heads

    for i in range(batch_size):
        ctx_len = context_lens[i].item()
        num_blocks_needed = (ctx_len + block_size - 1) // block_size
        block_indices = block_tables[i, :num_blocks_needed]

        # Gather and trim KV: [ctx_len, num_kv_heads, head_dim]
        ki = k_cache[block_indices].reshape(-1, num_kv_heads, k_cache.shape[-1])[:ctx_len]
        vi = v_cache[block_indices].reshape(-1, num_kv_heads, v_cache.shape[-1])[:ctx_len]

        # q[i]: [1, num_heads, head_dim] -> [1, num_heads, 1, head_dim]
        qi = q[i].unsqueeze(0).transpose(1, 2)     # [1, num_heads, 1, head_dim]
        ki = ki.unsqueeze(0).transpose(1, 2)        # [1, num_kv_heads, ctx_len, head_dim]
        vi = vi.unsqueeze(0).transpose(1, 2)        # [1, num_kv_heads, ctx_len, head_dim]

        oi = F.scaled_dot_product_attention(
            qi, ki, vi, scale=scale, is_causal=False, enable_gqa=enable_gqa
        )
        outputs.append(oi.transpose(1, 2).squeeze(0))  # [1, num_heads, head_dim]

    return torch.stack(outputs, dim=0)  # [batch, 1, num_heads, head_dim]


# ============================================================
# Attention module
# ============================================================

class Attention(nn.Module):

    def __init__(
        self,
        num_heads,
        head_dim,
        scale,
        num_kv_heads,
    ):
        super().__init__()
        self.num_heads = num_heads
        self.head_dim = head_dim
        self.scale = scale
        self.num_kv_heads = num_kv_heads
        self.k_cache = self.v_cache = torch.tensor([])

    def forward(self, q: torch.Tensor, k: torch.Tensor, v: torch.Tensor):
        context = get_context()
        k_cache, v_cache = self.k_cache, self.v_cache

        if _DEBUG:
            _debug_log(f"forward: q.shape={q.shape}, k.shape={k.shape}, v.shape={v.shape}")
            _debug_log(f"  is_prefill={context.is_prefill}")
            _debug_log(f"  k_cache.shape={k_cache.shape if k_cache.numel() else 'empty'}")
            if context.slot_mapping is not None:
                _debug_log(f"  slot_mapping.shape={context.slot_mapping.shape}, range=[{context.slot_mapping.min().item()}, {context.slot_mapping.max().item()}]")
            if context.block_tables is not None:
                valid_blocks = context.block_tables[context.block_tables >= 0]
                _debug_log(f"  block_tables.shape={context.block_tables.shape}, range=[{valid_blocks.min().item() if valid_blocks.numel() else -1}, {valid_blocks.max().item() if valid_blocks.numel() else -1}]")
            if context.context_lens is not None:
                _debug_log(f"  context_lens={context.context_lens.tolist()}")

        if k_cache.numel() and v_cache.numel():
            store_kvcache(k, v, k_cache, v_cache, context.slot_mapping)

        if _HAS_FLASH_ATTN:
            return self._forward_flash_attn(q, k, v, k_cache, v_cache, context)
        else:
            return self._forward_sdpa(q, k, v, k_cache, v_cache, context)

    def _forward_flash_attn(self, q, k, v, k_cache, v_cache, context):
        """Original flash attention path."""
        if context.is_prefill:
            if context.block_tables is not None:  # prefix cache
                k, v = k_cache, v_cache
            _debug_log(f"  calling flash_attn_varlen_func")
            o = flash_attn_varlen_func(
                q, k, v,
                max_seqlen_q=context.max_seqlen_q,
                cu_seqlens_q=context.cu_seqlens_q,
                max_seqlen_k=context.max_seqlen_k,
                cu_seqlens_k=context.cu_seqlens_k,
                softmax_scale=self.scale,
                causal=True,
                block_table=context.block_tables,
            )
        else:  # decode
            _debug_log(f"  calling flash_attn_with_kvcache")
            o = flash_attn_with_kvcache(
                q.unsqueeze(1), k_cache, v_cache,
                cache_seqlens=context.context_lens,
                block_table=context.block_tables,
                softmax_scale=self.scale,
                causal=True,
            )
        return o

    def _forward_sdpa(self, q, k, v, k_cache, v_cache, context):
        """SDPA fallback path (no flash_attn dependency)."""
        if context.is_prefill:
            if context.block_tables is not None:
                # Prefix cache: gather from paged cache
                _debug_log(f"  calling _sdpa_prefill_with_paged_cache")
                o = _sdpa_prefill_with_paged_cache(
                    q, k_cache, v_cache,
                    context.cu_seqlens_q, context.cu_seqlens_k,
                    context.block_tables,
                    self.scale, self.num_heads, self.num_kv_heads,
                )
            else:
                # Standard prefill: k, v are packed tokens
                _debug_log(f"  calling _sdpa_varlen_prefill")
                o = _sdpa_varlen_prefill(
                    q, k, v,
                    context.cu_seqlens_q, context.cu_seqlens_k,
                    self.scale, self.num_heads, self.num_kv_heads,
                )
        else:
            # Decode: single token per sequence against full KV cache
            _debug_log(f"  calling _sdpa_decode_with_paged_cache")
            o = _sdpa_decode_with_paged_cache(
                q.unsqueeze(1), k_cache, v_cache,
                context.context_lens, context.block_tables,
                self.scale, self.num_heads, self.num_kv_heads,
            )
        return o
