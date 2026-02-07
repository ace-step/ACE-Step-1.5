import torch


def build_context_latents(silence_latent, latent_length: int, device, dtype):
    """Build context latents for text2music."""
    src_latents = silence_latent[:, :latent_length, :].to(dtype)
    if src_latents.shape[0] < 1:
        src_latents = src_latents.expand(1, -1, -1)

    if src_latents.shape[1] < latent_length:
        pad_len = latent_length - src_latents.shape[1]
        src_latents = torch.cat(
            [
                src_latents,
                silence_latent[:, :pad_len, :].expand(1, -1, -1).to(dtype),
            ],
            dim=1,
        )
    elif src_latents.shape[1] > latent_length:
        src_latents = src_latents[:, :latent_length, :]

    chunk_masks = torch.ones(1, latent_length, 64, device=device, dtype=dtype)
    context_latents = torch.cat([src_latents, chunk_masks], dim=-1)
    return context_latents
