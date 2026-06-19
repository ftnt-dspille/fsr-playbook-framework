"""HTTP-level tests for /api/llm/* — the configuration surface the
Settings page drives. We mock the OpenAI client so connectivity tests
don't need an LM Studio instance running.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend import secrets_store, settings as _settings
from backend.app import app


@pytest.fixture
def client():
    return TestClient(app)


# ---- list / patch / redact --------------------------------------

def test_list_providers_redacts_keys(client):
    _settings.save_provider("anthropic", api_key="sk-ant-real", model="claude")
    r = client.get("/api/llm/providers")
    assert r.status_code == 200
    body = r.json()
    assert "sk-ant-real" not in r.text
    assert body["providers"]["anthropic"]["api_key_set"] is True


def test_patch_provider_writes_url_and_model(client):
    r = client.post("/api/llm/providers/lmstudio", json={
        "base_url": "http://10.0.0.5:1234/v1",
        "model": "qwen2.5-coder-7b",
    })
    assert r.status_code == 200
    cfg = _settings.load_provider("lmstudio")
    assert cfg.base_url == "http://10.0.0.5:1234/v1"
    assert cfg.model == "qwen2.5-coder-7b"


def test_patch_provider_strips_trailing_slash(client):
    """Tiny but matters: AsyncOpenAI rejects double-slash paths if the
    user pastes 'http://host/v1/'. Normalize at the boundary."""
    client.post("/api/llm/providers/lmstudio",
                json={"base_url": "http://localhost:1234/v1/"})
    assert _settings.load_provider("lmstudio").base_url == "http://localhost:1234/v1"


def test_patch_provider_unknown_name_404(client):
    r = client.post("/api/llm/providers/bogus", json={"model": "x"})
    assert r.status_code == 404


def test_patch_provider_clear_api_key(client):
    _settings.save_provider("anthropic", api_key="sk-ant-x", model="claude")
    r = client.post("/api/llm/providers/anthropic", json={"clear_api_key": True})
    assert r.status_code == 200
    assert _settings.load_provider("anthropic").api_key is None


# ---- test connectivity ------------------------------------------

def test_lmstudio_test_uses_form_values_not_saved(client):
    """The Test button must probe what's in the FORM, so a user can
    verify a new URL before clicking Save and clobbering working config."""
    fake_models = MagicMock()
    fake_models.list = AsyncMock(return_value=MagicMock(data=[]))
    fake_client = MagicMock(models=fake_models)
    with patch("openai.AsyncOpenAI",
               return_value=fake_client) as mk_ctor:
        r = client.post("/api/llm/providers/lmstudio/test", json={
            "base_url": "http://newhost:1234/v1", "api_key": "test-key",
        })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    # Critical: the constructor was called with the FORM values, not
    # whatever happens to be in settings.json.
    kwargs = mk_ctor.call_args.kwargs
    assert kwargs["base_url"] == "http://newhost:1234/v1"
    assert kwargs["api_key"] == "test-key"


def test_lmstudio_test_falls_back_to_saved_when_form_blank(client):
    _settings.save_provider("lmstudio",
                            base_url="http://saved:1234/v1", model="qwen")
    fake_models = MagicMock(); fake_models.list = AsyncMock(return_value=MagicMock(data=[]))
    fake_client = MagicMock(models=fake_models)
    with patch("openai.AsyncOpenAI",
               return_value=fake_client) as mk_ctor:
        r = client.post("/api/llm/providers/lmstudio/test", json={})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert mk_ctor.call_args.kwargs["base_url"] == "http://saved:1234/v1"


def test_lmstudio_test_reports_connection_refused(client):
    """A real ConnectionRefusedError surfaces a friendly hint, not the
    raw OpenAI traceback."""
    fake_models = MagicMock()
    fake_models.list = AsyncMock(side_effect=ConnectionRefusedError("nope"))
    fake_client = MagicMock(models=fake_models)
    with patch("openai.AsyncOpenAI", return_value=fake_client):
        r = client.post("/api/llm/providers/lmstudio/test",
                        json={"base_url": "http://localhost:1234/v1"})
    body = r.json()
    assert body["ok"] is False
    assert "refused" in body["error"].lower() or "ConnectionRefusedError" in body["error"]


def test_anthropic_test_is_shape_only(client):
    """Don't burn billable tokens on the Test button — just check shape."""
    r = client.post("/api/llm/providers/anthropic/test",
                    json={"api_key": "sk-ant-1234567890abcdef1234567890"})
    assert r.json()["ok"] is True

    r = client.post("/api/llm/providers/anthropic/test",
                    json={"api_key": "wrong-prefix"})
    body = r.json()
    assert body["ok"] is False
    assert "anthropic" in body["error"].lower() or "sk-ant" in body["error"]


# ---- list models ------------------------------------------------

def test_lmstudio_models_lists_advertised(client):
    _settings.save_provider("lmstudio",
                            base_url="http://localhost:1234/v1", model="x")
    fake_data = [MagicMock(id="qwen2.5-coder-32b"), MagicMock(id="llama-3.3-70b")]
    fake_models = MagicMock()
    fake_models.list = AsyncMock(return_value=MagicMock(data=fake_data))
    fake_client = MagicMock(models=fake_models)
    with patch("openai.AsyncOpenAI", return_value=fake_client):
        r = client.post("/api/llm/providers/lmstudio/models", json={})
    assert r.json() == {"ok": True, "models": ["qwen2.5-coder-32b", "llama-3.3-70b"]}


def test_lmstudio_models_without_url_returns_error(client, monkeypatch):
    """If base_url is somehow blank (env override / cleared default),
    surface a friendly message instead of letting AsyncOpenAI raise."""
    from backend import settings as _s
    monkeypatch.setitem(_s._DEFAULTS["lmstudio"], "base_url", "")
    r = client.post("/api/llm/providers/lmstudio/models", json={})
    assert r.json()["ok"] is False
    assert "base_url" in r.json()["error"]


def test_anthropic_models_returns_curated_catalog(client):
    r = client.post("/api/llm/providers/anthropic/models", json={})
    body = r.json()
    assert body["ok"] is True
    assert any("sonnet" in m for m in body["models"])


# ---- set active -------------------------------------------------

def test_set_active_persists(client):
    r = client.post("/api/llm/active", json={"name": "lmstudio", "model": "qwen-1"})
    assert r.status_code == 200
    assert _settings.get_active_provider_name() == "lmstudio"
    assert _settings.load_provider("lmstudio").model == "qwen-1"


def test_set_active_rejects_unknown(client):
    r = client.post("/api/llm/active", json={"name": "bogus"})
    assert r.status_code == 404
