"""LoRA management mixin for AceStepHandler."""

from .lora.adapter_discovery import collect_adapter_names
from .lora.controls import get_lora_status, set_active_lora_adapter, set_lora_scale, set_use_lora
from .lora.lifecycle import add_lora, add_voice_lora, load_lora, remove_lora, unload_lora
from .lora.registry_builder import rebuild_lora_registry
from .lora.registry_state import debug_lora_registry_snapshot, ensure_lora_registry, sync_lora_state_from_service
from .lora.scale_apply import apply_scale_to_adapter


class LoraManagerMixin:
    """LoRA management behavior mixed into AceStepHandler.

    Expected host attributes:
    - model, device, dtype, quantization
    - _base_decoder
    - lora_loaded, use_lora, lora_scale
    """

    _ensure_lora_registry = ensure_lora_registry
    _sync_lora_state_from_service = sync_lora_state_from_service
    _debug_lora_registry_snapshot = debug_lora_registry_snapshot
    _collect_adapter_names = collect_adapter_names

    _rebuild_lora_registry = rebuild_lora_registry
    _apply_scale_to_adapter = apply_scale_to_adapter

    add_lora = add_lora
    add_voice_lora = add_voice_lora
    load_lora = load_lora
    remove_lora = remove_lora
    unload_lora = unload_lora
    set_use_lora = set_use_lora
    set_lora_scale = set_lora_scale
    set_active_lora_adapter = set_active_lora_adapter
    get_lora_status = get_lora_status
