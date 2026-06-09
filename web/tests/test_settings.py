"""Settings + secrets store: split-store roundtrip, redaction, migration.

Covers the boundary between non-secret JSON and OS-keyring (faked here
via the in-memory backend wired up by conftest). The point of these
tests: prove the api_key never lands in settings.json regardless of the
code path, and that load/save are idempotent.
"""
from __future__ import annotations

import json

import pytest

from backend import secrets_store, settings as _settings


def test_load_provider_returns_blank_when_nothing_saved():
    cfg = _settings.load_provider("lmstudio")
    assert cfg.name == "lmstudio"
    assert cfg.base_url == "http://localhost:1234/v1"  # default
    assert cfg.model == ""
    assert cfg.api_key is None
    assert cfg.is_configured() is False


def test_save_then_load_roundtrips_non_secret_fields():
    _settings.save_provider("lmstudio",
                            base_url="http://192.168.1.42:1234/v1",
                            model="qwen2.5-coder-32b",
                            api_key="ignored-by-lmstudio")
    cfg = _settings.load_provider("lmstudio")
    assert cfg.base_url == "http://192.168.1.42:1234/v1"
    assert cfg.model == "qwen2.5-coder-32b"
    assert cfg.api_key == "ignored-by-lmstudio"


def test_api_key_never_lands_in_json_file():
    """The whole point of the split. settings.json holds URL/model;
    keyring holds the secret. Reading the raw file should never reveal
    the key under any field name."""
    _settings.save_provider("lmstudio",
                            base_url="http://localhost:1234/v1",
                            model="qwen", api_key="super-secret-xyz")
    raw = json.loads(_settings.SETTINGS_PATH.read_text())
    assert "super-secret-xyz" not in json.dumps(raw)


def test_clear_api_key_with_none():
    _settings.save_provider("anthropic", api_key="sk-ant-something")
    assert _settings.load_provider("anthropic").api_key == "sk-ant-something"
    _settings.save_provider("anthropic", api_key=None)
    assert _settings.load_provider("anthropic").api_key is None


def test_empty_string_api_key_rejected():
    """Empty strings are footguns — make the caller pass None to mean
    'clear'. Stops a UI bug from silently wiping a working key."""
    with pytest.raises(ValueError):
        _settings.save_provider("anthropic", api_key="")


def test_redacted_view_never_includes_real_key():
    _settings.save_provider("anthropic", api_key="sk-ant-real-key", model="claude")
    view = _settings.redacted_view()
    assert "sk-ant-real-key" not in json.dumps(view)
    assert view["providers"]["anthropic"]["api_key_set"] is True


def test_redacted_view_reports_unconfigured_when_no_key():
    secrets_store.get_secrets().delete("anthropic_api_key")
    view = _settings.redacted_view()
    assert view["providers"]["anthropic"]["api_key_set"] is False
    assert view["providers"]["anthropic"]["configured"] is False


def test_set_active_provider_persists_and_rereads():
    _settings.set_active_provider("lmstudio", model="qwen-7b")
    assert _settings.get_active_provider_name() == "lmstudio"
    assert _settings.load_provider("lmstudio").model == "qwen-7b"


def test_active_provider_falls_back_to_env_then_default(monkeypatch):
    """No settings.json yet → STUDIO_LLM_PROVIDER → 'anthropic'."""
    monkeypatch.delenv("STUDIO_LLM_PROVIDER", raising=False)
    assert _settings.get_active_provider_name() == "anthropic"
    monkeypatch.setenv("STUDIO_LLM_PROVIDER", "lmstudio")
    assert _settings.get_active_provider_name() == "lmstudio"


def test_lmstudio_is_configured_needs_url_and_model():
    cfg = _settings.load_provider("lmstudio")
    assert not cfg.is_configured()
    _settings.save_provider("lmstudio", base_url="http://localhost:1234/v1", model="qwen")
    assert _settings.load_provider("lmstudio").is_configured()


def test_anthropic_is_configured_needs_key_and_model():
    """Different gate from lmstudio: anthropic must have the key, the
    URL is fixed by the SDK."""
    secrets_store.get_secrets().delete("anthropic_api_key")
    assert not _settings.load_provider("anthropic").is_configured()
    _settings.save_provider("anthropic", api_key="sk-ant-x", model="claude-sonnet-4-5")
    assert _settings.load_provider("anthropic").is_configured()


def test_settings_health_reports_backend_name():
    health = _settings.secrets_health()
    assert health["ok"] is True
    assert health["backend"] == "MemorySecrets"  # fixture-installed backend


# ---- Secrets backend contract -----------------------------------

def test_secrets_get_set_delete_roundtrip():
    s = secrets_store.get_secrets()
    s.set("xyz", "value-1")
    assert s.get("xyz") == "value-1"
    s.delete("xyz")
    assert s.get("xyz") is None


def test_secrets_delete_is_idempotent():
    """Deleting a non-existent key shouldn't raise — UI flows assume
    'delete' is safe even if there's nothing to delete."""
    s = secrets_store.get_secrets()
    s.delete("never-set")
    s.delete("never-set")  # noqa — second call must not raise
