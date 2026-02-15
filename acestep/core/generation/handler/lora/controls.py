"""Runtime controls for LoRA enablement, scaling, and adapter selection."""

import math
from typing import Any

from loguru import logger

from acestep.constants import DEBUG_MODEL_LOADING
from acestep.debug_utils import debug_log


def set_use_lora(self, use_lora: bool) -> str:
    """Toggle LoRA usage for inference."""
    if use_lora and not self.lora_loaded:
        return "❌ No LoRA adapter loaded. Please load a LoRA first."

    self.use_lora = use_lora
    model = getattr(self, "model", None)
    decoder = getattr(model, "decoder", None) if model is not None else None
    if self.lora_loaded and decoder is None:
        logger.warning("LoRA is marked as loaded, but model/decoder is unavailable during toggle.")

    if self.lora_loaded and decoder is not None and hasattr(decoder, "disable_adapter_layers"):
        try:
            if use_lora:
                active = getattr(self, "_lora_active_adapter", None)
                if active and hasattr(decoder, "set_adapter"):
                    try:
                        decoder.set_adapter(active)
                    except Exception:
                        pass
                decoder.enable_adapter_layers()
                logger.info("LoRA adapter enabled")
                scale = getattr(self, "_active_loras", {}).get(active, 1.0)
                if active and scale != 1.0:
                    self.set_lora_scale(active, scale)
            else:
                decoder.disable_adapter_layers()
                logger.info("LoRA adapter disabled")
        except Exception as e:
            logger.warning(f"Could not toggle adapter layers: {e}")

    status = "enabled" if use_lora else "disabled"
    return f"✅ LoRA {status}"


def set_lora_scale(self, adapter_name_or_scale: str | float, scale: float | None = None) -> str:
    """Set LoRA scale (0–1). Call as set_lora_scale(scale) or set_lora_scale(adapter_name, scale)."""
    if not self.lora_loaded:
        return "⚠️ No LoRA loaded"

    if scale is None:
        # Single-arg: first arg is scale, use active adapter
        scale_value = adapter_name_or_scale
        effective_name = None
    else:
        effective_name = adapter_name_or_scale if isinstance(adapter_name_or_scale, str) else None
        scale_value = scale

    try:
        scale_value = float(scale_value)
    except (TypeError, ValueError):
        return "❌ Invalid LoRA scale: please provide a numeric value between 0 and 1."
    if not math.isfinite(scale_value):
        return "❌ Invalid LoRA scale: please provide a finite numeric value between 0 and 1."

    scale_value = max(0.0, min(1.0, scale_value))
    _active_loras = getattr(self, "_active_loras", None) or {}
    if not effective_name:
        effective_name = getattr(self, "_lora_active_adapter", None) or (
            next(iter(_active_loras), None) if _active_loras else None
        )
    if not effective_name:
        return "❌ No adapter specified and no active adapter. Load a LoRA or pass adapter_name."

    self._active_loras[effective_name] = scale_value
    self.lora_scale = scale_value  # backward compat: single "current" scale for status/UI

    if not self.use_lora:
        logger.info(f"LoRA scale for '{effective_name}' set to {scale_value:.2f} (will apply when LoRA is enabled)")
        return f"✅ LoRA scale ({effective_name}): {scale_value:.2f} (LoRA disabled)"

    try:
        rebuilt_adapters: list[str] | None = None
        if not getattr(self, "_lora_adapter_registry", None):
            _, rebuilt_adapters = self._rebuild_lora_registry()

        if rebuilt_adapters is not None:
            if effective_name not in (rebuilt_adapters or []):
                return f"❌ Adapter '{effective_name}' not in loaded adapters: {rebuilt_adapters}"
            active_adapter = self._lora_service.active_adapter or effective_name
            if active_adapter != effective_name:
                self._lora_service.set_active_adapter(effective_name)
                self._lora_active_adapter = effective_name
                if getattr(self.model, "decoder", None) and hasattr(self.model.decoder, "set_adapter"):
                    try:
                        self.model.decoder.set_adapter(effective_name)
                    except Exception:
                        pass
        else:
            active_adapter = self._lora_service.ensure_active_adapter()
            self._lora_active_adapter = active_adapter
        self._sync_lora_state_from_service()
        adapter_names = list(self._lora_service.registry.keys())

        debug_log(
            lambda: (
                f"LoRA scale request: adapter={effective_name} scale={scale_value:.3f} "
                f"adapters={adapter_names}"
            ),
            mode=DEBUG_MODEL_LOADING,
            prefix="lora",
        )

        modified = self._apply_scale_to_adapter(effective_name, scale_value)
        report = getattr(self, "_lora_last_scale_report", {})
        skipped_total = sum(report.get("skipped_by_kind", {}).values())

        if modified > 0:
            logger.info(
                f"LoRA scale for '{effective_name}' set to {scale_value:.2f} "
                f"(modified={modified}, by_kind={report.get('modified_by_kind', {})}, skipped={report.get('skipped_by_kind', {})})"
            )
            return (
                f"✅ LoRA scale ({effective_name}): {scale_value:.2f}"
                if skipped_total == 0
                else f"✅ LoRA scale ({effective_name}): {scale_value:.2f} (skipped {skipped_total} targets)"
            )

        if skipped_total > 0:
            logger.warning(
                f"No LoRA targets were modified for adapter '{effective_name}' "
                f"(skipped={report.get('skipped_by_kind', {})})"
            )
            return f"⚠️ LoRA scale unchanged: {scale_value:.2f} (skipped {skipped_total} targets)"

        logger.warning(f"No registered LoRA scaling targets found for adapter '{effective_name}'")
        return f"⚠️ Scale set to {scale_value:.2f} (no modules found)"
    except Exception as e:
        logger.warning(f"Could not set LoRA scale: {e}")
        return f"⚠️ Scale set to {scale_value:.2f} (partial)"


def set_active_lora_adapter(self, adapter_name: str) -> str:
    """Set the active LoRA adapter for scaling/inference."""
    self._ensure_lora_registry()
    if not self._lora_service.set_active_adapter(adapter_name):
        return f"❌ Unknown adapter: {adapter_name}"
    self._lora_active_adapter = self._lora_service.active_adapter
    debug_log(f"Selected active LoRA adapter: {adapter_name}", mode=DEBUG_MODEL_LOADING, prefix="lora")
    if self.model is not None and hasattr(self.model, "decoder") and hasattr(self.model.decoder, "set_adapter"):
        try:
            self.model.decoder.set_adapter(adapter_name)
        except Exception:
            pass
    return f"✅ Active LoRA adapter: {adapter_name}"


def get_lora_status(self) -> dict[str, Any]:
    """Get current LoRA status."""
    self._ensure_lora_registry()
    _active_loras = getattr(self, "_active_loras", None) or {}
    return {
        "loaded": self.lora_loaded,
        "active": self.use_lora,
        "scale": self.lora_scale,
        "scales": dict(_active_loras),
        "active_adapter": self._lora_active_adapter,
        "adapters": list(self._lora_service.registry.keys()),
        "synthetic_default_mode": self._lora_service.synthetic_default_mode,
    }
