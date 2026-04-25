"""VAE and text component loading helpers for service initialization."""

import os
from typing import Optional

import torch


class InitServiceLoaderComponentsMixin:
    """Load VAE and text components used during service initialization.

    Host contract:
        The concrete host in the MRO must provide ``offload_to_cpu``, ``dtype``,
        ``_get_vae_dtype(device)``, and ``_ensure_len_for_compile(module, name)``.
        The helpers also assign ``self.vae``, ``self.text_encoder``, and
        ``self.text_tokenizer`` as side effects.
    """

    def _load_vae_model(
        self,
        *,
        checkpoint_dir: str,
        device: str,
        compile_model: bool,
        vae_variant: Optional[str] = None,
    ) -> str:
        """Load the VAE checkpoint and return its resolved path.

        Args:
            checkpoint_dir: Root checkpoint directory.
            device: Target runtime device when CPU offload is disabled.
            compile_model: Whether to compile the loaded VAE after device placement.
            vae_variant: Optional VAE variant id (e.g. ``"official"`` or
                ``"scragvae"``) or an absolute path to a VAE directory.
                Defaults to ``"official"`` (= ``<checkpoint_dir>/vae``).

        Returns:
            The resolved VAE checkpoint path as a string.

        Raises:
            FileNotFoundError: If the resolved VAE directory does not exist.
            ValueError: If ``vae_variant`` is not a known registry id, the
                default, or an absolute path.
            Exception: Propagates loader, device transfer, or compile errors.
        """
        from diffusers.models import AutoencoderOobleck
        from acestep.model_downloader import resolve_vae_path

        vae_checkpoint_path = str(resolve_vae_path(checkpoint_dir, vae_variant))
        if not os.path.exists(vae_checkpoint_path):
            raise FileNotFoundError(f"VAE checkpoint not found at {vae_checkpoint_path}")

        self.vae = AutoencoderOobleck.from_pretrained(vae_checkpoint_path)
        if not self.offload_to_cpu:
            vae_dtype = self._get_vae_dtype(device)
            self.vae = self.vae.to(device).to(vae_dtype)
        else:
            vae_dtype = self._get_vae_dtype("cpu")
            self.vae = self.vae.to("cpu").to(vae_dtype)
        self.vae.eval()

        if compile_model:
            self._ensure_len_for_compile(self.vae, "vae")
            self.vae = torch.compile(self.vae)

        return vae_checkpoint_path

    def _load_text_encoder_and_tokenizer(self, *, checkpoint_dir: str, device: str) -> str:
        """Load the text tokenizer and embedding model, then return its path.

        Args:
            checkpoint_dir: Root checkpoint directory containing the text encoder subdirectory.
            device: Target runtime device when CPU offload is disabled.

        Returns:
            The resolved text encoder checkpoint path as a string.

        Raises:
            FileNotFoundError: If ``checkpoint_dir`` does not contain the text encoder checkpoint.
            Exception: Propagates tokenizer, model load, or device transfer errors from dependencies.

        Side Effects:
            Assigns ``self.text_tokenizer`` and ``self.text_encoder``, places the
            text encoder on the active runtime device or CPU depending on
            ``offload_to_cpu``, normalizes CPU offload to a CPU-safe dtype, and
            switches the model to eval mode.
        """
        from transformers import AutoModel, AutoTokenizer

        text_encoder_path = os.path.join(checkpoint_dir, "Qwen3-Embedding-0.6B")
        if not os.path.exists(text_encoder_path):
            raise FileNotFoundError(f"Text encoder not found at {text_encoder_path}")

        self.text_tokenizer = AutoTokenizer.from_pretrained(text_encoder_path)
        self.text_encoder = AutoModel.from_pretrained(text_encoder_path)
        if not self.offload_to_cpu:
            self.text_encoder = self.text_encoder.to(device).to(self.dtype)
        else:
            cpu_dtype = self._get_vae_dtype("cpu")
            self.text_encoder = self.text_encoder.to("cpu").to(cpu_dtype)
        self.text_encoder.eval()
        return text_encoder_path
