"""LoRA registry state helpers."""

from typing import Any

from acestep.core.lora import LoraService


def _decoder_from_host(self):
    model = getattr(self, "model", None)
    return getattr(model, "decoder", None) if model is not None else None


def _copy_registry(registry: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    copied: dict[str, dict[str, Any]] = {}
    for adapter_name, meta in registry.items():
        targets: list[dict[str, Any]] = []
        for target in meta.get("targets", []):
            target_copy = dict(target)
            module = target_copy.pop("module", None)
            if "module_class" not in target_copy:
                target_copy["module_class"] = module.__class__.__name__ if module is not None else None
            targets.append(target_copy)
        copied[adapter_name] = {
            "path": meta.get("path"),
            "targets": targets,
        }
    return copied


def sync_lora_state_from_service(self) -> None:
    """Sync handler-visible snapshots from the authoritative service state."""
    self._lora_adapter_registry = _copy_registry(self._lora_service.registry)
    self._lora_scale_state = dict(self._lora_service.scale_state)
    self._lora_active_adapter = self._lora_service.active_adapter
    self._lora_last_scale_report = dict(self._lora_service.last_scale_report)


def ensure_lora_registry(self) -> None:
    decoder = _decoder_from_host(self)
    if not hasattr(self, "_lora_service"):
        self._lora_service = LoraService(decoder=decoder)
    else:
        self._lora_service.bind_decoder(decoder)

    if not hasattr(self, "_lora_adapter_registry"):
        self._lora_adapter_registry = {}
    if not hasattr(self, "_lora_active_adapter"):
        self._lora_active_adapter = None
    if not hasattr(self, "_lora_scale_state"):
        self._lora_scale_state = {}
    if not hasattr(self, "_active_loras"):
        self._active_loras = {}
    if not hasattr(self, "_lora_last_scale_report"):
        self._lora_last_scale_report = {}

    sync_lora_state_from_service(self)


def debug_lora_registry_snapshot(self, max_targets_per_adapter: int = 20) -> dict[str, Any]:
    """Return debugger-friendly snapshot of LoRA adapter registry."""
    self._ensure_lora_registry()
    return self._lora_service.registry_snapshot(max_targets_per_adapter=max_targets_per_adapter)
