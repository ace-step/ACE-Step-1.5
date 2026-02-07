import torch


def vae_encode(vae, audio, dtype):
    """VAE encode audio to get target latents."""
    model_device = next(vae.parameters()).device
    if audio.device != model_device:
        audio = audio.to(model_device)

    latent = vae.encode(audio).latent_dist.sample()
    target_latents = latent.transpose(1, 2).to(dtype)
    return target_latents
