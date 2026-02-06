"""FastAPI server for ACE-Step V1.5.

Endpoints:
- POST /release_task          Create music generation task
- POST /query_result          Batch query task results
- POST /create_random_sample  Generate random music parameters via LLM
- POST /format_input          Format and enhance lyrics/caption via LLM
- GET  /v1/models             List available models
- GET  /v1/audio              Download audio file
- GET  /health                Health check

NOTE:
- In-memory queue and job store -> run uvicorn with workers=1.
"""

from __future__ import annotations

import asyncio
import glob
import json
import os
import random
import sys
import time
import traceback
import tempfile
import urllib.parse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4
from loguru import logger

try:
    from dotenv import load_dotenv
except ImportError:  # Optional dependency
    load_dotenv = None  # type: ignore

from fastapi import FastAPI, HTTPException, Request, Depends, Header
from pydantic import BaseModel, Field
from starlette.datastructures import UploadFile as StarletteUploadFile

from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.constants import (
    DEFAULT_DIT_INSTRUCTION,
    DEFAULT_LM_INSTRUCTION,
    TASK_INSTRUCTIONS,
)
from acestep.inference import (
    GenerationParams,
    GenerationConfig,
    generate_music,
    create_sample,
    format_sample,
)
from acestep.gradio_ui.events.results_handlers import _build_generation_info
from acestep.gpu_config import (
    get_gpu_config,
    get_gpu_memory_gb,
    print_gpu_config_info,
    set_global_gpu_config,
    get_recommended_lm_model,
    is_lm_model_supported,
    GPUConfig,
    VRAM_16GB_MIN_GB,
)


# =============================================================================
# Model Auto-Download Support
# =============================================================================

# Model name to repository mapping
MODEL_REPO_MAPPING = {
    # Main unified repository (contains: acestep-v15-turbo, acestep-5Hz-lm-1.7B, Qwen3-Embedding-0.6B, vae)
    "acestep-v15-turbo": "ACE-Step/Ace-Step1.5",
    "acestep-5Hz-lm-1.7B": "ACE-Step/Ace-Step1.5",
    "vae": "ACE-Step/Ace-Step1.5",
    "Qwen3-Embedding-0.6B": "ACE-Step/Ace-Step1.5",
    # Separate model repositories
    "acestep-5Hz-lm-0.6B": "ACE-Step/acestep-5Hz-lm-0.6B",
    "acestep-5Hz-lm-4B": "ACE-Step/acestep-5Hz-lm-4B",
    "acestep-v15-base": "ACE-Step/acestep-v15-base",
    "acestep-v15-sft": "ACE-Step/acestep-v15-sft",
    "acestep-v15-turbo-shift3": "ACE-Step/acestep-v15-turbo-shift3",
}

DEFAULT_REPO_ID = "ACE-Step/Ace-Step1.5"


def _can_access_google(timeout: float = 3.0) -> bool:
    """Check if Google is accessible (to determine HuggingFace vs ModelScope)."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect(("www.google.com", 443))
        return True
    except (socket.timeout, socket.error, OSError):
        return False
    finally:
        sock.close()


def _download_from_huggingface(repo_id: str, local_dir: str, model_name: str) -> str:
    """Download model from HuggingFace Hub."""
    from huggingface_hub import snapshot_download

    is_unified_repo = repo_id == DEFAULT_REPO_ID or repo_id == "ACE-Step/Ace-Step1.5"

    if is_unified_repo:
        download_dir = local_dir
        print(f"[Model Download] Downloading unified repo {repo_id} to {download_dir}...")
    else:
        download_dir = os.path.join(local_dir, model_name)
        os.makedirs(download_dir, exist_ok=True)
        print(f"[Model Download] Downloading {model_name} from {repo_id} to {download_dir}...")

    snapshot_download(
        repo_id=repo_id,
        local_dir=download_dir,
        local_dir_use_symlinks=False,
    )

    return os.path.join(local_dir, model_name)


def _download_from_modelscope(repo_id: str, local_dir: str, model_name: str) -> str:
    """Download model from ModelScope."""
    from modelscope import snapshot_download

    is_unified_repo = repo_id == DEFAULT_REPO_ID or repo_id == "ACE-Step/Ace-Step1.5"

    if is_unified_repo:
        download_dir = local_dir
        print(f"[Model Download] Downloading unified repo {repo_id} from ModelScope to {download_dir}...")
    else:
        download_dir = os.path.join(local_dir, model_name)
        os.makedirs(download_dir, exist_ok=True)
        print(f"[Model Download] Downloading {model_name} from ModelScope {repo_id} to {download_dir}...")

    # ModelScope snapshot_download returns the cache path
    # Use cache_dir parameter for better compatibility across versions
    try:
        # Try with local_dir first (newer versions)
        result_path = snapshot_download(
            model_id=repo_id,
            local_dir=download_dir,
        )
        print(f"[Model Download] ModelScope download completed: {result_path}")
    except TypeError:
        # Fallback to cache_dir for older versions
        print("[Model Download] Retrying with cache_dir parameter...")
        result_path = snapshot_download(
            model_id=repo_id,
            cache_dir=download_dir,
        )
        print(f"[Model Download] ModelScope download completed: {result_path}")

    return os.path.join(local_dir, model_name)


def _ensure_model_downloaded(model_name: str, checkpoint_dir: str) -> str:
    """
    Ensure model is downloaded. Auto-detect source based on network.

    Args:
        model_name: Model directory name (e.g., "acestep-v15-turbo")
        checkpoint_dir: Target checkpoint directory

    Returns:
        Path to the model directory
    """
    model_path = os.path.join(checkpoint_dir, model_name)

    # Check if model already exists
    if os.path.exists(model_path) and os.listdir(model_path):
        print(f"[Model Download] Model {model_name} already exists at {model_path}")
        return model_path

    # Get repository ID
    repo_id = MODEL_REPO_MAPPING.get(model_name, DEFAULT_REPO_ID)

    print(f"[Model Download] Model {model_name} not found, checking network...")

    # Check for user preference
    prefer_source = os.environ.get("ACESTEP_DOWNLOAD_SOURCE", "").lower()

    # Determine download source
    if prefer_source == "huggingface":
        use_huggingface = True
        print("[Model Download] User preference: HuggingFace Hub")
    elif prefer_source == "modelscope":
        use_huggingface = False
        print("[Model Download] User preference: ModelScope")
    else:
        use_huggingface = _can_access_google()
        print(f"[Model Download] Auto-detected: {'HuggingFace Hub' if use_huggingface else 'ModelScope'}")

    if use_huggingface:
        print("[Model Download] Using HuggingFace Hub...")
        try:
            return _download_from_huggingface(repo_id, checkpoint_dir, model_name)
        except Exception as e:
            print(f"[Model Download] HuggingFace download failed: {e}")
            print("[Model Download] Falling back to ModelScope...")
            return _download_from_modelscope(repo_id, checkpoint_dir, model_name)
    else:
        print("[Model Download] Using ModelScope...")
        try:
            return _download_from_modelscope(repo_id, checkpoint_dir, model_name)
        except Exception as e:
            print(f"[Model Download] ModelScope download failed: {e}")
            print("[Model Download] Trying HuggingFace as fallback...")
            return _download_from_huggingface(repo_id, checkpoint_dir, model_name)


def _get_project_root() -> str:
    current_file = os.path.abspath(__file__)
    return os.path.dirname(os.path.dirname(current_file))


# =============================================================================
# Constants
# =============================================================================

RESULT_KEY_PREFIX = "ace_step_v1.5_"
RESULT_EXPIRE_SECONDS = 7 * 24 * 60 * 60  # 7 days
TASK_TIMEOUT_SECONDS = 3600  # 1 hour
JOB_STORE_CLEANUP_INTERVAL = 300  # 5 minutes - interval for cleaning up old jobs
JOB_STORE_MAX_AGE_SECONDS = 86400  # 24 hours - completed jobs older than this will be cleaned
STATUS_MAP = {"queued": 0, "running": 0, "succeeded": 1, "failed": 2}

LM_DEFAULT_TEMPERATURE = 0.85
LM_DEFAULT_CFG_SCALE = 2.5
LM_DEFAULT_TOP_P = 0.9


def _wrap_response(data: Any, code: int = 200, error: Optional[str] = None) -> Dict[str, Any]:
    """Wrap response data in standard format."""
    return {
        "data": data,
        "code": code,
        "error": error,
        "timestamp": int(time.time() * 1000),
        "extra": None,
    }


# =============================================================================
# Example Data for Random Sample
# =============================================================================

SIMPLE_MODE_EXAMPLES_DIR = os.path.join(_get_project_root(), "examples", "simple_mode")
CUSTOM_MODE_EXAMPLES_DIR = os.path.join(_get_project_root(), "examples", "text2music")


def _load_all_examples(sample_mode: str = "simple_mode") -> List[Dict[str, Any]]:
    """Load all example data files from the examples directory."""
    examples = []
    examples_dir = SIMPLE_MODE_EXAMPLES_DIR if sample_mode == "simple_mode" else CUSTOM_MODE_EXAMPLES_DIR
    pattern = os.path.join(examples_dir, "example_*.json")

    for filepath in glob.glob(pattern):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                examples.append(data)
        except Exception as e:
            print(f"[API Server] Failed to load example file {filepath}: {e}")

    return examples


# Pre-load example data at module load time
SIMPLE_EXAMPLE_DATA: List[Dict[str, Any]] = _load_all_examples(sample_mode="simple_mode")
CUSTOM_EXAMPLE_DATA: List[Dict[str, Any]] = _load_all_examples(sample_mode="custom_mode")

# =============================================================================
# API Key Authentication
# =============================================================================

_api_key: Optional[str] = None


def set_api_key(key: Optional[str]):
    """Set the API key for authentication"""
    global _api_key
    _api_key = key


def verify_token_from_request(body: dict, authorization: Optional[str] = None) -> Optional[str]:
    """
    Verify API key from request body (ai_token) or Authorization header.
    Returns the token if valid, None if no auth required.
    """
    if _api_key is None:
        return None  # No auth required

    # Try ai_token from body first
    ai_token = body.get("ai_token") if body else None
    if ai_token:
        if ai_token == _api_key:
            return ai_token
        raise HTTPException(status_code=401, detail="Invalid ai_token")

    # Fallback to Authorization header
    if authorization:
        if authorization.startswith("Bearer "):
            token = authorization[7:]
        else:
            token = authorization
        if token == _api_key:
            return token
        raise HTTPException(status_code=401, detail="Invalid API key")

    # No token provided but auth is required
    raise HTTPException(status_code=401, detail="Missing ai_token or Authorization header")


async def verify_api_key(authorization: Optional[str] = Header(None)):
    """Verify API key from Authorization header (legacy, for non-body endpoints)"""
    if _api_key is None:
        return  # No auth required

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    # Support "Bearer <key>" format
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization

    if token != _api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

# Parameter aliases for request parsing
PARAM_ALIASES = {
    "prompt": ["prompt", "caption"],
    "lyrics": ["lyrics"],
    "thinking": ["thinking"],
    "analysis_only": ["analysis_only", "analysisOnly"],
    "sample_mode": ["sample_mode", "sampleMode"],
    "sample_query": ["sample_query", "sampleQuery", "description", "desc"],
    "use_format": ["use_format", "useFormat", "format"],
    "model": ["model", "model_name", "modelName", "dit_model", "ditModel"],
    "key_scale": ["key_scale", "keyscale", "keyScale", "key"],
    "time_signature": ["time_signature", "timesignature", "timeSignature"],
    "audio_duration": ["audio_duration", "duration", "audioDuration", "target_duration", "targetDuration"],
    "vocal_language": ["vocal_language", "vocalLanguage", "language"],
    "bpm": ["bpm"],
    "inference_steps": ["inference_steps", "inferenceSteps"],
    "guidance_scale": ["guidance_scale", "guidanceScale"],
    "use_random_seed": ["use_random_seed", "useRandomSeed"],
    "seed": ["seed"],
    "audio_code_string": ["audio_code_string", "audioCodeString"],
    "audio_cover_strength": ["audio_cover_strength", "audioCoverStrength"],
    "reference_audio_path": ["reference_audio_path", "ref_audio_path", "referenceAudioPath", "refAudioPath"],
    "src_audio_path": ["src_audio_path", "ctx_audio_path", "sourceAudioPath", "srcAudioPath", "ctxAudioPath"],
    "task_type": ["task_type", "taskType"],
    "infer_method": ["infer_method", "inferMethod"],
    "use_tiled_decode": ["use_tiled_decode", "useTiledDecode"],
    "constrained_decoding": ["constrained_decoding", "constrainedDecoding", "constrained"],
    "constrained_decoding_debug": ["constrained_decoding_debug", "constrainedDecodingDebug"],
    "use_cot_caption": ["use_cot_caption", "cot_caption", "cot-caption"],
    "use_cot_language": ["use_cot_language", "cot_language", "cot-language"],
    "is_format_caption": ["is_format_caption", "isFormatCaption"],
    "allow_lm_batch": ["allow_lm_batch", "allowLmBatch", "parallel_thinking"],
}


def _parse_description_hints(description: str) -> tuple[Optional[str], bool]:
    """
    Parse a description string to extract language code and instrumental flag.
    
    This function analyzes user descriptions like "Pop rock. English" or "piano solo"
    to detect:
    - Language: Maps language names to ISO codes (e.g., "English" -> "en")
    - Instrumental: Detects patterns indicating instrumental/no-vocal music
    
    Args:
        description: User's natural language music description
        
    Returns:
        (language_code, is_instrumental) tuple:
        - language_code: ISO language code (e.g., "en", "zh") or None if not detected
        - is_instrumental: True if description indicates instrumental music
    """
    import re
    
    if not description:
        return None, False
    
    description_lower = description.lower().strip()
    
    # Language mapping: input patterns -> ISO code
    language_mapping = {
        'english': 'en', 'en': 'en',
        'chinese': 'zh', '中文': 'zh', 'zh': 'zh', 'mandarin': 'zh',
        'japanese': 'ja', '日本語': 'ja', 'ja': 'ja',
        'korean': 'ko', '한국어': 'ko', 'ko': 'ko',
        'spanish': 'es', 'español': 'es', 'es': 'es',
        'french': 'fr', 'français': 'fr', 'fr': 'fr',
        'german': 'de', 'deutsch': 'de', 'de': 'de',
        'italian': 'it', 'italiano': 'it', 'it': 'it',
        'portuguese': 'pt', 'português': 'pt', 'pt': 'pt',
        'russian': 'ru', 'русский': 'ru', 'ru': 'ru',
        'bengali': 'bn', 'bn': 'bn',
        'hindi': 'hi', 'hi': 'hi',
        'arabic': 'ar', 'ar': 'ar',
        'thai': 'th', 'th': 'th',
        'vietnamese': 'vi', 'vi': 'vi',
        'indonesian': 'id', 'id': 'id',
        'turkish': 'tr', 'tr': 'tr',
        'dutch': 'nl', 'nl': 'nl',
        'polish': 'pl', 'pl': 'pl',
    }
    
    # Detect language
    detected_language = None
    for lang_name, lang_code in language_mapping.items():
        if len(lang_name) <= 2:
            pattern = r'(?:^|\s|[.,;:!?])' + re.escape(lang_name) + r'(?:$|\s|[.,;:!?])'
        else:
            pattern = r'\b' + re.escape(lang_name) + r'\b'
        
        if re.search(pattern, description_lower):
            detected_language = lang_code
            break
    
    # Detect instrumental
    is_instrumental = False
    if 'instrumental' in description_lower:
        is_instrumental = True
    elif 'pure music' in description_lower or 'pure instrument' in description_lower:
        is_instrumental = True
    elif description_lower.endswith(' solo') or description_lower == 'solo':
        is_instrumental = True
    
    return detected_language, is_instrumental


JobStatus = Literal["queued", "running", "succeeded", "failed"]


class GenerateMusicRequest(BaseModel):
    prompt: str = Field(default="", description="Text prompt describing the music")
    lyrics: str = Field(default="", description="Lyric text")

    # New API semantics:
    # - thinking=True: use 5Hz LM to generate audio codes (lm-dit behavior)
    # - thinking=False: do not use LM to generate codes (dit behavior)
    # Regardless of thinking, if some metas are missing, server may use LM to fill them.
    thinking: bool = False
    # Sample-mode requests auto-generate caption/lyrics/metas via LM (no user prompt).
    sample_mode: bool = False
    # Description for sample mode: auto-generate caption/lyrics from description query
    sample_query: str = Field(default="", description="Query/description for sample mode (use create_sample)")
    # Whether to use format_sample() to enhance input caption/lyrics
    use_format: bool = Field(default=False, description="Use format_sample() to enhance input (default: False)")
    # Model name for multi-model support (select which DiT model to use)
    model: Optional[str] = Field(default=None, description="Model name to use (e.g., 'acestep-v15-turbo')")

    bpm: Optional[int] = None
    # Accept common client keys via manual parsing (see RequestParser).
    key_scale: str = ""
    time_signature: str = ""
    vocal_language: str = "en"
    inference_steps: int = 8
    guidance_scale: float = 7.0
    use_random_seed: bool = True
    seed: int = -1

    reference_audio_path: Optional[str] = None
    src_audio_path: Optional[str] = None
    audio_duration: Optional[float] = None
    batch_size: Optional[int] = None

    audio_code_string: str = ""

    repainting_start: float = 0.0
    repainting_end: Optional[float] = None

    instruction: str = DEFAULT_DIT_INSTRUCTION
    audio_cover_strength: float = 1.0
    task_type: str = "text2music"
    analysis_only: bool = False

    use_adg: bool = False
    cfg_interval_start: float = 0.0
    cfg_interval_end: float = 1.0
    infer_method: str = "ode"  # "ode" or "sde" - diffusion inference method
    shift: float = Field(
        default=3.0,
        description="Timestep shift factor (range 1.0~5.0, default 3.0). Only effective for base models, not turbo models."
    )
    timesteps: Optional[str] = Field(
        default=None,
        description="Custom timesteps (comma-separated, e.g., '0.97,0.76,0.615,0.5,0.395,0.28,0.18,0.085,0'). Overrides inference_steps and shift."
    )

    audio_format: str = "mp3"
    use_tiled_decode: bool = True

    # 5Hz LM (server-side): used for metadata completion and (when thinking=True) codes generation.
    lm_model_path: Optional[str] = None  # e.g. "acestep-5Hz-lm-0.6B"
    lm_backend: Literal["vllm", "pt"] = "vllm"

    constrained_decoding: bool = True
    constrained_decoding_debug: bool = False
    use_cot_caption: bool = True
    use_cot_language: bool = True
    is_format_caption: bool = False
    allow_lm_batch: bool = True

    lm_temperature: float = 0.85
    lm_cfg_scale: float = 2.5
    lm_top_k: Optional[int] = None
    lm_top_p: Optional[float] = 0.9
    lm_repetition_penalty: float = 1.0
    lm_negative_prompt: str = "NO USER INPUT"

    class Config:
        allow_population_by_field_name = True
        allow_population_by_alias = True


class CreateJobResponse(BaseModel):
    task_id: str
    status: JobStatus
    queue_position: int = 0  # 1-based best-effort position when queued


class JobResult(BaseModel):
    first_audio_path: Optional[str] = None
    second_audio_path: Optional[str] = None
    audio_paths: list[str] = Field(default_factory=list)

    generation_info: str = ""
    status_message: str = ""
    seed_value: str = ""

    metas: Dict[str, Any] = Field(default_factory=dict)
    bpm: Optional[int] = None
    duration: Optional[float] = None
    genres: Optional[str] = None
    keyscale: Optional[str] = None
    timesignature: Optional[str] = None
    
    # Model information
    lm_model: Optional[str] = None
    dit_model: Optional[str] = None


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    # queue observability
    queue_position: int = 0
    eta_seconds: Optional[float] = None
    avg_job_seconds: Optional[float] = None

    result: Optional[JobResult] = None
    error: Optional[str] = None


@dataclass
class _JobRecord:
    job_id: str
    status: JobStatus
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    status_text: str = ""
    env: str = "development"
    progress: float = 0.0  # 0.0 - 1.0
    stage: str = "queued"
    updated_at: Optional[float] = None


class _JobStore:
    def __init__(self, max_age_seconds: int = JOB_STORE_MAX_AGE_SECONDS) -> None:
        self._lock = Lock()
        self._jobs: Dict[str, _JobRecord] = {}
        self._max_age = max_age_seconds

    def create(self) -> _JobRecord:
        job_id = str(uuid4())
        now = time.time()
        rec = _JobRecord(job_id=job_id, status="queued", created_at=now, progress=0.0, stage="queued", updated_at=now)
        with self._lock:
            self._jobs[job_id] = rec
        return rec

    def create_with_id(self, job_id: str, env: str = "development") -> _JobRecord:
        """Create job record with specified ID"""
        now = time.time()
        rec = _JobRecord(
            job_id=job_id,
            status="queued",
            created_at=now,
            env=env,
            progress=0.0,
            stage="queued",
            updated_at=now,
        )
        with self._lock:
            self._jobs[job_id] = rec
        return rec

    def get(self, job_id: str) -> Optional[_JobRecord]:
        with self._lock:
            return self._jobs.get(job_id)

    def mark_running(self, job_id: str) -> None:
        with self._lock:
            rec = self._jobs[job_id]
            rec.status = "running"
            rec.started_at = time.time()
            rec.progress = max(rec.progress, 0.01)
            rec.stage = "running"
            rec.updated_at = time.time()

    def mark_succeeded(self, job_id: str, result: Dict[str, Any]) -> None:
        with self._lock:
            rec = self._jobs[job_id]
            rec.status = "succeeded"
            rec.finished_at = time.time()
            rec.result = result
            rec.error = None
            rec.progress = 1.0
            rec.stage = "succeeded"
            rec.updated_at = time.time()

    def mark_failed(self, job_id: str, error: str) -> None:
        with self._lock:
            rec = self._jobs[job_id]
            rec.status = "failed"
            rec.finished_at = time.time()
            rec.result = None
            rec.error = error
            rec.progress = rec.progress if rec.progress > 0 else 0.0
            rec.stage = "failed"
            rec.updated_at = time.time()

    def update_progress(self, job_id: str, progress: float, stage: Optional[str] = None) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return
            rec.progress = max(0.0, min(1.0, float(progress)))
            if stage:
                rec.stage = stage
            rec.updated_at = time.time()

    def cleanup_old_jobs(self, max_age_seconds: Optional[int] = None) -> int:
        """
        Clean up completed jobs older than max_age_seconds.

        Only removes jobs with status 'succeeded' or 'failed'.
        Jobs that are 'queued' or 'running' are never removed.

        Returns the number of jobs removed.
        """
        max_age = max_age_seconds if max_age_seconds is not None else self._max_age
        now = time.time()
        removed = 0

        with self._lock:
            to_remove = []
            for job_id, rec in self._jobs.items():
                if rec.status in ("succeeded", "failed"):
                    finish_time = rec.finished_at or rec.created_at
                    age = now - finish_time
                    if age > max_age:
                        to_remove.append(job_id)

            for job_id in to_remove:
                del self._jobs[job_id]
                removed += 1

        return removed

    def get_stats(self) -> Dict[str, int]:
        """Get statistics about jobs in the store."""
        with self._lock:
            stats = {
                "total": len(self._jobs),
                "queued": 0,
                "running": 0,
                "succeeded": 0,
                "failed": 0,
            }
            for rec in self._jobs.values():
                if rec.status in stats:
                    stats[rec.status] += 1
            return stats
    
    def update_status_text(self, job_id: str, text: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].status_text = text

def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}




def _get_model_name(config_path: str) -> str:
    """
    Extract model name from config_path.
    
    Args:
        config_path: Path like "acestep-v15-turbo" or "/path/to/acestep-v15-turbo"
        
    Returns:
        Model name (last directory name from config_path)
    """
    if not config_path:
        return ""
    normalized = config_path.rstrip("/\\")
    return os.path.basename(normalized)


_project_env_loaded = False


def _load_project_env() -> None:
    """Load .env at most once per process to avoid epoch-boundary stalls (e.g. Windows LoRA training)."""
    global _project_env_loaded
    if _project_env_loaded or load_dotenv is None:
        return
    try:
        project_root = _get_project_root()
        env_path = os.path.join(project_root, ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path, override=False)
        _project_env_loaded = True
    except Exception:
        # Optional best-effort: continue even if .env loading fails.
        pass


_load_project_env()


def _to_int(v: Any, default: Optional[int] = None) -> Optional[int]:
    if v is None:
        return default
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if s == "":
        return default
    try:
        return int(s)
    except Exception:
        return default


def _to_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    if v is None:
        return default
    if isinstance(v, float):
        return v
    s = str(v).strip()
    if s == "":
        return default
    try:
        return float(s)
    except Exception:
        return default


def _to_bool(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s == "":
        return default
    return s in {"1", "true", "yes", "y", "on"}


def _map_status(status: str) -> int:
    """Map job status string to integer code."""
    return STATUS_MAP.get(status, 2)


def _parse_timesteps(s: Optional[str]) -> Optional[List[float]]:
    """Parse comma-separated timesteps string to list of floats."""
    if not s or not s.strip():
        return None
    try:
        return [float(t.strip()) for t in s.split(",") if t.strip()]
    except (ValueError, Exception):
        return None


def _is_instrumental(lyrics: str) -> bool:
    """
    Determine if the music should be instrumental based on lyrics.

    Returns True if:
    - lyrics is empty or whitespace only
    - lyrics (lowercased and trimmed) is "[inst]" or "[instrumental]"
    """
    if not lyrics:
        return True
    lyrics_clean = lyrics.strip().lower()
    if not lyrics_clean:
        return True
    return lyrics_clean in ("[inst]", "[instrumental]")


class RequestParser:
    """Parse request parameters from multiple sources with alias support."""

    def __init__(self, raw: dict):
        self._raw = dict(raw) if raw else {}
        self._param_obj = self._parse_json(self._raw.get("param_obj"))
        self._metas = self._find_metas()

    def _parse_json(self, v) -> dict:
        if isinstance(v, dict):
            return v
        if isinstance(v, str) and v.strip():
            try:
                return json.loads(v)
            except Exception:
                pass
        return {}

    def _find_metas(self) -> dict:
        for key in ("metas", "meta", "metadata", "user_metadata", "userMetadata"):
            v = self._raw.get(key)
            if v:
                return self._parse_json(v)
        return {}

    def get(self, name: str, default=None):
        """Get parameter by canonical name from all sources."""
        aliases = PARAM_ALIASES.get(name, [name])
        for source in (self._raw, self._param_obj, self._metas):
            for alias in aliases:
                v = source.get(alias)
                if v is not None:
                    return v
        return default

    def str(self, name: str, default: str = "") -> str:
        v = self.get(name)
        return str(v) if v is not None else default

    def int(self, name: str, default: Optional[int] = None) -> Optional[int]:
        return _to_int(self.get(name), default)

    def float(self, name: str, default: Optional[float] = None) -> Optional[float]:
        return _to_float(self.get(name), default)

    def bool(self, name: str, default: bool = False) -> bool:
        return _to_bool(self.get(name), default)


async def _save_upload_to_temp(upload: StarletteUploadFile, *, prefix: str) -> str:
    suffix = Path(upload.filename or "").suffix
    fd, path = tempfile.mkstemp(prefix=f"{prefix}_", suffix=suffix)
    os.close(fd)
    try:
        with open(path, "wb") as f:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    except Exception:
        try:
            os.remove(path)
        except Exception:
            pass
        raise
    finally:
        try:
            await upload.close()
        except Exception:
            pass
    return path

class LogBuffer:
    def __init__(self):
        self.last_message = "Waiting"

    def write(self, message):
        self.last_message = message.strip()

log_buffer = LogBuffer()
logger.add(lambda msg: log_buffer.write(msg), format="{time:HH:mm:ss} | {level} | {message}")

def create_app() -> FastAPI:
    store = _JobStore()

    # API Key authentication (from environment variable)
    api_key = os.getenv("ACESTEP_API_KEY", None)
    set_api_key(api_key)

    QUEUE_MAXSIZE = int(os.getenv("ACESTEP_QUEUE_MAXSIZE", "200"))
    WORKER_COUNT = int(os.getenv("ACESTEP_QUEUE_WORKERS", "1"))  # Single GPU recommended

    INITIAL_AVG_JOB_SECONDS = float(os.getenv("ACESTEP_AVG_JOB_SECONDS", "5.0"))
    AVG_WINDOW = int(os.getenv("ACESTEP_AVG_WINDOW", "50"))

    def _path_to_audio_url(path: str) -> str:
        """Convert local file path to downloadable relative URL"""
        if not path:
            return path
        if path.startswith("http://") or path.startswith("https://"):
            return path
        encoded_path = urllib.parse.quote(path, safe="")
        return f"/v1/audio?path={encoded_path}"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Clear proxy env that may affect downstream libs
        for proxy_var in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
            os.environ.pop(proxy_var, None)

        # Ensure compilation/temp caches do not fill up small default /tmp.
        # Triton/Inductor (and the system compiler) can create large temporary files.
        project_root = _get_project_root()
        cache_root = os.path.join(project_root, ".cache", "acestep")
        tmp_root = (os.getenv("ACESTEP_TMPDIR") or os.path.join(cache_root, "tmp")).strip()
        triton_cache_root = (os.getenv("TRITON_CACHE_DIR") or os.path.join(cache_root, "triton")).strip()
        inductor_cache_root = (os.getenv("TORCHINDUCTOR_CACHE_DIR") or os.path.join(cache_root, "torchinductor")).strip()

        for p in [cache_root, tmp_root, triton_cache_root, inductor_cache_root]:
            try:
                os.makedirs(p, exist_ok=True)
            except Exception:
                # Best-effort: do not block startup if directory creation fails.
                pass

        # Respect explicit user overrides; if ACESTEP_TMPDIR is set, it should win.
        if os.getenv("ACESTEP_TMPDIR"):
            os.environ["TMPDIR"] = tmp_root
            os.environ["TEMP"] = tmp_root
            os.environ["TMP"] = tmp_root
        else:
            os.environ.setdefault("TMPDIR", tmp_root)
            os.environ.setdefault("TEMP", tmp_root)
            os.environ.setdefault("TMP", tmp_root)

        os.environ.setdefault("TRITON_CACHE_DIR", triton_cache_root)
        os.environ.setdefault("TORCHINDUCTOR_CACHE_DIR", inductor_cache_root)

        handler = AceStepHandler()
        llm_handler = LLMHandler()
        init_lock = asyncio.Lock()
        app.state._initialized = False
        app.state._init_error = None
        app.state._init_lock = init_lock

        app.state.llm_handler = llm_handler
        app.state._llm_initialized = False
        app.state._llm_init_error = None
        app.state._llm_init_lock = Lock()
        app.state._llm_lazy_load_disabled = False  # Will be set to True if LLM skipped due to GPU config

        # Multi-model support: secondary DiT handlers
        handler2 = None
        handler3 = None
        config_path2 = os.getenv("ACESTEP_CONFIG_PATH2", "").strip()
        config_path3 = os.getenv("ACESTEP_CONFIG_PATH3", "").strip()
        
        if config_path2:
            handler2 = AceStepHandler()
        if config_path3:
            handler3 = AceStepHandler()
        
        app.state.handler2 = handler2
        app.state.handler3 = handler3
        app.state._initialized2 = False
        app.state._initialized3 = False
        app.state._config_path = os.getenv("ACESTEP_CONFIG_PATH", "acestep-v15-turbo")
        app.state._config_path2 = config_path2
        app.state._config_path3 = config_path3

        max_workers = int(os.getenv("ACESTEP_API_WORKERS", "1"))
        executor = ThreadPoolExecutor(max_workers=max_workers)

        # Queue & observability
        app.state.job_queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)  # (job_id, req)
        app.state.pending_ids = deque()  # queued job_ids
        app.state.pending_lock = asyncio.Lock()

        # temp files per job (from multipart uploads)
        app.state.job_temp_files = {}  # job_id -> list[path]
        app.state.job_temp_files_lock = asyncio.Lock()

        # stats
        app.state.stats_lock = asyncio.Lock()
        app.state.recent_durations = deque(maxlen=AVG_WINDOW)
        app.state.avg_job_seconds = INITIAL_AVG_JOB_SECONDS

        app.state.handler = handler
        app.state.executor = executor
        app.state.job_store = store
        app.state._python_executable = sys.executable
        
        # Temporary directory for saving generated audio files
        app.state.temp_audio_dir = os.path.join(tmp_root, "api_audio")
        os.makedirs(app.state.temp_audio_dir, exist_ok=True)

        # Initialize local cache
        try:
            from acestep.local_cache import get_local_cache
            local_cache_dir = os.path.join(cache_root, "local_redis")
            app.state.local_cache = get_local_cache(local_cache_dir)
        except ImportError:
            app.state.local_cache = None

        async def _ensure_initialized() -> None:
            """Check if models are initialized (they should be loaded at startup)."""
            if getattr(app.state, "_init_error", None):
                raise RuntimeError(app.state._init_error)
            if not getattr(app.state, "_initialized", False):
                raise RuntimeError("Model not initialized")

        async def _cleanup_job_temp_files(job_id: str) -> None:
            async with app.state.job_temp_files_lock:
                paths = app.state.job_temp_files.pop(job_id, [])
            for p in paths:
                try:
                    os.remove(p)
                except Exception:
                    pass

        def _update_local_cache(job_id: str, result: Optional[Dict], status: str) -> None:
            """Update local cache with job result"""
            local_cache = getattr(app.state, 'local_cache', None)
            if not local_cache:
                return

            rec = store.get(job_id)
            env = getattr(rec, 'env', 'development') if rec else 'development'
            create_time = rec.created_at if rec else time.time()

            status_int = _map_status(status)

            if status == "succeeded" and result:
                audio_paths = result.get("audio_paths", [])
                # Final prompt/lyrics (may be modified by thinking/format)
                final_prompt = result.get("prompt", "")
                final_lyrics = result.get("lyrics", "")
                # Original user input from metas
                metas_raw = result.get("metas", {}) or {}
                original_prompt = metas_raw.get("prompt", "")
                original_lyrics = metas_raw.get("lyrics", "")
                # metas contains original input + other metadata
                metas = {
                    "bpm": metas_raw.get("bpm"),
                    "duration": metas_raw.get("duration"),
                    "genres": metas_raw.get("genres", ""),
                    "keyscale": metas_raw.get("keyscale", ""),
                    "timesignature": metas_raw.get("timesignature", ""),
                    "prompt": original_prompt,
                    "lyrics": original_lyrics,
                }
                # Extra fields for Discord bot
                generation_info = result.get("generation_info", "")
                seed_value = result.get("seed_value", "")
                lm_model = result.get("lm_model", "")
                dit_model = result.get("dit_model", "")

                if audio_paths:
                    result_data = [
                        {
                            "file": p,
                            "wave": "",
                            "status": status_int,
                            "create_time": int(create_time),
                            "env": env,
                            "prompt": final_prompt,
                            "lyrics": final_lyrics,
                            "metas": metas,
                            "generation_info": generation_info,
                            "seed_value": seed_value,
                            "lm_model": lm_model,
                            "dit_model": dit_model,
                            "progress": 1.0,
                            "stage": "succeeded",
                        }
                        for p in audio_paths
                    ]
                else:
                    result_data = [{
                        "file": "",
                        "wave": "",
                        "status": status_int,
                        "create_time": int(create_time),
                        "env": env,
                        "prompt": final_prompt,
                        "lyrics": final_lyrics,
                        "metas": metas,
                        "generation_info": generation_info,
                        "seed_value": seed_value,
                        "lm_model": lm_model,
                        "dit_model": dit_model,
                        "progress": 1.0,
                        "stage": "succeeded",
                    }]
            else:
                result_data = [{
                    "file": "",
                    "wave": "",
                    "status": status_int,
                    "create_time": int(create_time),
                    "env": env,
                    "progress": 0.0,
                    "stage": "failed" if status == "failed" else status,
                }]

            result_key = f"{RESULT_KEY_PREFIX}{job_id}"
            local_cache.set(result_key, result_data, ex=RESULT_EXPIRE_SECONDS)

        def _update_local_cache_progress(job_id: str, progress: float, stage: str) -> None:
            """Update local cache with job progress for queued/running states."""
            local_cache = getattr(app.state, 'local_cache', None)
            if not local_cache:
                return

            rec = store.get(job_id)
            env = getattr(rec, 'env', 'development') if rec else 'development'
            create_time = rec.created_at if rec else time.time()
            status_int = _map_status("running")

            result_data = [{
                "file": "",
                "wave": "",
                "status": status_int,
                "create_time": int(create_time),
                "env": env,
                "progress": float(progress),
                "stage": stage,
            }]
                # Failed or other status - include error from job store
                error_msg = rec.error if rec and rec.error else None
                result_data = [{"file": "", "wave": "", "status": status_int, "create_time": int(create_time), "env": env, "error": error_msg}]

            result_key = f"{RESULT_KEY_PREFIX}{job_id}"
            local_cache.set(result_key, result_data, ex=RESULT_EXPIRE_SECONDS)

        async def _run_one_job(job_id: str, req: GenerateMusicRequest) -> None:
            job_store: _JobStore = app.state.job_store
            llm: LLMHandler = app.state.llm_handler
            executor: ThreadPoolExecutor = app.state.executor

            await _ensure_initialized()
            job_store.mark_running(job_id)
            _update_local_cache_progress(job_id, 0.01, "running")
            
            # Select DiT handler based on user's model choice
            # Default: use primary handler
            selected_handler: AceStepHandler = app.state.handler
            selected_model_name = _get_model_name(app.state._config_path)
            
            if req.model:
                model_matched = False
                
                # Check if it matches the second model
                if app.state.handler2 and getattr(app.state, "_initialized2", False):
                    model2_name = _get_model_name(app.state._config_path2)
                    if req.model == model2_name:
                        selected_handler = app.state.handler2
                        selected_model_name = model2_name
                        model_matched = True
                        print(f"[API Server] Job {job_id}: Using second model: {model2_name}")
                
                # Check if it matches the third model
                if not model_matched and app.state.handler3 and getattr(app.state, "_initialized3", False):
                    model3_name = _get_model_name(app.state._config_path3)
                    if req.model == model3_name:
                        selected_handler = app.state.handler3
                        selected_model_name = model3_name
                        model_matched = True
                        print(f"[API Server] Job {job_id}: Using third model: {model3_name}")
                
                if not model_matched:
                    available_models = [_get_model_name(app.state._config_path)]
                    if app.state.handler2 and getattr(app.state, "_initialized2", False):
                        available_models.append(_get_model_name(app.state._config_path2))
                    if app.state.handler3 and getattr(app.state, "_initialized3", False):
                        available_models.append(_get_model_name(app.state._config_path3))
                    print(f"[API Server] Job {job_id}: Model '{req.model}' not found in {available_models}, using primary: {selected_model_name}")
            
            # Use selected handler for generation
            h: AceStepHandler = selected_handler

            def _blocking_generate() -> Dict[str, Any]:
                """Generate music using unified inference logic from acestep.inference"""

                def _ensure_llm_ready() -> None:
                    """Ensure LLM handler is initialized when needed"""
                    with app.state._llm_init_lock:
                        initialized = getattr(app.state, "_llm_initialized", False)
                        had_error = getattr(app.state, "_llm_init_error", None)
                        if initialized or had_error is not None:
                            return
                        print("[API Server] reloading.")

                        # Check if lazy loading is disabled (GPU memory insufficient)
                        if getattr(app.state, "_llm_lazy_load_disabled", False):
                            app.state._llm_init_error = (
                                "LLM not initialized at startup. To enable LLM, set ACESTEP_INIT_LLM=true "
                                "in .env or environment variables. For this request, optional LLM features "
                                "(use_cot_caption, use_cot_language) will be auto-disabled."
                            )
                            print(f"[API Server] LLM lazy load blocked: LLM was not initialized at startup")
                            return

                        project_root = _get_project_root()
                        checkpoint_dir = os.path.join(project_root, "checkpoints")
                        lm_model_path = (req.lm_model_path or os.getenv("ACESTEP_LM_MODEL_PATH") or "acestep-5Hz-lm-0.6B").strip()
                        backend = (req.lm_backend or os.getenv("ACESTEP_LM_BACKEND") or "vllm").strip().lower()
                        if backend not in {"vllm", "pt"}:
                            backend = "vllm"

                        # Auto-download LM model if not present
                        lm_model_name = _get_model_name(lm_model_path)
                        if lm_model_name:
                            try:
                                _ensure_model_downloaded(lm_model_name, checkpoint_dir)
                            except Exception as e:
                                print(f"[API Server] Warning: Failed to download LM model {lm_model_name}: {e}")

                        lm_device = os.getenv("ACESTEP_LM_DEVICE", os.getenv("ACESTEP_DEVICE", "auto"))
                        lm_offload = _env_bool("ACESTEP_LM_OFFLOAD_TO_CPU", False)

                        status, ok = llm.initialize(
                            checkpoint_dir=checkpoint_dir,
                            lm_model_path=lm_model_path,
                            backend=backend,
                            device=lm_device,
                            offload_to_cpu=lm_offload,
                            dtype=h.dtype,
                        )
                        if not ok:
                            app.state._llm_init_error = status
                        else:
                            app.state._llm_initialized = True

                def _normalize_metas(meta: Dict[str, Any]) -> Dict[str, Any]:
                    """Ensure a stable `metas` dict (keys always present)."""
                    meta = meta or {}
                    out: Dict[str, Any] = dict(meta)

                    # Normalize key aliases
                    if "keyscale" not in out and "key_scale" in out:
                        out["keyscale"] = out.get("key_scale")
                    if "timesignature" not in out and "time_signature" in out:
                        out["timesignature"] = out.get("time_signature")

                    # Ensure required keys exist
                    for k in ["bpm", "duration", "genres", "keyscale", "timesignature"]:
                        if out.get(k) in (None, ""):
                            out[k] = "N/A"
                    return out

                # Normalize LM sampling parameters
                lm_top_k = req.lm_top_k if req.lm_top_k and req.lm_top_k > 0 else 0
                lm_top_p = req.lm_top_p if req.lm_top_p and req.lm_top_p < 1.0 else 0.9

                # Determine if LLM is needed
                thinking = bool(req.thinking)
                sample_mode = bool(req.sample_mode)
                has_sample_query = bool(req.sample_query and req.sample_query.strip())
                use_format = bool(req.use_format)
                use_cot_caption = bool(req.use_cot_caption)
                use_cot_language = bool(req.use_cot_language)
                
                # Unload LM for cover tasks on MPS to reduce memory; reload lazily when needed.
                if req.task_type == "cover" and h.device == "mps":
                    if getattr(app.state, "_llm_initialized", False) and getattr(llm, "llm_initialized", False):
                        try:
                            print("[API Server] unloading.")
                            llm.unload()
                            app.state._llm_initialized = False
                            app.state._llm_init_error = None
                        except Exception as e:
                            print(f"[API Server] Failed to unload LM: {e}")

                # LLM is needed for:

                # LLM is REQUIRED for these features (fail if unavailable):
                # - thinking mode (LM generates audio codes)
                # - sample_mode (LM generates random caption/lyrics/metas)
                # - sample_query/description (LM generates from description)
                # - use_format (LM enhances caption/lyrics)
                require_llm = thinking or sample_mode or has_sample_query or use_format

                # LLM is OPTIONAL for these features (auto-disable if unavailable):
                # - use_cot_caption or use_cot_language (LM enhances metadata)
                want_llm = use_cot_caption or use_cot_language

                # Check if LLM is available
                llm_available = True
                if require_llm or want_llm:
                    _ensure_llm_ready()
                    if getattr(app.state, "_llm_init_error", None):
                        llm_available = False

                # Fail if LLM is required but unavailable
                if require_llm and not llm_available:
                    raise RuntimeError(f"5Hz LM init failed: {app.state._llm_init_error}")

                # Auto-disable optional LLM features if unavailable
                if want_llm and not llm_available:
                    if use_cot_caption or use_cot_language:
                        print(f"[API Server] LLM unavailable, auto-disabling: use_cot_caption={use_cot_caption}->False, use_cot_language={use_cot_language}->False")
                    use_cot_caption = False
                    use_cot_language = False

                # Handle sample mode or description: generate caption/lyrics/metas via LM
                caption = req.prompt
                lyrics = req.lyrics
                bpm = req.bpm
                key_scale = req.key_scale
                time_signature = req.time_signature
                audio_duration = req.audio_duration

                # Save original user input for metas
                original_prompt = req.prompt or ""
                original_lyrics = req.lyrics or ""
                
                if sample_mode or has_sample_query:
                    # Parse description hints from sample_query (if provided)
                    sample_query = req.sample_query if has_sample_query else "NO USER INPUT"
                    parsed_language, parsed_instrumental = _parse_description_hints(sample_query)

                    # Determine vocal_language with priority:
                    # 1. User-specified vocal_language (if not default "en")
                    # 2. Language parsed from description
                    # 3. None (no constraint)
                    if req.vocal_language and req.vocal_language not in ("en", "unknown", ""):
                        sample_language = req.vocal_language
                    else:
                        sample_language = parsed_language

                    sample_result = create_sample(
                        llm_handler=llm,
                        query=sample_query,
                        instrumental=parsed_instrumental,
                        vocal_language=sample_language,
                        temperature=req.lm_temperature,
                        top_k=lm_top_k if lm_top_k > 0 else None,
                        top_p=lm_top_p if lm_top_p < 1.0 else None,
                        use_constrained_decoding=True,
                    )

                    if not sample_result.success:
                        raise RuntimeError(f"create_sample failed: {sample_result.error or sample_result.status_message}")

                    # Use generated sample data
                    caption = sample_result.caption
                    lyrics = sample_result.lyrics
                    bpm = sample_result.bpm
                    key_scale = sample_result.keyscale
                    time_signature = sample_result.timesignature
                    audio_duration = sample_result.duration

                # Apply format_sample() if use_format is True and caption/lyrics are provided
                format_has_duration = False

                if req.use_format and (caption or lyrics):
                    _ensure_llm_ready()
                    if getattr(app.state, "_llm_init_error", None):
                        raise RuntimeError(f"5Hz LM init failed (needed for format): {app.state._llm_init_error}")
                    
                    # Build user_metadata from request params (matching bot.py behavior)
                    user_metadata_for_format = {}
                    if bpm is not None:
                        user_metadata_for_format['bpm'] = bpm
                    if audio_duration is not None and float(audio_duration) > 0:
                        user_metadata_for_format['duration'] = float(audio_duration)
                    if key_scale:
                        user_metadata_for_format['keyscale'] = key_scale
                    if time_signature:
                        user_metadata_for_format['timesignature'] = time_signature
                    if req.vocal_language and req.vocal_language != "unknown":
                        user_metadata_for_format['language'] = req.vocal_language
                    
                    format_result = format_sample(
                        llm_handler=llm,
                        caption=caption,
                        lyrics=lyrics,
                        user_metadata=user_metadata_for_format if user_metadata_for_format else None,
                        temperature=req.lm_temperature,
                        top_k=lm_top_k if lm_top_k > 0 else None,
                        top_p=lm_top_p if lm_top_p < 1.0 else None,
                        use_constrained_decoding=True,
                    )
                    
                    if format_result.success:
                        # Extract all formatted data (matching bot.py behavior)
                        caption = format_result.caption or caption
                        lyrics = format_result.lyrics or lyrics
                        if format_result.duration:
                            audio_duration = format_result.duration
                            format_has_duration = True
                        if format_result.bpm:
                            bpm = format_result.bpm
                        if format_result.keyscale:
                            key_scale = format_result.keyscale
                        if format_result.timesignature:
                            time_signature = format_result.timesignature

                # Parse timesteps string to list of floats if provided
                parsed_timesteps = _parse_timesteps(req.timesteps)

                # Determine actual inference steps (timesteps override inference_steps)
                actual_inference_steps = len(parsed_timesteps) if parsed_timesteps else req.inference_steps

                # Auto-select instruction based on task_type if user didn't provide custom instruction
                # This matches gradio behavior which uses TASK_INSTRUCTIONS for each task type
                instruction_to_use = req.instruction
                if instruction_to_use == DEFAULT_DIT_INSTRUCTION and req.task_type in TASK_INSTRUCTIONS:
                    instruction_to_use = TASK_INSTRUCTIONS[req.task_type]

                # Build GenerationParams using unified interface
                # Note: thinking controls LM code generation, sample_mode only affects CoT metas
                params = GenerationParams(
                    task_type=req.task_type,
                    instruction=instruction_to_use,
                    reference_audio=req.reference_audio_path,
                    src_audio=req.src_audio_path,
                    audio_codes=req.audio_code_string,
                    caption=caption,
                    lyrics=lyrics,
                    instrumental=_is_instrumental(lyrics),
                    vocal_language=req.vocal_language,
                    bpm=bpm,
                    keyscale=key_scale,
                    timesignature=time_signature,
                    duration=audio_duration if audio_duration else -1.0,
                    inference_steps=req.inference_steps,
                    seed=req.seed,
                    guidance_scale=req.guidance_scale,
                    use_adg=req.use_adg,
                    cfg_interval_start=req.cfg_interval_start,
                    cfg_interval_end=req.cfg_interval_end,
                    shift=req.shift,
                    infer_method=req.infer_method,
                    timesteps=parsed_timesteps,
                    repainting_start=req.repainting_start,
                    repainting_end=req.repainting_end if req.repainting_end else -1,
                    audio_cover_strength=req.audio_cover_strength,
                    # LM parameters
                    thinking=thinking,  # Use LM for code generation when thinking=True
                    lm_temperature=req.lm_temperature,
                    lm_cfg_scale=req.lm_cfg_scale,
                    lm_top_k=lm_top_k,
                    lm_top_p=lm_top_p,
                    lm_negative_prompt=req.lm_negative_prompt,
                    # use_cot_metas logic:
                    # - sample_mode: metas already generated, skip Phase 1
                    # - format with duration: metas already generated, skip Phase 1
                    # - format without duration: need Phase 1 to generate duration
                    # - no format: need Phase 1 to generate all metas
                    use_cot_metas=not sample_mode and not format_has_duration,
                    use_cot_caption=use_cot_caption,  # Use local var (may be auto-disabled)
                    use_cot_language=use_cot_language,  # Use local var (may be auto-disabled)
                    use_constrained_decoding=True,
                )

                # Build GenerationConfig - default to 2 audios like gradio_ui
                batch_size = req.batch_size if req.batch_size is not None else 2
                config = GenerationConfig(
                    batch_size=batch_size,
                    allow_lm_batch=req.allow_lm_batch,
                    use_random_seed=req.use_random_seed,
                    seeds=None,  # Let unified logic handle seed generation
                    audio_format=req.audio_format,
                    constrained_decoding_debug=req.constrained_decoding_debug,
                )

                # Check LLM initialization status
                llm_is_initialized = getattr(app.state, "_llm_initialized", False)
                llm_to_pass = llm if llm_is_initialized else None

                # Progress callback for API polling
                last_progress = {"value": -1.0, "time": 0.0, "stage": ""}

                def _progress_cb(value: float, desc: str = "") -> None:
                    now = time.time()
                    try:
                        value_f = max(0.0, min(1.0, float(value)))
                    except Exception:
                        value_f = 0.0
                    stage = desc or last_progress["stage"] or "running"
                    # Throttle updates to avoid excessive cache writes
                    if (
                        value_f - last_progress["value"] >= 0.01
                        or stage != last_progress["stage"]
                        or (now - last_progress["time"]) >= 0.5
                    ):
                        last_progress["value"] = value_f
                        last_progress["time"] = now
                        last_progress["stage"] = stage
                        job_store.update_progress(job_id, value_f, stage=stage)
                        _update_local_cache_progress(job_id, value_f, stage)
                if req.analysis_only:
                    lm_res = llm_to_pass.generate_with_stop_condition(
                        caption=params.caption,
                        lyrics=params.lyrics,
                        infer_type="dit",
                        temperature=req.lm_temperature,
                        top_p=req.lm_top_p,
                        use_cot_metas=True,
                        use_cot_caption=req.use_cot_caption,
                        use_cot_language=req.use_cot_language,
                        use_constrained_decoding=True
                    )

                    if not lm_res.get("success"):
                        raise RuntimeError(f"Analysis Failed: {lm_res.get('error')}")

                    metas_found = lm_res.get("metadata", {})
                    return {
                        "first_audio_path": None,
                        "audio_paths": [],
                        "generation_info": "Analysis Only Mode Complete",
                        "status_message": "Success",
                        "metas": metas_found,
                        "bpm": metas_found.get("bpm"),
                        "keyscale": metas_found.get("keyscale"),
                        "duration": metas_found.get("duration"),
                        "prompt": metas_found.get("caption", params.caption),
                        "lyrics": params.lyrics,
                        "lm_model": os.getenv("ACESTEP_LM_MODEL_PATH", ""),
                        "dit_model": "None (Analysis Only)"
                    }

                # Generate music using unified interface
                sequential_runs = 1
                if req.task_type == "cover" and h.device == "mps":
                    # If user asked for multiple outputs, run sequentially on MPS to avoid OOM.
                    if config.batch_size is not None and config.batch_size > 1:
                        sequential_runs = int(config.batch_size)
                        config.batch_size = 1
                        print(f"[API Server] Job {job_id}: MPS cover sequential mode enabled (runs={sequential_runs})")

                def _progress_for_slice(start: float, end: float):
                    base = {"seen": False, "value": 0.0}
                    def _cb(value: float, desc: str = "") -> None:
                        try:
                            value_f = max(0.0, min(1.0, float(value)))
                        except Exception:
                            value_f = 0.0
                        if not base["seen"]:
                            base["seen"] = True
                            base["value"] = value_f
                        # Normalize progress to avoid initial jump (e.g., 0.51 -> 0.0)
                        if value_f <= base["value"]:
                            norm = 0.0
                        else:
                            denom = max(1e-6, 1.0 - base["value"])
                            norm = min(1.0, (value_f - base["value"]) / denom)
                        mapped = start + (end - start) * norm
                        _progress_cb(mapped, desc=desc)
                    return _cb

                aggregated_result = None
                all_audios: List[Dict[str, Any]] = []
                for run_idx in range(sequential_runs):
                    if sequential_runs > 1:
                        print(f"[API Server] Job {job_id}: Sequential cover run {run_idx + 1}/{sequential_runs}")
                    if sequential_runs > 1:
                        start = run_idx / sequential_runs
                        end = (run_idx + 1) / sequential_runs
                        progress_cb = _progress_for_slice(start, end)
                    else:
                        progress_cb = _progress_cb

                    result = generate_music(
                        dit_handler=h,
                        llm_handler=llm_to_pass,
                        params=params,
                        config=config,
                        save_dir=app.state.temp_audio_dir,
                        progress=progress_cb,
                    )
                    if not result.success:
                        raise RuntimeError(f"Music generation failed: {result.error or result.status_message}")

                    if aggregated_result is None:
                        aggregated_result = result
                    all_audios.extend(result.audios)

                # Use aggregated result with combined audios
                if aggregated_result is None:
                    raise RuntimeError("Music generation failed: no results")
                aggregated_result.audios = all_audios
                result = aggregated_result

                if not result.success:
                    raise RuntimeError(f"Music generation failed: {result.error or result.status_message}")

                # Extract results
                audio_paths = [audio["path"] for audio in result.audios if audio.get("path")]
                first_audio = audio_paths[0] if len(audio_paths) > 0 else None
                second_audio = audio_paths[1] if len(audio_paths) > 1 else None

                # Get metadata from LM or CoT results
                lm_metadata = result.extra_outputs.get("lm_metadata", {})
                metas_out = _normalize_metas(lm_metadata)
                
                # Update metas with actual values used
                if params.cot_bpm:
                    metas_out["bpm"] = params.cot_bpm
                elif bpm:
                    metas_out["bpm"] = bpm
                    
                if params.cot_duration:
                    metas_out["duration"] = params.cot_duration
                elif audio_duration:
                    metas_out["duration"] = audio_duration
                    
                if params.cot_keyscale:
                    metas_out["keyscale"] = params.cot_keyscale
                elif key_scale:
                    metas_out["keyscale"] = key_scale
                    
                if params.cot_timesignature:
                    metas_out["timesignature"] = params.cot_timesignature
                elif time_signature:
                    metas_out["timesignature"] = time_signature

                # Store original user input in metas (not the final/modified values)
                metas_out["prompt"] = original_prompt
                metas_out["lyrics"] = original_lyrics

                # Extract seed values for response (comma-separated for multiple audios)
                seed_values = []
                for audio in result.audios:
                    audio_params = audio.get("params", {})
                    seed = audio_params.get("seed")
                    if seed is not None:
                        seed_values.append(str(seed))
                seed_value = ",".join(seed_values) if seed_values else ""

                # Build generation_info using the helper function (like gradio_ui)
                time_costs = result.extra_outputs.get("time_costs", {})
                generation_info = _build_generation_info(
                    lm_metadata=lm_metadata,
                    time_costs=time_costs,
                    seed_value=seed_value,
                    inference_steps=req.inference_steps,
                    num_audios=len(result.audios),
                )

                def _none_if_na_str(v: Any) -> Optional[str]:
                    if v is None:
                        return None
                    s = str(v).strip()
                    if s in {"", "N/A"}:
                        return None
                    return s

                # Get model information
                lm_model_name = os.getenv("ACESTEP_LM_MODEL_PATH", "acestep-5Hz-lm-0.6B")
                # Use selected_model_name (set at the beginning of _run_one_job)
                dit_model_name = selected_model_name
                
                return {
                    "first_audio_path": _path_to_audio_url(first_audio) if first_audio else None,
                    "second_audio_path": _path_to_audio_url(second_audio) if second_audio else None,
                    "audio_paths": [_path_to_audio_url(p) for p in audio_paths],
                    "generation_info": generation_info,
                    "status_message": result.status_message,
                    "seed_value": seed_value,
                    # Final prompt/lyrics (may be modified by thinking/format)
                    "prompt": caption or "",
                    "lyrics": lyrics or "",
                    # metas contains original user input + other metadata
                    "metas": metas_out,
                    "bpm": metas_out.get("bpm") if isinstance(metas_out.get("bpm"), int) else None,
                    "duration": metas_out.get("duration") if isinstance(metas_out.get("duration"), (int, float)) else None,
                    "genres": _none_if_na_str(metas_out.get("genres")),
                    "keyscale": _none_if_na_str(metas_out.get("keyscale")),
                    "timesignature": _none_if_na_str(metas_out.get("timesignature")),
                    "lm_model": lm_model_name,
                    "dit_model": dit_model_name,
                }

            t0 = time.time()
            try:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(executor, _blocking_generate)
                job_store.mark_succeeded(job_id, result)

                # Update local cache
                _update_local_cache(job_id, result, "succeeded")
            except Exception as e:
                error_traceback = traceback.format_exc()
                print(f"[API Server] Job {job_id} FAILED: {e}")
                print(f"[API Server] Traceback:\n{error_traceback}")
                job_store.mark_failed(job_id, error_traceback)

                # Update local cache
                _update_local_cache(job_id, None, "failed")
            finally:
                # Best-effort cache cleanup to reduce MPS memory fragmentation between jobs
                try:
                    if hasattr(h, "_empty_cache"):
                        h._empty_cache()
                    else:
                        import torch
                        if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                            torch.mps.empty_cache()
                except Exception:
                    pass
                dt = max(0.0, time.time() - t0)
                async with app.state.stats_lock:
                    app.state.recent_durations.append(dt)
                    if app.state.recent_durations:
                        app.state.avg_job_seconds = sum(app.state.recent_durations) / len(app.state.recent_durations)

        async def _queue_worker(worker_idx: int) -> None:
            while True:
                job_id, req = await app.state.job_queue.get()
                try:
                    async with app.state.pending_lock:
                        try:
                            app.state.pending_ids.remove(job_id)
                        except ValueError:
                            pass

                    await _run_one_job(job_id, req)
                finally:
                    await _cleanup_job_temp_files(job_id)
                    app.state.job_queue.task_done()

        async def _job_store_cleanup_worker() -> None:
            """Background task to periodically clean up old completed jobs."""
            while True:
                try:
                    await asyncio.sleep(JOB_STORE_CLEANUP_INTERVAL)
                    removed = store.cleanup_old_jobs()
                    if removed > 0:
                        stats = store.get_stats()
                        print(f"[API Server] Cleaned up {removed} old jobs. Current stats: {stats}")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"[API Server] Job cleanup error: {e}")

        worker_count = max(1, WORKER_COUNT)
        workers = [asyncio.create_task(_queue_worker(i)) for i in range(worker_count)]
        cleanup_task = asyncio.create_task(_job_store_cleanup_worker())
        app.state.worker_tasks = workers
        app.state.cleanup_task = cleanup_task

        # =================================================================
        # Initialize models at startup (not lazily on first request)
        # =================================================================
        print("[API Server] Initializing models at startup...")

        # Detect GPU memory and get configuration
        gpu_config = get_gpu_config()
        set_global_gpu_config(gpu_config)
        app.state.gpu_config = gpu_config

        gpu_memory_gb = gpu_config.gpu_memory_gb
        auto_offload = gpu_memory_gb > 0 and gpu_memory_gb < VRAM_16GB_MIN_GB

        # Print GPU configuration info
        print(f"\n{'='*60}")
        print("[API Server] GPU Configuration Detected:")
        print(f"{'='*60}")
        print(f"  GPU Memory: {gpu_memory_gb:.2f} GB")
        print(f"  Configuration Tier: {gpu_config.tier}")
        print(f"  Max Duration (with LM): {gpu_config.max_duration_with_lm}s")
        print(f"  Max Duration (without LM): {gpu_config.max_duration_without_lm}s")
        print(f"  Max Batch Size (with LM): {gpu_config.max_batch_size_with_lm}")
        print(f"  Max Batch Size (without LM): {gpu_config.max_batch_size_without_lm}")
        print(f"  Default LM Init: {gpu_config.init_lm_default}")
        print(f"  Available LM Models: {gpu_config.available_lm_models or 'None'}")
        print(f"{'='*60}\n")

        if auto_offload:
            print(f"[API Server] Auto-enabling CPU offload (GPU < 16GB)")
        elif gpu_memory_gb > 0:
            print(f"[API Server] CPU offload disabled by default (GPU >= 16GB)")
        else:
            print("[API Server] No GPU detected, running on CPU")

        project_root = _get_project_root()
        config_path = os.getenv("ACESTEP_CONFIG_PATH", "acestep-v15-turbo")
        device = os.getenv("ACESTEP_DEVICE", "auto")
        use_flash_attention = _env_bool("ACESTEP_USE_FLASH_ATTENTION", True)

        # Auto-determine offload settings based on GPU config if not explicitly set
        offload_to_cpu_env = os.getenv("ACESTEP_OFFLOAD_TO_CPU")
        if offload_to_cpu_env is not None:
            offload_to_cpu = _env_bool("ACESTEP_OFFLOAD_TO_CPU", False)
        else:
            offload_to_cpu = auto_offload
            if auto_offload:
                print(f"[API Server] Auto-setting offload_to_cpu=True based on GPU memory")

        offload_dit_to_cpu = _env_bool("ACESTEP_OFFLOAD_DIT_TO_CPU", False)

        # Checkpoint directory
        checkpoint_dir = os.path.join(project_root, "checkpoints")
        os.makedirs(checkpoint_dir, exist_ok=True)

        # Download and initialize primary DiT model
        dit_model_name = _get_model_name(config_path)
        if dit_model_name:
            try:
                _ensure_model_downloaded(dit_model_name, checkpoint_dir)
            except Exception as e:
                print(f"[API Server] Warning: Failed to download DiT model: {e}")

        # Download VAE model
        try:
            _ensure_model_downloaded("vae", checkpoint_dir)
        except Exception as e:
            print(f"[API Server] Warning: Failed to download VAE model: {e}")

        print(f"[API Server] Loading primary DiT model: {config_path}")
        status_msg, ok = handler.initialize_service(
            project_root=project_root,
            config_path=config_path,
            device=device,
            use_flash_attention=use_flash_attention,
            compile_model=False,
            offload_to_cpu=offload_to_cpu,
            offload_dit_to_cpu=offload_dit_to_cpu,
        )
        if not ok:
            app.state._init_error = status_msg
            print(f"[API Server] ERROR: Primary model failed to load: {status_msg}")
            raise RuntimeError(status_msg)
        app.state._initialized = True
        print(f"[API Server] Primary model loaded: {_get_model_name(config_path)}")

        # Initialize secondary model if configured
        if handler2 and config_path2:
            model2_name = _get_model_name(config_path2)
            if model2_name:
                try:
                    _ensure_model_downloaded(model2_name, checkpoint_dir)
                except Exception as e:
                    print(f"[API Server] Warning: Failed to download secondary model: {e}")

            print(f"[API Server] Loading secondary DiT model: {config_path2}")
            try:
                status_msg2, ok2 = handler2.initialize_service(
                    project_root=project_root,
                    config_path=config_path2,
                    device=device,
                    use_flash_attention=use_flash_attention,
                    compile_model=False,
                    offload_to_cpu=offload_to_cpu,
                    offload_dit_to_cpu=offload_dit_to_cpu,
                )
                app.state._initialized2 = ok2
                if ok2:
                    print(f"[API Server] Secondary model loaded: {model2_name}")
                else:
                    print(f"[API Server] Warning: Secondary model failed: {status_msg2}")
            except Exception as e:
                print(f"[API Server] Warning: Failed to initialize secondary model: {e}")
                app.state._initialized2 = False

        # Initialize third model if configured
        if handler3 and config_path3:
            model3_name = _get_model_name(config_path3)
            if model3_name:
                try:
                    _ensure_model_downloaded(model3_name, checkpoint_dir)
                except Exception as e:
                    print(f"[API Server] Warning: Failed to download third model: {e}")

            print(f"[API Server] Loading third DiT model: {config_path3}")
            try:
                status_msg3, ok3 = handler3.initialize_service(
                    project_root=project_root,
                    config_path=config_path3,
                    device=device,
                    use_flash_attention=use_flash_attention,
                    compile_model=False,
                    offload_to_cpu=offload_to_cpu,
                    offload_dit_to_cpu=offload_dit_to_cpu,
                )
                app.state._initialized3 = ok3
                if ok3:
                    print(f"[API Server] Third model loaded: {model3_name}")
                else:
                    print(f"[API Server] Warning: Third model failed: {status_msg3}")
            except Exception as e:
                print(f"[API Server] Warning: Failed to initialize third model: {e}")
                app.state._initialized3 = False

        # Initialize LLM model based on GPU configuration
        # ACESTEP_INIT_LLM controls LLM initialization:
        #   - "auto" / empty / not set: Use GPU config default (auto-detect)
        #   - "true"/"1"/"yes": Force enable LLM after GPU config is applied
        #   - "false"/"0"/"no": Force disable LLM
        #
        # Flow: GPU detection → model validation → ACESTEP_INIT_LLM override
        # This ensures GPU optimizations (offload, quantization, etc.) are always applied.
        init_llm_env = os.getenv("ACESTEP_INIT_LLM", "").strip().lower()

        # Step 1: Start with GPU auto-detection result
        init_llm = gpu_config.init_lm_default
        print(f"[API Server] GPU auto-detection: init_llm={init_llm} (VRAM: {gpu_config.gpu_memory_gb:.1f}GB, tier: {gpu_config.tier})")

        # Step 2: Apply user override if set
        if not init_llm_env or init_llm_env == "auto":
            print(f"[API Server] ACESTEP_INIT_LLM=auto, using GPU auto-detection result")
        elif init_llm_env in {"1", "true", "yes", "y", "on"}:
            if init_llm:
                print(f"[API Server] ACESTEP_INIT_LLM=true (GPU already supports LLM, no override needed)")
            else:
                init_llm = True
                print(f"[API Server] ACESTEP_INIT_LLM=true, overriding GPU auto-detection (force enable)")
        else:
            if not init_llm:
                print(f"[API Server] ACESTEP_INIT_LLM=false (GPU already disabled LLM, no override needed)")
            else:
                init_llm = False
                print(f"[API Server] ACESTEP_INIT_LLM=false, overriding GPU auto-detection (force disable)")

        if init_llm:
            print("[API Server] Loading LLM model...")

            # Auto-select LM model based on GPU config if not explicitly set
            lm_model_path_env = os.getenv("ACESTEP_LM_MODEL_PATH", "").strip()
            if lm_model_path_env:
                lm_model_path = lm_model_path_env
                print(f"[API Server] Using user-specified LM model: {lm_model_path}")
            else:
                # Get recommended LM model for this GPU tier
                recommended_lm = get_recommended_lm_model(gpu_config)
                if recommended_lm:
                    lm_model_path = recommended_lm
                    print(f"[API Server] Auto-selected LM model: {lm_model_path} based on GPU tier")
                else:
                    # No recommended model (GPU tier too low), default to smallest
                    lm_model_path = "acestep-5Hz-lm-0.6B"
                    print(f"[API Server] No recommended model for this GPU tier, using smallest: {lm_model_path}")

            # Validate LM model support (warning only, does not block)
            is_supported, warning_msg = is_lm_model_supported(lm_model_path, gpu_config)
            if not is_supported:
                print(f"[API Server] Warning: {warning_msg}")
                # Try to fall back to a supported model
                recommended_lm = get_recommended_lm_model(gpu_config)
                if recommended_lm:
                    lm_model_path = recommended_lm
                    print(f"[API Server] Falling back to supported LM model: {lm_model_path}")
                else:
                    # No supported model, but user may have forced init
                    print(f"[API Server] No GPU-validated LM model available, attempting {lm_model_path} anyway (may cause OOM)")

        if init_llm:
            lm_backend = os.getenv("ACESTEP_LM_BACKEND", "vllm").strip().lower()
            if lm_backend not in {"vllm", "pt"}:
                lm_backend = "vllm"
            lm_device = os.getenv("ACESTEP_LM_DEVICE", device)

            # Auto-determine LM offload based on GPU config
            lm_offload_env = os.getenv("ACESTEP_LM_OFFLOAD_TO_CPU")
            if lm_offload_env is not None:
                lm_offload = _env_bool("ACESTEP_LM_OFFLOAD_TO_CPU", False)
            else:
                lm_offload = offload_to_cpu

            try:
                _ensure_model_downloaded(lm_model_path, checkpoint_dir)
            except Exception as e:
                print(f"[API Server] Warning: Failed to download LLM model: {e}")

            llm_status, llm_ok = llm_handler.initialize(
                checkpoint_dir=checkpoint_dir,
                lm_model_path=lm_model_path,
                backend=lm_backend,
                device=lm_device,
                offload_to_cpu=lm_offload,
                dtype=handler.dtype,
            )
            if llm_ok:
                app.state._llm_initialized = True
                print(f"[API Server] LLM model loaded: {lm_model_path}")
            else:
                app.state._llm_init_error = llm_status
                print(f"[API Server] Warning: LLM model failed to load: {llm_status}")
        else:
            print("[API Server] Skipping LLM initialization (disabled or not supported for this GPU)")
            app.state._llm_initialized = False
            # Disable lazy loading of LLM - don't try to load it later during requests
            app.state._llm_lazy_load_disabled = True
            print("[API Server] LLM lazy loading disabled. To enable LLM:")
            print("[API Server]   - Set ACESTEP_INIT_LLM=true in .env or environment")
            print("[API Server]   - Or use --init-llm command line flag")

        print("[API Server] All models initialized successfully!")

        try:
            yield
        finally:
            cleanup_task.cancel()
            for t in workers:
                t.cancel()
            executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="ACE-Step API", version="1.0", lifespan=lifespan)

    async def _queue_position(job_id: str) -> int:
        async with app.state.pending_lock:
            try:
                return list(app.state.pending_ids).index(job_id) + 1
            except ValueError:
                return 0

    async def _eta_seconds_for_position(pos: int) -> Optional[float]:
        if pos <= 0:
            return None
        async with app.state.stats_lock:
            avg = float(getattr(app.state, "avg_job_seconds", INITIAL_AVG_JOB_SECONDS))
        return pos * avg

    @app.post("/release_task")
    async def create_music_generate_job(request: Request, authorization: Optional[str] = Header(None)):
        content_type = (request.headers.get("content-type") or "").lower()
        temp_files: list[str] = []

        def _build_request(p: RequestParser, **kwargs) -> GenerateMusicRequest:
            """Build GenerateMusicRequest from parsed parameters."""
            return GenerateMusicRequest(
                prompt=p.str("prompt"),
                lyrics=p.str("lyrics"),
                thinking=p.bool("thinking"),
                analysis_only=p.bool("analysis_only"),
                sample_mode=p.bool("sample_mode"),
                sample_query=p.str("sample_query"),
                use_format=p.bool("use_format"),
                model=p.str("model") or None,
                bpm=p.int("bpm"),
                key_scale=p.str("key_scale"),
                time_signature=p.str("time_signature"),
                audio_duration=p.float("audio_duration"),
                vocal_language=p.str("vocal_language", "en"),
                inference_steps=p.int("inference_steps", 8),
                guidance_scale=p.float("guidance_scale", 7.0),
                use_random_seed=p.bool("use_random_seed", True),
                seed=p.int("seed", -1),
                batch_size=p.int("batch_size"),
                audio_code_string=p.str("audio_code_string"),
                repainting_start=p.float("repainting_start", 0.0),
                repainting_end=p.float("repainting_end"),
                instruction=p.str("instruction", DEFAULT_DIT_INSTRUCTION),
                audio_cover_strength=p.float("audio_cover_strength", 1.0),
                reference_audio_path=p.str("reference_audio_path") or None,
                src_audio_path=p.str("src_audio_path") or None,
                task_type=p.str("task_type", "text2music"),
                use_adg=p.bool("use_adg"),
                cfg_interval_start=p.float("cfg_interval_start", 0.0),
                cfg_interval_end=p.float("cfg_interval_end", 1.0),
                infer_method=p.str("infer_method", "ode"),
                shift=p.float("shift", 3.0),
                audio_format=p.str("audio_format", "mp3"),
                use_tiled_decode=p.bool("use_tiled_decode", True),
                lm_model_path=p.str("lm_model_path") or None,
                lm_backend=p.str("lm_backend", "vllm"),
                lm_temperature=p.float("lm_temperature", LM_DEFAULT_TEMPERATURE),
                lm_cfg_scale=p.float("lm_cfg_scale", LM_DEFAULT_CFG_SCALE),
                lm_top_k=p.int("lm_top_k"),
                lm_top_p=p.float("lm_top_p", LM_DEFAULT_TOP_P),
                lm_repetition_penalty=p.float("lm_repetition_penalty", 1.0),
                lm_negative_prompt=p.str("lm_negative_prompt", "NO USER INPUT"),
                constrained_decoding=p.bool("constrained_decoding", True),
                constrained_decoding_debug=p.bool("constrained_decoding_debug"),
                use_cot_caption=p.bool("use_cot_caption", True),
                use_cot_language=p.bool("use_cot_language", True),
                is_format_caption=p.bool("is_format_caption"),
                allow_lm_batch=p.bool("allow_lm_batch", True),
                **kwargs,
            )

        if content_type.startswith("application/json"):
            body = await request.json()
            if not isinstance(body, dict):
                raise HTTPException(status_code=400, detail="JSON payload must be an object")
            verify_token_from_request(body, authorization)
            req = _build_request(RequestParser(body))

        elif content_type.endswith("+json"):
            body = await request.json()
            if not isinstance(body, dict):
                raise HTTPException(status_code=400, detail="JSON payload must be an object")
            verify_token_from_request(body, authorization)
            req = _build_request(RequestParser(body))

        elif content_type.startswith("multipart/form-data"):
            form = await request.form()
            form_dict = {k: v for k, v in form.items() if not hasattr(v, 'read')}
            verify_token_from_request(form_dict, authorization)

            # Support both naming conventions: ref_audio/reference_audio, ctx_audio/src_audio
            ref_up = form.get("ref_audio") or form.get("reference_audio")
            ctx_up = form.get("ctx_audio") or form.get("src_audio")

            reference_audio_path = None
            src_audio_path = None

            if isinstance(ref_up, StarletteUploadFile):
                reference_audio_path = await _save_upload_to_temp(ref_up, prefix="ref_audio")
                temp_files.append(reference_audio_path)
            else:
                reference_audio_path = str(form.get("ref_audio_path") or form.get("reference_audio_path") or "").strip() or None

            if isinstance(ctx_up, StarletteUploadFile):
                src_audio_path = await _save_upload_to_temp(ctx_up, prefix="ctx_audio")
                temp_files.append(src_audio_path)
            else:
                src_audio_path = str(form.get("ctx_audio_path") or form.get("src_audio_path") or "").strip() or None

            req = _build_request(
                RequestParser(dict(form)),
                reference_audio_path=reference_audio_path,
                src_audio_path=src_audio_path,
            )

        elif content_type.startswith("application/x-www-form-urlencoded"):
            form = await request.form()
            form_dict = dict(form)
            verify_token_from_request(form_dict, authorization)
            reference_audio_path = str(form.get("ref_audio_path") or form.get("reference_audio_path") or "").strip() or None
            src_audio_path = str(form.get("ctx_audio_path") or form.get("src_audio_path") or "").strip() or None
            req = _build_request(
                RequestParser(form_dict),
                reference_audio_path=reference_audio_path,
                src_audio_path=src_audio_path,
            )

        else:
            raw = await request.body()
            raw_stripped = raw.lstrip()
            # Best-effort: accept missing/incorrect Content-Type if payload is valid JSON.
            if raw_stripped.startswith(b"{") or raw_stripped.startswith(b"["):
                try:
                    body = json.loads(raw.decode("utf-8"))
                    if isinstance(body, dict):
                        verify_token_from_request(body, authorization)
                        req = _build_request(RequestParser(body))
                    else:
                        raise HTTPException(status_code=400, detail="JSON payload must be an object")
                except HTTPException:
                    raise
                except Exception:
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid JSON body (hint: set 'Content-Type: application/json')",
                    )
            # Best-effort: parse key=value bodies even if Content-Type is missing.
            elif raw_stripped and b"=" in raw:
                parsed = urllib.parse.parse_qs(raw.decode("utf-8"), keep_blank_values=True)
                flat = {k: (v[0] if isinstance(v, list) and v else v) for k, v in parsed.items()}
                verify_token_from_request(flat, authorization)
                reference_audio_path = str(flat.get("ref_audio_path") or flat.get("reference_audio_path") or "").strip() or None
                src_audio_path = str(flat.get("ctx_audio_path") or flat.get("src_audio_path") or "").strip() or None
                req = _build_request(
                    RequestParser(flat),
                    reference_audio_path=reference_audio_path,
                    src_audio_path=src_audio_path,
                )
            else:
                raise HTTPException(
                    status_code=415,
                    detail=(
                        f"Unsupported Content-Type: {content_type or '(missing)'}; "
                        "use application/json, application/x-www-form-urlencoded, or multipart/form-data"
                    ),
                )

        rec = store.create()

        q: asyncio.Queue = app.state.job_queue
        if q.full():
            for p in temp_files:
                try:
                    os.remove(p)
                except Exception:
                    pass
            raise HTTPException(status_code=429, detail="Server busy: queue is full")

        if temp_files:
            async with app.state.job_temp_files_lock:
                app.state.job_temp_files[rec.job_id] = temp_files

        async with app.state.pending_lock:
            app.state.pending_ids.append(rec.job_id)
            position = len(app.state.pending_ids)

        await q.put((rec.job_id, req))
        return _wrap_response({"task_id": rec.job_id, "status": "queued", "queue_position": position})

    @app.post("/query_result")
    async def query_result(request: Request, authorization: Optional[str] = Header(None)):
        """Batch query job results"""
        content_type = (request.headers.get("content-type") or "").lower()

        if "json" in content_type:
            body = await request.json()
        else:
            form = await request.form()
            body = {k: v for k, v in form.items()}

        verify_token_from_request(body, authorization)
        task_id_list_str = body.get("task_id_list", "[]")

        # Parse task ID list
        if isinstance(task_id_list_str, list):
            task_id_list = task_id_list_str
        else:
            try:
                task_id_list = json.loads(task_id_list_str)
            except Exception:
                task_id_list = []

        local_cache = getattr(app.state, 'local_cache', None)
        data_list = []
        current_time = time.time()

        for task_id in task_id_list:
            result_key = f"{RESULT_KEY_PREFIX}{task_id}"

            # Read from local cache first
            if local_cache:
                data = local_cache.get(result_key)
                if data:
                    try:
                        data_json = json.loads(data)
                    except Exception:
                        data_json = []

                    if len(data_json) <= 0:
                        data_list.append({"task_id": task_id, "result": data, "status": 2})
                    else:
                        status = data_json[0].get("status")
                        create_time = data_json[0].get("create_time", 0)
                        if status == 0 and (current_time - create_time) > TASK_TIMEOUT_SECONDS:
                            data_list.append({"task_id": task_id, "result": data, "status": 2})
                        else:
                            data_list.append({
                                "task_id": task_id,
                                "result": data,
                                "status": int(status) if status is not None else 1,
                                "progress_text": log_buffer.last_message
                            })
                    continue

            # Fallback to job_store query
            rec = store.get(task_id)
            if rec:
                env = getattr(rec, 'env', 'development')
                create_time = rec.created_at
                status_int = _map_status(rec.status)

                if rec.result and rec.status == "succeeded":
                    audio_paths = rec.result.get("audio_paths", [])
                    metas = rec.result.get("metas", {}) or {}
                    result_data = [
                        {
                            "file": p, "wave": "", "status": status_int,
                            "create_time": int(create_time), "env": env,
                            "prompt": metas.get("caption", ""),
                            "lyrics": metas.get("lyrics", ""),
                            "metas": {
                                "bpm": metas.get("bpm"),
                                "duration": metas.get("duration"),
                                "genres": metas.get("genres", ""),
                                "keyscale": metas.get("keyscale", ""),
                                "timesignature": metas.get("timesignature", ""),
                            }
                        }
                        for p in audio_paths
                    ] if audio_paths else [{
                        "file": "", "wave": "", "status": status_int,
                        "create_time": int(create_time), "env": env,
                        "prompt": metas.get("caption", ""),
                        "lyrics": metas.get("lyrics", ""),
                        "metas": {
                            "bpm": metas.get("bpm"),
                            "duration": metas.get("duration"),
                            "genres": metas.get("genres", ""),
                            "keyscale": metas.get("keyscale", ""),
                            "timesignature": metas.get("timesignature", ""),
                        }
                    }]
                else:
                    result_data = [{
                        "file": "", "wave": "", "status": status_int,
                        "create_time": int(create_time), "env": env,
                        "prompt": "", "lyrics": "",
                        "metas": {},
                        "progress": float(rec.progress) if rec else 0.0,
                        "stage": rec.stage if rec else "queued",
                        "error": rec.error if rec.error else None,
                    }]

                data_list.append({
                    "task_id": task_id,
                    "result": json.dumps(result_data, ensure_ascii=False),
                    "status": status_int,
                    "progress_text": log_buffer.last_message
                })
            else:
                data_list.append({"task_id": task_id, "result": "[]", "status": 0})

        return _wrap_response(data_list)

    @app.get("/health")
    async def health_check():
        """Health check endpoint for service status."""
        return _wrap_response({
            "status": "ok",
            "service": "ACE-Step API",
            "version": "1.0",
        })

    @app.get("/v1/stats")
    async def get_stats(_: None = Depends(verify_api_key)):
        """Get server statistics including job store stats."""
        job_stats = store.get_stats()
        async with app.state.stats_lock:
            avg_job_seconds = getattr(app.state, "avg_job_seconds", INITIAL_AVG_JOB_SECONDS)
        return _wrap_response({
            "jobs": job_stats,
            "queue_size": app.state.job_queue.qsize(),
            "queue_maxsize": QUEUE_MAXSIZE,
            "avg_job_seconds": avg_job_seconds,
        })

    @app.get("/v1/models")
    async def list_models(_: None = Depends(verify_api_key)):
        """List available DiT models."""
        models = []
        
        # Primary model (always available if initialized)
        if getattr(app.state, "_initialized", False):
            primary_model = _get_model_name(app.state._config_path)
            if primary_model:
                models.append({
                    "name": primary_model,
                    "is_default": True,
                })
        
        # Secondary model
        if getattr(app.state, "_initialized2", False) and app.state._config_path2:
            secondary_model = _get_model_name(app.state._config_path2)
            if secondary_model:
                models.append({
                    "name": secondary_model,
                    "is_default": False,
                })
        
        # Third model
        if getattr(app.state, "_initialized3", False) and app.state._config_path3:
            third_model = _get_model_name(app.state._config_path3)
            if third_model:
                models.append({
                    "name": third_model,
                    "is_default": False,
                })
        
        return _wrap_response({
            "models": models,
            "default_model": models[0]["name"] if models else None,
        })

    @app.post("/create_random_sample")
    async def create_random_sample_endpoint(request: Request, authorization: Optional[str] = Header(None)):
        """
        Get random sample parameters from pre-loaded example data.

        Returns a random example from the examples directory for form filling.
        """
        content_type = (request.headers.get("content-type") or "").lower()

        if "json" in content_type:
            body = await request.json()
        else:
            form = await request.form()
            body = {k: v for k, v in form.items()}

        verify_token_from_request(body, authorization)
        sample_type = body.get("sample_type", "simple_mode") or "simple_mode"

        if sample_type == "simple_mode":
            example_data = SIMPLE_EXAMPLE_DATA
        else:
            example_data = CUSTOM_EXAMPLE_DATA

        if not example_data:
            return _wrap_response(None, code=500, error="No example data available")

        random_example = random.choice(example_data)
        return _wrap_response(random_example)

    @app.post("/format_input")
    async def format_input_endpoint(request: Request, authorization: Optional[str] = Header(None)):
        """
        Format and enhance lyrics/caption via LLM.

        Takes user-provided caption and lyrics, and uses the LLM to enhance them
        with proper structure and metadata.
        """
        content_type = (request.headers.get("content-type") or "").lower()

        if "json" in content_type:
            body = await request.json()
        else:
            form = await request.form()
            body = {k: v for k, v in form.items()}

        verify_token_from_request(body, authorization)
        llm: LLMHandler = app.state.llm_handler

        # Initialize LLM if needed
        with app.state._llm_init_lock:
            if not getattr(app.state, "_llm_initialized", False):
                if getattr(app.state, "_llm_init_error", None):
                    raise HTTPException(status_code=500, detail=f"LLM init failed: {app.state._llm_init_error}")

                # Check if lazy loading is disabled
                if getattr(app.state, "_llm_lazy_load_disabled", False):
                    raise HTTPException(
                        status_code=503,
                        detail="LLM not initialized. Set ACESTEP_INIT_LLM=true in .env to enable."
                    )

                project_root = _get_project_root()
                checkpoint_dir = os.path.join(project_root, "checkpoints")
                lm_model_path = os.getenv("ACESTEP_LM_MODEL_PATH", "acestep-5Hz-lm-0.6B").strip()
                backend = os.getenv("ACESTEP_LM_BACKEND", "vllm").strip().lower()
                if backend not in {"vllm", "pt"}:
                    backend = "vllm"

                # Auto-download LM model if not present
                lm_model_name = _get_model_name(lm_model_path)
                if lm_model_name:
                    try:
                        _ensure_model_downloaded(lm_model_name, checkpoint_dir)
                    except Exception as e:
                        print(f"[API Server] Warning: Failed to download LM model {lm_model_name}: {e}")

                lm_device = os.getenv("ACESTEP_LM_DEVICE", os.getenv("ACESTEP_DEVICE", "auto"))
                lm_offload = _env_bool("ACESTEP_LM_OFFLOAD_TO_CPU", False)

                h: AceStepHandler = app.state.handler
                status, ok = llm.initialize(
                    checkpoint_dir=checkpoint_dir,
                    lm_model_path=lm_model_path,
                    backend=backend,
                    device=lm_device,
                    offload_to_cpu=lm_offload,
                    dtype=h.dtype,
                )
                if not ok:
                    app.state._llm_init_error = status
                    raise HTTPException(status_code=500, detail=f"LLM init failed: {status}")
                app.state._llm_initialized = True

        # Parse parameters
        prompt = body.get("prompt", "") or ""
        lyrics = body.get("lyrics", "") or ""
        temperature = _to_float(body.get("temperature"), 0.85)

        # Parse param_obj if provided
        param_obj_str = body.get("param_obj", "{}")
        if isinstance(param_obj_str, dict):
            param_obj = param_obj_str
        else:
            try:
                param_obj = json.loads(param_obj_str) if param_obj_str else {}
            except json.JSONDecodeError:
                param_obj = {}

        # Extract metadata from param_obj
        duration = _to_float(param_obj.get("duration"))
        bpm = _to_int(param_obj.get("bpm"))
        key_scale = param_obj.get("key", "") or param_obj.get("key_scale", "") or ""
        time_signature = param_obj.get("time_signature", "") or body.get("time_signature", "") or ""
        language = param_obj.get("language", "") or ""

        # Build user_metadata for format_sample
        user_metadata_for_format = {}
        if bpm is not None:
            user_metadata_for_format['bpm'] = bpm
        if duration is not None and duration > 0:
            user_metadata_for_format['duration'] = int(duration)
        if key_scale:
            user_metadata_for_format['keyscale'] = key_scale
        if time_signature:
            user_metadata_for_format['timesignature'] = time_signature
        if language and language != "unknown":
            user_metadata_for_format['language'] = language

        # Call format_sample
        try:
            format_result = format_sample(
                llm_handler=llm,
                caption=prompt,
                lyrics=lyrics,
                user_metadata=user_metadata_for_format if user_metadata_for_format else None,
                temperature=temperature,
                use_constrained_decoding=True,
            )

            if not format_result.success:
                error_msg = format_result.error or format_result.status_message
                return _wrap_response(None, code=500, error=f"format_sample failed: {error_msg}")

            # Use formatted results or fallback to original
            result_caption = format_result.caption or prompt
            result_lyrics = format_result.lyrics or lyrics
            result_duration = format_result.duration or duration
            result_bpm = format_result.bpm or bpm
            result_key_scale = format_result.keyscale or key_scale
            result_time_signature = format_result.timesignature or time_signature

            return _wrap_response({
                "caption": result_caption,
                "lyrics": result_lyrics,
                "bpm": result_bpm,
                "key_scale": result_key_scale,
                "time_signature": result_time_signature,
                "duration": result_duration,
                "vocal_language": format_result.language or language or "unknown",
            })
        except Exception as e:
            return _wrap_response(None, code=500, error=f"format_sample error: {str(e)}")

    @app.get("/v1/audio")
    async def get_audio(path: str, request: Request, _: None = Depends(verify_api_key)):
        """Serve audio file by path."""
        from fastapi.responses import FileResponse

        # Security: Validate path is within allowed directory to prevent path traversal
        resolved_path = os.path.realpath(path)
        allowed_dir = os.path.realpath(request.app.state.temp_audio_dir)
        if not resolved_path.startswith(allowed_dir + os.sep) and resolved_path != allowed_dir:
            raise HTTPException(status_code=403, detail="Access denied: path outside allowed directory")
        if not os.path.exists(resolved_path):
            raise HTTPException(status_code=404, detail="Audio file not found")

        ext = os.path.splitext(resolved_path)[1].lower()
        media_types = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".flac": "audio/flac",
            ".ogg": "audio/ogg",
        }
        media_type = media_types.get(ext, "audio/mpeg")

        return FileResponse(resolved_path, media_type=media_type)

    return app


app = create_app()


def main() -> None:
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="ACE-Step API server")
    parser.add_argument(
        "--host",
        default=os.getenv("ACESTEP_API_HOST", "127.0.0.1"),
        help="Bind host (default from ACESTEP_API_HOST or 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ACESTEP_API_PORT", "8001")),
        help="Bind port (default from ACESTEP_API_PORT or 8001)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.getenv("ACESTEP_API_KEY", None),
        help="API key for authentication (default from ACESTEP_API_KEY)",
    )
    parser.add_argument(
        "--download-source",
        type=str,
        choices=["huggingface", "modelscope", "auto"],
        default=os.getenv("ACESTEP_DOWNLOAD_SOURCE", "auto"),
        help="Preferred model download source: auto (default), huggingface, or modelscope",
    )
    parser.add_argument(
        "--init-llm",
        action="store_true",
        default=_env_bool("ACESTEP_INIT_LLM", False),
        help="Initialize LLM even if GPU memory is insufficient (may cause OOM). "
             "Can also be set via ACESTEP_INIT_LLM=true environment variable.",
    )
    parser.add_argument(
        "--lm-model-path",
        type=str,
        default=os.getenv("ACESTEP_LM_MODEL_PATH", ""),
        help="LM model to load (e.g., 'acestep-5Hz-lm-0.6B'). Default from ACESTEP_LM_MODEL_PATH.",
    )
    args = parser.parse_args()

    # Set API key from command line argument
    if args.api_key:
        os.environ["ACESTEP_API_KEY"] = args.api_key

    # Set download source preference
    if args.download_source and args.download_source != "auto":
        os.environ["ACESTEP_DOWNLOAD_SOURCE"] = args.download_source
        print(f"Using preferred download source: {args.download_source}")

    # Set init LLM flag
    if args.init_llm:
        os.environ["ACESTEP_INIT_LLM"] = "true"
        print("[API Server] LLM initialization enabled via --init-llm")

    # Set LM model path
    if args.lm_model_path:
        os.environ["ACESTEP_LM_MODEL_PATH"] = args.lm_model_path
        print(f"[API Server] Using LM model: {args.lm_model_path}")

    # IMPORTANT: in-memory queue/store -> workers MUST be 1
    uvicorn.run(
        "acestep.api_server:app",
        host=str(args.host),
        port=int(args.port),
        reload=False,
        workers=1,
    )

if __name__ == "__main__":
    main()
