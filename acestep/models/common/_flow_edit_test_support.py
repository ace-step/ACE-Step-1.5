"""Shared stub model + input fixtures for flow-edit unit tests (#1156).

The real DiT decoder needs full model weights and a GPU, so tests
substitute a deterministic linear stand-in.  Underscored module name
keeps it out of unittest discovery.
"""

from typing import Tuple

import torch


class _StubDecoderOutput(tuple):
    """Mimics HuggingFace's ``ModelOutput``-like 2-tuple ``(vt, kv)``."""


class StubDecoder(torch.nn.Module):
    """Deterministic linear-ish stand-in for a DiT decoder.

    Approximates ``decoder(hidden_states, ..., context_latents)`` with a
    fixed linear projection plus a context-dependent perturbation so
    that:

    * ``V_src`` and ``V_tar`` differ when their context_latents differ.
    * Output is reproducible given fixed inputs.
    * No gradients, no real network — runs in milliseconds on CPU.
    """

    def __init__(self, channels: int):
        super().__init__()
        self.channels = channels
        torch.manual_seed(13)
        self.W = torch.randn(channels, channels) * 0.1

    def forward(
        self,
        hidden_states,
        timestep,
        timestep_r,
        attention_mask,
        encoder_hidden_states,
        encoder_attention_mask,
        context_latents,
        use_cache=False,
        past_key_values=None,
    ):
        ctx_signal = context_latents[..., : self.channels].mean(dim=-2, keepdim=True)
        proj = hidden_states @ self.W.to(hidden_states.dtype)
        vt = proj + 0.05 * ctx_signal + 0.01 * timestep.view(-1, 1, 1)
        return _StubDecoderOutput((vt, past_key_values))

    def __call__(self, *args, **kwargs):
        return self.forward(*args, **kwargs)


class StubModel:
    """Minimal model facade exposing the surface ``flow_edit`` uses."""

    def __init__(self, channels: int = 16):
        self.channels = channels
        self.decoder = StubDecoder(channels)
        self.null_condition_emb = torch.randn(1, 1, channels)


def make_inputs(bsz: int = 1, seq: int = 8, channels: int = 16) -> Tuple[
    torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor,
]:
    """Return ``(src_latents, enc_hs, enc_am, ctx, attn)`` with fixed seeds."""
    torch.manual_seed(42)
    src_latents = torch.randn(bsz, seq, channels)
    enc_hs = torch.randn(bsz, 4, channels)
    enc_am = torch.ones(bsz, 4)
    ctx = torch.randn(bsz, seq, channels * 2)
    attn = torch.ones(bsz, seq)
    return src_latents, enc_hs, enc_am, ctx, attn
