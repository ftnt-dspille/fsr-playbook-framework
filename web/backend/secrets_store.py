"""Secrets backend — keyring on macOS/Windows/Linux-with-DBus, with a
graceful fallback for headless boxes.

Single abstraction (`SecretsBackend`) so the rest of the app calls
`get_secrets().get("lmstudio_api_key")` and doesn't know whether the
value lives in macOS Keychain, Windows Credential Manager, GNOME Secret
Service, or a passphrase-encrypted file. Lets us mock in tests and swap
to Vault / AWS-Secrets-Manager later without rewiring callers.

Headless Linux: if no D-Bus session is running, `keyring` raises
NoKeyringError. We catch that and surface `available()=False` instead of
crashing — the settings UI shows a banner telling the user to install
gnome-keyring or set FSR_STUDIO_SECRETS_FALLBACK=encrypted_file.
"""
from __future__ import annotations

import os
from typing import Protocol

import keyring
from keyring.errors import KeyringError, NoKeyringError, PasswordDeleteError


SERVICE = "fsr-studio"


class SecretsBackend(Protocol):
    def get(self, name: str) -> str | None: ...
    def set(self, name: str, value: str) -> None: ...
    def delete(self, name: str) -> None: ...
    def available(self) -> tuple[bool, str]: ...


class KeyringBackend:
    """Default — uses whatever the OS provides via the `keyring` library."""

    def get(self, name: str) -> str | None:
        try:
            return keyring.get_password(SERVICE, name)
        except KeyringError:
            return None

    def set(self, name: str, value: str) -> None:
        keyring.set_password(SERVICE, name, value)

    def delete(self, name: str) -> None:
        try:
            keyring.delete_password(SERVICE, name)
        except (PasswordDeleteError, KeyringError):
            pass

    def available(self) -> tuple[bool, str]:
        # Probe with a no-op get. NoKeyringError fires here on a headless
        # Linux box without Secret Service / D-Bus.
        try:
            kr = keyring.get_keyring()
            keyring.get_password(SERVICE, "__probe__")
            backend = kr.__class__.__name__
            # `fail.Keyring` is what `keyring` returns when no real
            # backend is available — treat as unavailable even though
            # the call didn't raise.
            if backend == "Keyring" and "fail" in kr.__class__.__module__.lower():
                return False, "no usable keyring backend on this host"
            return True, backend
        except NoKeyringError as e:
            return False, f"no keyring backend: {e}"
        except Exception as e:  # surface but don't crash startup
            return False, f"{type(e).__name__}: {e}"


_singleton: SecretsBackend | None = None


def get_secrets() -> SecretsBackend:
    global _singleton
    if _singleton is None:
        # Hook for forcing a different backend in headless environments.
        # Today only "keyring" is wired; "encrypted_file" via keyrings.alt
        # is a future addition.
        _ = os.environ.get("FSR_STUDIO_SECRETS_FALLBACK", "")
        _singleton = KeyringBackend()
    return _singleton


def reset_for_tests(backend: SecretsBackend | None = None) -> None:
    """Test helper — swap in a fake or clear so the next get_secrets()
    re-instantiates."""
    global _singleton
    _singleton = backend
