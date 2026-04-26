"""
Distributed utilities for nano-vllm.

This module provides wrapper functions for torch.distributed that gracefully
handle single-GPU mode (world_size == 1) without requiring distributed initialization.
"""

import torch.distributed as dist


# Global flag to track if distributed is actually initialized
_distributed_initialized = False


def initialize_distributed(backend: str, init_method: str, world_size: int, rank: int) -> bool:
    """
    Initialize distributed process group only if world_size > 1.
    
    Args:
        backend: Distributed backend (e.g., "nccl" or "gloo")
        init_method: Initialization method (e.g., "tcp://127.0.0.1:2333")
        world_size: Total number of processes
        rank: Rank of current process
        
    Returns:
        True if distributed was initialized, False otherwise
    """
    global _distributed_initialized
    
    if world_size == 1:
        # Single GPU mode - no distributed needed
        _distributed_initialized = False
        return False
    
    # Multi-GPU mode - initialize distributed
    dist.init_process_group(backend, init_method, world_size=world_size, rank=rank)
    _distributed_initialized = True
    return True


def is_initialized() -> bool:
    """Check if distributed is initialized."""
    return _distributed_initialized


def get_rank() -> int:
    """Get current process rank. Returns 0 if distributed is not initialized."""
    if _distributed_initialized:
        return dist.get_rank()
    return 0


def get_world_size() -> int:
    """Get world size. Returns 1 if distributed is not initialized."""
    if _distributed_initialized:
        return dist.get_world_size()
    return 1


def barrier():
    """Synchronize all processes. No-op if distributed is not initialized."""
    if _distributed_initialized:
        dist.barrier()


def all_reduce(tensor, op=None):
    """
    All-reduce operation. No-op if distributed is not initialized.
    
    Args:
        tensor: Tensor to reduce
        op: Reduce operation (default: SUM)
    """
    if _distributed_initialized:
        if op is None:
            op = dist.ReduceOp.SUM
        dist.all_reduce(tensor, op)


def gather(tensor, gather_list=None, dst=0):
    """
    Gather tensors from all processes. No-op if distributed is not initialized.
    
    Args:
        tensor: Tensor to gather
        gather_list: List to gather into (only used on dst rank)
        dst: Destination rank
    """
    if _distributed_initialized:
        dist.gather(tensor, gather_list, dst)


def destroy_process_group():
    """Destroy process group. No-op if distributed is not initialized."""
    global _distributed_initialized
    
    if _distributed_initialized:
        dist.destroy_process_group()
        _distributed_initialized = False
