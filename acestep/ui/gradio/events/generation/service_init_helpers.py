"""Helper functions for generation service initialization."""

import os

import gradio as gr
from loguru import logger

from acestep.gpu_config import get_global_gpu_config

from .model_config import get_model_type_ui_settings, is_pure_base_model, is_sft_model
def select_quantization_value(
    *,
    quantization_enabled: bool,
    device: str,
) -> str | None:
    """Return the DiT quantization mode selected for the current UI state."""
    quant_value = "int8_weight_only" if quantization_enabled else None
    if not quantization_enabled or device not in {"auto", "cuda"}:
        return quant_value

    try:
        import torch
    except ImportError:
        return quant_value

    try:
        if torch.cuda.is_available():
            major, _ = torch.cuda.get_device_capability(0)
            if major < 7:
                logger.info(
                    "Pre-Ampere CUDA detected: using w8a8_dynamic quantization for stability"
                )
                return "w8a8_dynamic"
    except Exception:
        return quant_value
    return quant_value
def resolve_project_root(current_file: str) -> str:
    """Derive the project root from the current module path."""
    return os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file))))
        )
    )
def configure_external_llm(
    *,
    llm_handler,
    profile,
    provider: str,
    model: str,
    base_url: str,
    api_key: str,
    save_runtime_settings,
    status: str,
) -> str:
    """Persist external LM state onto the handler and append a status message."""
    should_unload_local_llm = (
        callable(getattr(llm_handler, "unload", None))
        and str(getattr(llm_handler, "llm_backend", "")).strip().lower() != "external"
        and (
            getattr(llm_handler, "llm_initialized", False)
            or getattr(llm_handler, "llm", None) is not None
            or getattr(llm_handler, "_mlx_model", None) is not None
        )
    )
    if should_unload_local_llm:
        llm_handler.unload()

    save_external_runtime(
        save_runtime_settings=save_runtime_settings,
        provider=provider,
        protocol=profile.protocol,
        model=model,
        base_url=base_url,
    )
    # Keep the inline key only in-process so external format can run immediately
    # after Initialize even when the user has not saved credentials to env/secret storage.
    llm_handler.external_config = {
        "provider": provider,
        "protocol": profile.protocol,
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
    }
    llm_handler.llm_backend = "external"
    llm_handler.llm_initialized = False
    if callable(getattr(llm_handler, "has_external_llm_config", None)) and llm_handler.has_external_llm_config():
        return status + f"\n✅ External LM ready for caption enhancement ({provider}:{model})"
    return (
        status
        + "\n⚠️ External LM settings saved, but the configuration is incomplete."
        + "\nProvide the model/base URL/API key (or matching provider env vars)"
        + " before using Enhance Caption."
    )
def save_external_runtime(
    *,
    save_runtime_settings,
    provider: str,
    protocol: str,
    model: str,
    base_url: str,
) -> None:
    """Persist provider-scoped runtime settings for external LM setup."""
    save_runtime_settings(
        provider=provider,
        protocol=protocol,
        model=model,
        base_url=base_url,
    )
def build_post_init_result(
    *,
    dit_handler,
    llm_handler,
    config_path: str,
    current_mode,
    current_batch_size,
    status: str,
    enable: bool,
    get_gpu_config_fn=get_global_gpu_config,
    get_model_type_ui_settings_fn=get_model_type_ui_settings,
    is_pure_base_model_fn=is_pure_base_model,
    is_sft_model_fn=is_sft_model,
):
    """Build the post-initialization UI updates returned to the Gradio layer."""
    is_model_initialized = dit_handler.model is not None
    config_path_lower = (config_path or "").lower()
    model_type_settings = get_model_type_ui_settings_fn(
        dit_handler.is_turbo_model(),
        current_mode=current_mode,
        is_pure_base=is_pure_base_model_fn(config_path_lower),
        is_sft=is_sft_model_fn(config_path_lower),
    )
    max_duration, max_batch, lm_actually_initialized = resolve_runtime_limits(
        llm_handler,
        get_gpu_config_fn=get_gpu_config_fn,
    )
    batch_value = clamp_batch_size(current_batch_size, max_batch)
    status_with_gpu = append_gpu_status(
        status=status,
        max_duration=max_duration,
        max_batch=max_batch,
        get_gpu_config_fn=get_gpu_config_fn,
    )

    return (
        status_with_gpu,
        gr.update(interactive=enable),
        gr.Accordion(open=not is_model_initialized),
        *model_type_settings,
        gr.update(
            maximum=float(max_duration),
            info=f"Duration in seconds (-1 for auto). Max: {max_duration}s / {max_duration // 60} min.",
            elem_classes=["has-info-container"],
        ),
        gr.update(
            value=batch_value,
            maximum=max_batch,
            info=f"Number of samples to generate (Max: {max_batch}).",
            elem_classes=["has-info-container"],
        ),
        gr.update(interactive=lm_actually_initialized, value=lm_actually_initialized),
    )
def resolve_runtime_limits(llm_handler, *, get_gpu_config_fn=get_global_gpu_config) -> tuple[int, int, bool]:
    """Return audio-code LM limits used by Think mode and local 5Hz generation.

    External text-LM setup enables caption enhancement only; it does not unlock
    the local audio-code LM path that drives Think mode or the stricter
    with-LM GPU limits. This helper therefore keys off ``llm_initialized``
    rather than ``has_available_text_llm()`` on purpose.
    """
    gpu_config = get_gpu_config_fn()
    audio_code_lm_initialized = llm_handler.llm_initialized if llm_handler else False
    if audio_code_lm_initialized:
        return gpu_config.max_duration_with_lm, gpu_config.max_batch_size_with_lm, True
    return gpu_config.max_duration_without_lm, gpu_config.max_batch_size_without_lm, False
def clamp_batch_size(current_batch_size, max_batch: int) -> int:
    """Clamp the requested batch size to the current GPU limits."""
    if current_batch_size is None:
        return min(2, max_batch)
    try:
        batch_value_int = int(current_batch_size)
        if batch_value_int < 1:
            raise ValueError("batch size must be >= 1")
        batch_value = min(batch_value_int, max_batch)
        if batch_value_int > max_batch:
            logger.warning(
                f"Batch size {batch_value_int} exceeds GPU limit {max_batch}, clamping to {batch_value}"
            )
        return batch_value
    except ValueError:
        logger.warning(
            f"Cannot use batch size '{current_batch_size}', falling back to {min(2, max_batch)}"
        )
        return min(2, max_batch)
    except TypeError:
        logger.warning(
            f"Invalid batch size type {type(current_batch_size).__name__}, using default {min(2, max_batch)}"
        )
        return min(2, max_batch)
def append_gpu_status(
    *,
    status: str,
    max_duration: int,
    max_batch: int,
    get_gpu_config_fn=get_global_gpu_config,
) -> str:
    """Append current GPU-tier limits to the service status message."""
    gpu_config = get_gpu_config_fn()
    status += f"\n📊 GPU Config: tier={gpu_config.tier}, max_duration={max_duration}s, max_batch={max_batch}"
    if gpu_config.available_lm_models:
        return status + f", available_lm={gpu_config.available_lm_models}"
    return status + ", LM not available for this GPU tier"
