"""Native-keyring or encrypted-file storage for external API credentials."""

from __future__ import annotations

# TODO(1larity): Split OpenSSL and keyring backends into smaller modules after
# PR #881 lands. Keeping the facade together here avoids widening this storage slice.
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_OPENSSL_TIMEOUT_SEC = 30


class SecretStoreError(RuntimeError):
    """Raised when encrypted secret read/write operations fail."""


@dataclass(frozen=True)
class EncryptedSecretStore:
    """Native-keyring or OpenSSL-backed secret store in user-local storage."""

    secret_path: Path
    openssl_path: str | None = None

    def __post_init__(self) -> None:
        """Validate backend availability for storage operations."""
        object.__setattr__(self, "secret_path", self.secret_path.expanduser())
        if self._uses_native_keyring():
            return
        openssl_binary = self.openssl_path or shutil.which("openssl")
        if not openssl_binary:
            raise SecretStoreError("OpenSSL is required for encrypted secret storage.")
        object.__setattr__(self, "openssl_path", openssl_binary)

    @staticmethod
    def default_path(filename: str = "glm_api_key.enc") -> Path:
        """Return the default encrypted-secret path under user-local data."""
        xdg_data_home = os.getenv("XDG_DATA_HOME")
        base = (
            Path(xdg_data_home).expanduser()
            if xdg_data_home
            else Path.home() / ".local" / "share"
        )
        return base / "acestep" / "secrets" / filename

    @staticmethod
    def legacy_default_path(filename: str = "glm_api_key.enc") -> Path:
        """Return the historical encrypted-secret path."""
        return Path.home() / ".local" / "share" / "acestep" / "secrets" / filename

    @staticmethod
    def resolve_existing_default_path(filename: str = "glm_api_key.enc") -> Path:
        """Return the existing default path, falling back to the legacy path."""
        primary = EncryptedSecretStore.default_path(filename=filename)
        if primary.exists():
            return primary
        legacy = EncryptedSecretStore.legacy_default_path(filename=filename)
        if legacy.exists():
            return legacy
        return primary

    def save(self, *, secret: str, passphrase: str) -> None:
        """Encrypt and store a secret value."""
        if secret == "":
            raise SecretStoreError("Secret cannot be empty.")
        if self._uses_native_keyring():
            self._save_to_keyring(secret)
            return
        if passphrase == "":
            raise SecretStoreError("Passphrase cannot be empty.")

        self.secret_path.parent.mkdir(parents=True, exist_ok=True)
        self.secret_path.parent.chmod(0o700)
        result = self._run_openssl(
            args=[
                "enc",
                "-aes-256-cbc",
                "-pbkdf2",
                "-salt",
                "-out",
                str(self.secret_path),
            ],
            passphrase=passphrase,
            stdin_bytes=secret.encode("utf-8"),
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="ignore")
            raise SecretStoreError(self._sanitize_error(stderr))
        self.secret_path.chmod(0o600)

    def load(self, *, passphrase: str) -> str:
        """Decrypt and return a stored secret value."""
        if self._uses_native_keyring():
            return self._load_from_keyring()
        if not self.secret_path.exists():
            raise SecretStoreError(f"Secret not found at: {self.secret_path}")
        if passphrase == "":
            raise SecretStoreError("Passphrase cannot be empty.")

        result = self._run_openssl(
            args=[
                "enc",
                "-d",
                "-aes-256-cbc",
                "-pbkdf2",
                "-in",
                str(self.secret_path),
            ],
            passphrase=passphrase,
            stdin_bytes=None,
        )
        if result.returncode != 0:
            raise SecretStoreError("Failed to decrypt secret. Check passphrase.")
        try:
            return result.stdout.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SecretStoreError("Decrypted secret is not valid UTF-8.") from exc

    def _run_openssl(
        self,
        *,
        args: list[str],
        passphrase: str,
        stdin_bytes: bytes | None,
    ) -> subprocess.CompletedProcess[bytes]:
        """Execute OpenSSL with the passphrase stored in a temporary file."""
        passphrase_path: Path | None = None
        passphrase_fd = -1
        try:
            passphrase_fd, raw_path = tempfile.mkstemp()
            passphrase_path = Path(raw_path)
            os.chmod(passphrase_path, 0o600)
            os.write(passphrase_fd, passphrase.encode("utf-8"))
            os.close(passphrase_fd)
            passphrase_fd = -1
            cmd = [self.openssl_path, *args, "-pass", f"file:{passphrase_path}"]
            try:
                return subprocess.run(
                    cmd,
                    input=stdin_bytes,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=_OPENSSL_TIMEOUT_SEC,
                )
            except subprocess.TimeoutExpired as exc:
                raise SecretStoreError("OpenSSL operation timed out.") from exc
        finally:
            if passphrase_fd != -1:
                try:
                    os.close(passphrase_fd)
                except OSError:
                    pass
            if passphrase_path is not None:
                try:
                    passphrase_path.unlink()
                except OSError:
                    pass

    def _uses_native_keyring(self) -> bool:
        """Return whether the current platform should prefer the system keyring."""
        return sys.platform in {"win32", "darwin"} and self._load_keyring_module() is not None

    def _save_to_keyring(self, secret: str) -> None:
        """Store the secret directly in the native OS keyring."""
        keyring = self._load_keyring_module()
        if keyring is None:
            raise SecretStoreError("Python keyring backend unavailable.")
        keyring_error = self._keyring_error_type(keyring)
        try:
            keyring.set_password("acestep.external_lm.secret_store", self._keyring_username(), secret)
        except keyring_error as exc:
            raise SecretStoreError("Failed storing secret in system keyring.") from exc

    def _load_from_keyring(self) -> str:
        """Load the secret directly from the native OS keyring."""
        keyring = self._load_keyring_module()
        if keyring is None:
            raise SecretStoreError("Python keyring backend unavailable.")
        keyring_error = self._keyring_error_type(keyring)
        try:
            value = keyring.get_password(
                "acestep.external_lm.secret_store",
                self._keyring_username(),
            )
        except keyring_error as exc:
            raise SecretStoreError("Failed reading secret from system keyring.") from exc
        if value is None:
            raise SecretStoreError("Secret not found in system keyring.")
        return value

    def _keyring_username(self) -> str:
        """Return the keyring username derived from the configured secret path."""
        return str(self.secret_path)

    @staticmethod
    def _load_keyring_module():
        """Return the Python keyring module when available."""
        try:
            import keyring
        except ImportError:
            return None
        return keyring

    @staticmethod
    def _keyring_error_type(keyring_module) -> type[Exception]:
        """Return the stable keyring base exception type for backend operations."""

        errors_module = getattr(keyring_module, "errors", None)
        keyring_error = getattr(errors_module, "KeyringError", None)
        if isinstance(keyring_error, type) and issubclass(keyring_error, Exception):
            return keyring_error
        raise SecretStoreError("Python keyring backend missing KeyringError support.")

    @staticmethod
    def _sanitize_error(stderr: str) -> str:
        """Return a concise sanitized OpenSSL error message."""
        if not stderr:
            return "OpenSSL operation failed."
        first_line = stderr.strip().splitlines()[0]
        return first_line[:200]
