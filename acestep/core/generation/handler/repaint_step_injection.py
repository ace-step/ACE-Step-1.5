"""Step-level repaint injection and boundary blending for diffusion loops."""

import torch


def apply_repaint_step_injection(
    xt: torch.Tensor,
    clean_src_latents: torch.Tensor,
    repaint_mask: torch.Tensor,
    t_next: float,
    noise: torch.Tensor,
) -> torch.Tensor:
    """Replace non-repaint regions of xt with noised source latents.

    At each diffusion step the non-repaint regions are forced back to the
    appropriately-noised version of the original audio so they cannot drift.

    Args:
        xt: Current diffusion state [B, T, C].
        clean_src_latents: VAE-encoded source audio (unmasked) [B, T, C].
        repaint_mask: Boolean [B, T], True = repaint (generate), False = preserve.
        t_next: Noise level after this step (flow-matching: 1.0=noise, 0.0=clean).
        noise: Initial noise tensor [B, T, C], reused across steps for consistency.

    Returns:
        Updated xt with non-repaint regions replaced by noised source.
    """
    zt_src = t_next * noise + (1.0 - t_next) * clean_src_latents
    mask_expanded = repaint_mask.unsqueeze(-1).expand_as(xt)
    return torch.where(mask_expanded, xt, zt_src)


def build_soft_repaint_mask(
    repaint_mask: torch.Tensor,
    crossfade_frames: int,
) -> torch.Tensor:
    """Build a soft float mask with linear crossfade at repaint boundaries.

    The crossfade zones extend into the preserved (non-repaint) region on each
    side of the boundary, linearly ramping from 0 to 1 (left) or 1 to 0 (right).

    Args:
        repaint_mask: Boolean [B, T], True = repaint region.
        crossfade_frames: Width of each crossfade ramp (in latent frames).

    Returns:
        Soft float mask [B, T] with smooth boundary transitions.
    """
    soft_mask = repaint_mask.float().clone()
    if crossfade_frames <= 0:
        return soft_mask

    B, T = repaint_mask.shape
    for b in range(B):
        row = repaint_mask[b]
        if row.all() or not row.any():
            continue

        indices = torch.nonzero(row, as_tuple=False).squeeze(-1)
        if indices.numel() == 0:
            continue
        left = indices[0].item()
        right = indices[-1].item() + 1

        fade_start = max(left - crossfade_frames, 0)
        ramp_len = left - fade_start
        if ramp_len > 0:
            ramp = torch.linspace(
                0.0, 1.0, ramp_len + 2, device=soft_mask.device,
            )[1:-1]
            soft_mask[b, fade_start:left] = ramp

        fade_end = min(right + crossfade_frames, T)
        ramp_len = fade_end - right
        if ramp_len > 0:
            ramp = torch.linspace(
                1.0, 0.0, ramp_len + 2, device=soft_mask.device,
            )[1:-1]
            soft_mask[b, right:fade_end] = ramp

    return soft_mask


def apply_repaint_boundary_blend(
    x_gen: torch.Tensor,
    clean_src_latents: torch.Tensor,
    repaint_mask: torch.Tensor,
    crossfade_frames: int = 10,
) -> torch.Tensor:
    """Blend generated latents with source at repaint boundaries.

    Args:
        x_gen: Diffusion output [B, T, C].
        clean_src_latents: Original source latents [B, T, C].
        repaint_mask: Boolean [B, T], True = repaint region.
        crossfade_frames: Width of crossfade zone per boundary side.

    Returns:
        Blended output with smooth transitions at repaint edges.
    """
    soft_mask = build_soft_repaint_mask(repaint_mask, crossfade_frames)
    m = soft_mask.unsqueeze(-1).expand_as(x_gen)
    return m * x_gen + (1.0 - m) * clean_src_latents
