"""mcp_server.assert_playbook_outcome — declarative outcome assertions.

Closes Level 5 of the success ladder: after `run_playbook`, did the
playbook actually do what its description claimed? Tests stub the
live FSR client so they're hermetic.
"""
from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.fastmcp",
                    reason="mcp package not installed")

import fsr_core.mcp_server as mcp_server  # noqa: E402
import fsr_core.mcp_server._shared  # noqa: E402, F401


class _FakeResp:
    def __init__(self, status: int, payload):
        self.status_code = status
        self._payload = payload
        self.text = "" if status == 200 else "boom"

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status
        self.calls: list[tuple[str, dict]] = []

    def post(self, url, json=None, verify=True):  # noqa: A002
        self.calls.append((url, json))
        return _FakeResp(self.status, self.payload)


class _FakeClient:
    def __init__(self, payload, status=200):
        self.base_url = "https://fsr"
        self.verify_ssl = False
        self.session = _FakeSession(payload, status)


@pytest.fixture
def patch_live(monkeypatch):
    holder: dict[str, _FakeClient] = {}

    def setup(payload, status=200):
        c = _FakeClient(payload, status)
        holder["c"] = c
        monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: c)
        return c

    return setup


def test_record_exists_pass(patch_live):
    patch_live({"hydra:totalItems": 3, "hydra:member": [{"name": "x"}]})
    out = mcp_server.assert_playbook_outcome([
        {"kind": "record_exists", "module": "alerts",
         "filters": {"name": "Demo"}},
    ])
    assert out["ok"] is True
    assert out["passed"] == 1
    assert out["results"][0]["observed_count"] == 3


def test_record_exists_fail_no_match(patch_live):
    patch_live({"hydra:totalItems": 0, "hydra:member": []})
    out = mcp_server.assert_playbook_outcome([
        {"kind": "record_exists", "module": "alerts",
         "filters": {"name": "Missing"}},
    ])
    assert out["ok"] is False
    assert out["results"][0]["code"] == "no_match"


def test_record_count_gte(patch_live):
    patch_live({"hydra:totalItems": 12, "hydra:member": []})
    out = mcp_server.assert_playbook_outcome([
        {"kind": "record_count", "module": "indicators",
         "filters": {"sourceId": "feed-123"}, "op": "gte", "value": 10},
    ])
    assert out["ok"] is True
    assert out["results"][0]["code"] == "ok"


def test_record_count_lt_fail(patch_live):
    patch_live({"hydra:totalItems": 5, "hydra:member": []})
    out = mcp_server.assert_playbook_outcome([
        {"kind": "record_count", "module": "indicators",
         "filters": {}, "op": "lt", "value": 5},
    ])
    assert out["ok"] is False
    assert out["results"][0]["code"] == "count_mismatch"


def test_field_equals_dotted_path(patch_live):
    patch_live({
        "hydra:totalItems": 1,
        "hydra:member": [{"name": "Demo",
                          "status": {"itemValue": "Closed"}}],
    })
    out = mcp_server.assert_playbook_outcome([
        {"kind": "field_equals", "module": "alerts",
         "filters": {"name": "Demo"}, "field": "status.itemValue",
         "value": "Closed"},
    ])
    assert out["ok"] is True


def test_field_equals_mismatch(patch_live):
    patch_live({
        "hydra:totalItems": 1,
        "hydra:member": [{"name": "Demo",
                          "status": {"itemValue": "Open"}}],
    })
    out = mcp_server.assert_playbook_outcome([
        {"kind": "field_equals", "module": "alerts",
         "filters": {"name": "Demo"}, "field": "status.itemValue",
         "value": "Closed"},
    ])
    assert out["ok"] is False
    r = out["results"][0]
    assert r["code"] == "field_mismatch"
    assert r["observed"] == "Open"
    assert r["expected"] == "Closed"


def test_field_equals_ambiguous(patch_live):
    patch_live({"hydra:totalItems": 2, "hydra:member": [{}, {}]})
    out = mcp_server.assert_playbook_outcome([
        {"kind": "field_equals", "module": "alerts",
         "filters": {"severity.itemValue": "High"},
         "field": "name", "value": "x"},
    ])
    assert out["ok"] is False
    assert out["results"][0]["code"] == "ambiguous"


def test_unknown_kind_returns_structured_error(patch_live):
    patch_live({"hydra:totalItems": 0, "hydra:member": []})
    out = mcp_server.assert_playbook_outcome([
        {"kind": "lol_what", "module": "alerts"},
    ])
    assert out["ok"] is False
    assert out["results"][0]["code"] == "unknown_kind"


def test_pre_shaped_filter_body_passes_through(patch_live):
    c = patch_live({"hydra:totalItems": 1, "hydra:member": []})
    body = {"logic": "OR", "filters": [
        {"field": "name", "operator": "eq", "value": "a"},
        {"field": "name", "operator": "eq", "value": "b"},
    ]}
    out = mcp_server.assert_playbook_outcome([
        {"kind": "record_exists", "module": "alerts", "filters": body},
    ])
    assert out["ok"] is True
    sent = c.session.calls[0][1]
    assert sent == body


def test_no_live_fsr(monkeypatch):
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)
    out = mcp_server.assert_playbook_outcome([
        {"kind": "record_exists", "module": "alerts", "filters": {"x": 1}},
    ])
    assert out["ok"] is False
    assert out["code"] == "no_live_fsr"


def test_empty_assertions_rejected():
    out = mcp_server.assert_playbook_outcome([])
    assert out["ok"] is False
    assert out["code"] == "empty_assertions"
