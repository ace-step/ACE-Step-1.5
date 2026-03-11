"""Model auto-download helpers extracted from API server runtime."""

from __future__ import annotations

import os


MODEL_REPO_MAPPING = {
    "acestep-v15-turbo": "ACE-Step/Ace-Step1.5",
    "acestep-5Hz-lm-1.7B": "ACE-Step/Ace-Step1.5",
    "vae": "ACE-Step/Ace-Step1.5",
    "Qwen3-Embedding-0.6B": "ACE-Step/Ace-Step1.5",
    "acestep-5Hz-lm-0.6B": "ACE-Step/acestep-5Hz-lm-0.6B",
    "acestep-5Hz-lm-4B": "ACE-Step/acestep-5Hz-lm-4B",
    "acestep-v15-base": "ACE-Step/acestep-v15-base",
    "acestep-v15-sft": "ACE-Step/acestep-v15-sft",
    "acestep-v15-turbo-shift3": "ACE-Step/acestep-v15-turbo-shift3",
}

DEFAULT_REPO_ID = "ACE-Step/Ace-Step1.5"


def can_access_google(timeout: float = 3.0) -> bool:
    """Check if Google is reachable to select preferred model source."""

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


def download_from_huggingface(repo_id: str, local_dir: str, model_name: str) -> str:
    """Download model snapshot from HuggingFace Hub."""

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


def download_from_modelscope(repo_id: str, local_dir: str, model_name: str) -> str:
    """Download model snapshot from ModelScope."""

    from modelscope import snapshot_download

    is_unified_repo = repo_id == DEFAULT_REPO_ID or repo_id == "ACE-Step/Ace-Step1.5"

    if is_unified_repo:
        download_dir = local_dir
        print(f"[Model Download] Downloading unified repo {repo_id} from ModelScope to {download_dir}...")
    else:
        download_dir = os.path.join(local_dir, model_name)
        os.makedirs(download_dir, exist_ok=True)
        print(f"[Model Download] Downloading {model_name} from ModelScope {repo_id} to {download_dir}...")

    try:
        result_path = snapshot_download(
            model_id=repo_id,
            local_dir=download_dir,
        )
        print(f"[Model Download] ModelScope download completed: {result_path}")
    except TypeError:
        print("[Model Download] Retrying with cache_dir parameter...")
        result_path = snapshot_download(
            model_id=repo_id,
            cache_dir=download_dir,
        )
        print(f"[Model Download] ModelScope download completed: {result_path}")

    return os.path.join(local_dir, model_name)


def ensure_model_downloaded(model_name: str, checkpoint_dir: str) -> str:
    """Ensure model exists locally, downloading from configured source if missing."""

    model_path = os.path.join(checkpoint_dir, model_name)

    if os.path.exists(model_path) and os.listdir(model_path):
        print(f"[Model Download] Model {model_name} already exists at {model_path}")
        return model_path

    repo_id = MODEL_REPO_MAPPING.get(model_name, DEFAULT_REPO_ID)
    print(f"[Model Download] Model {model_name} not found, checking network...")

    prefer_source = os.environ.get("ACESTEP_DOWNLOAD_SOURCE", "").lower()
    if prefer_source == "huggingface":
        use_huggingface = True
        print("[Model Download] User preference: HuggingFace Hub")
    elif prefer_source == "modelscope":
        use_huggingface = False
        print("[Model Download] User preference: ModelScope")
    else:
        use_huggingface = can_access_google()
        print(f"[Model Download] Auto-detected: {'HuggingFace Hub' if use_huggingface else 'ModelScope'}")

    if use_huggingface:
        print("[Model Download] Using HuggingFace Hub...")
        try:
            return download_from_huggingface(repo_id, checkpoint_dir, model_name)
        except Exception as exc:
            print(f"[Model Download] HuggingFace download failed: {exc}")
            print("[Model Download] Falling back to ModelScope...")
            return download_from_modelscope(repo_id, checkpoint_dir, model_name)

    print("[Model Download] Using ModelScope...")
    try:
        return download_from_modelscope(repo_id, checkpoint_dir, model_name)
    except Exception as exc:
        print(f"[Model Download] ModelScope download failed: {exc}")
        print("[Model Download] Trying HuggingFace as fallback...")
        return download_from_huggingface(repo_id, checkpoint_dir, model_name)
