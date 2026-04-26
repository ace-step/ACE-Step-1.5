import torch
import torch.nn.functional as F


class MomentumBuffer:

    def __init__(self, momentum: float = -0.75):
        self.momentum = momentum
        self.running_average = 0

    def update(self, update_value: torch.Tensor):
        new_average = self.momentum * self.running_average
        self.running_average = update_value + new_average


def project(
    v0: torch.Tensor,  # [B, C, T]
    v1: torch.Tensor,  # [B, C, T]
    dims=[-1],
):
    dtype = v0.dtype
    device_type = v0.device.type
    if device_type == "mps":
        v0, v1 = v0.cpu(), v1.cpu()

    v0, v1 = v0.double(), v1.double()
    v1 = torch.nn.functional.normalize(v1, dim=dims)
    v0_parallel = (v0 * v1).sum(dim=dims, keepdim=True) * v1
    v0_orthogonal = v0 - v0_parallel
    return v0_parallel.to(dtype).to(device_type), v0_orthogonal.to(dtype).to(device_type)


def apg_forward(
    pred_cond: torch.Tensor,  # [B, C, T]
    pred_uncond: torch.Tensor,  # [B, C, T]
    guidance_scale: float,
    momentum_buffer: MomentumBuffer = None,
    eta: float = 0.0,
    norm_threshold: float = 2.5,
    dims=[-1],
):
    diff = pred_cond - pred_uncond
    if momentum_buffer is not None:
        momentum_buffer.update(diff)
        diff = momentum_buffer.running_average

    if norm_threshold > 0:
        ones = torch.ones_like(diff)
        diff_norm = diff.norm(p=2, dim=dims, keepdim=True)
        scale_factor = torch.minimum(ones, norm_threshold / diff_norm)
        diff = diff * scale_factor

    diff_parallel, diff_orthogonal = project(diff, pred_cond, dims)
    normalized_update = diff_orthogonal + eta * diff_parallel
    pred_guided = pred_cond + (guidance_scale - 1) * normalized_update
    return pred_guided


def cfg_forward(cond_output, uncond_output, cfg_strength):
    return uncond_output + cfg_strength * (cond_output - uncond_output)


def call_cos_tensor(tensor1, tensor2):
    """
    Calculate cosine similarity between two normalized tensors.

    Args:
        tensor1: First tensor [B, ...]
        tensor2: Second tensor [B, ...]

    Returns:
        Cosine similarity value [B, 1]
    """
    tensor1 = tensor1 / torch.linalg.norm(tensor1, dim=1, keepdim=True)
    tensor2 = tensor2 / torch.linalg.norm(tensor2, dim=1, keepdim=True)
    cosvalue = torch.sum(tensor1 * tensor2, dim=1, keepdim=True)
    return cosvalue


def compute_perpendicular_component(latent_diff, latent_hat_uncond):
    """
    Decompose latent_diff into parallel and perpendicular components relative to latent_hat_uncond.

    Args:
        latent_diff: Difference tensor [B, C, ...]
        latent_hat_uncond: Unconditional prediction tensor [B, C, ...]

    Returns:
        projection: Parallel component
        perpendicular_component: Perpendicular component
    """
    n, t, c = latent_diff.shape
    latent_diff = latent_diff.view(n * t, c).float()
    latent_hat_uncond = latent_hat_uncond.view(n * t, c).float()

    if latent_diff.size() != latent_hat_uncond.size():
        raise ValueError("latent_diff and latent_hat_uncond must have the same shape [n, d].")

    dot_product = torch.sum(latent_diff * latent_hat_uncond, dim=1, keepdim=True)  # [n, 1]
    norm_square = torch.sum(latent_hat_uncond * latent_hat_uncond, dim=1, keepdim=True)  # [n, 1]
    projection = (dot_product / (norm_square + 1e-8)) * latent_hat_uncond
    perpendicular_component = latent_diff - projection

    return projection.view(n, t, c), perpendicular_component.reshape(n, t, c)


def adg_forward(
    latents: torch.Tensor,
    noise_pred_cond: torch.Tensor,
    noise_pred_uncond: torch.Tensor,
    sigma: torch.Tensor,
    guidance_scale: float,
    angle_clip: float = 3.14 / 6,  # pi/6 by default
    apply_norm: bool = False,
    apply_clip: bool = True,
):
    """
    ADG (Angle-based Dynamic Guidance) forward pass for Flow Matching.

    In flow matching (including SD3), sigma represents the current timestep t_curr.
    The predictions are velocity fields v(x_t, t).

    Args:
        latents: Current state x_t [N, T, d] where d=64
        noise_pred_cond: Conditional velocity prediction v_cond [N, T, d]
        noise_pred_uncond: Unconditional velocity prediction v_uncond [N, T, d]
        sigma: Current timestep t_curr (not t_prev!)
        guidance_scale: Guidance strength
        angle_clip: Maximum angle for clipping (default: pi/6)
        apply_norm: Whether to normalize the result (ADG_w_norm variant)
        apply_clip: Whether to clip the angle (ADG_wo_clip when False)

    Returns:
        Guided velocity prediction [N, T, d]
    """
    if latents.shape[1] != noise_pred_cond.shape[1]:
        if noise_pred_cond.shape[1] % latents.shape[1] != 0:
            raise ValueError("noise_pred_cond time dimension must be a whole-number multiple of latents time dimension.")
        repeats = noise_pred_cond.shape[1] // latents.shape[1]
        latents = latents.repeat_interleave(repeats, dim=1)

    # Get batch size
    n = noise_pred_cond.shape[0]
    noise_pred_text = noise_pred_cond
    n, t, c = noise_pred_text.shape

    # Ensure sigma/t has the right shape for broadcasting [N, 1, 1]
    if isinstance(sigma, (int, float)):
        sigma = torch.tensor(sigma, device=latents.device, dtype=latents.dtype)
        sigma = sigma.view(1, 1, 1).expand(n, 1, 1)
    elif torch.is_tensor(sigma):
        if sigma.numel() == 1:
            sigma = sigma.view(1, 1, 1).expand(n, 1, 1)
        elif sigma.numel() == n:
            sigma = sigma.view(n, 1, 1)
        else:
            raise ValueError(f"sigma has incompatible shape. Expected scalar or size {n}, got {sigma.shape}")
    else:
        raise TypeError(f"sigma must be a number or tensor, got {type(sigma)}")

    # Adjust guidance weight
    weight = guidance_scale - 1
    weight = weight * (weight > 0) + 1e-3

    latent_hat_text = latents - sigma * noise_pred_text
    latent_hat_uncond = latents - sigma * noise_pred_uncond
    latent_diff = latent_hat_text - latent_hat_uncond

    # Calculate angle between conditional and unconditional predicted data
    cos_theta = call_cos_tensor(
        latent_hat_text.view(-1, c).to(float),
        latent_hat_uncond.reshape(-1, c).contiguous().to(float)
    ).clamp(-1.0 + 1e-6, 1.0 - 1e-6)
    latent_theta = torch.acos(cos_theta).view(n, t, 1)
    latent_theta_new = torch.clip(weight * latent_theta, -angle_clip, angle_clip) if apply_clip else weight * latent_theta
    proj, perp = compute_perpendicular_component(latent_diff, latent_hat_uncond)
    latent_v_new = torch.cos(latent_theta_new) * latent_hat_text

    latent_p_new = perp * torch.sin(latent_theta_new) / torch.sin(latent_theta) * (
        torch.sin(latent_theta) > 1e-3) + perp * weight * (torch.sin(latent_theta) <= 1e-3)
    latent_new = latent_v_new + latent_p_new
    if apply_norm:
        latent_new = latent_new * torch.linalg.norm(latent_hat_text, dim=1, keepdim=True) / torch.linalg.norm(
            latent_new, dim=1, keepdim=True)

    noise_pred = (latents - latent_new) / sigma
    noise_pred = noise_pred.reshape(n, t, c).to(latents.dtype)
    return noise_pred


def adg_w_norm_forward(
    latents: torch.Tensor,
    noise_pred_cond: torch.Tensor,
    noise_pred_uncond: torch.Tensor,
    sigma: float,
    guidance_scale: float,
    angle_clip: float = 3.14 / 3,
):
    """
    ADG with normalization - preserves the magnitude of latent predictions.

    This variant normalizes the final latent to maintain the same norm as the
    conditional prediction, which can help preserve image quality.
    """
    return adg_forward(latents,
                       noise_pred_cond,
                       noise_pred_uncond,
                       sigma,
                       guidance_scale,
                       angle_clip=angle_clip,
                       apply_norm=True,
                       apply_clip=True)


def adg_wo_clip_forward(
    latents: torch.Tensor,
    noise_pred_cond: torch.Tensor,
    noise_pred_uncond: torch.Tensor,
    sigma: float,
    guidance_scale: float,
):
    """
    ADG without angle clipping - allows unbounded angle adjustments.

    This variant doesn't clip the angle, which may result in more aggressive
    guidance but could be less stable.
    """
    return adg_forward(latents, noise_pred_cond, noise_pred_uncond, sigma, guidance_scale, apply_norm=False, apply_clip=False)
