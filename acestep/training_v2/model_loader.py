"""
Lean Per-Phase Model Loading for ACE-Step Training V2

Two entry points:
    load_preprocessing_models()  -- VAE + text encoder + condition encoder
    load_decoder_for_training()  -- Full model with decoder accessible

Each function loads only what is needed for its phase, supports torch.no_grad()
context, and provides proper cleanup helpers.
"""

from __future__ import annotations

import gc
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import torch

logger = logging.getLogger(__name__)


def _is_flash_attention_available(device: str) -> bool:
    """Check if flash_attn is usable on the target device.

    Requirements (all must be met):
        1. Device is CUDA.
        2. GPU compute capability >= 8.0 (Ampere / RTX 30xx or newer).
        3. ``flash_attn`` package is importable.
    """
    if not device.startswith("cuda"):
        return False
    try:
        dev_idx = int(device.split(":")[1]) if ":" in device else 0
        props = torch.cuda.get_device_properties(dev_idx)
        if props.major < 8:
            logger.info(
                "[INFO] Flash Attention skipped: GPU compute capability %d.%d < 8.0",
                props.major, props.minor,
            )
            return False
    except Exception:
        return False
    try:
        import flash_attn  # noqa: F401
        return True
    except ImportError:
        return False


# Variant -> subdirectory mapping
_VARIANT_DIR = {
    "turbo": "acestep-v15-turbo",
    "base": "acestep-v15-base",
    "sft": "acestep-v15-sft",
}


def _resolve_model_dir(checkpoint_dir: str | Path, variant: str) -> Path:
    """Return the model subdirectory for *variant* under *checkpoint_dir*.

    Checks the known ``_VARIANT_DIR`` mapping first.  If *variant* is not
    a recognised alias, it is treated as a literal subdirectory name (to
    support custom fine-tunes with arbitrary folder names).
    """
    # 1. Known alias (turbo -> acestep-v15-turbo, etc.)
    subdir = _VARIANT_DIR.get(variant)
    if subdir is not None:
        p = Path(checkpoint_dir) / subdir
        if p.is_dir():
            return p

    # 2. Literal subdirectory name (e.g. "my-custom-finetune")
    p = Path(checkpoint_dir) / variant
    if p.is_dir():
        return p

    # 3. None found
    raise FileNotFoundError(
        f"Model directory not found: tried {_VARIANT_DIR.get(variant, variant)!r} "
        f"and {variant!r} under {checkpoint_dir}"
    )


def _resolve_dtype(precision: str) -> torch.dtype:
    """Map precision string to torch dtype."""
    mapping = {
        "bf16": torch.bfloat16,
        "fp16": torch.float16,
        "fp32": torch.float32,
    }
    return mapping.get(precision, torch.bfloat16)


def read_model_config(checkpoint_dir: str | Path, variant: str) -> Dict[str, Any]:
    """Read and return the model ``config.json`` as a dict.

    Useful for extracting ``timestep_mu``, ``timestep_sigma``,
    ``data_proportion``, ``is_turbo``, etc. without loading the model.
    """
    model_dir = _resolve_model_dir(checkpoint_dir, variant)
    config_path = model_dir / "config.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"config.json not found at {config_path}")
    return json.loads(config_path.read_text())


# ---------------------------------------------------------------------------
# Decoder loading (for training / estimation)
# ---------------------------------------------------------------------------

def load_decoder_for_training(
    checkpoint_dir: str | Path,
    variant: str = "turbo",
    device: str = "cpu",
    precision: str = "bf16",
) -> Any:
    """Load the full ``AceStepConditionGenerationModel`` for training.

    The model is loaded in eval mode with gradients disabled on all
    parameters (the caller -- the trainer -- will selectively enable
    gradients on LoRA-injected parameters).

    Args:
        checkpoint_dir: Root checkpoints directory.
        variant: 'turbo', 'base', or 'sft'.
        device: Target device string.
        precision: 'bf16', 'fp16', or 'fp32'.

    Returns:
        The loaded ``AceStepConditionGenerationModel`` instance.
    """
    from transformers import AutoModel

    model_dir = _resolve_model_dir(checkpoint_dir, variant)
    dtype = _resolve_dtype(precision)

    logger.info("[INFO] Loading model from %s (variant=%s, dtype=%s)", model_dir, variant, dtype)
    print(f"[INFO] Loading model from {model_dir} (variant={variant}, dtype={dtype})")

    # Try attention implementations in preference order.
    # flash_attention_2 first (matches handler.initialize_service), then sdpa, then eager.
    attn_candidates = []
    if _is_flash_attention_available(device):
        attn_candidates.append("flash_attention_2")
    attn_candidates.extend(["sdpa", "eager"])

    model = None
    last_err: Optional[Exception] = None

    for attn_impl in attn_candidates:
        try:
            model = AutoModel.from_pretrained(
                str(model_dir),
                trust_remote_code=True,
                attn_implementation=attn_impl,
                dtype=dtype,
            )
            print(f"[OK] Model loaded with attn_implementation={attn_impl}")
            break
        except Exception as exc:
            last_err = exc
            logger.warning("[WARN] Failed with attn_implementation=%s: %s", attn_impl, exc)

    if model is None:
        raise RuntimeError(
            f"Failed to load model from {model_dir}: {last_err}"
        ) from last_err

    # Freeze everything by default -- trainer will unfreeze LoRA params
    for param in model.parameters():
        param.requires_grad = False

    model = model.to(device=device, dtype=dtype)
    model.eval()

    logger.info("[OK] Model on %s (%s), all params frozen", device, dtype)
    return model


# ---------------------------------------------------------------------------
# Preprocessing models (VAE + text encoder + condition encoder)
# ---------------------------------------------------------------------------

def load_preprocessing_models(
    checkpoint_dir: str | Path,
    variant: str = "turbo",
    device: str = "cpu",
    precision: str = "bf16",
) -> Dict[str, Any]:
    """Load only models needed for the preprocessing phase.

    Returns a dict with keys:
        - ``model``: the full ``AceStepConditionGenerationModel``
        - ``vae``: ``AutoencoderOobleck`` (or None)
        - ``text_tokenizer``: HuggingFace tokenizer
        - ``text_encoder``: Qwen3 text encoder

    The caller must call :func:`cleanup_preprocessing_models` when done.
    """
    from transformers import AutoModel, AutoTokenizer
    from diffusers.models import AutoencoderOobleck

    ckpt = Path(checkpoint_dir)
    dtype = _resolve_dtype(precision)
    result: Dict[str, Any] = {}

    # 1. Full model (needed for condition encoder)
    model = load_decoder_for_training(checkpoint_dir, variant, device, precision)
    result["model"] = model

    # 2. VAE
    vae_path = ckpt / "vae"
    if vae_path.is_dir():
        vae = AutoencoderOobleck.from_pretrained(str(vae_path))
        vae = vae.to(device=device, dtype=dtype)
        vae.eval()
        result["vae"] = vae
        logger.info("[OK] VAE loaded from %s", vae_path)
    else:
        result["vae"] = None
        logger.warning("[WARN] VAE directory not found: %s", vae_path)

    # 3. Text encoder + tokenizer
    text_path = ckpt / "Qwen3-Embedding-0.6B"
    if text_path.is_dir():
        result["text_tokenizer"] = AutoTokenizer.from_pretrained(str(text_path))
        text_enc = AutoModel.from_pretrained(str(text_path))
        text_enc = text_enc.to(device=device, dtype=dtype)
        text_enc.eval()
        result["text_encoder"] = text_enc
        logger.info("[OK] Text encoder loaded from %s", text_path)
    else:
        result["text_tokenizer"] = None
        result["text_encoder"] = None
        logger.warning("[WARN] Text encoder directory not found: %s", text_path)

    return result


def cleanup_preprocessing_models(models: Dict[str, Any]) -> None:
    """Free memory occupied by preprocessing models.

    Moves tensors to CPU, deletes references, and forces garbage collection.
    """
    for key in list(models.keys()):
        obj = models.pop(key, None)
        if obj is not None and hasattr(obj, "to"):
            try:
                obj.to("cpu")
            except Exception:
                pass
        del obj

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    logger.info("[OK] Preprocessing models cleaned up")


# ---------------------------------------------------------------------------
# Per-component loaders (for sequential / low-VRAM preprocessing)
# ---------------------------------------------------------------------------

def load_vae(
    checkpoint_dir: str | Path,
    device: str = "cpu",
    precision: str = "bf16",
) -> Any:
    """Load only the VAE (``AutoencoderOobleck``).

    Returns the VAE model in eval mode, or raises ``FileNotFoundError``
    if the ``vae/`` directory is missing.
    """
    from diffusers.models import AutoencoderOobleck

    vae_path = Path(checkpoint_dir) / "vae"
    if not vae_path.is_dir():
        raise FileNotFoundError(f"VAE directory not found: {vae_path}")

    dtype = _resolve_dtype(precision)
    vae = AutoencoderOobleck.from_pretrained(str(vae_path))
    vae = vae.to(device=device, dtype=dtype)
    vae.eval()
    logger.info("[OK] VAE loaded from %s (%s)", vae_path, dtype)
    return vae


def load_text_encoder(
    checkpoint_dir: str | Path,
    device: str = "cpu",
    precision: str = "bf16",
) -> Tuple[Any, Any]:
    """Load the text tokenizer and encoder (Qwen3-Embedding-0.6B).

    Returns:
        ``(tokenizer, text_encoder)`` -- both ready for inference.

    Raises ``FileNotFoundError`` if the encoder directory is missing.
    """
    from transformers import AutoModel, AutoTokenizer

    text_path = Path(checkpoint_dir) / "Qwen3-Embedding-0.6B"
    if not text_path.is_dir():
        raise FileNotFoundError(f"Text encoder directory not found: {text_path}")

    dtype = _resolve_dtype(precision)
    tokenizer = AutoTokenizer.from_pretrained(str(text_path))
    encoder = AutoModel.from_pretrained(str(text_path))
    encoder = encoder.to(device=device, dtype=dtype)
    encoder.eval()
    logger.info("[OK] Text encoder loaded from %s (%s)", text_path, dtype)
    return tokenizer, encoder


def load_silence_latent(
    checkpoint_dir: str | Path,
    device: str = "cpu",
    precision: str = "bf16",
    variant: str | None = None,
) -> torch.Tensor:
    """Load ``silence_latent.pt`` from the checkpoint directory.

    The tensor is transposed to match the handler convention
    ``(1, T, 64)`` and moved to *device* / *dtype*.

    Search order:
        1. ``checkpoint_dir/silence_latent.pt`` (root -- custom layouts)
        2. ``checkpoint_dir/<variant_subdir>/silence_latent.pt`` (upstream)
        3. Scan all known variant subdirectories as a last-resort fallback

    Raises ``FileNotFoundError`` if the file cannot be found anywhere.
    """
    ckpt = Path(checkpoint_dir)
    sl_path: Path | None = None

    # 1. Direct root path
    candidate = ckpt / "silence_latent.pt"
    if candidate.is_file():
        sl_path = candidate

    # 2. Variant-specific subdirectory
    if sl_path is None and variant is not None:
        subdir = _VARIANT_DIR.get(variant, f"acestep-v15-{variant}")
        candidate = ckpt / subdir / "silence_latent.pt"
        if candidate.is_file():
            sl_path = candidate

    # 3. Last-resort: scan all known variant subdirectories
    if sl_path is None:
        for subdir in _VARIANT_DIR.values():
            candidate = ckpt / subdir / "silence_latent.pt"
            if candidate.is_file():
                sl_path = candidate
                break

    if sl_path is None:
        raise FileNotFoundError(
            f"silence_latent.pt not found under {ckpt} "
            f"(checked root and variant subdirectories)"
        )

    dtype = _resolve_dtype(precision)
    sl = torch.load(str(sl_path), weights_only=True).transpose(1, 2)
    sl = sl.to(device=device, dtype=dtype)
    logger.info("[OK] silence_latent loaded from %s", sl_path)
    return sl


def unload_models(*models: Any) -> None:
    """Move models to CPU, delete references, and free GPU memory.

    Accepts any number of model objects (or ``None`` values, which are
    silently skipped).
    """
    for obj in models:
        if obj is None:
            continue
        if hasattr(obj, "to"):
            try:
                obj.to("cpu")
            except Exception:
                pass
        del obj

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    logger.info("[OK] Models unloaded and GPU cache cleared")
