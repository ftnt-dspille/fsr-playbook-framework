"""Pytest config — make the FastAPI app importable from any cwd, and
swap in an in-memory secrets backend + temporary settings.json so tests
never touch the real OS keychain or the developer's saved settings."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _MemorySecrets:
    """Drop-in for SecretsBackend that lives in process memory only.
    Tests can preload entries to stand in for "user has saved a key"."""

    def __init__(self, initial: dict[str, str] | None = None):
        self._data = dict(initial or {})

    def get(self, name): return self._data.get(name)
    def set(self, name, value): self._data[name] = value
    def delete(self, name): self._data.pop(name, None)
    def available(self): return True, "MemorySecrets"


@pytest.fixture(autouse=True)
def _isolate_secrets_and_settings(tmp_path, monkeypatch):
    """Every test gets a fresh in-memory keyring and a tmp settings.json
    so config writes don't leak between tests or hit real OS storage.

    Anthropic is pre-seeded with a fake key so any test that doesn't
    care about LLM config can still hit /api/chat without a config_error
    short-circuit. Tests that DO care about config can override the
    backend via `secrets_backend` param or write their own settings."""
    from backend import secrets_store, settings as _settings
    fake = _MemorySecrets({"anthropic_api_key": "sk-ant-test-fixture"})
    secrets_store.reset_for_tests(fake)
    monkeypatch.setattr(_settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(_settings, "SETTINGS_PATH", tmp_path / "settings.json")
    # `load_provider("anthropic")` auto-migrates ANTHROPIC_API_KEY from
    # env into the keyring when none is stored. A developer `.env` with a
    # real key would silently repopulate the in-memory backend mid-test
    # and defeat any "no key configured" assertion. Pin it absent.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    yield
    secrets_store.reset_for_tests(None)
