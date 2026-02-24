"""Diffusion-related handler helpers."""

from typing import Any, Dict

import torch
from acestep.models.mlx.dit_generate import mlx_generate_diffusion


class DiffusionMixin:
    """Mixin containing diffusion execution helpers.

    Required host attributes:
    - ``mlx_decoder``: MLX decoder object passed to ``mlx_generate_diffusion``.
    - ``device``: torch device string used for output tensor placement.
    - ``dtype``: torch dtype used for output tensor conversion.
    """

    def _mlx_run_diffusion(
        self,
        encoder_hidden_states,
        encoder_attention_mask,
        context_latents,
        src_latents,
        seed,
        infer_method: str = "ode",
        shift: float = 3.0,
        timesteps=None,
        audio_cover_strength: float = 1.0,
        encoder_hidden_states_non_cover=None,
        encoder_attention_mask_non_cover=None,
        context_latents_non_cover=None,
        disable_tqdm: bool = False,
    ) -> Dict[str, Any]:
        """Run the MLX diffusion loop and return generated latents.

        This method accepts the same signature as the handler diffusion path for
        API compatibility. Attention-mask parameters are intentionally accepted
        but unused because the MLX generator consumes hidden states/latents only.

        Args:
            encoder_hidden_states: Prompt conditioning tensor.
            encoder_attention_mask: Unused; accepted for API compatibility.
            context_latents: Context/reference latent tensor.
            src_latents: Source latent tensor used for shape and initialization.
            seed: Random seed used by MLX diffusion.
            infer_method: Diffusion method, one of ``"ode"`` or ``"sde"``.
            shift: Timestep shift value.
            timesteps: Optional iterable or tensor-like custom timesteps.
            audio_cover_strength: Blend factor for cover conditioning.
            encoder_hidden_states_non_cover: Optional non-cover conditioning tensor.
            encoder_attention_mask_non_cover: Unused; accepted for API compatibility.
            context_latents_non_cover: Optional non-cover context latent tensor.
            disable_tqdm: If True, suppress the diffusion progress bar.

        Returns:
            Dict[str, Any]: ``{"target_latents": torch.Tensor, "time_costs": dict}``.

        Raises:
            AttributeError: If required host attributes are missing.
            ValueError: If infer method is unsupported or batch dimensions mismatch.
            TypeError: If ``timesteps`` is neither iterable nor tensor-like.
        """
        import numpy as np

        # Kept for API compatibility with non-MLX diffusion path.
        _ = encoder_attention_mask, encoder_attention_mask_non_cover

        for required_attr in ("mlx_decoder", "device", "dtype"):
            if not hasattr(self, required_attr):
                raise AttributeError(f"DiffusionMixin host is missing required attribute '{required_attr}'")

        if infer_method not in {"ode", "sde"}:
            raise ValueError(f"Unsupported infer_method '{infer_method}'. Expected 'ode' or 'sde'.")

        if timesteps is not None and not (hasattr(timesteps, "__iter__") or hasattr(timesteps, "tolist")):
            raise TypeError("timesteps must be iterable, tensor-like, or None")

        if encoder_hidden_states.shape[0] != context_latents.shape[0]:
            raise ValueError(
                "Batch dimension mismatch: encoder_hidden_states and context_latents must share dim 0"
            )
        if encoder_hidden_states.shape[0] != src_latents.shape[0]:
            raise ValueError(
                "Batch dimension mismatch: encoder_hidden_states and src_latents must share dim 0"
            )
        if encoder_hidden_states_non_cover is not None and encoder_hidden_states_non_cover.shape[0] != encoder_hidden_states.shape[0]:
            raise ValueError(
                "Batch dimension mismatch: encoder_hidden_states_non_cover must share dim 0 with encoder_hidden_states"
            )
        if context_latents_non_cover is not None and context_latents_non_cover.shape[0] != context_latents.shape[0]:
            raise ValueError(
                "Batch dimension mismatch: context_latents_non_cover must share dim 0 with context_latents"
            )

        # Convert inputs to numpy (float32)
        enc_np = encoder_hidden_states.detach().cpu().float().numpy()
        ctx_np = context_latents.detach().cpu().float().numpy()
        src_shape = (src_latents.shape[0], src_latents.shape[1], src_latents.shape[2])

        enc_nc_np = (
            encoder_hidden_states_non_cover.detach().cpu().float().numpy()
            if encoder_hidden_states_non_cover is not None else None
        )
        ctx_nc_np = (
            context_latents_non_cover.detach().cpu().float().numpy()
            if context_latents_non_cover is not None else None
        )

        # Convert timesteps tensor if present
        ts_list = None
        if timesteps is not None:
            if hasattr(timesteps, "tolist"):
                ts_list = timesteps.tolist()
            else:
                ts_list = list(timesteps)

        result = mlx_generate_diffusion(
            mlx_decoder=self.mlx_decoder,
            encoder_hidden_states_np=enc_np,
            context_latents_np=ctx_np,
            src_latents_shape=src_shape,
            seed=seed,
            infer_method=infer_method,
            shift=shift,
            timesteps=ts_list,
            audio_cover_strength=audio_cover_strength,
            encoder_hidden_states_non_cover_np=enc_nc_np,
            context_latents_non_cover_np=ctx_nc_np,
            compile_model=getattr(self, "mlx_dit_compiled", False),
            disable_tqdm=disable_tqdm,
        )

        # Convert result latents back to PyTorch tensor on the correct device
        target_np = result["target_latents"]
        target_tensor = torch.from_numpy(target_np).to(device=self.device, dtype=self.dtype)

        return {
            "target_latents": target_tensor,
            "time_costs": result["time_costs"],
        }
