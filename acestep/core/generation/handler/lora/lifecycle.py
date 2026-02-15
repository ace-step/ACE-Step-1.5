"""LoRA/LoKr adapter load/unload lifecycle management."""

import json
import os
from typing import Any

from loguru import logger

from acestep.constants import DEBUG_MODEL_LOADING
from acestep.debug_utils import debug_log
from acestep.training.configs import LoKRConfig

LOKR_WEIGHTS_FILENAME = "lokr_weights.safetensors"


def _resolve_lokr_weights_path(adapter_path: str) -> str | None:
    """Return LoKr safetensors path when ``adapter_path`` points to LoKr artifacts."""
    if os.path.isfile(adapter_path):
        return adapter_path if os.path.basename(adapter_path) == LOKR_WEIGHTS_FILENAME else None
    if os.path.isdir(adapter_path):
        weights_path = os.path.join(adapter_path, LOKR_WEIGHTS_FILENAME)
        return weights_path if os.path.exists(weights_path) else None
    return None


def _load_lokr_config(weights_path: str) -> LoKRConfig:
    """Build ``LoKRConfig`` from safetensors metadata, with defaults on parse failure."""
    config = LoKRConfig()
    try:
        from safetensors import safe_open
    except ImportError:
        logger.warning("safetensors metadata reader unavailable; using default LoKr config.")
        return config

    try:
        with safe_open(weights_path, framework="pt", device="cpu") as sf:
            metadata: dict[str, Any] = sf.metadata() or {}
    except Exception as exc:
        logger.warning(f"Unable to read LoKr metadata from {weights_path}: {exc}")
        return config

    raw_config = metadata.get("lokr_config")
    if not isinstance(raw_config, str) or not raw_config.strip():
        return config

    try:
        parsed = json.loads(raw_config)
    except json.JSONDecodeError as exc:
        logger.warning(f"Invalid LoKr metadata config JSON in {weights_path}: {exc}")
        return config

    if not isinstance(parsed, dict):
        return config

    allowed_keys = set(LoKRConfig.__dataclass_fields__.keys())
    filtered = {k: v for k, v in parsed.items() if k in allowed_keys}
    if not filtered:
        return config

    try:
        return LoKRConfig(**filtered)
    except Exception as exc:
        logger.warning(f"Failed to apply LoKr metadata config from {weights_path}: {exc}")
        return config


def _load_lokr_adapter(decoder: Any, weights_path: str) -> Any:
    """Inject and load a LoKr LyCORIS adapter into ``decoder``."""
    try:
        from lycoris import LycorisNetwork, create_lycoris
    except ImportError as exc:
        raise ImportError("LyCORIS library not installed. Please install with: pip install lycoris-lora") from exc

    lokr_config = _load_lokr_config(weights_path)
    LycorisNetwork.apply_preset(
        {
            "unet_target_name": lokr_config.target_modules,
            "target_name": lokr_config.target_modules,
        }
    )
    lycoris_net = create_lycoris(
        decoder,
        1.0,
        linear_dim=lokr_config.linear_dim,
        linear_alpha=lokr_config.linear_alpha,
        algo="lokr",
        factor=lokr_config.factor,
        decompose_both=lokr_config.decompose_both,
        use_tucker=lokr_config.use_tucker,
        use_scalar=lokr_config.use_scalar,
        full_matrix=lokr_config.full_matrix,
        bypass_mode=lokr_config.bypass_mode,
        rs_lora=lokr_config.rs_lora,
        unbalanced_factorization=lokr_config.unbalanced_factorization,
    )

    if lokr_config.weight_decompose:
        try:
            lycoris_net = create_lycoris(
                decoder,
                1.0,
                linear_dim=lokr_config.linear_dim,
                linear_alpha=lokr_config.linear_alpha,
                algo="lokr",
                factor=lokr_config.factor,
                decompose_both=lokr_config.decompose_both,
                use_tucker=lokr_config.use_tucker,
                use_scalar=lokr_config.use_scalar,
                full_matrix=lokr_config.full_matrix,
                bypass_mode=lokr_config.bypass_mode,
                rs_lora=lokr_config.rs_lora,
                unbalanced_factorization=lokr_config.unbalanced_factorization,
                dora_wd=True,
            )
        except Exception as exc:
            logger.warning(f"DoRA mode not supported in current LyCORIS build: {exc}")

    lycoris_net.apply_to()
    decoder._lycoris_net = lycoris_net
    lycoris_net.load_weights(weights_path)
    return lycoris_net


def _default_adapter_name_from_path(lora_path: str) -> str:
    """Derive a default adapter name from path (e.g. 'final' from './lora/final')."""
    name = os.path.basename(lora_path.rstrip(os.sep))
    return name if name else "default"


def add_lora(self, lora_path: str, adapter_name: str | None = None) -> str:
    """Load a LoRA adapter into the decoder under the given name.

    If the decoder is not yet a PeftModel, wraps it and loads the first adapter.
    If it is already a PeftModel, loads an additional adapter (no base restore).
    """
    if self.model is None:
        return "❌ Model not initialized. Please initialize service first."

    if self.quantization is not None:
        return (
            "❌ LoRA loading is not supported on quantized models. "
            f"Current quantization: {self.quantization}. "
            "Please re-initialize the service with quantization disabled, then try loading the LoRA adapter again."
        )

    if not lora_path or not lora_path.strip():
        return "❌ Please provide a LoRA path."

    lora_path = lora_path.strip()
    if not os.path.exists(lora_path):
        return f"❌ LoRA path not found: {lora_path}"

    lokr_weights_path = _resolve_lokr_weights_path(lora_path)
    if lokr_weights_path is None:
        config_file = os.path.join(lora_path, "adapter_config.json")
        if not os.path.exists(config_file):
            return (
                "❌ Invalid adapter: expected PEFT LoRA directory containing adapter_config.json "
                f"or LoKr artifact {LOKR_WEIGHTS_FILENAME} in {lora_path}"
            )

    try:
        from peft import PeftModel
    except ImportError:
        if lokr_weights_path is None:
            return "❌ PEFT library not installed. Please install with: pip install peft"
        PeftModel = None  # type: ignore[assignment]

    effective_name = adapter_name.strip() if isinstance(adapter_name, str) and adapter_name.strip() else _default_adapter_name_from_path(lora_path)
    _active_loras = getattr(self, "_active_loras", None)
    if _active_loras is None:
        self._active_loras = {}
        _active_loras = self._active_loras
    if effective_name in _active_loras:
        return f"❌ Adapter name already in use: {effective_name}. Use a different name or remove it first."

    try:
        decoder = self.model.decoder
        is_peft = isinstance(decoder, PeftModel)

        if not is_peft:
            # First LoRA: backup base once, then wrap with PEFT
            if self._base_decoder is None:
                if hasattr(self, "_memory_allocated"):
                    mem_before = self._memory_allocated() / (1024**3)
                    logger.info(f"VRAM before LoRA load: {mem_before:.2f}GB")
                try:
                    state_dict = decoder.state_dict()
                    if not state_dict:
                        raise ValueError("state_dict is empty - cannot backup decoder")
                    self._base_decoder = {k: v.detach().cpu().clone() for k, v in state_dict.items()}
                except Exception as e:
                    logger.error(f"Failed to create state_dict backup: {e}")
                    raise
                backup_size_mb = sum(v.numel() * v.element_size() for v in self._base_decoder.values()) / (1024**2)
                logger.info(f"Base decoder state_dict backed up to CPU ({backup_size_mb:.1f}MB)")

            if lokr_weights_path is not None:
                logger.info(f"Loading LoKr adapter from {lokr_weights_path} as '{effective_name}'")
                _load_lokr_adapter(decoder, lokr_weights_path)
                self.model.decoder = decoder
            else:
                logger.info(f"Loading LoRA adapter from {lora_path} as '{effective_name}'")
                self.model.decoder = PeftModel.from_pretrained(
                    decoder, lora_path, adapter_name=effective_name, is_trainable=False
                )
        else:
            # Already PEFT: load additional adapter (no base restore). LoKr not supported as second adapter.
            if lokr_weights_path is not None:
                return "❌ LoKr cannot be added as a second adapter when PEFT is already loaded."
            logger.info(f"Loading additional LoRA from {lora_path} as '{effective_name}'")
            self.model.decoder.load_adapter(lora_path, adapter_name=effective_name)

        self.model.decoder = self.model.decoder.to(self.device).to(self.dtype)
        self.model.decoder.eval()

        if hasattr(self, "_memory_allocated"):
            mem_after = self._memory_allocated() / (1024**3)
            logger.info(f"VRAM after LoRA load: {mem_after:.2f}GB")

        self.lora_loaded = True
        self.use_lora = True
        self._active_loras[effective_name] = 1.0
        self._ensure_lora_registry()
        self._lora_active_adapter = None
        target_count, adapters = self._rebuild_lora_registry(lora_path=lora_path)
        # Set the newly added adapter as active
        if effective_name in (getattr(self._lora_service, "registry", {}) or {}):
            self._lora_service.set_active_adapter(effective_name)
            self._lora_active_adapter = effective_name
        if hasattr(self.model.decoder, "set_adapter"):
            try:
                self.model.decoder.set_adapter(effective_name)
            except Exception:
                pass

        logger.info(
            f"LoRA adapter '{effective_name}' loaded from {lora_path} "
            f"(adapters={adapters}, targets={target_count})"
        )
        debug_log(
            lambda: f"LoRA registry snapshot: {self._debug_lora_registry_snapshot()}",
            mode=DEBUG_MODEL_LOADING,
            prefix="lora",
        )
        return f"✅ LoRA '{effective_name}' loaded from {lora_path}"
    except Exception as e:
        logger.exception("Failed to load LoRA adapter")
        return f"❌ Failed to load LoRA: {str(e)}"


def load_lora(self, lora_path: str) -> str:
    """Load a single LoRA adapter (backward-compat). Uses path-derived adapter name."""
    return self.add_lora(lora_path, adapter_name=None)


def add_voice_lora(self, lora_path: str, scale: float = 1.0) -> str:
    """Load a LoRA as the 'voice' adapter and set its scale. Same machinery as style LoRA."""
    msg = self.add_lora(lora_path, adapter_name="voice")
    if not msg.startswith("✅"):
        return msg
    return self.set_lora_scale("voice", scale)


def remove_lora(self, adapter_name: str) -> str:
    """Remove one LoRA adapter by name. If no adapters remain, restores base decoder."""
    if not self.lora_loaded:
        return "⚠️ No LoRA adapter loaded."

    _active_loras = getattr(self, "_active_loras", None) or {}
    if adapter_name not in _active_loras:
        return f"❌ Unknown adapter: {adapter_name}. Loaded: {list(_active_loras.keys())}"

    try:
        from peft import PeftModel
    except ImportError:
        return "❌ PEFT library not installed."

    decoder = getattr(self.model, "decoder", None)
    if decoder is None or not isinstance(decoder, PeftModel):
        # Inconsistent state: clear our bookkeeping
        _active_loras.pop(adapter_name, None)
        if not _active_loras:
            self.lora_loaded = False
            self.use_lora = False
        return "⚠️ Adapter removed from registry (decoder was not PEFT)."

    if adapter_name not in (getattr(decoder, "peft_config", None) or {}):
        _active_loras.pop(adapter_name, None)
        self._ensure_lora_registry()
        self._rebuild_lora_registry()
        return f"✅ Adapter '{adapter_name}' removed (was not in PEFT)."

    try:
        decoder.delete_adapter(adapter_name)
        _active_loras.pop(adapter_name, None)
        remaining = list(_active_loras.keys())

        if not remaining:
            # No adapters left: restore base decoder
            if self._base_decoder is None:
                self.lora_loaded = False
                self.use_lora = False
                self._active_loras.clear()
                self._ensure_lora_registry()
                self._lora_service.registry = {}
                self._lora_service.scale_state = {}
                self._lora_service.active_adapter = None
                self._lora_service.last_scale_report = {}
                self._lora_adapter_registry = {}
                self._lora_active_adapter = None
                self._lora_scale_state = {}
                return "✅ Last adapter removed; base decoder still wrapped (no backup). Restart or load a new LoRA."
            mem_before = None
            if hasattr(self, "_memory_allocated"):
                mem_before = self._memory_allocated() / (1024**3)
                logger.info(f"VRAM before LoRA unload: {mem_before:.2f}GB")
            self.model.decoder = decoder.get_base_model()
            load_result = self.model.decoder.load_state_dict(self._base_decoder, strict=False)
            if load_result.missing_keys:
                logger.warning(f"Missing keys when restoring decoder: {load_result.missing_keys[:5]}")
            if load_result.unexpected_keys:
                logger.warning(f"Unexpected keys when restoring decoder: {load_result.unexpected_keys[:5]}")
            self.model.decoder = self.model.decoder.to(self.device).to(self.dtype)
            self.model.decoder.eval()
            self.lora_loaded = False
            self.use_lora = False
            self._active_loras = {}
            self._ensure_lora_registry()
            self._lora_service.registry = {}
            self._lora_service.scale_state = {}
            self._lora_service.active_adapter = None
            self._lora_service.last_scale_report = {}
            self._lora_adapter_registry = {}
            self._lora_active_adapter = None
            self._lora_scale_state = {}
            if mem_before is not None and hasattr(self, "_memory_allocated"):
                mem_after = self._memory_allocated() / (1024**3)
                logger.info(f"VRAM after LoRA unload: {mem_after:.2f}GB (freed: {mem_before - mem_after:.2f}GB)")
            logger.info("LoRA unloaded, base decoder restored")
            return "✅ LoRA unloaded, using base model"
        # Else: set another adapter active and rebuild registry
        next_active = remaining[0]
        if hasattr(decoder, "set_adapter"):
            try:
                decoder.set_adapter(next_active)
            except Exception:
                pass
        self._lora_active_adapter = next_active
        self._ensure_lora_registry()
        self._rebuild_lora_registry()
        self._lora_service.set_active_adapter(next_active)
        # Re-apply scale for the now-active adapter
        scale = self._active_loras.get(next_active, 1.0)
        self._apply_scale_to_adapter(next_active, scale)
        logger.info(f"Adapter '{adapter_name}' removed. Active: {next_active}")
        return f"✅ Adapter '{adapter_name}' removed. Active: {next_active}"
    except Exception as e:
        logger.exception("Failed to remove LoRA adapter")
        return f"❌ Failed to remove LoRA: {str(e)}"


def unload_lora(self) -> str:
    """Unload all LoRA adapters and restore base decoder."""
    if not self.lora_loaded:
        return "⚠️ No LoRA adapter loaded."

    if self._base_decoder is None:
        return "❌ Base decoder backup not found. Cannot restore."

    try:
        mem_before = None
        if hasattr(self, "_memory_allocated"):
            mem_before = self._memory_allocated() / (1024**3)
            logger.info(f"VRAM before LoRA unload: {mem_before:.2f}GB")

        # If this decoder has an attached LyCORIS net, restore original module graph first.
        lycoris_net = getattr(self.model.decoder, "_lycoris_net", None)
        if lycoris_net is not None:
            restore_fn = getattr(lycoris_net, "restore", None)
            if callable(restore_fn):
                logger.info("Restoring decoder structure from LyCORIS adapter")
                restore_fn()
            else:
                logger.warning("Decoder has _lycoris_net but no restore() method; continuing with state_dict restore")
            self.model.decoder._lycoris_net = None

        try:
            from peft import PeftModel
        except ImportError:
            PeftModel = None  # type: ignore[assignment]

        if PeftModel is not None and isinstance(self.model.decoder, PeftModel):
            logger.info("Extracting base model from PEFT wrapper")
            self.model.decoder = self.model.decoder.get_base_model()
            load_result = self.model.decoder.load_state_dict(self._base_decoder, strict=False)
            if load_result.missing_keys:
                logger.warning(f"Missing keys when restoring decoder: {load_result.missing_keys[:5]}")
            if load_result.unexpected_keys:
                logger.warning(f"Unexpected keys when restoring decoder: {load_result.unexpected_keys[:5]}")
        else:
            logger.info("Restoring base decoder from state_dict backup")
            load_result = self.model.decoder.load_state_dict(self._base_decoder, strict=False)
            if load_result.missing_keys:
                logger.warning(f"Missing keys when restoring decoder: {load_result.missing_keys[:5]}")
            if load_result.unexpected_keys:
                logger.warning(f"Unexpected keys when restoring decoder: {load_result.unexpected_keys[:5]}")

        self.model.decoder = self.model.decoder.to(self.device).to(self.dtype)
        self.model.decoder.eval()

        self.lora_loaded = False
        self.use_lora = False
        self.lora_scale = 1.0
        _active_loras = getattr(self, "_active_loras", None)
        if _active_loras is not None:
            _active_loras.clear()
        self._ensure_lora_registry()
        self._lora_service.registry = {}
        self._lora_service.scale_state = {}
        self._lora_service.active_adapter = None
        self._lora_service.last_scale_report = {}
        self._lora_adapter_registry = {}
        self._lora_active_adapter = None
        self._lora_scale_state = {}

        if mem_before is not None and hasattr(self, "_memory_allocated"):
            mem_after = self._memory_allocated() / (1024**3)
            logger.info(f"VRAM after LoRA unload: {mem_after:.2f}GB (freed: {mem_before - mem_after:.2f}GB)")

        logger.info("LoRA unloaded, base decoder restored")
        return "✅ LoRA unloaded, using base model"
    except Exception as e:
        logger.exception("Failed to unload LoRA")
        return f"❌ Failed to unload LoRA: {str(e)}"
