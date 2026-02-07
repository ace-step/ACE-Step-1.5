from dataclasses import dataclass
import threading
import torch


@dataclass
class Context:
    is_prefill: bool = False
    cu_seqlens_q: torch.Tensor | None = None
    cu_seqlens_k: torch.Tensor | None = None
    max_seqlen_q: int = 0
    max_seqlen_k: int = 0
    slot_mapping: torch.Tensor | None = None
    context_lens: torch.Tensor | None = None
    block_tables: torch.Tensor | None = None


# Thread-local storage for context.
# 
# ROOT CAUSE FIX: The original implementation used a plain module-level global
# `_CONTEXT` variable. In concurrent serving scenarios (API server with
# ThreadPoolExecutor, multiple queue workers, or Gradio with concurrent requests),
# multiple threads can call set_context() / get_context() / reset_context()
# concurrently. This creates a race condition:
#
#   Thread A: set_context(...)        # sets slot_mapping, block_tables for request A
#   Thread B: set_context(...)        # OVERWRITES with request B's data
#   Thread A: run_model(...)          # reads Thread B's context → WRONG KV cache addresses
#                                     # → CUDA illegal memory access / device-side assertion
#
# By using threading.local(), each thread gets its own independent Context,
# eliminating the race condition entirely.
_THREAD_LOCAL = threading.local()


def get_context():
    ctx = getattr(_THREAD_LOCAL, 'context', None)
    if ctx is None:
        ctx = Context()
        _THREAD_LOCAL.context = ctx
    return ctx

def set_context(is_prefill, cu_seqlens_q=None, cu_seqlens_k=None, max_seqlen_q=0, max_seqlen_k=0, slot_mapping=None, context_lens=None, block_tables=None):
    _THREAD_LOCAL.context = Context(is_prefill, cu_seqlens_q, cu_seqlens_k, max_seqlen_q, max_seqlen_k, slot_mapping, context_lens, block_tables)

def reset_context():
    _THREAD_LOCAL.context = Context()
