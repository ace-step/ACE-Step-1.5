"""Runtime setup helpers for initialization orchestration."""

from typing import Any, Dict, Optional, Tuple

import torch
from loguru import logger

from acestep import gpu_config
from acestep.device_map import (
    ComponentDeviceMap,
    is_cuda_device,
    log_device_map,
    normalize_component_device,
    resolve_component_device_map,
)


class InitServiceSetupMixin:
    """Device/runtime normalization and status helpers."""

    def _resolve_initialize_device(self, requested_device: str) -> str:
        """Resolve a concrete runtime device, applying backend fallback rules."""
        device = requested_device
        if device == "auto":
            if gpu_config.is_cuda_available():
                return "cuda"
            if gpu_config.is_mps_available():
                return "mps"
            if gpu_config.is_xpu_available():
                return "xpu"
            return "cpu"

        if is_cuda_device(device):
            if not gpu_config.is_cuda_available():
                if gpu_config.is_mps_available():
                    logger.warning(
                        "[initialize_service] CUDA device requested but unavailable. Falling back to MPS."
                    )
                    return "mps"
                if gpu_config.is_xpu_available():
                    logger.warning(
                        "[initialize_service] CUDA device requested but unavailable. Falling back to XPU."
                    )
                    return "xpu"
                logger.warning(
                    "[initialize_service] CUDA device requested but unavailable. Falling back to CPU."
                )
                return "cpu"
            return normalize_component_device(device)

        if device == "mps" and not gpu_config.is_mps_available():
            if gpu_config.is_cuda_available():
                logger.warning("[initialize_service] MPS requested but unavailable. Falling back to CUDA.")
                return "cuda"
            if gpu_config.is_xpu_available():
                logger.warning("[initialize_service] MPS requested but unavailable. Falling back to XPU.")
                return "xpu"
            logger.warning("[initialize_service] MPS requested but unavailable. Falling back to CPU.")
            return "cpu"

        if device == "xpu" and not gpu_config.is_xpu_available():
            if gpu_config.is_cuda_available():
                logger.warning("[initialize_service] XPU requested but unavailable. Falling back to CUDA.")
                return "cuda"
            if gpu_config.is_mps_available():
                logger.warning("[initialize_service] XPU requested but unavailable. Falling back to MPS.")
                return "mps"
            logger.warning("[initialize_service] XPU requested but unavailable. Falling back to CPU.")
            return "cpu"

        return device

    def _resolve_component_device_map(
        self,
        *,
        resolved_device: str,
        gpu_mapping: Optional[str] = None,
        config_path: Optional[str] = None,
        lm_model_path: Optional[str] = None,
        use_lm: bool = True,
        batch_size: int = 1,
    ) -> ComponentDeviceMap:
        """Resolve per-component device placement for initialization."""
        device_map = resolve_component_device_map(
            requested_device=resolved_device,
            gpu_mapping=gpu_mapping,
            config_path=config_path,
            lm_model_path=lm_model_path,
            use_lm=use_lm,
            batch_size=batch_size,
        )
        log_device_map(device_map)
        return device_map

    def _get_component_device(self, component: str) -> str:
        """Return the device string for a model component."""
        device_map = getattr(self, "device_map", None)
        if device_map is None:
            return self.device
        if component == "model":
            component = "dit"
        return device_map.device_for(component)

    def _to_component_device(self, value: Any, component: str) -> Any:
        """Move a tensor to the device assigned to *component* when needed."""
        if value is None or not isinstance(value, torch.Tensor):
            return value
        target = self._get_component_device(component)
        device = torch.device(target)
        if value.device != device:
            return value.to(device)
        return value

    def _route_service_payload_to_dit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Move service-generation tensors onto the DiT device for diffusion."""
        device_map = getattr(self, "device_map", None)
        if device_map is None or not device_map.is_multi_device():
            return payload

        routed = dict(payload)
        for key in (
            "text_hidden_states",
            "text_attention_mask",
            "lyric_hidden_states",
            "lyric_attention_mask",
            "refer_audio_acoustic_hidden_states_packed",
            "refer_audio_order_mask",
            "src_latents",
            "chunk_mask",
            "is_covers",
            "precomputed_lm_hints_25Hz",
            "non_cover_text_hidden_states",
            "non_cover_text_attention_masks",
            "repaint_mask",
            "target_latents",
        ):
            if key in routed:
                routed[key] = self._to_component_device(routed[key], "dit")
        return routed

    def _route_service_generate_kwargs_to_dit(
        self,
        generate_kwargs: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Move diffusion kwargs tensors onto the DiT device for multi-GPU runs."""
        device_map = getattr(self, "device_map", None)
        if device_map is None or not device_map.is_multi_device():
            return generate_kwargs

        routed = dict(generate_kwargs)
        payload_field_map = {
            "text_hidden_states": "text_hidden_states",
            "text_attention_mask": "text_attention_mask",
            "lyric_hidden_states": "lyric_hidden_states",
            "lyric_attention_mask": "lyric_attention_mask",
            "refer_audio_acoustic_hidden_states_packed": "refer_audio_acoustic_hidden_states_packed",
            "refer_audio_order_mask": "refer_audio_order_mask",
            "src_latents": "src_latents",
            "chunk_masks": "chunk_mask",
            "is_covers": "is_covers",
            "non_cover_text_hidden_states": "non_cover_text_hidden_states",
            "non_cover_text_attention_mask": "non_cover_text_attention_masks",
            "precomputed_lm_hints_25Hz": "precomputed_lm_hints_25Hz",
            "repaint_mask": "repaint_mask",
            "clean_src_latents": "target_latents",
        }
        for kwarg_key, payload_key in payload_field_map.items():
            if payload_key in payload:
                routed[kwarg_key] = payload[payload_key]

        for key in (
            "silence_latent",
            "timesteps",
            "repaint_mask",
            "clean_src_latents",
        ):
            if key in routed:
                routed[key] = self._to_component_device(routed[key], "dit")
        return routed

    def _configure_initialize_runtime(
        self,
        *,
        device: str,
        compile_model: bool,
        quantization: Optional[str],
    ) -> Tuple[bool, Optional[str], bool]:
        """Apply backend constraints and return normalized compile/quantization settings."""
        mlx_compile_requested = False
        normalized_compile = compile_model
        normalized_quantization = quantization

        if device == "mps":
            if normalized_compile:
                logger.info(
                    "[initialize_service] MPS detected: torch.compile is not "
                    "supported - redirecting to mx.compile for MLX components."
                )
                mlx_compile_requested = True
                normalized_compile = False
            if normalized_quantization is not None:
                logger.warning("[initialize_service] Quantization (torchao) is not supported on MPS; disabling.")
                normalized_quantization = None

        return normalized_compile, normalized_quantization, mlx_compile_requested

    @staticmethod
    def _ensure_len_for_compile(model: Any, method_name: str) -> None:
        """Inject a fallback ``__len__`` implementation for torch.compile introspection.

        Args:
            model: Model instance whose class may need a ``__len__`` shim.
            method_name: Label used in debug logs to identify the target model.
        """
        if hasattr(model.__class__, "__len__"):
            return

        def _len_impl(_model_self):
            """Return a neutral length for torch.compile compatibility."""
            return 0

        model.__class__.__len__ = _len_impl
        logger.debug(f"[initialize_service] Injected __len__ into {method_name} class for torch.compile")

    def _validate_quantization_setup(self, *, quantization: Optional[str], compile_model: bool) -> None:
        """Validate quantization prerequisites before model loading."""
        if quantization is None:
            return
        try:
            import torchao  # noqa: F401
        except Exception as exc:
            raise ImportError(
                "torchao is required for quantization but is unavailable or incompatible "
                "with this PyTorch build. Please install a compatible torchao version."
            ) from exc

    def _initialize_mlx_backends(
        self,
        *,
        device: str,
        use_mlx_dit: bool,
        mlx_compile_requested: bool,
    ) -> Tuple[str, str]:
        """Initialize MLX DiT/VAE integrations and return status labels."""
        mlx_dit_status = "Disabled"
        if use_mlx_dit and device in ("mps", "cpu"):
            mlx_ok = self._init_mlx_dit(compile_model=mlx_compile_requested)
            if mlx_ok:
                mlx_dit_status = (
                    "Active (native MLX, mx.compile)"
                    if mlx_compile_requested
                    else "Active (native MLX)"
                )
            else:
                mlx_dit_status = "Unavailable (PyTorch fallback)"
        elif not use_mlx_dit:
            mlx_dit_status = "Disabled by user"
            self.mlx_decoder = None
            self.use_mlx_dit = False

        mlx_vae_status = "Disabled"
        if device in ("mps", "cpu"):
            mlx_vae_ok = self._init_mlx_vae()
            mlx_vae_status = "Active (native MLX)" if mlx_vae_ok else "Unavailable (PyTorch fallback)"
        else:
            self.mlx_vae = None
            self.use_mlx_vae = False

        return mlx_dit_status, mlx_vae_status

    @staticmethod
    def _build_initialize_status_message(
        *,
        device: str,
        model_path: str,
        vae_path: str,
        text_encoder_path: str,
        dtype: torch.dtype,
        attention: str,
        compile_model: bool,
        mlx_compile_requested: bool,
        offload_to_cpu: bool,
        offload_dit_to_cpu: bool,
        quantization: Optional[str],
        mlx_dit_status: str,
        mlx_vae_status: str,
    ) -> str:
        """Format initialize_service status output for UI/API consumers."""
        status_msg = f"[OK] Model initialized successfully on {device}\n"
        status_msg += f"Main model: {model_path}\n"
        status_msg += f"VAE: {vae_path}\n"
        status_msg += f"Text encoder: {text_encoder_path}\n"
        status_msg += f"Dtype: {dtype}\n"
        status_msg += f"Attention: {attention}\n"
        compiled_label = "mx.compile (MLX)" if mlx_compile_requested else str(compile_model)
        status_msg += f"Compiled: {compiled_label}\n"
        status_msg += f"Quantization: {quantization or 'Disabled'}\n"
        status_msg += f"Offload to CPU: {offload_to_cpu}\n"
        status_msg += f"Offload DiT to CPU: {offload_dit_to_cpu}\n"
        status_msg += f"MLX DiT: {mlx_dit_status}\n"
        status_msg += f"MLX VAE: {mlx_vae_status}"
        return status_msg

