"""Collate helpers for preprocessed ACE-Step training tensors."""

from __future__ import annotations

from typing import Dict, List

import torch


def collate_preprocessed_batch(batch: List[Dict]) -> Dict[str, torch.Tensor]:
    """Pad and stack variable-length preprocessed training tensors.

    Args:
        batch: Per-sample tensor dictionaries.

    Returns:
        Batched tensor dictionary with padding to max lengths in batch.
    """
    max_latent_len = max(s["target_latents"].shape[0] for s in batch)
    max_encoder_len = max(s["encoder_hidden_states"].shape[0] for s in batch)

    target_latents = []
    attention_masks = []
    encoder_hidden_states = []
    encoder_attention_masks = []
    context_latents = []

    for sample in batch:
        tl = sample["target_latents"]
        if tl.shape[0] < max_latent_len:
            tl = torch.cat([tl, tl.new_zeros(max_latent_len - tl.shape[0], tl.shape[1])], dim=0)
        target_latents.append(tl)

        am = sample["attention_mask"]
        if am.shape[0] < max_latent_len:
            am = torch.cat([am, am.new_zeros(max_latent_len - am.shape[0])], dim=0)
        attention_masks.append(am)

        cl = sample["context_latents"]
        if cl.shape[0] < max_latent_len:
            cl = torch.cat([cl, cl.new_zeros(max_latent_len - cl.shape[0], cl.shape[1])], dim=0)
        context_latents.append(cl)

        ehs = sample["encoder_hidden_states"]
        if ehs.shape[0] < max_encoder_len:
            ehs = torch.cat([ehs, ehs.new_zeros(max_encoder_len - ehs.shape[0], ehs.shape[1])], dim=0)
        encoder_hidden_states.append(ehs)

        eam = sample["encoder_attention_mask"]
        if eam.shape[0] < max_encoder_len:
            eam = torch.cat([eam, eam.new_zeros(max_encoder_len - eam.shape[0])], dim=0)
        encoder_attention_masks.append(eam)

    return {
        "target_latents": torch.stack(target_latents),
        "attention_mask": torch.stack(attention_masks),
        "encoder_hidden_states": torch.stack(encoder_hidden_states),
        "encoder_attention_mask": torch.stack(encoder_attention_masks),
        "context_latents": torch.stack(context_latents),
        "metadata": [s["metadata"] for s in batch],
    }
