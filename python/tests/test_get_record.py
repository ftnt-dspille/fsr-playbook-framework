"""mcp_server.get_record — single-record fetch by IRI or module+uuid.

Closes the prompt↔tool gap (hardening plan 2.1): the triage prompt tells
the agent to pull a record by ``iri``/``module``/``uuid`` to build an
attack timeline, but no read-only fetch tool existed. Tests stub the live
FSR client so they're hermetic.
"""
from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="mcp package not installed")

import fsr_core.mcp_server as mcp_server  # noqa: E402
import fsr_core.mcp_server._shared  # noqa: E402, F401


class _FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = "" if status == 200 else "boom"

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status
        self.urls: list[str] = []

    def get(self, url, verify=True):
        self.urls.append(url)
        return _FakeResp(self.status, self.payload)


class _FakeClient:
    def __init__(self, payload, status=200):
        self.base_url = "https://fsr"
        self.verify_ssl = False
        self.session = _FakeSession(payload, status)


@pytest.fixture
def patch_live(monkeypatch):
    holder = {}

    def setup(payload, status=200):
        c = _FakeClient(payload, status)
        holder["c"] = c
        monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: c)
        return c

    return setup


def test_missing_target_errors():
    out = mcp_server.get_record()
    assert out["ok"] is False
    assert out["code"] == "missing_target"


def test_fetch_by_iri_hydrates_relationships(patch_live):
    c = patch_live({"@id": "/api/3/alerts/abc", "name": "phish"})
    out = mcp_server.get_record(iri="/api/3/alerts/abc")
    assert out["ok"] is True
    assert out["record"]["name"] == "phish"
    assert c.session.urls[-1] == "https://fsr/api/3/alerts/abc?$relationships=true"


def test_fetch_by_module_uuid(patch_live):
    c = patch_live({"@id": "/api/3/alerts/xyz"})
    out = mcp_server.get_record(module="alerts", uuid="xyz", relationships=False)
    assert out["ok"] is True
    assert c.session.urls[-1] == "https://fsr/api/3/alerts/xyz"


def test_iri_normalised_and_querystring_stripped(patch_live):
    c = patch_live({"@id": "/api/3/alerts/abc"})
    mcp_server.get_record(iri="api/3/alerts/abc?$relationships=true")
    assert c.session.urls[-1] == "https://fsr/api/3/alerts/abc?$relationships=true"


def test_404_maps_to_not_found(patch_live):
    patch_live({}, status=404)
    out = mcp_server.get_record(iri="/api/3/alerts/missing")
    assert out["ok"] is False
    assert out["code"] == "not_found"


def test_no_fsr_configured(monkeypatch):
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)
    out = mcp_server.get_record(module="alerts", uuid="x")
    assert out["ok"] is False
    assert out["code"] == "no_fsr_configured"
