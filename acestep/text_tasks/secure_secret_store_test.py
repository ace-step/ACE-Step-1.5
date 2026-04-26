"""Tests for encrypted secret storage helpers."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from acestep.text_tasks import secure_secret_store
from acestep.text_tasks.secure_secret_store import EncryptedSecretStore, SecretStoreError


class SecureSecretStoreTests(unittest.TestCase):
    """Verify encrypted secret storage save/load flows."""

    @staticmethod
    def _fake_keyring_module() -> types.SimpleNamespace:
        """Return a fake keyring module with a KeyringError base class."""

        class _FakeKeyringError(Exception):
            """Fake stable keyring base exception."""

        return types.SimpleNamespace(errors=types.SimpleNamespace(KeyringError=_FakeKeyringError))

    def test_save_and_load_round_trip_with_mocked_openssl(self) -> None:
        """Save followed by load should round-trip the secret content."""

        with tempfile.TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / "secret.enc"
            with patch("shutil.which", return_value="/usr/bin/openssl"):
                store = EncryptedSecretStore(secret_path=secret_path)

            def fake_run_openssl(*, args, passphrase, stdin_bytes):
                if "-d" in args:
                    return subprocess.CompletedProcess(
                        args=["openssl"],
                        returncode=0,
                        stdout=b"test-key",
                        stderr=b"",
                    )
                secret_path.write_bytes(b"encrypted")
                return subprocess.CompletedProcess(
                    args=["openssl"],
                    returncode=0,
                    stdout=b"",
                    stderr=b"",
                )

            with patch.object(
                EncryptedSecretStore,
                "_run_openssl",
                autospec=True,
                side_effect=lambda _self, **kwargs: fake_run_openssl(**kwargs),
            ):
                store.save(secret="test-key", passphrase="passphrase")
                secret = store.load(passphrase="passphrase")
                self.assertTrue(secret_path.exists())

        self.assertEqual(secret, "test-key")

    def test_save_and_load_round_trip_with_native_keyring(self) -> None:
        """Windows/macOS should prefer the native keyring backend when available."""

        fake_keyring = self._fake_keyring_module()
        captured: dict[tuple[str, str], str] = {}

        def set_password(service: str, username: str, secret: str) -> None:
            captured[(service, username)] = secret

        def get_password(service: str, username: str) -> str | None:
            return captured.get((service, username))

        fake_keyring.set_password = set_password
        fake_keyring.get_password = get_password

        with tempfile.TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / "openai_api_key.enc"
            with patch.object(secure_secret_store.sys, "platform", "win32"):
                with patch.dict(sys.modules, {"keyring": fake_keyring}):
                    with patch("shutil.which", return_value=None):
                        store = EncryptedSecretStore(secret_path=secret_path)
                        store.save(secret="test-key", passphrase="")
                        secret = store.load(passphrase="")

        self.assertEqual(secret, "test-key")
        self.assertEqual(
            captured[("acestep.external_lm.secret_store", str(secret_path))],
            "test-key",
        )

    def test_run_openssl_uses_restricted_temp_passphrase_file(self) -> None:
        """OpenSSL passphrase files should be created with owner-only permissions."""

        captured: dict[str, object] = {}

        def fake_run(cmd, **kwargs):
            passphrase_arg = cmd[cmd.index("-pass") + 1]
            passphrase_path = Path(passphrase_arg.removeprefix("file:"))
            captured["mode"] = passphrase_path.stat().st_mode & 0o777
            captured["path"] = passphrase_path
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

        with tempfile.TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / "secret.enc"
            store = EncryptedSecretStore(
                secret_path=secret_path,
                openssl_path="/usr/bin/openssl",
            )
            with patch("subprocess.run", side_effect=fake_run):
                result = store._run_openssl(
                    args=["enc", "-aes-256-cbc"],
                    passphrase="passphrase",
                    stdin_bytes=b"secret",
                )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(captured["mode"], 0o600)
        self.assertFalse(captured["path"].exists())

    def test_run_openssl_raises_clear_error_when_process_times_out(self) -> None:
        """Hung OpenSSL invocations should surface a deterministic secret-store error."""

        with tempfile.TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / "secret.enc"
            store = EncryptedSecretStore(
                secret_path=secret_path,
                openssl_path="/usr/bin/openssl",
            )
            with patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(
                    cmd=["openssl", "enc"],
                    timeout=secure_secret_store._OPENSSL_TIMEOUT_SEC,
                ),
            ):
                with self.assertRaises(SecretStoreError) as exc:
                    store._run_openssl(
                        args=["enc", "-aes-256-cbc"],
                        passphrase="passphrase",
                        stdin_bytes=b"secret",
                    )

        self.assertIn("timed out", str(exc.exception))

    def test_save_to_keyring_wraps_keyring_error(self) -> None:
        """Native keyring write failures should surface as SecretStoreError."""

        fake_keyring = self._fake_keyring_module()
        keyring_error = fake_keyring.errors.KeyringError

        def set_password(*_args) -> None:
            raise keyring_error("locked")

        fake_keyring.set_password = set_password

        with tempfile.TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / "openai_api_key.enc"
            with patch.object(secure_secret_store.sys, "platform", "win32"):
                with patch.dict(sys.modules, {"keyring": fake_keyring}):
                    with patch("shutil.which", return_value=None):
                        store = EncryptedSecretStore(secret_path=secret_path)
                        with self.assertRaises(SecretStoreError) as exc:
                            store.save(secret="test-key", passphrase="")

        self.assertIn("Failed storing secret", str(exc.exception))

    def test_load_from_keyring_wraps_keyring_error(self) -> None:
        """Native keyring read failures should surface as SecretStoreError."""

        fake_keyring = self._fake_keyring_module()
        keyring_error = fake_keyring.errors.KeyringError

        def get_password(*_args) -> str | None:
            raise keyring_error("locked")

        fake_keyring.set_password = lambda *_args: None
        fake_keyring.get_password = get_password

        with tempfile.TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / "openai_api_key.enc"
            with patch.object(secure_secret_store.sys, "platform", "win32"):
                with patch.dict(sys.modules, {"keyring": fake_keyring}):
                    with patch("shutil.which", return_value=None):
                        store = EncryptedSecretStore(secret_path=secret_path)
                        with self.assertRaises(SecretStoreError) as exc:
                            store.load(passphrase="")

        self.assertIn("Failed reading secret", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
