"""Cross-platform runtime passphrase storage helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from loguru import logger


EXTERNAL_LM_SECRET_SERVICE = "acestep.external_lm"
EXTERNAL_LM_SECRET_USERNAME = "external_lm_store_passphrase"
# Backward-compatible GLM aliases are kept for callers that still import them directly.
GLM_SECRET_SERVICE = EXTERNAL_LM_SECRET_SERVICE
GLM_SECRET_USERNAME = EXTERNAL_LM_SECRET_USERNAME
_SECRET_TOOL_PATH = "secret-tool"
_SECRET_TOOL_TIMEOUT_SEC = 5


def resolve_runtime_passphrase() -> str | None:
    """Resolve a runtime passphrase from env, file, secret-tool, or keyring."""

    env_passphrase = os.getenv("ACESTEP_GLM_STORE_PASSPHRASE")
    if env_passphrase not in {None, ""}:
        return env_passphrase

    file_path_raw = os.getenv("ACESTEP_GLM_STORE_PASSPHRASE_FILE", "").strip()
    if file_path_raw:
        try:
            text = Path(file_path_raw).expanduser().read_text(encoding="utf-8")
        except OSError:
            text = ""
        if text != "":
            return text

    service, username = _resolve_secret_service_identity()

    secret_tool_passphrase = _load_passphrase_from_secret_tool(
        service=service,
        username=username,
    )
    if secret_tool_passphrase:
        return secret_tool_passphrase

    return _load_passphrase_from_keyring(service=service, username=username)


def store_runtime_passphrase(passphrase: str) -> tuple[bool, str]:
    """Persist a runtime passphrase using the best available secret store."""

    if passphrase == "":
        return False, "Passphrase cannot be empty."

    service, username = _resolve_secret_service_identity()

    ok_secret_tool, msg_secret_tool = _store_passphrase_in_secret_tool(
        service=service,
        username=username,
        passphrase=passphrase,
    )
    if ok_secret_tool:
        return True, msg_secret_tool

    ok_keyring, msg_keyring = _store_passphrase_in_keyring(
        service=service,
        username=username,
        passphrase=passphrase,
    )
    if ok_keyring:
        return True, msg_keyring
    return False, f"{msg_secret_tool} | {msg_keyring}"


def _load_passphrase_from_secret_tool(*, service: str, username: str) -> str | None:
    """Read passphrase from Linux libsecret when ``secret-tool`` exists."""

    tool_path = shutil.which(_SECRET_TOOL_PATH)
    if not tool_path:
        return None
    try:
        result = subprocess.run(
            [tool_path, "lookup", "service", service, "username", username],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=_SECRET_TOOL_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        logger.debug(
            "secret-tool lookup timed out for service={} username={}",
            service,
            username,
        )
        return None
    if result.returncode != 0:
        return None
    value = result.stdout
    return value or None


def _store_passphrase_in_secret_tool(
    *,
    service: str,
    username: str,
    passphrase: str,
) -> tuple[bool, str]:
    """Write passphrase to Linux libsecret when ``secret-tool`` exists."""

    tool_path = shutil.which(_SECRET_TOOL_PATH)
    if not tool_path:
        return False, "secret-tool not available"

    try:
        result = subprocess.run(
            [
                tool_path,
                "store",
                "--label",
                "ACE-Step external LM passphrase",
                "service",
                service,
                "username",
                username,
            ],
            input=passphrase,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=_SECRET_TOOL_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        logger.debug(
            "secret-tool store timed out for service={} username={}",
            service,
            username,
        )
        return False, "Timed out writing passphrase with secret-tool"
    if result.returncode != 0:
        return False, "Failed writing passphrase with secret-tool"
    return True, f"Stored passphrase in secret-tool ({service}/{username})"


def _load_passphrase_from_keyring(*, service: str, username: str) -> str | None:
    """Read passphrase from Python keyring when available."""

    keyring = _load_keyring_module()
    if keyring is None:
        return None

    keyring_error = _resolve_keyring_error_type(keyring)
    if keyring_error is not None:
        try:
            value = keyring.get_password(service, username)
        except keyring_error as exc:
            logger.debug("Failed to retrieve password from keyring: {}", exc)
            return None
    else:
        try:
            value = keyring.get_password(service, username)
        except Exception as exc:
            logger.debug("Failed to retrieve password from keyring: {}", exc)
            return None
    return value if value else None


def _store_passphrase_in_keyring(
    *,
    service: str,
    username: str,
    passphrase: str,
) -> tuple[bool, str]:
    """Write passphrase to Python keyring when available."""

    keyring = _load_keyring_module()
    if keyring is None:
        return False, "python keyring backend unavailable"

    keyring_error = _resolve_keyring_error_type(keyring)
    if keyring_error is not None:
        try:
            keyring.set_password(service, username, passphrase)
        except keyring_error as exc:
            logger.debug("Failed writing passphrase with python keyring: {}", exc)
            return False, str(exc)
    else:
        keyring.set_password(service, username, passphrase)
    return True, f"Stored passphrase in python keyring ({service}/{username})"


def _resolve_secret_service_identity() -> tuple[str, str]:
    """Return normalized secret service coordinates with safe fallback defaults."""

    service = (
        (os.getenv("ACESTEP_GLM_SECRET_SERVICE") or "").strip() or EXTERNAL_LM_SECRET_SERVICE
    )
    username = (
        (os.getenv("ACESTEP_GLM_SECRET_USERNAME") or "").strip() or EXTERNAL_LM_SECRET_USERNAME
    )
    return service, username


def _load_keyring_module():
    """Return the keyring module when importable."""

    try:
        import keyring
    except ImportError:
        logger.debug("keyring module not available")
        return None
    return keyring


def _resolve_keyring_error_type(keyring_module):
    """Return the specific keyring exception type when the backend exposes one."""

    errors_module = getattr(keyring_module, "errors", None)
    keyring_error = getattr(errors_module, "KeyringError", None)
    if isinstance(keyring_error, type) and issubclass(keyring_error, Exception):
        return keyring_error
    return None
