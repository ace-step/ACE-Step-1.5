import torch
from torch import nn
import torch.nn.functional as F

from nanovllm.utils.compat import maybe_compile


class SiluAndMul(nn.Module):

    def __init__(self):
        super().__init__()

    @maybe_compile
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x, y = x.chunk(2, -1)
        return F.silu(x) * y
