"""
DTW and signal-processing utilities shared by DiT scoring modules.

Provides Numba-optimized Dynamic Time Warping and a median filter helper.
"""
import numba
import numpy as np
import torch
import torch.nn.functional as F


@numba.jit(nopython=True)
def dtw_cpu(x: np.ndarray):
    """
    Dynamic Time Warping algorithm optimized with Numba.

    Args:
        x: Cost matrix of shape [N, M]

    Returns:
        Tuple of (text_indices, time_indices) arrays
    """
    N, M = x.shape
    # Use float32 for memory efficiency
    cost = np.ones((N + 1, M + 1), dtype=np.float32) * np.inf
    trace = -np.ones((N + 1, M + 1), dtype=np.float32)
    cost[0, 0] = 0

    for j in range(1, M + 1):
        for i in range(1, N + 1):
            c0 = cost[i - 1, j - 1]
            c1 = cost[i - 1, j]
            c2 = cost[i, j - 1]

            if c0 < c1 and c0 < c2:
                c, t = c0, 0
            elif c1 < c0 and c1 < c2:
                c, t = c1, 1
            else:
                c, t = c2, 2

            cost[i, j] = x[i - 1, j - 1] + c
            trace[i, j] = t

    return _backtrace(trace, N, M)


@numba.jit(nopython=True)
def _backtrace(trace: np.ndarray, N: int, M: int):
    """
    Optimized backtrace function for DTW.

    Args:
        trace: Trace matrix of shape (N+1, M+1)
        N, M: Original matrix dimensions

    Returns:
        Path array of shape (2, path_len) - first row is text indices, second is time indices
    """
    # Boundary handling
    trace[0, :] = 2
    trace[:, 0] = 1

    # Pre-allocate array, max path length is N+M
    max_path_len = N + M
    path = np.zeros((2, max_path_len), dtype=np.int32)

    i, j = N, M
    path_idx = max_path_len - 1

    while i > 0 or j > 0:
        path[0, path_idx] = i - 1  # text index
        path[1, path_idx] = j - 1  # time index
        path_idx -= 1

        t = trace[i, j]
        if t == 0:
            i -= 1
            j -= 1
        elif t == 1:
            i -= 1
        elif t == 2:
            j -= 1
        else:
            break

    return path[:, path_idx + 1:max_path_len]


def median_filter(x: torch.Tensor, filter_width: int) -> torch.Tensor:
    """
    Apply median filter to tensor.

    Args:
        x: Input tensor
        filter_width: Width of median filter

    Returns:
        Filtered tensor
    """
    pad_width = filter_width // 2
    if x.shape[-1] <= pad_width:
        return x
    if x.ndim == 2:
        x = x[None, :]
    x = F.pad(x, (filter_width // 2, filter_width // 2, 0, 0), mode="reflect")
    result = x.unfold(-1, filter_width, 1).sort()[0][..., filter_width // 2]
    if result.ndim > 2:
        result = result.squeeze(0)
    return result
