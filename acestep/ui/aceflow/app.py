"""Minimal Ace-Step UI (FastAPI) with a job queue.

- no training endpoints
- no training endpoints
- limited but flexible generation settings (batch max 4)
- requests are serialized via an in-process queue

Run (example):
  python -m acestep.ui.aceflow.run --host 127.0.0.1 --port 7861

Env overrides:
  ACESTEP_REMOTE_CONFIG_PATH   (default: "acestep-v15-turbo")
  ACESTEP_REMOTE_DEVICE        (default: "auto")
  ACESTEP_REMOTE_MAX_DURATION  (default: 600)
  ACESTEP_REMOTE_RESULTS_DIR   (default: <project>/aceflow_outputs)
"""

from __future__ import annotations
import ast
import json
import logging
import os
import random
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

class _TeeStream:

    def __init__(self, original, capture_fp):
        self._original = original
        self._capture_fp = capture_fp
        self._capture_buffer = ""

    def write(self, data):
        if data is None:
            return 0
        written = 0
        try:
            written = self._original.write(data)
        except Exception:
            pass
        try:
            chunk = str(data)
            self._capture_buffer += chunk
            parts = re.split(r'(\r|\n)', self._capture_buffer)
            if len(parts) == 1:
                return written
            self._capture_buffer = ''
            assembled = []
            current = ''
            for part in parts:
                if part in ('\r', '\n'):
                    line = current
                    current = ''
                    if self._should_capture_cli_line(line):
                        assembled.append(line + part)
                else:
                    current += part
            self._capture_buffer = current
            if assembled:
                self._capture_fp.write(''.join(assembled))
                self._capture_fp.flush()
        except Exception:
            pass
        return written

    def flush(self):
        try:
            self._original.flush()
        except Exception:
            pass
        try:
            if self._capture_buffer:
                self._capture_fp.write(self._capture_buffer)
                self._capture_buffer = ''
            self._capture_fp.flush()
        except Exception:
            pass

    def isatty(self):
        try:
            return bool(self._original.isatty())
        except Exception:
            return False

    def _should_capture_cli_line(self, line):
        return True

    @property
    def encoding(self):
        try:
            return self._original.encoding
        except Exception:
            return 'utf-8'

from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.inference import generate_music, GenerationParams, GenerationConfig, understand_music
from acestep.constants import VALID_LANGUAGES
from .queue import InProcessJobQueue
from .chord_reference import render_reference_wav_file
import subprocess

def _is_sft_model(model_name: Optional[str]) -> bool:

    """Return True for SFT models.
    Remote UI must NOT apply the legacy turbo ("gradio parity") steps clamp to
    SFT variants, even if their name contains "turbo" (e.g. "...-sft-turbo...").
    """
    return "sft" in (model_name or "").lower()

def _is_turbo_model(model_name: Optional[str]) -> bool:

    """Return True for classic turbo models (excluding SFT turbo variants)."""
    name_lower = (model_name or "").lower()
    return ("turbo" in name_lower) and (not _is_sft_model(name_lower))

def _parse_timesteps_input(value):

    """Parse custom timestep input from UI/API into a float list or None."""
    if value is None:
        return None
    if isinstance(value, list):
        if all(isinstance(t, (int, float)) for t in value):
            return [float(t) for t in value]
        return None
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith("[") or raw.startswith("("):
        try:
            parsed = ast.literal_eval(raw)
        except Exception:
            return None
        if isinstance(parsed, list) and all(isinstance(t, (int, float)) for t in parsed):
            return [float(t) for t in parsed]
        return None
    try:
        return [float(t.strip()) for t in raw.split(",") if t.strip()]
    except Exception:
        return None

_CHORD_NOTE_INDEX = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
_CHORD_NOTE_NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_CHORD_NOTE_NAMES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
_CHORD_ROMAN_MAP = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7}
_CHORD_SCALE_INTERVALS = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10]}
_CHORD_QUALITY_SUFFIX = {"major": "", "minor": "m", "maj7": "maj7", "dom7": "7", "min7": "m7", "dim": "dim", "dim7": "dim7", "aug": "aug", "sus2": "sus2", "sus4": "sus4"}

def _prefer_flats_for_key(key: str, scale: str = "major") -> bool:
    key_name = str(key or '').strip()
    if 'b' in key_name:
        return True
    if '#' in key_name:
        return False
    return key_name in {"F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb", "D", "G", "C"} and str(scale or 'major').strip().lower() == 'minor' and key_name in {"D", "G", "C", "F", "Bb", "Eb"}

def _note_name_for_semitone(semitone: int, key: str, scale: str = "major") -> str:
    names = _CHORD_NOTE_NAMES_FLAT if _prefer_flats_for_key(key, scale) else _CHORD_NOTE_NAMES_SHARP
    return names[semitone % 12]

def _parse_roman_chord_token(token: str) -> Optional[dict]:
    rest = str(token or '').strip()
    if not rest:
        return None
    modifier = ''
    if rest[:1] in {'#', 'b', '♯', '♭'}:
        modifier = '#' if rest[0] == '♯' else ('b' if rest[0] == '♭' else rest[0])
        rest = rest[1:]
    m = re.match(r'^(VII|VI|IV|III|II|V|I|vii|vi|iv|iii|ii|v|i)', rest)
    if not m:
        return None
    roman_part = m.group(1)
    suffix = rest[len(roman_part):].lower()
    is_minor = roman_part == roman_part.lower()
    degree = _CHORD_ROMAN_MAP.get(roman_part.upper(), 1)
    quality = 'minor' if is_minor else 'major'
    if 'maj7' in suffix:
        quality = 'maj7'
    elif 'dim7' in suffix:
        quality = 'dim7'
    elif 'dim' in suffix or suffix in {'°', 'o'}:
        quality = 'dim'
    elif 'aug' in suffix or suffix == '+':
        quality = 'aug'
    elif suffix in {'7', 'dom7', '9'}:
        quality = 'min7' if is_minor else 'dom7'
    elif suffix == 'm7':
        quality = 'min7'
    elif suffix == 'sus2':
        quality = 'sus2'
    elif suffix == 'sus4':
        quality = 'sus4'
    return {'degree': degree, 'quality': quality, 'modifier': modifier}

def _resolve_chord_progression(roman_str: str, key: str, scale: str) -> list[str]:
    root_key = str(key or 'C').strip()
    root_index = _CHORD_NOTE_INDEX.get(root_key)
    scale_name = str(scale or 'major').strip().lower()
    intervals = _CHORD_SCALE_INTERVALS['minor' if scale_name == 'minor' else 'major']
    if root_index is None:
        return []
    tokens = [tok for tok in re.split(r'[\s,\-–—]+', str(roman_str or '')) if tok]
    chords = []
    for tok in tokens:
        parsed = _parse_roman_chord_token(tok)
        if not parsed:
            continue
        semitone = (root_index + intervals[(parsed['degree'] - 1) % 7]) % 12
        if parsed['modifier'] == '#':
            semitone = (semitone + 1) % 12
        elif parsed['modifier'] == 'b':
            semitone = (semitone + 11) % 12
        chords.append(f"{_note_name_for_semitone(semitone, root_key, scale)}{_CHORD_QUALITY_SUFFIX.get(parsed['quality'], '')}")
    return chords

def _strip_chord_caption_tag(text: str) -> str:
    out = str(text or '')
    out = re.sub(
        r',?\s*[A-G][#b]?\s*(Major|Minor)\s+key,?\s*chord progression\s*[^,]+,\s*harmonic structure,\s*(major|minor)\s+tonality',
        '',
        out,
        flags=re.I,
    )
    out = re.sub(
        r',?\s*chord progression\s*[^,]+,\s*harmonic structure,\s*(major|minor)\s+tonality',
        '',
        out,
        flags=re.I,
    )
    out = re.sub(r',?\s*harmonic structure,\s*(major|minor)\s+tonality', '', out, flags=re.I)
    out = re.sub(r'\s+,', ',', out)
    out = re.sub(r',\s*,+', ',', out)
    return re.sub(r'^\s*,\s*|\s*,\s*$', '', out).strip()

def _strip_chord_lyrics_tag(text: str) -> str:
    src = re.sub(r'^\s*\[Chord Progression:[^\n]*\]\s*\n?', '', str(text or ''), flags=re.I)
    out = []
    for line in src.splitlines():
        m = re.match(r'^\s*\[(.+)\]\s*$', line)
        if not m:
            out.append(line)
            continue
        inner = re.sub(r'\s*\|\s*Chords:\s*[^\]]*$', '', m.group(1), flags=re.I).strip()
        out.append(f'[{inner}]')
    return '\n'.join(out).lstrip()

def _inject_chord_server_hints(caption: str, lyrics: str, req: dict) -> tuple[str, str, str, list[str]]:
    chord_key = str(req.get('chord_key') or '').strip()
    chord_scale = str(req.get('chord_scale') or 'major').strip().lower() or 'major'
    chord_roman = str(req.get('chord_roman') or '').strip()
    clean_caption = _strip_chord_caption_tag(caption)
    clean_lyrics = _strip_chord_lyrics_tag(lyrics)
    if not chord_key or not chord_roman:
        return clean_caption, clean_lyrics, str(req.get('keyscale') or '').strip(), []
    chords = _resolve_chord_progression(chord_roman, chord_key, chord_scale)
    if not chords:
        return clean_caption, clean_lyrics, str(req.get('keyscale') or '').strip(), []
    scale_label = 'Minor' if chord_scale == 'minor' else 'Major'
    keyscale = str(req.get('keyscale') or '').strip() or f"{chord_key} {scale_label}"
    chord_tag = ' '.join(chords)
    injected_lines = []
    for line in clean_lyrics.splitlines():
        m = re.match(r'^\s*\[([^\]]+)\]\s*$', line)
        if not m:
            injected_lines.append(line)
            continue
        inner = re.sub(r'\s*\|\s*Chords:\s*[^\]]*$', '', m.group(1), flags=re.I).strip()
        injected_lines.append(f'[{inner} | Chords: {chord_tag}]')
    return clean_caption, '\n'.join(injected_lines), keyscale, chords

def _is_peft_like(obj: Any) -> bool:

    """Best-effort detection for PEFT-wrapped decoders across versions."""
    if obj is None:
        return False
    if hasattr(obj, "peft_config") or hasattr(obj, "active_adapters") or hasattr(obj, "active_adapter"):
        return True
    if hasattr(obj, "get_base_model") or hasattr(obj, "disable_adapter") or hasattr(obj, "set_adapter"):
        return True
    mod = getattr(obj.__class__, "__module__", "") or ""
    name = getattr(obj.__class__, "__name__", "") or ""
    return ("peft" in mod.lower()) or name.lower().startswith("peft")

def _strip_peft_attributes(model: Any) -> None:

    """Best-effort removal of PEFT bookkeeping to avoid adapter accumulation."""
    if model is None:
        return
    for attr in (
        "peft_config",
        "active_adapter",
        "active_adapters",
        "peft_type",
        "base_model",
        "modules_to_save",
        "prompt_encoder",
        "_hf_peft_config_loaded",
    ):
        if hasattr(model, attr):
            try:
                delattr(model, attr)
            except Exception:
                try:
                    setattr(model, attr, None)
                except Exception:
                    pass

def _unwrap_peft(model: Any) -> Any:

    """Attempt to unwrap PEFT wrappers and return the plain base decoder."""
    m = model
    if m is None:
        return m
    unload_fn = getattr(m, "unload", None)
    if callable(unload_fn):
        try:
            unloaded = unload_fn()
            if unloaded is not None:
                m = unloaded
        except Exception:
            pass
    for _ in range(6):
        if not _is_peft_like(m):
            break
        get_base = getattr(m, "get_base_model", None)
        if callable(get_base):
            try:
                m2 = get_base()
                if m2 is not None and m2 is not m:
                    m = m2
                    continue
            except Exception:
                pass
        base_model = getattr(m, "base_model", None)
        inner = getattr(base_model, "model", None) if base_model is not None else None
        if inner is not None and inner is not m:
            m = inner
            continue
        break
    _strip_peft_attributes(model)
    if m is not model:
        _strip_peft_attributes(m)
    return m

def _restore_decoder_state_dict(decoder_model: Any, backup_sd: dict) -> Any:

    """Restore base decoder weights with fallback key remap for PEFT leftovers."""
    try:
        return decoder_model.load_state_dict(backup_sd, strict=False)
    except Exception:
        pass
    model_keys = set(decoder_model.state_dict().keys())
    remapped = {}
    for k, v in backup_sd.items():
        if k in model_keys:
            remapped[k] = v
            continue
        if isinstance(k, str) and k.endswith(".weight"):
            alt = k[:-7] + ".base_layer.weight"
            if alt in model_keys:
                remapped[alt] = v
                continue
        remapped[k] = v
    return decoder_model.load_state_dict(remapped, strict=False)

def _cleanup_lora_runtime_memory() -> None:

    """Best-effort GC/CUDA cleanup after LoRA unload/load transitions."""
    try:
        import gc
        gc.collect()
    except Exception:
        pass
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            try:
                torch.cuda.ipc_collect()
            except Exception:
                pass
    except Exception:
        pass

def _collect_lora_runtime_state(handler) -> dict:

    """Best-effort snapshot of current LoRA/adapter state for diagnostics."""
    state = {
        "lora_loaded": bool(getattr(handler, "lora_loaded", False)),
        "use_lora": bool(getattr(handler, "use_lora", False)),
        "adapter_type": getattr(handler, "_adapter_type", None),
        "active_adapter": None,
        "active_loras": [],
        "registry_keys": [],
        "peft_adapters": [],
        "decoder_is_peft": False,
        "has_lycoris": False,
    }
    try:
        active = getattr(handler, "_active_loras", None)
        if isinstance(active, dict):
            state["active_loras"] = sorted(str(k) for k in active.keys())
        elif active:
            state["active_loras"] = [str(active)]
    except Exception:
        pass
    try:
        registry = getattr(handler, "_lora_adapter_registry", None)
        if isinstance(registry, dict):
            state["registry_keys"] = sorted(str(k) for k in registry.keys())
    except Exception:
        pass
    decoder = getattr(getattr(handler, "model", None), "decoder", None)
    try:
        state["decoder_is_peft"] = bool(_is_peft_like(decoder))
    except Exception:
        pass
    try:
        state["has_lycoris"] = getattr(decoder, "_lycoris_net", None) is not None
    except Exception:
        pass
    try:
        active_adapter = getattr(handler, "_lora_active_adapter", None)
        if not active_adapter:
            svc = getattr(handler, "_lora_service", None)
            active_adapter = getattr(svc, "active_adapter", None)
        state["active_adapter"] = active_adapter
    except Exception:
        pass
    try:
        if _is_peft_like(decoder):
            names = []
            peft_cfg = getattr(decoder, "peft_config", None)
            if isinstance(peft_cfg, dict):
                names.extend(list(peft_cfg.keys()))
            list_fn = getattr(decoder, "list_adapters", None)
            if callable(list_fn):
                try:
                    listed = list_fn()
                    if isinstance(listed, dict):
                        for _, vals in listed.items():
                            if isinstance(vals, (list, tuple, set)):
                                names.extend(list(vals))
                    elif isinstance(listed, (list, tuple, set)):
                        names.extend(list(listed))
                    elif listed:
                        names.append(str(listed))
                except Exception:
                    pass
            state["peft_adapters"] = sorted(dict.fromkeys(str(n) for n in names if n))
    except Exception:
        pass
    return state

def _format_lora_runtime_state(handler) -> str:

    state = _collect_lora_runtime_state(handler)
    return (
        f"loaded={state['lora_loaded']} use_lora={state['use_lora']} "
        f"adapter_type={state['adapter_type']!r} active_adapter={state['active_adapter']!r} "
        f"active_loras={state['active_loras']} registry={state['registry_keys']} "
        f"peft_adapters={state['peft_adapters']} decoder_is_peft={state['decoder_is_peft']} "
        f"lycoris={state['has_lycoris']}"
    )

def _install_aceflow_lora_runtime_patch() -> None:

    """Keep upstream lifecycle.py untouched while enforcing AceFlow single-LoRA policy."""
    if getattr(AceStepHandler, "_aceflow_lora_runtime_patch", False):
        return
    original_add_lora = getattr(AceStepHandler, "add_lora", None)
    original_unload_lora = getattr(AceStepHandler, "unload_lora", None)
    if not callable(original_add_lora) or not callable(original_unload_lora):
        logger.warning("[AceFlow LoRA] runtime patch skipped: handler methods not found")
        return

    def patched_unload_lora(self) -> str:

        if getattr(self, "_base_decoder", None) is None:
            return original_unload_lora(self)
        decoder = getattr(getattr(self, "model", None), "decoder", None)
        has_active = bool(getattr(self, "lora_loaded", False) or (getattr(self, "_active_loras", None) or {}))
        has_lycoris = getattr(decoder, "_lycoris_net", None) is not None
        if (not has_active) and (not has_lycoris) and (not _is_peft_like(decoder)):
            logger.info(f"[AceFlow LoRA] state before unload (noop): {_format_lora_runtime_state(self)}")
            return "⚠️ No LoRA adapter loaded."
        try:
            mem_before = None
            if hasattr(self, "_memory_allocated"):
                try:
                    mem_before = self._memory_allocated() / (1024**3)
                    logger.info(f"[AceFlow LoRA] VRAM before unload: {mem_before:.2f}GB")
                except Exception:
                    mem_before = None
            logger.info(f"[AceFlow LoRA] state before unload: {_format_lora_runtime_state(self)}")
            lycoris_net = getattr(self.model.decoder, "_lycoris_net", None)
            if lycoris_net is not None:
                restore_fn = getattr(lycoris_net, "restore", None)
                if callable(restore_fn):
                    logger.info("[AceFlow LoRA] restoring decoder structure from LyCORIS adapter")
                    restore_fn()
                self.model.decoder._lycoris_net = None
            peft_decoder = self.model.decoder
            is_peft = _is_peft_like(peft_decoder)
            if is_peft:
                logger.info("[AceFlow LoRA] unloading PEFT adapters")
                try:
                    disable_one = getattr(peft_decoder, "disable_adapter", None)
                    if callable(disable_one):
                        disable_one()
                    disable_many = getattr(peft_decoder, "disable_adapters", None)
                    if callable(disable_many):
                        disable_many()
                except Exception:
                    pass
                base_model = None
                unload_fn = getattr(peft_decoder, "unload", None)
                if callable(unload_fn):
                    try:
                        base_model = unload_fn()
                    except Exception as exc:
                        logger.warning(f"[AceFlow LoRA] PEFT unload() failed, falling back to delete_adapter(): {exc!r}")
                if base_model is None:
                    try:
                        names = []
                        peft_cfg = getattr(peft_decoder, "peft_config", None)
                        if isinstance(peft_cfg, dict):
                            names.extend(list(peft_cfg.keys()))
                        list_fn = getattr(peft_decoder, "list_adapters", None)
                        if callable(list_fn):
                            try:
                                names.extend(list(list_fn()))
                            except Exception:
                                pass
                        names = list(dict.fromkeys([n for n in names if isinstance(n, str) and n]))
                        delete_fn = getattr(peft_decoder, "delete_adapter", None)
                        if callable(delete_fn):
                            for name in names:
                                try:
                                    delete_fn(name)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                try:
                    base_model = _unwrap_peft(peft_decoder)
                except Exception:
                    base_model = peft_decoder
                if _is_peft_like(base_model):
                    try:
                        bm = getattr(peft_decoder, "base_model", None)
                        bm = getattr(bm, "model", bm)
                        if bm is not None:
                            base_model = bm
                    except Exception:
                        pass
                _strip_peft_attributes(peft_decoder)
                _strip_peft_attributes(base_model)
                self.model.decoder = base_model
                load_result = _restore_decoder_state_dict(self.model.decoder, self._base_decoder)
            else:
                logger.info("[AceFlow LoRA] restoring base decoder from state_dict backup")
                load_result = _restore_decoder_state_dict(self.model.decoder, self._base_decoder)
            try:
                self.model.decoder = self.model.decoder.to(self.device).to(self.dtype)
                self.model.decoder.eval()
            except Exception:
                pass
            self.lora_loaded = False
            self.use_lora = False
            self._adapter_type = None
            self.lora_scale = 1.0
            active = getattr(self, "_active_loras", None)
            if active is not None:
                try:
                    active.clear()
                except Exception:
                    pass
            try:
                self._ensure_lora_registry()
                self._lora_service.registry = {}
                self._lora_service.scale_state = {}
                self._lora_service.active_adapter = None
                self._lora_service.last_scale_report = {}
            except Exception:
                pass
            try:
                self._lora_adapter_registry = {}
                self._lora_active_adapter = None
                self._lora_scale_state = {}
            except Exception:
                pass
            if getattr(load_result, "missing_keys", None):
                logger.warning(f"[AceFlow LoRA] missing keys when restoring decoder: {load_result.missing_keys[:5]}")
            if getattr(load_result, "unexpected_keys", None):
                logger.warning(f"[AceFlow LoRA] unexpected keys when restoring decoder: {load_result.unexpected_keys[:5]}")
            _cleanup_lora_runtime_memory()
            if mem_before is not None and hasattr(self, "_memory_allocated"):
                try:
                    mem_after = self._memory_allocated() / (1024**3)
                    logger.info(f"[AceFlow LoRA] VRAM after unload: {mem_after:.2f}GB (freed: {mem_before - mem_after:.2f}GB)")
                except Exception:
                    pass
            logger.info(f"[AceFlow LoRA] state after unload: {_format_lora_runtime_state(self)}")
            logger.info("[AceFlow LoRA] unload complete; base decoder restored")
            return "✅ LoRA unloaded, using base model"
        except Exception as exc:
            logger.exception("[AceFlow LoRA] robust unload failed; falling back to upstream unload")
            try:
                return original_unload_lora(self)
            finally:
                _cleanup_lora_runtime_memory()

    def patched_add_lora(self, lora_path: str, adapter_name: Optional[str] = None) -> str:

        logger.info(f"[AceFlow LoRA] state before load request: {_format_lora_runtime_state(self)}")
        decoder = getattr(getattr(self, "model", None), "decoder", None)
        needs_cleanup = bool(
            getattr(self, "lora_loaded", False)
            or (getattr(self, "_active_loras", None) or {})
            or _is_peft_like(decoder)
            or getattr(decoder, "_lycoris_net", None) is not None
        )
        if needs_cleanup:
            try:
                cleanup_msg = patched_unload_lora(self)
                logger.info(f"[AceFlow LoRA] pre-load cleanup: {cleanup_msg}")
            except Exception as exc:
                logger.warning(f"[AceFlow LoRA] pre-load cleanup failed (continuing): {exc!r}")
        decoder = getattr(getattr(self, "model", None), "decoder", None)
        if _is_peft_like(decoder):
            try:
                base_model = _unwrap_peft(decoder)
                _strip_peft_attributes(base_model)
                self.model.decoder = base_model
            except Exception:
                pass
        result = original_add_lora(self, lora_path, adapter_name)
        logger.info(f"[AceFlow LoRA] state after load: {_format_lora_runtime_state(self)}")
        return result
    AceStepHandler.unload_lora = patched_unload_lora
    AceStepHandler.add_lora = patched_add_lora
    AceStepHandler._aceflow_lora_runtime_patch = True
    logger.info("[AceFlow LoRA] runtime patch enabled (single-LoRA policy, upstream lifecycle untouched)")

def _query_nvidia_smi() -> Optional[dict]:

    """Return GPU name + VRAM usage + temperature via nvidia-smi (best-effort).
    We intentionally avoid adding dependencies (pynvml). If nvidia-smi is not
    available or fails, return None.
    """
    try:
        cmd = [
            "nvidia-smi",
            "--query-gpu=name,memory.used,memory.total,temperature.gpu",
            "--format=csv,noheader,nounits",
            "--id=0",
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=1.5)
        line = out.decode("utf-8", errors="replace").strip().splitlines()[0].strip()
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            return None
        name = parts[0]
        used = int(float(parts[1]))
        total = int(float(parts[2]))
        temp = None
        try:
            if len(parts) >= 4 and parts[3] != "":
                temp = int(float(parts[3]))
        except Exception:
            temp = None
        return {
            "gpu_name": name,
            "vram_used_mb": used,
            "vram_total_mb": total,
            "gpu_temp_c": temp,
        }
    except Exception:
        return None

def _get_gpu_info_cached(app: FastAPI, ttl_seconds: float = 1.0) -> Optional[dict]:

    """Cache GPU query for a short time to avoid repeated subprocess calls."""
    now = time.time()
    cache = getattr(app.state, "_gpu_cache", None)
    if cache and (now - cache.get("ts", 0.0)) < ttl_seconds:
        return cache.get("val")
    val = _query_nvidia_smi()
    app.state._gpu_cache = {"ts": now, "val": val}
    return val

_UUID_RE = re.compile(

    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"

)

def is_job_dir(p: Path) -> bool:

    """Return True only for directories that are clearly per-job output dirs.
    Conservative rule-set:
    - must be a real directory (not a symlink)
    - must look like the UUID naming used by /api/jobs
    - must contain at least one unambiguous job marker (metadata.json) OR
      a typical produced audio file.
    """
    try:
        if not p.is_dir():
            return False
        if p.is_symlink():
            return False
        if not _UUID_RE.match(p.name or ""):
            return False
        if (p / "metadata.json").is_file():
            return True
        for ext in (".wav", ".mp3", ".flac", ".opus", ".aac"):
            try:
                if any(p.glob(f"*{ext}")):
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False

def cleanup_old_job_dirs(base_dir: Path, ttl_seconds: int = 3600) -> dict:

    """Delete per-job output directories older than ttl_seconds.
    Safety properties (HARD):
    - only deletes directories, never files
    - skips symlinks
    - resolves paths and deletes only if the candidate is under base_dir
    - uses directory mtime (stat().st_mtime) as age
    - never raises; returns a small report
    """
    report = {"scanned": 0, "deleted": 0, "skipped": 0, "errors": 0}
    try:
        base_resolved = base_dir.resolve()
    except Exception:
        report["errors"] += 1
        return report
    try:
        if not getattr(cleanup_old_job_dirs, "_logged_base", False):
            logger.info("[cleanup] base={}", str(base_resolved))
            setattr(cleanup_old_job_dirs, "_logged_base", True)
    except Exception:
        pass
    now = time.time()
    try:
        for child in base_dir.iterdir():
            report["scanned"] += 1
            try:
                if not child.is_dir():
                    report["skipped"] += 1
                    continue
                if child.is_symlink():
                    report["skipped"] += 1
                    continue
                try:
                    child_resolved = child.resolve()
                except Exception:
                    report["skipped"] += 1
                    continue
                try:
                    if not child_resolved.is_relative_to(base_resolved):
                        report["skipped"] += 1
                        continue
                except AttributeError:
                    if not str(child_resolved).startswith(str(base_resolved) + os.sep):
                        report["skipped"] += 1
                        continue
                if child_resolved == base_resolved:
                    report["skipped"] += 1
                    continue
                if not is_job_dir(child):
                    report["skipped"] += 1
                    continue
                try:
                    mtime = float(child.stat().st_mtime)
                except Exception:
                    report["skipped"] += 1
                    continue
                if (now - mtime) <= float(ttl_seconds):
                    report["skipped"] += 1
                    continue
                try:
                    shutil.rmtree(child)
                    report["deleted"] += 1
                except Exception as exc:
                    report["errors"] += 1
                    logger.warning("[cleanup] failed path={} err={!r}", str(child), exc)
            except Exception as exc:
                report["errors"] += 1
                logger.warning("[cleanup] scan failed path={} err={!r}", str(child), exc)
    except Exception as exc:
        report["errors"] += 1
        logger.warning("[cleanup] iterdir failed base={} err={!r}", str(base_dir), exc)
    return report

def cleanup_old_upload_files(uploads_dir: Path, ttl_seconds: int = 3600) -> dict:

    """Delete uploaded audio files older than ttl_seconds.
    Safety properties (HARD):
    - only deletes regular files, never directories
    - skips symlinks
    - resolves paths and deletes only if the candidate is under uploads_dir
    - uses file mtime (stat().st_mtime) as age
    - never raises; returns a small report
    """
    report = {"scanned": 0, "deleted": 0, "skipped": 0, "errors": 0}
    try:
        uploads_dir.mkdir(parents=True, exist_ok=True)
        base_resolved = uploads_dir.resolve()
    except Exception:
        report["errors"] += 1
        return report
    now = time.time()
    try:
        for child in uploads_dir.iterdir():
            report["scanned"] += 1
            try:
                if not child.is_file():
                    report["skipped"] += 1
                    continue
                if child.is_symlink():
                    report["skipped"] += 1
                    continue
                try:
                    child_resolved = child.resolve()
                except Exception:
                    report["skipped"] += 1
                    continue
                try:
                    if not child_resolved.is_relative_to(base_resolved):
                        report["skipped"] += 1
                        continue
                except AttributeError:
                    if not str(child_resolved).startswith(str(base_resolved) + os.sep):
                        report["skipped"] += 1
                        continue
                try:
                    mtime = float(child.stat().st_mtime)
                except Exception:
                    report["skipped"] += 1
                    continue
                if (now - mtime) <= float(ttl_seconds):
                    report["skipped"] += 1
                    continue
                try:
                    child.unlink()
                    report["deleted"] += 1
                except Exception as exc:
                    report["errors"] += 1
                    logger.warning("[cleanup_uploads] failed path={} err={!r}", str(child), exc)
            except Exception as exc:
                report["errors"] += 1
                logger.warning("[cleanup_uploads] scan failed path={} err={!r}", str(child), exc)
    except Exception as exc:
        report["errors"] += 1
        logger.warning("[cleanup_uploads] iterdir failed base={} err={!r}", str(uploads_dir), exc)
    return report

def cleanup_old_log_files(logs_dir: Path, ttl_seconds: int = 3600) -> dict:

    report = {"scanned": 0, "deleted": 0, "skipped": 0, "errors": 0}
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        base_resolved = logs_dir.resolve()
    except Exception:
        report["errors"] += 1
        return report
    now = time.time()
    try:
        for child in logs_dir.iterdir():
            report["scanned"] += 1
            try:
                if not child.is_file():
                    report["skipped"] += 1
                    continue
                if child.is_symlink():
                    report["skipped"] += 1
                    continue
                try:
                    child_resolved = child.resolve()
                except Exception:
                    report["skipped"] += 1
                    continue
                try:
                    if not child_resolved.is_relative_to(base_resolved):
                        report["skipped"] += 1
                        continue
                except AttributeError:
                    if not str(child_resolved).startswith(str(base_resolved) + os.sep):
                        report["skipped"] += 1
                        continue
                try:
                    mtime = float(child.stat().st_mtime)
                except Exception:
                    report["skipped"] += 1
                    continue
                if (now - mtime) <= float(ttl_seconds):
                    report["skipped"] += 1
                    continue
                try:
                    child.unlink()
                    report["deleted"] += 1
                except Exception as exc:
                    report["errors"] += 1
                    logger.warning("[cleanup_logs] failed path={} err={!r}", str(child), exc)
            except Exception as exc:
                report["errors"] += 1
                logger.warning("[cleanup_logs] scan failed path={} err={!r}", str(child), exc)
    except Exception as exc:
        report["errors"] += 1
        logger.warning("[cleanup_logs] iterdir failed base={} err={!r}", str(logs_dir), exc)
    return report

def _get_project_root() -> str:

    p = Path(__file__).resolve()
    return str(p.parents[3])

def _env_int(name: str, default: int) -> int:

    try:
        v = os.environ.get(name)
        if v is None or str(v).strip() == "":
            return default
        return int(float(v))
    except Exception:
        return default

def _resolve_lora_root(project_root: str) -> str:

    """Return LoRA root directory.
    Remote UI requirement: prefer the explicit Windows path used by Marco.
    Falls back to <project_root>/lora if the preferred path does not exist.
    """
    preferred = r"F:\\AI\\ACE-Step-1.5\\lora"
    try:
        if os.path.exists(preferred):
            return preferred
    except Exception:
        pass
    return os.path.join(project_root, "lora")

def _json_safe(obj, _depth: int = 0, _seen: Optional[set[int]] = None):

    """Convert arbitrary objects into JSON-serializable structures.
    This is a defensive sanitizer used for BOTH API responses and metadata.json.
    It must never throw, and it must never leak raw torch tensors.
    """
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if _seen is None:
        _seen = set()
    try:
        oid = id(obj)
        if oid in _seen:
            return "<circular>"
        _seen.add(oid)
    except Exception:
        pass
    if _depth > 25:
        return "<max_depth>"
    try:
        from pathlib import Path as _Path
        if isinstance(obj, _Path):
            return str(obj)
    except Exception:
        pass
    if isinstance(obj, (bytes, bytearray, memoryview)):
        try:
            return obj.decode("utf-8", errors="replace")
        except Exception:
            return str(obj)
    try:
        import torch
        if isinstance(obj, torch.Tensor):
            try:
                numel = int(obj.numel())
                if numel == 1:
                    return obj.detach().cpu().item()
                if numel <= 64:
                    return obj.detach().cpu().tolist()
                return {
                    "__tensor__": True,
                    "shape": list(obj.shape),
                    "dtype": str(obj.dtype),
                    "device": str(obj.device),
                    "numel": numel,
                }
            except Exception:
                return {
                    "__tensor__": True,
                    "shape": list(getattr(obj, "shape", [])),
                    "dtype": str(getattr(obj, "dtype", "")),
                }
    except Exception:
        pass
    try:
        import numpy as np
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.generic,)):
            return obj.item()
    except Exception:
        pass
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            try:
                sk = str(k)
            except Exception:
                sk = "<key>"
            out[sk] = _json_safe(v, _depth=_depth + 1, _seen=_seen)
        return out
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v, _depth=_depth + 1, _seen=_seen) for v in obj]
    try:
        import dataclasses
        if dataclasses.is_dataclass(obj):
            return _json_safe(dataclasses.asdict(obj), _depth=_depth + 1, _seen=_seen)
    except Exception:
        pass
    for attr in ("model_dump", "dict", "to_dict"):
        if hasattr(obj, attr):
            try:
                fn = getattr(obj, attr)
                if callable(fn):
                    return _json_safe(fn(), _depth=_depth + 1, _seen=_seen)
            except Exception:
                pass
    if hasattr(obj, "__dict__"):
        try:
            return _json_safe(vars(obj), _depth=_depth + 1, _seen=_seen)
        except Exception:
            pass
    try:
        return str(obj)
    except Exception:
        return "<unprintable>"

def _write_json(path: str, data: dict):

    os.makedirs(os.path.dirname(path), exist_ok=True)
    safe = _json_safe(data)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(safe, f, ensure_ascii=False, indent=2)

def create_app() -> FastAPI:

    project_root = _get_project_root()
    config_path = os.environ.get("ACESTEP_REMOTE_CONFIG_PATH", "acestep-v15-turbo")
    device = os.environ.get("ACESTEP_REMOTE_DEVICE", "auto")
    max_duration = 600
    results_root = os.environ.get(
        "ACESTEP_REMOTE_RESULTS_DIR",
        os.path.join(project_root, "aceflow_outputs"),
    )
    results_root = results_root.replace("\\", "/")
    counter_path = os.path.join(results_root, "_songs_generated.json").replace("\\", "/")
    os.makedirs(results_root, exist_ok=True)
    uploads_dir = os.path.join(results_root, "_uploads").replace("\\", "/")
    logs_dir = os.path.join(results_root, "_logs").replace("\\", "/")
    os.makedirs(uploads_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)

    def _ensure_uploads_dir() -> str:

        """Ensure results_root/_uploads exists and return uploads_dir."""
        try:
            Path(results_root).mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning("[upload] ensure results_root failed base={} err={!r}", results_root, exc)
            raise
        try:
            Path(uploads_dir).mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning("[upload] ensure uploads_dir failed dir={} err={!r}", uploads_dir, exc)
            raise
        return uploads_dir

    def _ensure_logs_dir() -> str:

        try:
            Path(results_root).mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning("[logs] ensure results_root failed base={} err={!r}", results_root, exc)
            raise
        try:
            Path(logs_dir).mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning("[logs] ensure logs_dir failed dir={} err={!r}", logs_dir, exc)
            raise
        return logs_dir

    def _start_job_cli_capture(job_id: str) -> str:

        _ensure_logs_dir()
        tmp_path = os.path.join(logs_dir, f"{job_id}__live_cli.txt").replace("\\", "/")
        capture_fp = open(tmp_path, "a", encoding="utf-8", buffering=1)
        fmt = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}"
        sink_id = logger.add(capture_fp, level="DEBUG", format=fmt, enqueue=False, backtrace=False, diagnose=False)
        py_handler = logging.StreamHandler(capture_fp)
        py_handler.setLevel(logging.DEBUG)
        py_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        attached = []
        for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            py_logger = logging.getLogger(logger_name)
            py_logger.addHandler(py_handler)
            attached.append(py_logger)
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        sys.stdout = _TeeStream(original_stdout, capture_fp)
        sys.stderr = _TeeStream(original_stderr, capture_fp)
        app.state._job_cli_captures[job_id] = {
            "tmp_path": tmp_path,
            "capture_fp": capture_fp,
            "sink_id": sink_id,
            "py_handler": py_handler,
            "attached": attached,
            "stdout": original_stdout,
            "stderr": original_stderr,
        }
        return tmp_path

    def _finalize_job_cli_capture(job_id: str, audio_paths: list[str] | None = None) -> list[str]:

        created = []
        ctx = app.state._job_cli_captures.pop(job_id, None)
        if not ctx:
            return created
        try:
            sys.stdout = ctx.get("stdout", sys.stdout)
            sys.stderr = ctx.get("stderr", sys.stderr)
        except Exception:
            pass
        try:
            logger.remove(ctx.get("sink_id"))
        except Exception:
            pass
        py_handler = ctx.get("py_handler")
        for py_logger in ctx.get("attached", []):
            try:
                py_logger.removeHandler(py_handler)
            except Exception:
                pass
        capture_fp = ctx.get("capture_fp")
        if capture_fp is not None:
            try:
                capture_fp.flush()
            except Exception:
                pass
            try:
                capture_fp.close()
            except Exception:
                pass
        tmp_path = str(ctx.get("tmp_path") or "")
        if not tmp_path or not Path(tmp_path).exists():
            return created
        targets = []
        if audio_paths:
            for idx, audio_path in enumerate(audio_paths or []):
                audio_name = os.path.basename(str(audio_path or "")).strip()
                base_name = os.path.splitext(audio_name)[0].strip() or f"{job_id}_{idx}"
                targets.append(os.path.join(logs_dir, f"{base_name}_log.txt").replace("\\", "/"))
        else:
            targets.append(os.path.join(logs_dir, f"{job_id}_log.txt").replace("\\", "/"))
        for target in targets:
            try:
                shutil.copyfile(tmp_path, target)
                created.append(target)
            except Exception as exc:
                logger.warning("[job_log] copy failed src={} dst={} err={!r}", tmp_path, target, exc)
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass
        return created
    app_counter_lock = None
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    ui_root = os.path.dirname(__file__)
    app = FastAPI(title="AceFlow")
    app.state._job_cli_captures = {}
    _ALLOWED_MODELS = {
        "acestep-v15-base",
        "acestep-v15-sft",
        "acestep-v15-sft-turbo-ta-0.5",
        "acestep-v15-turbo",
        "acestep-v15-turbo-continuous",
        "acestep-v15-turbo-shift1",
        "acestep-v15-turbo-shift3",
    }

    def _normalize_model_choice(v: Optional[str]) -> str:

        s = str(v or "").strip()
        if not s:
            return str(config_path)
        if s in _ALLOWED_MODELS:
            return s
        return str(config_path)
    remote_token = os.environ.get('ACESTEP_REMOTE_TOKEN', '').strip()

    def _require_token(request: Request) -> None:

        """Optional token gate for remote exposure."""
        if not remote_token:
            return
        tok = (request.headers.get('x-ace-token') or request.headers.get('authorization') or '').strip()
        if tok.lower().startswith('bearer '):
            tok = tok[7:].strip()
        if tok != remote_token:
            raise HTTPException(status_code=401, detail='Unauthorized')

    @app.middleware("http")

    async def _no_cache_ui(request, call_next):
        resp = await call_next(request)
        p = request.url.path or ""
        if p == "/" or p.startswith("/static") or p.startswith("/favicon"):
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
        return resp
    import threading
    app.state._counter_lock = threading.Lock()
    app.state._rate_lock = threading.Lock()
    app.state._last_job_at_by_ip = {}
    app.state._rate_min_interval_s = float(os.environ.get("ACESTEP_REMOTE_MIN_JOB_INTERVAL_S", "5"))
    app.state._queue_active_cap = int(os.environ.get("ACESTEP_REMOTE_MAX_ACTIVE_JOBS", "30"))

    def _load_counter() -> int:

        try:
            if os.path.exists(counter_path):
                with open(counter_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                v = int(data.get("songs_generated", 0))
                return max(0, v)
        except Exception:
            return 0
        return 0

    def _save_counter(n: int) -> None:

        try:
            tmp = counter_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"songs_generated": int(n)}, f, ensure_ascii=False)
            os.replace(tmp, counter_path)
        except Exception:
            pass
    app.state.songs_generated = _load_counter()
    lora_catalog_path = os.path.join(ui_root, "lora_catalog.json").replace("\\", "/")

    def _load_lora_catalog() -> list[dict]:

        try:
            if os.path.exists(lora_catalog_path):
                with open(lora_catalog_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    out = []
                    for it in data:
                        if not isinstance(it, dict):
                            continue
                        _id = str(it.get("id", "") or "")
                        _trigger = str((it.get("trigger", it.get("tag", "")) ) or "")
                        _label = str(it.get("label", "") or _id)
                        out.append({"id": _id, "trigger": _trigger, "label": _label})
                    if not out or out[0].get("id", "") != "":
                        out.insert(0, {"id": "", "trigger": "", "label": "(Nessun LoRA)"})
                    try:
                        if out and str(out[0].get("id", "") or "") == "":
                            out[0]["trigger"] = ""
                    except Exception:
                        pass
                    return out
        except Exception:
            pass
        return [{"id": "", "trigger": "", "label": "(Nessun LoRA)"}]
    app.state._lora_catalog = _load_lora_catalog()
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    _install_aceflow_lora_runtime_patch()
    dit_handler = AceStepHandler()
    llm_handler = LLMHandler()
    app.state._active_model = _normalize_model_choice(config_path)
    app.state._default_model = app.state._active_model

    def _ensure_model_loaded(model_name: str) -> AceStepHandler:

        """Ensure the requested model is loaded.
        The remote queue is single-job, so a simple switch (re-init) is safe.
        We avoid keeping multiple models resident to reduce VRAM pressure.
        """
        want = _normalize_model_choice(model_name)
        cur = str(getattr(app.state, "_active_model", app.state._default_model) or app.state._default_model)
        if want == cur and getattr(app.state, "dit_handler", None) is not None:
            return app.state.dit_handler
        def _dispose_handler(h: object) -> None:
            """Aggressively drop references held by an AceStepHandler.
            IMPORTANT: This is ONLY called when the user requested a DIFFERENT model.
            It is intentionally *not* run after each generation.
            """
            try:
                for attr in (
                    "model",
                    "vae",
                    "text_encoder",
                    "text_tokenizer",
                    "silence_latent",
                    "reward_model",
                    "mlx_decoder",
                    "mlx_vae",
                ):
                    if hasattr(h, attr):
                        try:
                            setattr(h, attr, None)
                        except Exception:
                            pass
                for attr in (
                    "_base_decoder",
                    "_active_loras",
                    "_lora_adapter_registry",
                    "_lora_active_adapter",
                ):
                    if hasattr(h, attr):
                        try:
                            setattr(h, attr, None)
                        except Exception:
                            pass
            except Exception:
                pass
        def _cleanup_cuda_cache() -> None:
            try:
                import gc
                import torch
                gc.collect()
                if torch.cuda.is_available():
                    try:
                        torch.cuda.synchronize()
                    except Exception:
                        pass
                    torch.cuda.empty_cache()
                    try:
                        torch.cuda.ipc_collect()
                    except Exception:
                        pass
                try:
                    import torch._dynamo
                    torch._dynamo.reset()
                except Exception:
                    pass
                try:
                    import torch._inductor.codecache
                    torch._inductor.codecache.clear_cache()
                except Exception:
                    pass
            except Exception:
                pass
        old = getattr(app.state, "dit_handler", None)
        logger.info(f"[aceflow] Switching model: {cur} -> {want}")
        if old is not None:
            _dispose_handler(old)
            _cleanup_cuda_cache()
            try:
                del old
            except Exception:
                pass
        newh = AceStepHandler()
        status, ok = newh.initialize_service(
            project_root=project_root,
            config_path=want,
            device=device,
            use_flash_attention=True,
            compile_model=True,
            offload_to_cpu=False,
            offload_dit_to_cpu=False,
            quantization=None,
            use_mlx_dit=False,
        )
        if not ok or newh.model is None:
            logger.error(status)
            rollback_to = cur
            logger.warning(f"[aceflow] Model switch failed; attempting rollback to {rollback_to}...")
            try:
                rh = AceStepHandler()
                rstatus, rok = rh.initialize_service(
                    project_root=project_root,
                    config_path=rollback_to,
                    device=device,
                    use_flash_attention=True,
                    compile_model=True,
                    offload_to_cpu=False,
                    offload_dit_to_cpu=False,
                    quantization=None,
                    use_mlx_dit=False,
                )
                if rok and rh.model is not None:
                    app.state.dit_handler = rh
                    app.state._active_model = rollback_to
                    return rh
            except Exception:
                pass
            raise RuntimeError(f"Model init failed: {status}")
        app.state.dit_handler = newh
        app.state._active_model = want
        _cleanup_cuda_cache()
        return newh

    @app.on_event("startup")

    def _startup():

        logger.info("[aceflow] Initializing DiT model…")
        status, ok = dit_handler.initialize_service(
            project_root=project_root,
            config_path=app.state._active_model,
            device=device,
            use_flash_attention=True,
            compile_model=True,
            offload_to_cpu=False,
            offload_dit_to_cpu=False,
            quantization=None,
            use_mlx_dit=False,
        )
        if not ok or dit_handler.model is None:
            logger.error(status)
            raise RuntimeError(f"Model init failed: {status}")
        logger.info(status)
        app.state.dit_handler = dit_handler
        app.state.llm_handler = llm_handler
        app.state.project_root = project_root
        app.state.results_root = results_root
        app.state.max_duration = max_duration
        app.state.queue = InProcessJobQueue(worker_fn=_run_job, outputs_root=results_root)
        logger.info(f"[aceflow] Queue online. outputs={results_root}")
        lm_model_path = os.environ.get("ACESTEP_REMOTE_LM_MODEL_PATH", "acestep-5Hz-lm-4B").strip() or "acestep-5Hz-lm-4B"
        lm_backend = os.environ.get("ACESTEP_REMOTE_LM_BACKEND", "vllm").strip().lower() or "vllm"
        if lm_backend not in {"vllm", "pt", "mlx"}:
            lm_backend = "vllm"
        lm_device = os.environ.get("ACESTEP_REMOTE_LM_DEVICE", device)
        lm_offload = os.environ.get("ACESTEP_REMOTE_LM_OFFLOAD_TO_CPU", "").strip().lower() in {"1", "true", "yes", "y", "on"}
        try:
            logger.info(f"[aceflow] Initializing 5Hz LM… ({lm_model_path}, backend={lm_backend})")
            llm_status, llm_ok = llm_handler.initialize(
                checkpoint_dir=os.path.join(project_root, "checkpoints"),
                lm_model_path=lm_model_path,
                backend=lm_backend,
                device=lm_device,
                offload_to_cpu=lm_offload,
                dtype=None,
            )
            if llm_ok:
                logger.info(f"[aceflow] 5Hz LM ready: {lm_model_path}")
                app.state._llm_ready = True
            else:
                logger.warning(f"[aceflow] 5Hz LM init failed: {llm_status}")
                app.state._llm_ready = False
        except Exception as exc:
            logger.warning(f"[aceflow] 5Hz LM init exception: {exc}")
            app.state._llm_ready = False

    @app.on_event("shutdown")

    def _shutdown():

        q: Optional[InProcessJobQueue] = getattr(app.state, "queue", None)
        if q:
            q.stop()

    def _run_job(job_id: str, req: dict) -> dict:

        """Executes a single generation request."""
        save_dir = os.path.join(results_root, job_id).replace("\\", "/")
        os.makedirs(save_dir, exist_ok=True)
        meta_path = os.path.join(save_dir, 'metadata.json').replace('\\', '/')
        dt = 0.0
        caption = (req.get('caption') or '').strip()
        lyrics = (req.get('lyrics') or '').strip()
        instrumental = bool(req.get('instrumental', False))
        lora_id = (req.get('lora_id') or '').strip()
        lora_trigger = (req.get('lora_trigger') or req.get('lora_tag') or '').strip()
        lora_weight = req.get('lora_weight', 0.5)
        try:
            lora_weight = float(lora_weight)
        except Exception:
            lora_weight = 0.5
        lora_path = ''
        lora_loaded_for_job = False
        try:
                duration_auto = bool(req.get("duration_auto", False))
                bpm_auto = bool(req.get("bpm_auto", False))
                key_auto = bool(req.get("key_auto", False))
                timesig_auto = bool(req.get("timesig_auto", False))
                language_auto = bool(req.get("language_auto", False))
                requested_model = _normalize_model_choice(req.get("model"))
                try:
                    dit_handler = _ensure_model_loaded(requested_model)
                except Exception as e:
                    logger.warning(f"[aceflow] model load failed ({requested_model}): {e}")
                    dit_handler = app.state.dit_handler
                if duration_auto:
                    duration = -1.0
                else:
                    duration = float(req.get("duration", max_duration))
                    if duration <= 0:
                        duration = float(max_duration)
                    duration = max(10.0, min(duration, float(max_duration)))
                caption = (req.get("caption") or "").strip()
                lyrics = (req.get("lyrics") or "").strip()
                original_caption = caption
                original_lyrics = lyrics
                instrumental = bool(req.get("instrumental", False))
                lora_id = (req.get("lora_id") or "").strip()
                lora_trigger = (req.get("lora_trigger") or req.get("lora_tag") or "").strip()
                lora_weight = req.get("lora_weight", 0.5)
                try:
                    lora_weight = float(lora_weight)
                except Exception:
                    lora_weight = 0.5
                if not (lora_weight == lora_weight):
                    lora_weight = 0.5
                lora_weight = max(0.0, min(lora_weight, 1.0))
                try:
                    logger.info(
                        f"[LoRA] requested id='{lora_id or ''}' trigger='{lora_trigger or ''}' weight={lora_weight:.2f}"
                    )
                except Exception:
                    pass
                if lora_id and lora_trigger:
                    try:
                        known_tags = {
                            str((it.get("trigger", it.get("tag", "")) ) or "").strip()
                            for it in (getattr(app.state, "_lora_catalog", []) or [])
                            if isinstance(it, dict)
                        }
                        known_tags.discard("")
                    except Exception:
                        known_tags = set()
                    cap_trim = str(caption or "").lstrip()
                    try:
                        import re
                        m = re.match(r"^([a-zA-Z0-9_\-]+)\s*,\s*(.*)$", cap_trim)
                        if m and (m.group(1) in known_tags):
                            cap_trim = str(m.group(2) or "").strip()
                    except Exception:
                        pass
                    prefix = f"{lora_trigger},"
                    if not cap_trim.lower().startswith(prefix.lower()):
                        caption = f"{lora_trigger}, {cap_trim}" if cap_trim else f"{lora_trigger}"
                    else:
                        caption = cap_trim
                    try:
                        logger.info(f"[LoRA] Caption prefixed (first 80 chars): {caption[:80]!r}")
                    except Exception:
                        pass
                chord_key = str(req.get('chord_key') or '').strip()
                chord_scale = str(req.get('chord_scale') or 'major').strip().lower() or 'major'
                chord_roman = str(req.get('chord_roman') or '').strip()
                chord_section_map = str(req.get('chord_section_map') or '').strip()
                chord_family = str(req.get('chord_family') or '').strip()
                caption, lyrics, keyscale_from_chords, resolved_chords = _inject_chord_server_hints(caption, lyrics, req)
                seed = req.get("seed", -1)
                try:
                    seed = int(seed)
                except Exception:
                    seed = -1
                batch_size = req.get("batch_size", 1)
                try:
                    batch_size = int(batch_size)
                except Exception:
                    batch_size = 1
                batch_size = max(1, min(batch_size, 4))
                inference_steps = req.get("inference_steps", None)
                try:
                    inference_steps = (
                        int(inference_steps)
                        if inference_steps is not None and str(inference_steps) != ""
                        else None
                    )
                except Exception:
                    inference_steps = None
                model_name_for_limits = req.get("model") or req.get("model_used") or ""
                config_name = str(model_name_for_limits) if model_name_for_limits is not None else ""
                is_sft = _is_sft_model(config_name)
                is_turbo = _is_turbo_model(config_name)
                if inference_steps is None:
                    inference_steps = 8 if is_turbo else (50 if is_sft else 32)
                if inference_steps is not None:
                    max_steps = 20 if is_turbo else 200
                    inference_steps = max(1, min(inference_steps, max_steps))
                infer_method = str(req.get("infer_method") or "ode").strip().lower()
                if infer_method not in {"ode", "sde"}:
                    infer_method = "ode"
                timesteps_raw = req.get("timesteps", None)
                parsed_timesteps = _parse_timesteps_input(timesteps_raw)
                repainting_start = req.get("repainting_start", 0.0)
                repainting_end = req.get("repainting_end", -1.0)
                try:
                    repainting_start = float(repainting_start) if repainting_start is not None and str(repainting_start) != "" else 0.0
                except Exception:
                    repainting_start = 0.0
                try:
                    repainting_end = float(repainting_end) if repainting_end is not None and str(repainting_end) != "" else -1.0
                except Exception:
                    repainting_end = -1.0
                repainting_start = max(0.0, min(repainting_start, float(max_duration)))
                repainting_end = max(-1.0, min(repainting_end, float(max_duration)))
                guidance_scale = req.get("guidance_scale", None)
                try:
                    guidance_scale = (
                        float(guidance_scale)
                        if guidance_scale is not None and str(guidance_scale) != ""
                        else None
                    )
                except Exception:
                    guidance_scale = None
                if guidance_scale is not None:
                    guidance_scale = max(1.0, min(guidance_scale, 15.0))
                shift = req.get("shift", None)
                try:
                    shift = float(shift) if shift is not None and str(shift) != "" else None
                except Exception:
                    shift = None
                if shift is not None:
                    shift = max(1.0, min(shift, 5.0))
                use_adg = bool(req.get("use_adg", False))
                cfg_interval_start = req.get("cfg_interval_start", None)
                cfg_interval_end = req.get("cfg_interval_end", None)
                try:
                    cfg_interval_start = (
                        float(cfg_interval_start)
                        if cfg_interval_start is not None and str(cfg_interval_start) != ""
                        else None
                    )
                except Exception:
                    cfg_interval_start = None
                try:
                    cfg_interval_end = (
                        float(cfg_interval_end)
                        if cfg_interval_end is not None and str(cfg_interval_end) != ""
                        else None
                    )
                except Exception:
                    cfg_interval_end = None
                if cfg_interval_start is not None:
                    cfg_interval_start = max(0.0, min(cfg_interval_start, 1.0))
                if cfg_interval_end is not None:
                    cfg_interval_end = max(0.0, min(cfg_interval_end, 1.0))
                enable_normalization = bool(req.get("enable_normalization", True))
                normalization_db = req.get("normalization_db", None)
                try:
                    normalization_db = (
                        float(normalization_db)
                        if normalization_db is not None and str(normalization_db) != ""
                        else None
                    )
                except Exception:
                    normalization_db = None
                if normalization_db is not None:
                    normalization_db = max(-10.0, min(normalization_db, 0.0))
                score_scale = req.get("score_scale", 0.5)
                try:
                    score_scale = float(score_scale)
                except Exception:
                    score_scale = 0.5
                score_scale = max(0.01, min(score_scale, 1.0))
                auto_score = bool(req.get("auto_score", False))
                latent_shift = req.get("latent_shift", None)
                latent_rescale = req.get("latent_rescale", None)
                try:
                    latent_shift = (
                        float(latent_shift)
                        if latent_shift is not None and str(latent_shift) != ""
                        else None
                    )
                except Exception:
                    latent_shift = None
                try:
                    latent_rescale = (
                        float(latent_rescale)
                        if latent_rescale is not None and str(latent_rescale) != ""
                        else None
                    )
                except Exception:
                    latent_rescale = None
                if latent_shift is not None:
                    latent_shift = max(-0.2, min(latent_shift, 0.2))
                if latent_rescale is not None:
                    latent_rescale = max(0.5, min(latent_rescale, 1.5))
                bpm = req.get("bpm", None)
                try:
                    bpm = float(bpm) if bpm is not None and str(bpm) != "" else None
                except Exception:
                    bpm = None
                if bpm is not None:
                    bpm = max(30.0, min(bpm, 300.0))
                if bpm_auto:
                    bpm = None
                keyscale = keyscale_from_chords or (req.get("keyscale") or "").strip()
                if key_auto:
                    keyscale = ""
                timesignature = (req.get("timesignature") or "").strip()
                if timesignature not in {"", "2/4", "3/4", "4/4", "6/8"}:
                    timesignature = ""
                if timesig_auto:
                    timesignature = ""
                vocal_language = (req.get("vocal_language") or "unknown").strip()
                if vocal_language not in set(VALID_LANGUAGES):
                    vocal_language = "unknown"
                if language_auto:
                    vocal_language = "unknown"
                if instrumental:
                    lyrics = "[Instrumental]"
                    vocal_language = "unknown"
                try:
                    logger.info(
                        "[worker] metas duration=%r duration_auto=%r bpm=%r bpm_auto=%r keyscale=%r key_auto=%r timesignature=%r timesig_auto=%r vocal_language=%r language_auto=%r"
                        % (duration, duration_auto, bpm, bpm_auto, keyscale, key_auto, timesignature, timesig_auto, vocal_language, language_auto)
                    )
                except Exception:
                    pass
                thinking = bool(req.get("thinking", True))
                if "use_lm" in req:
                    try:
                        thinking = bool(req.get("use_lm"))
                    except Exception:
                        pass
                lm_temperature = req.get("lm_temperature", 0.85)
                lm_cfg_scale = req.get("lm_cfg_scale", 2.0)
                lm_top_k = req.get("lm_top_k", 0)
                lm_top_p = req.get("lm_top_p", 0.9)
                lm_negative_prompt = req.get("lm_negative_prompt", "NO USER INPUT")
                use_constrained_decoding = req.get("use_constrained_decoding", True)
                try:
                    lm_temperature = float(lm_temperature)
                except Exception:
                    lm_temperature = 0.85
                lm_temperature = max(0.0, min(lm_temperature, 2.0))
                try:
                    lm_cfg_scale = float(lm_cfg_scale)
                except Exception:
                    lm_cfg_scale = 2.0
                lm_cfg_scale = max(1.0, min(lm_cfg_scale, 3.0))
                try:
                    lm_top_k = int(float(lm_top_k))
                except Exception:
                    lm_top_k = 0
                lm_top_k = max(0, min(lm_top_k, 200))
                try:
                    lm_top_p = float(lm_top_p)
                except Exception:
                    lm_top_p = 0.9
                lm_top_p = max(0.0, min(lm_top_p, 1.0))
                try:
                    lm_negative_prompt = str(lm_negative_prompt or "NO USER INPUT")
                except Exception:
                    lm_negative_prompt = "NO USER INPUT"
                lm_negative_prompt = lm_negative_prompt.strip() or "NO USER INPUT"
                use_constrained_decoding = bool(use_constrained_decoding)
                use_cot_metas = bool(req.get("use_cot_metas", thinking))
                use_cot_caption = bool(req.get("use_cot_caption", thinking))
                use_cot_language = bool(req.get("use_cot_language", thinking))
                parallel_thinking = bool(req.get("parallel_thinking", False))
                constrained_decoding_debug = bool(req.get("constrained_decoding_debug", False))
                if not thinking:
                    use_cot_metas = False
                    use_cot_caption = False
                    use_cot_language = False
                    parallel_thinking = False
                    constrained_decoding_debug = False
                audio_format = (req.get("audio_format") or "flac").strip().lower()
                if audio_format not in ("mp3", "wav", "flac", "wav32", "opus", "aac"):
                    audio_format = "flac"
                generation_mode = str(req.get("generation_mode") or "").strip() or "Custom"
                if generation_mode not in {"Simple", "Custom", "Cover", "Remix"}:
                    generation_mode = "Custom"
                task_type = str(req.get("task_type") or "text2music").strip() or "text2music"
                if task_type not in {"text2music", "cover", "repaint"}:
                    task_type = "text2music"
                reference_audio_abs = None
                src_audio_abs = None
                reference_audio_rel = ""
                src_audio_rel = ""
                if task_type == "cover":
                    reference_audio_rel = str(req.get("reference_audio") or "").strip()
                    if reference_audio_rel:
                        reference_audio_abs = _resolve_uploaded_path(reference_audio_rel)
                    src_audio_rel = str(req.get("src_audio") or "").strip()
                    if src_audio_rel:
                        src_audio_abs = _resolve_uploaded_path(src_audio_rel)
                if task_type == "repaint":
                    src_audio_rel = str(req.get("src_audio") or "").strip()
                    if src_audio_rel:
                        src_audio_abs = _resolve_uploaded_path(src_audio_rel)
                try:
                    audio_cover_strength = float(req.get("audio_cover_strength", 0.0))
                except Exception:
                    audio_cover_strength = 0.0
                audio_cover_strength = max(0.0, min(audio_cover_strength, 1.0))
                try:
                    cover_noise_strength = float(req.get("cover_noise_strength", 0.0))
                except Exception:
                    cover_noise_strength = 0.0
                cover_noise_strength = max(0.0, min(cover_noise_strength, 1.0))
                params = GenerationParams(
                    task_type=task_type,
                    reference_audio=reference_audio_abs,
                    src_audio=src_audio_abs,
                    caption=caption,
                    lyrics=lyrics,
                    instrumental=instrumental,
                    duration=duration,
                    seed=seed,
                    bpm=bpm,
                    keyscale=keyscale,
                    timesignature=timesignature,
                    vocal_language=vocal_language,
                    enable_normalization=enable_normalization,
                    normalization_db=normalization_db,
                    latent_shift=latent_shift,
                    latent_rescale=latent_rescale,
                    inference_steps=inference_steps,
                    guidance_scale=guidance_scale,
                    use_adg=use_adg,
                    cfg_interval_start=cfg_interval_start,
                    cfg_interval_end=cfg_interval_end,
                    shift=shift,
                    infer_method=infer_method,
                    timesteps=parsed_timesteps,
                    repainting_start=repainting_start,
                    repainting_end=repainting_end,
                    audio_cover_strength=audio_cover_strength,
                    cover_noise_strength=cover_noise_strength,
                    thinking=thinking,
                    lm_temperature=lm_temperature,
                    lm_cfg_scale=lm_cfg_scale,
                    lm_top_k=lm_top_k,
                    lm_top_p=lm_top_p,
                    lm_negative_prompt=lm_negative_prompt,
                    use_constrained_decoding=use_constrained_decoding,
                    use_cot_metas=use_cot_metas,
                    use_cot_caption=use_cot_caption,
                    use_cot_language=use_cot_language,
                )
                config = GenerationConfig(
                    batch_size=batch_size,
                    use_random_seed=(seed < 0),
                    seeds=([int(seed)] if (isinstance(seed, int) and seed >= 0) else None),
                    allow_lm_batch=parallel_thinking,
                    constrained_decoding_debug=constrained_decoding_debug,
                    audio_format=audio_format,
                )
                lora_loaded_for_job = False
                lora_path = ""
                if lora_id:
                    if ('..' in lora_id) or ('/' in lora_id) or ('\\' in lora_id):
                        raise RuntimeError('LoRA id non valido (path).')
                    lora_root = _resolve_lora_root(project_root)
                    lora_path = os.path.join(lora_root, lora_id)
                    try:
                        exists = bool(os.path.exists(lora_path))
                    except Exception:
                        exists = False
                    logger.info(f"[LoRA] requested id='{lora_id}' weight={lora_weight:.2f}")
                    logger.info(f"[LoRA] resolved path={lora_path} exists={exists}")
                    if not exists:
                        logger.error("[LoRA] load FAIL (path missing)")
                        raise RuntimeError(f"LoRA non trovato: {lora_id} (atteso: {lora_path})")
                    try:
                        msg = dit_handler.load_lora(lora_path)
                        if not str(msg).startswith("✅"):
                            logger.error(f"[LoRA] load FAIL ({msg})")
                            raise RuntimeError(str(msg))
                        logger.info("[LoRA] load OK")
                    except Exception:
                        logger.exception("[LoRA] load FAIL (exception)")
                        raise
                    try:
                        dit_handler.set_use_lora(True)
                    except Exception:
                        pass
                    try:
                        scale_msg = dit_handler.set_lora_scale(lora_id, lora_weight)
                        if isinstance(scale_msg, str) and scale_msg.startswith("❌"):
                            scale_msg = dit_handler.set_lora_scale(lora_weight)
                        if isinstance(scale_msg, str) and not scale_msg.startswith("✅"):
                            logger.warning(f"[LoRA] set_lora_scale warning: {scale_msg}")
                    except Exception as e:
                        logger.warning(f"[LoRA] set_lora_scale exception (continuo comunque): {e}")
                    lora_loaded_for_job = True
                _seed_list = getattr(config, "seeds", None)
                _audio_codes = str(req.get('audio_codes') or '')
                _audio_codes_trim = _audio_codes.strip()
                _audio_cover_strength = req.get('audio_cover_strength', None)
                _cover_noise_strength = req.get('cover_noise_strength', None)
                _reference_only = bool(reference_audio_abs and (not src_audio_abs) and (not _audio_codes_trim))
                logger.info(
                    f"[job {job_id}] summary mode={generation_mode} task_type={task_type} seed={seed} "
                    f"use_random_seed={bool(getattr(config,'use_random_seed',False))} reference_only={_reference_only} "
                    f"reference_present={bool(reference_audio_abs)} src_present={bool(src_audio_abs)} "
                    f"audio_codes_present={bool(_audio_codes_trim)}"
                )
                logger.debug(
                    f"[job {job_id}] mode={generation_mode} task_type={task_type} seed={seed} "
                    f"use_random_seed={bool(getattr(config,'use_random_seed',False))} seeds={_seed_list}"
                )
                logger.debug(f"[job {job_id}] conditioning mode={str(req.get('chord_debug_mode') or req.get('generation_mode') or '')!r}")
                logger.debug(f"[job {job_id}] conditioning reference_present={bool(reference_audio_abs)} reference_audio_raw={reference_audio_abs!r}")
                logger.debug(f"[job {job_id}] conditioning src_present={bool(src_audio_abs)} src_audio_raw={src_audio_abs!r}")
                logger.debug(f"[job {job_id}] conditioning audio_codes_present={bool(_audio_codes_trim)} audio_codes_len={len(_audio_codes_trim)}")
                logger.debug(f"[job {job_id}] conditioning audio_cover_strength={_audio_cover_strength!r} cover_noise_strength={_cover_noise_strength!r}")
                logger.debug(f"[job {job_id}] conditioning reference_only={_reference_only}")
                _conditioning_route, _conditioning_source = _compute_conditioning_route(generation_mode, reference_audio_rel, src_audio_rel, _audio_codes_trim)
                logger.info(f"[job {job_id}] conditioning_route route={_conditioning_route!r} source={_conditioning_source!r} generation_mode={generation_mode!r} task_type={task_type!r}")
                logger.debug(f"[job {job_id}] chord_debug reference_only_raw={req.get('chord_debug_reference_only', False)!r}")
                logger.debug(f"[job {job_id}] chord_debug bpm={req.get('chord_debug_reference_bpm', None)!r} target_duration={req.get('chord_debug_reference_target_duration', None)!r}")
                logger.debug(f"[job {job_id}] chord_debug sequence={str(req.get('chord_debug_reference_sequence') or '')[:1200]!r}")
                logger.debug(f"[job {job_id}] chord_debug section_plan={str(req.get('chord_debug_section_plan') or '')[:1200]!r}")
                t0 = time.time()
                try:
                    result = generate_music(
                        dit_handler=dit_handler,
                        llm_handler=(app.state.llm_handler if getattr(app.state, "_llm_ready", False) else None),
                        params=params,
                        config=config,
                        save_dir=save_dir,
                    )
                    dt = time.time() - t0
                finally:
                    if lora_loaded_for_job:
                        try:
                            try:
                                import torch
                                import gc
                                if torch.cuda.is_available():
                                    alloc0 = torch.cuda.memory_allocated() / (1024**3)
                                    res0 = torch.cuda.memory_reserved() / (1024**3)
                                    logger.info(f"[LoRA] VRAM before unload: allocated={alloc0:.2f}GB reserved={res0:.2f}GB")
                            except Exception:
                                pass
                            dit_handler.unload_lora()
                            try:
                                dit_handler.set_use_lora(False)
                            except Exception:
                                pass
                            try:
                                import torch
                                import gc
                                if torch.cuda.is_available():
                                    gc.collect()
                                    torch.cuda.empty_cache()
                                    try:
                                        torch.cuda.ipc_collect()
                                    except Exception:
                                        pass
                                    alloc1 = torch.cuda.memory_allocated() / (1024**3)
                                    res1 = torch.cuda.memory_reserved() / (1024**3)
                                    logger.info(f"[LoRA] VRAM after unload: allocated={alloc1:.2f}GB reserved={res1:.2f}GB (delta_alloc={alloc1-alloc0:+.2f}GB delta_res={res1-res0:+.2f}GB)")
                            except Exception:
                                pass
                            logger.info("[LoRA] unload OK")
                        except Exception as e:
                            logger.exception("[LoRA] unload FAIL")
                if not result.success:
                    raise RuntimeError(result.error or result.status_message or "Errore sconosciuto")
                audio_paths = []
                if result.audios:
                    for a in result.audios:
                        p = a.get("path", "")
                        if p:
                            audio_paths.append(p)
                score_entries = []
                if auto_score:
                    try:
                        from acestep.core.scoring.lm_score import calculate_pmi_score_per_condition
                        llm_handler = app.state.llm_handler if getattr(app.state, "_llm_ready", False) else None
                        lm_meta = getattr(result, "extra_outputs", {}) or {}
                        lm_metadata = lm_meta.get("lm_metadata") if isinstance(lm_meta, dict) else None
                        for a in (result.audios or []):
                            a_params = a.get("params") or {}
                            audio_codes_str = str(a_params.get("audio_codes") or "").strip()
                            if not audio_codes_str or not llm_handler or not getattr(llm_handler, "llm_initialized", False):
                                score_entries.append({
                                    "quality_score": None,
                                    "quality_score_per_condition": {},
                                    "quality_score_status": "skipped" if not audio_codes_str else "lm_not_ready",
                                })
                                continue
                            metadata = {}
                            if isinstance(lm_metadata, dict):
                                metadata.update(lm_metadata)
                            if caption and "caption" not in metadata:
                                metadata["caption"] = caption
                            if bpm is not None and "bpm" not in metadata:
                                try:
                                    metadata["bpm"] = int(bpm)
                                except Exception:
                                    pass
                            if duration and duration > 0 and "duration" not in metadata:
                                try:
                                    metadata["duration"] = int(duration)
                                except Exception:
                                    pass
                            if keyscale and "keyscale" not in metadata:
                                metadata["keyscale"] = str(keyscale)
                            if vocal_language and "language" not in metadata:
                                metadata["language"] = str(vocal_language)
                            if timesignature and "timesignature" not in metadata:
                                metadata["timesignature"] = str(timesignature)
                            scores_per_condition, global_score, status = calculate_pmi_score_per_condition(
                                llm_handler=llm_handler,
                                audio_codes=audio_codes_str,
                                caption=caption or "",
                                lyrics=lyrics or "",
                                metadata=(metadata if metadata else None),
                                temperature=1.0,
                                topk=10,
                                score_scale=float(score_scale),
                            )
                            score_entries.append({
                                "quality_score": float(global_score) if global_score is not None else None,
                                "quality_score_per_condition": scores_per_condition or {},
                                "quality_score_status": status,
                            })
                    except Exception as _score_exc:
                        logger.warning(f"[score] auto_score failed: {_score_exc}")
                meta_path = os.path.join(save_dir, "metadata.json").replace("\\", "/")
                result_block = {
                    "success": bool(getattr(result, "success", True)),
                    "error": getattr(result, "error", None),
                    "status_message": (
                        (f"[LM] thinking={bool(thinking)} temp={lm_temperature:.2f} cfg={lm_cfg_scale:.2f} top_k={int(lm_top_k)} top_p={lm_top_p:.2f} constrained={bool(use_constrained_decoding)}\n")
                        + str(getattr(result, "status_message", ""))
                    ),
                    "audios": [
                        {
                            "path": p,
                            "format": audio_format,
                            **(
                                (score_entries[i] if (score_entries and i < len(score_entries)) else {})
                            ),
                        }
                        for i, p in enumerate(audio_paths or [])
                    ],
                    "extra_outputs": _json_safe(getattr(result, "extra_outputs", {})),
                }
                job_log_paths = _finalize_job_cli_capture(job_id, audio_paths)
                payload = {
                    "job_id": job_id,
                    "created_at": int(time.time()),
                    "seconds": dt,
                    "request": {
                        "model": requested_model,
                        "model_used": str(getattr(app.state, "_active_model", requested_model) or requested_model),
                        "caption": original_caption,
                        "lyrics": original_lyrics,
                        "instrumental": instrumental,
                        "duration": duration,
                        "duration_auto": duration_auto,
                        "seed": seed,
                        "generation_mode": generation_mode,
                        "task_type": task_type,
                        "reference_audio": reference_audio_rel,
                        "src_audio": src_audio_rel,
                        "lora_id": lora_id,
                        "lora_trigger": lora_trigger,
                        "lora_weight": lora_weight,
                        "lora_path": lora_path,
                        "lora_loaded": bool(lora_loaded_for_job),
                        "batch_size": batch_size,
                        "audio_format": audio_format,
                        "inference_steps": inference_steps,
                        "infer_method": infer_method,
                        "timesteps": timesteps_raw if isinstance(timesteps_raw, str) else (parsed_timesteps if parsed_timesteps is not None else ""),
                        "repainting_start": repainting_start,
                        "repainting_end": repainting_end,
                        "guidance_scale": guidance_scale,
                        "shift": shift,
                        "use_adg": use_adg,
                        "cfg_interval_start": cfg_interval_start,
                        "cfg_interval_end": cfg_interval_end,
                        "enable_normalization": enable_normalization,
                        "normalization_db": normalization_db,
                        "score_scale": score_scale,
                        "auto_score": auto_score,
                        "latent_shift": latent_shift,
                        "latent_rescale": latent_rescale,
                        "bpm": bpm,
                        "bpm_auto": bpm_auto,
                        "keyscale": keyscale,
                        "key_auto": key_auto,
                        "timesignature": timesignature,
                        "timesig_auto": timesig_auto,
                        "vocal_language": vocal_language,
                        "language_auto": language_auto,
                        "audio_codes": req.get("audio_codes", ""),
                        "audio_cover_strength": req.get("audio_cover_strength", None),
                        "cover_noise_strength": req.get("cover_noise_strength", None),
                        "chord_debug_mode": req.get("chord_debug_mode", ""),
                        "chord_debug_reference_only": bool(req.get("chord_debug_reference_only", False)),
                        "chord_debug_reference_sequence": req.get("chord_debug_reference_sequence", ""),
                        "chord_debug_section_plan": req.get("chord_debug_section_plan", ""),
                        "chord_debug_reference_bpm": req.get("chord_debug_reference_bpm", None),
                        "chord_debug_reference_target_duration": req.get("chord_debug_reference_target_duration", None),
                        "chord_key": req.get("chord_key", ""),
                        "chord_scale": req.get("chord_scale", "major"),
                        "chord_roman": req.get("chord_roman", ""),
                        "chord_section_map": req.get("chord_section_map", ""),
                        "chord_apply_keyscale": bool(req.get("chord_apply_keyscale", False)),
                        "chord_apply_bpm": bool(req.get("chord_apply_bpm", False)),
                        "chord_apply_lyrics": bool(req.get("chord_apply_lyrics", False)),
                        "chord_family": req.get("chord_family", ""),
                        "chord_resolved": resolved_chords if 'resolved_chords' in locals() else [],
                        "thinking": thinking,
                        "lm_temperature": lm_temperature,
                        "lm_cfg_scale": lm_cfg_scale,
                        "lm_top_k": lm_top_k,
                        "lm_top_p": lm_top_p,
                        "lm_negative_prompt": lm_negative_prompt,
                        "use_constrained_decoding": use_constrained_decoding,
                        "use_cot_metas": use_cot_metas,
                        "use_cot_caption": use_cot_caption,
                        "use_cot_language": use_cot_language,
                        "parallel_thinking": parallel_thinking,
                        "constrained_decoding_debug": constrained_decoding_debug,
                    },
                    "result": result_block,
                }
                _write_json(meta_path, payload)
                try:
                    with app.state._counter_lock:
                        app.state.songs_generated = int(getattr(app.state, "songs_generated", 0)) + 1
                        _save_counter(app.state.songs_generated)
                except Exception:
                    pass
                return {
                    "audio_paths": audio_paths,
                    "json_path": meta_path,
                    "audio_count": len(audio_paths) if isinstance(audio_paths, list) else 0,
                    "job_log_paths": job_log_paths,
                    "save_dir": save_dir,
                    "seconds": dt,
                }
        except Exception as e:
            try:
                payload = {
                    'job_id': job_id,
                    'created_at': int(time.time()),
                    'seconds': float(dt or 0.0),
                    'request': {
                        'model': _normalize_model_choice(req.get('model')),
                        'model_used': str(getattr(app.state, '_active_model', _normalize_model_choice(req.get('model'))) or _normalize_model_choice(req.get('model'))),
                        'caption': caption,
                        'lyrics': lyrics,
                        'instrumental': instrumental,
                        'duration': req.get('duration', None),
                        'seed': req.get('seed', None),
                        'generation_mode': req.get('generation_mode', None),
                        'task_type': req.get('task_type', None),
                        'reference_audio': req.get('reference_audio', None),
                        'src_audio': req.get('src_audio', None),
                        'lora_id': lora_id,
                        'lora_weight': lora_weight,
                        'lora_path': lora_path,
                        'lora_loaded': bool(lora_loaded_for_job),
                    },
                    'result': {
                        'success': False,
                        'error': str(e),
                        'status_message': str(e),
                        'audios': [],
                        'extra_outputs': {},
                    },
                }
                _write_json(meta_path, payload)
            except Exception:
                pass
            try:
                _finalize_job_cli_capture(job_id, [])
            except Exception:
                pass
            raise

    def _get_client_ip(request) -> str:

        """Best-effort client WAN IP, works behind reverse proxies."""
        try:
            xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
            if xff:
                parts = [p.strip() for p in xff.split(",") if p.strip()]
                if parts:
                    return parts[0]
        except Exception:
            pass
        try:
            xri = request.headers.get("x-real-ip") or request.headers.get("X-Real-IP")
            if xri:
                return str(xri).strip()
        except Exception:
            pass
        try:
            return request.client.host
        except Exception:
            return "unknown"

    @app.get("/favicon.ico")

    def favicon():

        fav_path = os.path.join(static_dir, "favicon.ico")
        if os.path.exists(fav_path):
            return FileResponse(fav_path, media_type="image/x-icon")
        return Response(status_code=204)

    @app.get("/api/client_ip")

    def client_ip(request: Request):

        return {"ip": _get_client_ip(request)}

    @app.get("/api/stats")

    def stats(request: Request):

        with app.state._counter_lock:
            n = int(getattr(app.state, "songs_generated", 0))
        return {"ip": _get_client_ip(request), "songs_generated": n}

    @app.get("/api/system")

    def system_info(request: Request):

        gpu = _get_gpu_info_cached(app)
        if not gpu:
            return {
                "gpu_name": None,
                "vram_used_mb": None,
                "vram_total_mb": None,
                "gpu_temp_c": None,
            }
        return gpu

    @app.get("/api/lora_catalog")

    def lora_catalog():

        return app.state._lora_catalog

    @app.get("/", response_class=HTMLResponse)

    def index():

        index_path = os.path.join(static_dir, "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()

    @app.get("/api/health")

    def health():

        return {
            "status": "ok",
            "max_duration": max_duration,
            "model": str(getattr(app.state, "_active_model", config_path) or config_path),
            "max_batch_size": 4,
            "audio_formats": ["flac","wav","mp3","opus","aac","wav32"],
        }

    @app.get("/api/options")

    def options():

        return {
            "valid_languages": VALID_LANGUAGES,
            "time_signatures": ["", "2/4", "3/4", "4/4", "6/8"],
            "lm_ready": bool(getattr(app.state, "_llm_ready", False)),
            "think_default": True,
            "limits": {
                "max_inference_steps_turbo": 20,
                "max_inference_steps_base": 200,
            },
            "infer_methods": ["ode", "sde"],
            "defaults": {
                "inference_steps": 8,
                "infer_method": "ode",
                "timesteps": "",
                "repainting_start": 0.0,
                "repainting_end": -1.0,
                "guidance_scale": 7.0,
                "shift": 3.0,
                "cfg_interval_start": 0.0,
                "cfg_interval_end": 1.0,
                "latent_shift": 0.0,
                "latent_rescale": 1.0,
                "enable_normalization": True,
                "normalization_db": -1.0,
                "audio_cover_strength": 0.0,
                "cover_noise_strength": 0.0,
            },
        }
    examples_path = os.path.join(os.path.dirname(__file__), "examples.json").replace("\\", "/")
    _examples_cache = None

    def _load_examples():

        nonlocal _examples_cache
        if _examples_cache is not None:
            return _examples_cache
        if not os.path.exists(examples_path):
            _examples_cache = {"examples": []}
            return _examples_cache
        with open(examples_path, "r", encoding="utf-8") as f:
            _examples_cache = json.load(f)
        return _examples_cache

    @app.get("/api/examples/random")

    def random_example():

        data = _load_examples()
        items = data.get("examples", []) if isinstance(data, dict) else []
        if not items:
            return {}
        return random.choice(items)
    _ALLOWED_AUDIO_EXTS = {".wav", ".mp3", ".flac", ".opus", ".aac", ".m4a"}

    def _save_uploaded_audio(file: UploadFile) -> dict:

        """Save an uploaded audio file under results_root/_uploads.
        Returns a dict with:
          path: relative path ("_uploads/<name>") to send back to the client
          filename: original client filename
        """
        orig = (file.filename or "audio").strip()
        orig_name = Path(orig).name
        suffix = (Path(orig_name).suffix or "").lower()
        if suffix and suffix not in _ALLOWED_AUDIO_EXTS:
            raise HTTPException(status_code=400, detail="Formato audio non supportato.")
        if not suffix:
            ct = (file.content_type or "").lower()
            if "wav" in ct:
                suffix = ".wav"
            elif "mpeg" in ct or "mp3" in ct:
                suffix = ".mp3"
            elif "flac" in ct:
                suffix = ".flac"
            elif "opus" in ct:
                suffix = ".opus"
            elif "aac" in ct:
                suffix = ".aac"
            elif "m4a" in ct:
                suffix = ".m4a"
            else:
                suffix = ".wav"
        safe_name = f"{uuid4().hex}{suffix}"
        dst = os.path.join(uploads_dir, safe_name).replace("\\", "/")
        try:
            os.makedirs(uploads_dir, exist_ok=True)
            with open(dst, "wb") as out:
                shutil.copyfileobj(file.file, out)
        except Exception as exc:
            logger.warning("[upload] save failed dst={} err={!r}", dst, exc)
            raise HTTPException(status_code=500, detail="Errore salvataggio upload.")
        return {"path": f"_uploads/{safe_name}", "filename": orig_name}

    def _resolve_uploaded_path(rel_path: str) -> str:

        """Resolve a client-provided relative upload path to an absolute path.
        Security rules:
        - must start with "_uploads/"
        - must not contain path traversal
        - final path must be under uploads_dir
        """
        rp = (rel_path or "").replace("\\", "/").strip()
        if not rp.startswith("_uploads/"):
            raise HTTPException(status_code=400, detail="Percorso upload non valido.")
        if ".." in rp or rp.startswith("/"):
            raise HTTPException(status_code=400, detail="Percorso upload non valido.")
        abs_path = os.path.join(results_root, rp).replace("\\", "/")
        try:
            base = Path(uploads_dir).resolve()
            cand = Path(abs_path).resolve()
            if not cand.is_relative_to(base):
                raise HTTPException(status_code=400, detail="Percorso upload non valido.")
        except AttributeError:
            if not str(Path(abs_path).resolve()).startswith(str(Path(uploads_dir).resolve()) + os.sep):
                raise HTTPException(status_code=400, detail="Percorso upload non valido.")
        if not os.path.exists(abs_path):
            raise HTTPException(status_code=400, detail="File upload non trovato.")
        return abs_path

    @app.post("/api/uploads/audio")

    async def upload_audio(request: Request, file: UploadFile = File(...)):
        _require_token(request)
        if not file:
            raise HTTPException(status_code=400, detail="Nessun file.")
        _ensure_uploads_dir()
        return _save_uploaded_audio(file)

    @app.post("/api/lm/transcribe")

    def transcribe_audio_codes(payload: dict, request: Request):

        _require_token(request)
        codes = str((payload or {}).get("codes") or "").strip()
        if not codes:
            raise HTTPException(status_code=400, detail="Codici audio mancanti.")
        llm_handler = getattr(app.state, "llm_handler", None)
        if llm_handler is None or not getattr(llm_handler, "llm_initialized", False):
            raise HTTPException(status_code=503, detail="LLM non disponibile.")
        try:
            result = understand_music(
                llm_handler=llm_handler,
                audio_codes=codes,
                use_constrained_decoding=True,
                constrained_decoding_debug=False,
            )
        except Exception as exc:
            logger.exception("[lm/transcribe] transcription failed err={!r}", exc)
            raise HTTPException(status_code=500, detail="Errore trascrizione audio codes.")
        if not getattr(result, "success", False):
            detail = getattr(result, "status_message", None) or getattr(result, "error", None) or "Trascrizione non riuscita."
            detail_str = str(detail or "").strip()
            lowered = detail_str.lower()
            if detail_str == "Not Found" or "404" in lowered or "not found" in lowered:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "LM transcription failed because the upstream LLM endpoint returned Not Found. "
                        "Check the LM backend/provider URL or model endpoint configuration."
                    ),
                )
            raise HTTPException(status_code=400, detail=detail_str or "Trascrizione non riuscita.")
        duration = getattr(result, "duration", None)
        max_duration_local = int(getattr(app.state, "max_duration", max_duration) or max_duration)
        try:
            if duration is not None:
                duration = min(int(duration), max_duration_local)
        except Exception:
            pass
        return {
            "status": getattr(result, "status_message", "OK") or "OK",
            "caption": getattr(result, "caption", "") or "",
            "lyrics": getattr(result, "lyrics", "") or "",
            "bpm": getattr(result, "bpm", None),
            "duration": duration,
            "keyscale": getattr(result, "keyscale", "") or "",
            "vocal_language": getattr(result, "language", "") or "unknown",
            "timesignature": getattr(result, "timesignature", "") or "",
        }

    @app.post("/api/chords/render-reference")

    def render_chord_reference(payload: dict, request: Request):

        _require_token(request)
        payload = payload or {}
        raw_chords = payload.get("chords") or []
        if not isinstance(raw_chords, list):
            raise HTTPException(status_code=400, detail="Lista accordi non valida.")
        chords = [str(item or "").strip() for item in raw_chords if str(item or "").strip()]
        if not chords:
            raise HTTPException(status_code=400, detail="Nessun accordo fornito.")
        try:
            bpm = float(payload.get("bpm") or 120.0)
        except Exception:
            bpm = 120.0
        try:
            beats_per_chord = int(payload.get("beats_per_chord") or 4)
        except Exception:
            beats_per_chord = 4
        try:
            target_duration = float(payload.get("target_duration") or 0.0)
        except Exception:
            target_duration = 0.0
        _ensure_uploads_dir()
        safe_name = f"chord_reference_{int(time.time() * 1000)}_{uuid4().hex[:8]}.wav"
        out_abs = os.path.join(uploads_dir, safe_name).replace("\\", "/")
        try:
            meta = render_reference_wav_file(
                chords=chords,
                output_path=out_abs,
                bpm=bpm,
                beats_per_chord=max(1, beats_per_chord),
                target_duration_sec=target_duration if target_duration > 0 else None,
            )
        except Exception as exc:
            logger.exception("[chords/render-reference] render failed err={!r}", exc)
            raise HTTPException(status_code=500, detail="Errore rendering reference WAV.")
        return {
            "path": f"_uploads/{safe_name}",
            "filename": safe_name,
            "meta": meta,
        }

    @app.post("/api/chords/extract-codes")

    def extract_chord_codes(payload: dict, request: Request):

        _require_token(request)
        rel_path = str((payload or {}).get("path") or "").strip()
        if not rel_path:
            raise HTTPException(status_code=400, detail="Percorso audio mancante.")
        audio_abs = _resolve_uploaded_path(rel_path)
        handler = getattr(app.state, "dit_handler", None)
        if handler is None:
            raise HTTPException(status_code=503, detail="Handler DiT non disponibile.")
        try:
            codes = handler.convert_src_audio_to_codes(audio_abs)
        except Exception as exc:
            logger.exception("[chords/extract-codes] conversion failed err={!r}", exc)
            raise HTTPException(status_code=500, detail="Errore estrazione codici audio.")
        codes = str(codes or "").strip()
        if not codes:
            raise HTTPException(status_code=500, detail="Nessun codice audio estratto.")
        return {
            "path": rel_path,
            "codes": codes,
            "code_count": len([tok for tok in codes.split() if tok.strip()]),
        }

    def _compute_conditioning_route(generation_mode: str, reference_audio: str, src_audio: str, audio_codes: str) -> tuple[str, str]:

        gm = str(generation_mode or "Custom").strip() or "Custom"
        ref = str(reference_audio or "").strip()
        src = str(src_audio or "").strip()
        codes = str(audio_codes or "").strip()
        if gm == "Cover":
            if src:
                return "src_audio_wav", "src_audio_wav"
            route = "reference_audio_wav" if ref else "none"
            return route, route
        if gm == "Remix":
            route = "src_audio_wav" if src else "none"
            return route, route
        if codes:
            return "audio_codes", "audio_codes"
        if ref:
            return "reference_audio_wav", "reference_audio_wav"
        return "none", "none"

    def _safe_json_dump(value) -> str:

        try:
            return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        except Exception as exc:
            return json.dumps({"_serialization_error": repr(exc)}, ensure_ascii=False, indent=2, sort_keys=True)

    def _build_formatted_prompt_with_cot_snapshot(req: dict) -> str:

        caption = str(req.get("caption") or "").strip()
        lyrics = str(req.get("lyrics") or "").strip()
        bpm = req.get("bpm", None)
        duration = req.get("duration", None)
        keyscale = str(req.get("keyscale") or "").strip()
        timesignature = str(req.get("timesignature") or "").strip()
        return f"""<|im_start|>system
# Instruction
Generate audio semantic tokens based on the given conditions:

<|im_end|>
<|im_start|>user
# Caption
{caption}

# Lyric
{lyrics}
<|im_end|>
<|im_start|>assistant
<think>
bpm: {bpm}
duration: {duration}
keyscale: {keyscale}
timesignature: {timesignature}
</think>

<|im_end|>"""

    @app.post("/api/jobs")

    def create_job(payload: dict, request: Request):

        _require_token(request)
        job_id = str(uuid4())
        try:
            _start_job_cli_capture(job_id)
        except Exception as exc:
            logger.warning("[job_log] live capture start failed job_id={} err={!r}", job_id, exc)
        try:
            snap = app.state.queue.snapshot_queue()
            active = len(snap.get("queued", []) or []) + (1 if snap.get("running") else 0)
        except Exception:
            active = 0
        cap = int(getattr(app.state, "_queue_active_cap", 30) or 30)
        if cap > 0 and active >= cap:
            raise HTTPException(
                status_code=429,
                detail={"error_code": "queue_full", "cap": cap, "active": active},
            )
        ip = _get_client_ip(request)
        now = time.time()
        min_interval = float(getattr(app.state, "_rate_min_interval_s", 5.0) or 5.0)
        if min_interval > 0:
            with app.state._rate_lock:
                last = float(app.state._last_job_at_by_ip.get(ip, 0.0) or 0.0)
                if (now - last) < min_interval:
                    wait_s = max(0.0, min_interval - (now - last))
                    raise HTTPException(
                        status_code=429,
                        detail={"error_code": "rate_limited", "retry_after_s": round(float(wait_s), 2)},
                    )
                app.state._last_job_at_by_ip[ip] = now
        try:
            rep = cleanup_old_job_dirs(Path(results_root), 3600)
            logger.info(
                "[cleanup] ttl={}s scanned={} deleted={} skipped={} errors={}",
                3600,
                rep.get("scanned", 0),
                rep.get("deleted", 0),
                rep.get("skipped", 0),
                rep.get("errors", 0),
            )
        except Exception as exc:
            logger.warning("[cleanup] exception err={!r}", exc)
        try:
            _ensure_uploads_dir()
            repu = cleanup_old_upload_files(Path(uploads_dir), 3600)
            _ensure_uploads_dir()
            logger.info(
                "[cleanup_uploads] ttl={}s scanned={} deleted={} skipped={} errors={}",
                3600,
                repu.get("scanned", 0),
                repu.get("deleted", 0),
                repu.get("skipped", 0),
                repu.get("errors", 0),
            )
        except Exception as exc:
            logger.warning("[cleanup_uploads] exception err={!r}", exc)
        try:
            _ensure_logs_dir()
            repl = cleanup_old_log_files(Path(logs_dir), 3600)
            _ensure_logs_dir()
            logger.info(
                "[cleanup_logs] ttl={}s scanned={} deleted={} skipped={} errors={}",
                3600,
                repl.get("scanned", 0),
                repl.get("deleted", 0),
                repl.get("skipped", 0),
                repl.get("errors", 0),
            )
        except Exception as exc:
            logger.warning("[cleanup_logs] exception err={!r}", exc)
        q: InProcessJobQueue = app.state.queue
        caption = (payload.get("caption") or "").strip()
        lyrics = (payload.get("lyrics") or "").strip()
        instrumental = bool(payload.get("instrumental", False))
        thinking = bool(payload.get("thinking", True))
        duration_auto = bool(payload.get("duration_auto", False))
        bpm_auto = bool(payload.get("bpm_auto", False))
        key_auto = bool(payload.get("key_auto", False))
        timesig_auto = bool(payload.get("timesig_auto", False))
        language_auto = bool(payload.get("language_auto", False))
        duration = payload.get("duration", max_duration)
        seed = payload.get("seed", -1)
        lora_id = (payload.get("lora_id") or "").strip()
        lora_trigger = (payload.get("lora_trigger") or payload.get("lora_tag") or "").strip()
        lora_weight = payload.get("lora_weight", 0.5)
        try:
            lora_weight = float(lora_weight)
        except Exception:
            lora_weight = 0.5
        lora_weight = max(0.0, min(lora_weight, 1.0))
        _keys = sorted([str(k) for k in payload.keys()]) if isinstance(payload, dict) else []
        _audio_codes = str(payload.get('audio_codes') or '')
        _audio_codes_trim = _audio_codes.strip()
        _reference_audio = str(payload.get('reference_audio') or '').strip()
        _src_audio = str(payload.get('src_audio') or '').strip()
        _reference_only = bool(_reference_audio and (not _src_audio) and (not _audio_codes_trim))
        logger.info(
            "[api/jobs] summary mode={!r} reference_only={} reference_present={} src_present={} audio_codes_present={} lora_id={!r} lora_weight={!r}",
            str(payload.get('generation_mode') or ''),
            _reference_only,
            bool(_reference_audio),
            bool(_src_audio),
            bool(_audio_codes_trim),
            lora_id,
            payload.get('lora_weight', None),
        )
        logger.debug(f"[api/jobs] payload keys={_keys}")
        logger.debug(f"[api/jobs] lora id={lora_id!r} trigger={lora_trigger!r} weight={payload.get('lora_weight', None)!r}")
        logger.debug(f"[api/jobs] conditioning mode={str(payload.get('chord_debug_mode') or payload.get('generation_mode') or '')!r}")
        logger.debug(f"[api/jobs] conditioning reference_audio_present={bool(_reference_audio)} reference_audio_raw={_reference_audio!r}")
        logger.debug(f"[api/jobs] conditioning src_audio_present={bool(_src_audio)} src_audio_raw={_src_audio!r}")
        logger.debug(f"[api/jobs] conditioning audio_codes_present={bool(_audio_codes_trim)} audio_codes_len={len(_audio_codes_trim)}")
        logger.debug(f"[api/jobs] conditioning audio_cover_strength={payload.get('audio_cover_strength', None)!r} cover_noise_strength={payload.get('cover_noise_strength', None)!r}")
        logger.debug(f"[api/jobs] conditioning reference_only={_reference_only}")
        logger.debug(f"[api/jobs] chord_debug reference_only_raw={payload.get('chord_debug_reference_only', False)!r}")
        logger.debug(f"[api/jobs] chord_debug bpm={payload.get('chord_debug_reference_bpm', None)!r} target_duration={payload.get('chord_debug_reference_target_duration', None)!r}")
        logger.debug(f"[api/jobs] chord_debug sequence={str(payload.get('chord_debug_reference_sequence') or '')[:1200]!r}")
        logger.debug(f"[api/jobs] chord_debug section_plan={str(payload.get('chord_debug_section_plan') or '')[:1200]!r}")
        model_choice = _normalize_model_choice(payload.get("model"))
        lora_entry = None
        if lora_id:
            if (".." in lora_id) or ("/" in lora_id) or ("\\" in lora_id):
                raise HTTPException(status_code=400, detail="LoRA non valido.")
            catalog = (getattr(app.state, "_lora_catalog", []) or [])
            by_id = {str(it.get("id", "") or ""): it for it in catalog if isinstance(it, dict)}
            by_id.pop("", None)
            lora_entry = by_id.get(lora_id)
            if not lora_entry:
                logger.warning(f"[LoRA] Rejected unknown id='{lora_id}'. Valid: {sorted(by_id.keys())}")
                raise HTTPException(status_code=400, detail="LoRA non valido.")
            if not lora_trigger:
                try:
                    cat_trigger = str((lora_entry.get("trigger", lora_entry.get("tag", "")) ) or "").strip()
                except Exception:
                    cat_tag = ""
                if cat_trigger:
                    lora_trigger = cat_trigger
                    logger.info("[LoRA] compat: missing lora_trigger -> using catalog trigger")
                else:
                    lora_trigger = lora_id
                    logger.info("[LoRA] compat: missing catalog trigger -> using lora_id as trigger")
            try:
                canonical_trigger = str((lora_entry.get("trigger", lora_entry.get("tag", "")) ) or "").strip()
            except Exception:
                canonical_tag = ""
            if canonical_trigger and lora_trigger != canonical_trigger:
                logger.warning(
                    f"[LoRA] overriding client lora_trigger={lora_trigger!r} with catalog trigger={canonical_trigger!r} for id={lora_id!r}"
                )
                lora_trigger = canonical_trigger
        if not lora_id:
            lora_trigger = ""
        batch_size = payload.get("batch_size", 1)
        audio_format = payload.get("audio_format", "flac")
        inference_steps = payload.get("inference_steps", None)
        infer_method = str(payload.get("infer_method") or "ode").strip().lower()
        timesteps = payload.get("timesteps", None)
        repainting_start = payload.get("repainting_start", None)
        repainting_end = payload.get("repainting_end", None)
        guidance_scale = payload.get("guidance_scale", None)
        shift = payload.get("shift", None)
        use_adg = payload.get("use_adg", False)
        cfg_interval_start = payload.get("cfg_interval_start", None)
        cfg_interval_end = payload.get("cfg_interval_end", None)
        enable_normalization = bool(payload.get("enable_normalization", True))
        normalization_db = payload.get("normalization_db", None)
        score_scale = payload.get("score_scale", 0.5)
        try:
            score_scale = float(score_scale)
        except Exception:
            score_scale = 0.5
        score_scale = max(0.01, min(score_scale, 1.0))
        auto_score = bool(payload.get("auto_score", False))
        latent_shift = payload.get("latent_shift", None)
        latent_rescale = payload.get("latent_rescale", None)
        bpm = payload.get("bpm", None)
        keyscale = payload.get("keyscale", "")
        timesignature = (payload.get("timesignature") or "").strip()
        vocal_language = (payload.get("vocal_language") or "unknown").strip()
        generation_mode = str(payload.get("generation_mode") or "Custom").strip()
        if generation_mode not in {"Simple", "Custom", "Cover", "Remix"}:
            generation_mode = "Custom"
        task_type = "text2music"
        if generation_mode == "Cover":
            task_type = "cover"
        elif generation_mode == "Remix":
            task_type = "cover"
        reference_audio = str(payload.get("reference_audio") or "").strip()
        src_audio = str(payload.get("src_audio") or "").strip()
        audio_codes = str(payload.get("audio_codes") or "").strip()
        if task_type == "cover":
            audio_codes = ""
            payload["audio_codes"] = ""
            if not src_audio:
                raise HTTPException(status_code=400, detail="Per COVER devi caricare un audio sorgente.")
            _resolve_uploaded_path(src_audio)
            if reference_audio:
                _resolve_uploaded_path(reference_audio)
        elif task_type == "repaint":
            if not src_audio:
                raise HTTPException(status_code=400, detail="Per REMIX devi caricare un audio sorgente.")
            _resolve_uploaded_path(src_audio)
        else:
            reference_audio = ""
            payload["reference_audio"] = ""
        _conditioning_route, _conditioning_source = _compute_conditioning_route(generation_mode, reference_audio, src_audio, audio_codes)
        logger.info(f"[api/jobs] conditioning_route route={_conditioning_route!r} source={_conditioning_source!r} generation_mode={generation_mode!r} task_type={task_type!r}")
        if duration_auto:
            duration = -1
        if bpm_auto:
            bpm = None
        if key_auto:
            keyscale = ""
        if timesig_auto:
            timesignature = ""
        if language_auto:
            vocal_language = "unknown"
        if len(caption) > 50000:
            raise HTTPException(status_code=400, detail="Stile troppo lungo (max 50000 caratteri).")
        if len(lyrics) > 20000:
            raise HTTPException(status_code=400, detail="Testo troppo lungo (max 20000 caratteri).")
        try:
            bs = int(batch_size)
        except Exception:
            bs = 1
        if bs < 1 or bs > 4:
            raise HTTPException(status_code=400, detail="Batch size non valido (consentito: 1–4).")
        try:
            d = float(duration)
        except Exception:
            d = float(max_duration)
        if int(d) != -1:
            if d < 10 or d > float(max_duration):
                raise HTTPException(status_code=400, detail=f"Durata non valida (10–{max_duration} secondi).")
        else:
            d = -1
        af = str(audio_format).lower().strip()
        if af not in ("mp3", "wav", "flac", "wav32", "opus", "aac"):
            raise HTTPException(status_code=400, detail="Formato audio non valido.")
        if timesignature not in {"", "2/4", "3/4", "4/4", "6/8"}:
            timesignature = ""
        if vocal_language not in set(VALID_LANGUAGES):
            vocal_language = "unknown"
        if instrumental:
            lyrics = "[Instrumental]"
            vocal_language = "unknown"
        try:
            logger.info(
                "[api/jobs] metas duration=%r duration_auto=%r bpm=%r bpm_auto=%r keyscale=%r key_auto=%r timesignature=%r timesig_auto=%r vocal_language=%r language_auto=%r"
                % (d, duration_auto, bpm, bpm_auto, keyscale, key_auto, timesignature, timesig_auto, vocal_language, language_auto)
            )
        except Exception:
            pass
        st = q.submit(
            job_id,
            {
                "model": model_choice,
                "generation_mode": generation_mode,
                "task_type": task_type,
                "reference_audio": reference_audio,
                "src_audio": src_audio,
                "caption": caption,
                "lyrics": lyrics,
                "instrumental": instrumental,
                "thinking": thinking,
                "duration": d,
                "duration_auto": duration_auto,
                "seed": seed,
                "lora_id": lora_id,
                "lora_trigger": lora_trigger,
                "lora_weight": lora_weight,
                "batch_size": batch_size,
                "audio_format": audio_format,
                "inference_steps": inference_steps,
                "infer_method": infer_method,
                "timesteps": timesteps,
                "repainting_start": repainting_start,
                "repainting_end": repainting_end,
                "guidance_scale": guidance_scale,
                "shift": shift,
                "use_adg": use_adg,
                "cfg_interval_start": cfg_interval_start,
                "cfg_interval_end": cfg_interval_end,
                "enable_normalization": enable_normalization,
                "normalization_db": normalization_db,
                "score_scale": score_scale,
                "auto_score": auto_score,
                "latent_shift": latent_shift,
                "latent_rescale": latent_rescale,
                "bpm": bpm,
                "bpm_auto": bpm_auto,
                "keyscale": keyscale,
                "key_auto": key_auto,
                "timesignature": timesignature,
                "timesig_auto": timesig_auto,
                "vocal_language": vocal_language,
                "language_auto": language_auto,
                "audio_codes": audio_codes,
                "audio_cover_strength": payload.get("audio_cover_strength", None),
                "cover_noise_strength": payload.get("cover_noise_strength", None),
                "chord_debug_mode": payload.get("chord_debug_mode", ""),
                "chord_debug_reference_only": payload.get("chord_debug_reference_only", False),
                "chord_debug_reference_sequence": payload.get("chord_debug_reference_sequence", ""),
                "chord_debug_section_plan": payload.get("chord_debug_section_plan", ""),
                "chord_debug_reference_bpm": payload.get("chord_debug_reference_bpm", None),
                "chord_debug_reference_target_duration": payload.get("chord_debug_reference_target_duration", None),
                "chord_key": payload.get("chord_key", ""),
                "chord_scale": payload.get("chord_scale", "major"),
                "chord_roman": payload.get("chord_roman", ""),
                "chord_section_map": payload.get("chord_section_map", ""),
                "chord_apply_keyscale": payload.get("chord_apply_keyscale", False),
                "chord_apply_bpm": payload.get("chord_apply_bpm", False),
                "chord_apply_lyrics": payload.get("chord_apply_lyrics", False),
                "chord_family": payload.get("chord_family", ""),
                "lm_temperature": payload.get("lm_temperature", 0.85),
                "lm_cfg_scale": payload.get("lm_cfg_scale", 2.0),
                "lm_top_k": payload.get("lm_top_k", 0),
                "lm_top_p": payload.get("lm_top_p", 0.9),
                "lm_negative_prompt": payload.get("lm_negative_prompt", "NO USER INPUT"),
                "use_constrained_decoding": payload.get("use_constrained_decoding", True),
                "use_cot_metas": payload.get("use_cot_metas", thinking),
                "use_cot_caption": payload.get("use_cot_caption", thinking),
                "use_cot_language": payload.get("use_cot_language", thinking),
                "parallel_thinking": payload.get("parallel_thinking", False),
                "constrained_decoding_debug": payload.get("constrained_decoding_debug", False),
            },
        )
        return {
            "job_id": job_id,
            "status": st.status,
            "position": st.position,
        }

    @app.get("/api/jobs/{job_id}")

    def get_job(job_id: str, request: Request):

        _require_token(request)
        q: InProcessJobQueue = app.state.queue
        st = q.get(job_id)
        if not st:
            raise HTTPException(status_code=404, detail="Job non trovato")
        out = {
            "job_id": st.job_id,
            "status": st.status,
            "position": st.position,
            "created_at": st.created_at,
            "started_at": st.started_at,
            "finished_at": st.finished_at,
            "error": st.error,
        }
        if st.status == "done" and st.result:
            audio_paths = st.result.get("audio_paths") or []
            audio_count = max(1, int(st.result.get("audio_count", 1)))
            out["result"] = {
                "seconds": st.result.get("seconds"),
                "audio_urls": [f"/download/{job_id}/audio/{i}" for i in range(audio_count)],
                "audio_filenames": [os.path.basename(str(p or "")) for p in audio_paths[:audio_count]],
                "json_url": f"/download/{job_id}/json",
            }
        return out

    @app.get("/api/queue")

    def queue_status():

        q: InProcessJobQueue = app.state.queue
        return q.snapshot_queue()

    @app.get("/download/{job_id}/audio")

    def download_audio_first(job_id: str, request: Request):

        _require_token(request)
        return download_audio_index(job_id, 0)

    @app.get("/download/{job_id}/audio/{idx}")

    def download_audio_index(job_id: str, idx: int, request: Request):

        _require_token(request)
        q: InProcessJobQueue = app.state.queue
        st = q.get(job_id)
        if not st or st.status != "done" or not st.result:
            raise HTTPException(status_code=404, detail="File non disponibile")
        audio_paths = st.result.get("audio_paths") or []
        if not isinstance(audio_paths, list) or len(audio_paths) == 0:
            raise HTTPException(status_code=404, detail="Audio non trovato")
        try:
            idx = int(idx)
        except Exception:
            idx = 0
        if idx < 0 or idx >= len(audio_paths):
            raise HTTPException(status_code=404, detail="Indice audio non valido")
        audio_path = audio_paths[idx]
        if not audio_path or not os.path.exists(audio_path):
            raise HTTPException(status_code=404, detail="Audio non trovato")
        filename = os.path.basename(audio_path)
        lower = audio_path.lower()
        if lower.endswith(".flac"):
            media_type = "audio/flac"
        elif lower.endswith(".wav") or lower.endswith(".wave"):
            media_type = "audio/wav"
        elif lower.endswith(".opus") or lower.endswith(".ogg"):
            media_type = "audio/ogg"
        elif lower.endswith(".aac") or lower.endswith(".m4a"):
            media_type = "audio/aac"
        else:
            media_type = "audio/mpeg"
        return FileResponse(
            path=audio_path,
            media_type=media_type,
            filename=filename,
        )

    @app.get("/download/{job_id}/json")

    def download_json(job_id: str, request: Request):

        _require_token(request)
        q: InProcessJobQueue = app.state.queue
        st = q.get(job_id)
        if not st or st.status != "done" or not st.result:
            raise HTTPException(status_code=404, detail="File non disponibile")
        json_path = st.result.get("json_path")
        if not json_path or not os.path.exists(json_path):
            raise HTTPException(status_code=404, detail="JSON non trovato")
        audio_paths = st.result.get("audio_paths") or []
        download_name = "metadata.json"
        if isinstance(audio_paths, list) and audio_paths:
            first_audio = str(audio_paths[0] or "").strip()
            if first_audio:
                audio_name = os.path.basename(first_audio)
                root, _ext = os.path.splitext(audio_name)
                if root:
                    download_name = f"{root}.json"
        return FileResponse(
            path=json_path,
            media_type="application/json",
            filename=download_name,
        )
    return app
