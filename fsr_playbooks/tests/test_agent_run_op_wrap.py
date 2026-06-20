"""Unit-test the agent-proxied run_op force-fail wrap (offline).

`_run_op_via_agent_playbook` compiles a 2-step [connector op] -> [boom]
playbook, pushes it UNWRAPPED, triggers it, polls to the (expected) failed
terminal, then reads the connector step's result from the failed run and
disambiguates success vs. real error. The live recipe is in memory
fsr_agent_proxied_execute_async.md; here we stub the HTTP seam so the
parse/disambiguate logic is locked in without a live FortiSOAR.
"""
from __future__ import annotations

import sqlite3

import pytest

from fsr_playbooks.mcp_server import tools_execution as te

_CONNECTOR = "fortinet-fortisiem"
_OP = "get_ip_context"


def _has_connector(name: str) -> bool:
    try:
        with sqlite3.connect(f"file:{te.DB_PATH}?mode=ro", uri=True) as con:
            return con.execute(
                "SELECT 1 FROM connectors WHERE name=? LIMIT 1", (name,)
            ).fetchone() is not None
    except Exception:
        return False


class _Resp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


class _FakeSession:
    """Routes the four calls the wrap makes; records them for assertions."""

    def __init__(self, run_step):
        self._run_step = run_step
        self.calls: list[tuple[str, str]] = []

    def post(self, url, json=None, verify=None):
        self.calls.append(("POST", url))
        if url.endswith("/api/3/workflow_collections"):
            return _Resp(201, {})
        if "/api/triggers/1/notrigger/" in url:
            return _Resp(200, {"task_id": "TASK1"})
        return _Resp(200, {})

    def put(self, url, json=None, verify=None):
        self.calls.append(("PUT", url))
        return _Resp(200, {})

    def get(self, url, verify=None):
        self.calls.append(("GET", url))
        if "step_detail=true" in url:
            return _Resp(200, {"steps": [
                self._run_step,
                {"name": "Boom", "status": "failed", "result": {}},
            ]})
        if "task_id=TASK1" in url:
            return _Resp(200, {"hydra:member": [
                {"status": "failed", "@id": "/api/3/workflows/PK1"},
            ]})
        return _Resp(200, {})

    def delete(self, url, json=None, verify=None):
        self.calls.append(("DELETE", url))
        return _Resp(200, {})


class _FakeClient:
    base_url = "http://fsr.test"
    verify_ssl = False

    def __init__(self, run_step):
        self.session = _FakeSession(run_step)


@pytest.fixture(autouse=True)
def _skip_if_no_connector():
    if not _has_connector(_CONNECTOR):
        pytest.skip(f"{_CONNECTOR} not in reference DB")


def test_agent_wrap_success_returns_step_data():
    run_step = {
        "name": "Run", "status": "finished",
        "result": {"data": {"blocked_ip": ["203.0.113.99"]},
                   "status": "Success", "_status": True},
    }
    client = _FakeClient(run_step)
    out = te._run_op_via_agent_playbook(
        _CONNECTOR, _OP, {"value": "203.0.113.99"},
        "cfg-uuid-1", "1.0.0", "agent-xyz", client, timeout_s=5)

    assert out["ok"] is True, out
    assert out["data"] == {"blocked_ip": ["203.0.113.99"]}
    assert out["_via_agent"] is True
    assert out["_agent_id"] == "agent-xyz"
    # UNWRAPPED push to the bare collection endpoint, then trigger.
    assert ("POST", "http://fsr.test/api/3/workflow_collections") in client.session.calls
    assert any(m == "POST" and "/api/triggers/1/notrigger/" in u
               for m, u in client.session.calls)


class _ConfiguredSession:
    """Stubs the `configured=true` connector_details POST only."""
    def __init__(self, configured_payload):
        self._payload = configured_payload

    def post(self, url, json=None, verify=None):
        return _Resp(200, {"data": self._payload})


class _ConfiguredClient:
    base_url = "http://fsr.test"
    verify_ssl = False

    def __init__(self, configured_payload):
        self.session = _ConfiguredSession(configured_payload)


def test_configured_rows_merges_agent_config_for_dual_install(monkeypatch):
    """A connector installed BOTH locally and on an agent must keep its
    agent-only config resolvable — regression for code-snippet, whose agent
    config `test` was dropped by the name-dedup so run_op never wrapped it
    (returned the empty in-progress stub instead). See
    fsr_agent_proxied_execute_async.md."""
    # Local install: only the "System" config (default), no agent id.
    local_row = {
        "name": "code-snippet", "config_count": 1, "status": "Completed",
        "configuration": [
            {"id": 45, "config_id": "a54ad23a-local", "name": "System",
             "default": True},
        ],
    }
    # Agent install of the SAME connector: the "test" config lives only here.
    agent_row = {
        "name": "code-snippet", "config_count": 1, "status": "Completed",
        "_agent_id": "agent-xyz",
        "configuration": [
            {"id": 156, "config_id": "af8622ab-agent", "name": "test",
             "default": False},
        ],
    }
    monkeypatch.setattr(te, "_agent_configured_rows", lambda client: [agent_row])
    te._CONFIGURED_CACHE["rows"] = None  # bypass any cached set

    rows = te._configured_rows(_ConfiguredClient([local_row]), force=True)
    cs = next(r for r in rows if r["name"] == "code-snippet")
    names = {c["name"] for c in cs["configuration"]}
    assert names == {"System", "test"}, cs["configuration"]
    assert cs.get("_agent_id") == "agent-xyz"
    # The agent-only config name now resolves to its UUID (the thing the
    # dispatch checks against _agent_config_ids).
    assert te._resolve_config_id(rows, "code-snippet", "test") == "af8622ab-agent"
    assert te._resolve_config_id(rows, "code-snippet", "System") == "a54ad23a-local"
    te._CONFIGURED_CACHE["rows"] = None  # don't leak the stub into other tests


def test_agent_config_ids_excludes_locally_runnable(monkeypatch):
    """A config that is configured locally on the master must NOT be treated as
    agent-bound, even when the same config_id also surfaces under a remote agent
    (a tenant `connector_details?agent=…` query echoes the master's shared
    configs). Regression for the FMG json-rpc device list coming back truncated
    to ~5 rows because run_op needlessly routed a local read through the
    force-fail-playbook wrap (which reads a PERSISTED, FSR-capped step result)."""
    agent_row = {
        "name": "fortinet-fortimanager-json-rpc", "_agent_id": "tenant-1",
        "configuration": [
            {"config_id": "shared-evoke", "name": "evoke"},   # also local
            {"config_id": "agent-only", "name": "remote"},     # agent-exclusive
        ],
    }
    monkeypatch.setattr(te, "_agent_configured_rows", lambda client: [agent_row])
    monkeypatch.setattr(te, "_local_config_ids", lambda client: {"shared-evoke"})
    te._AGENT_CFG_CACHE["ids"] = None  # bypass cache

    ids = te._agent_config_ids(client=object())
    assert "shared-evoke" not in ids   # local → direct execute, no wrap
    assert "agent-only" in ids         # agent-exclusive → still wrapped
    te._AGENT_CFG_CACHE["ids"] = None  # don't leak into other tests


def test_agent_wrap_connector_error_surfaces_as_failure():
    # The connector op itself failed inside the playbook (not the Boom step).
    run_step = {
        "name": "Run", "status": "failed",
        "result": {"status": "Failure", "message": "auth scope denied"},
    }
    client = _FakeClient(run_step)
    out = te._run_op_via_agent_playbook(
        _CONNECTOR, _OP, {"value": "203.0.113.99"},
        "cfg-uuid-1", "1.0.0", "agent-xyz", client, timeout_s=5)

    assert out["ok"] is False
    assert out["_via_agent"] is True
    assert "auth scope denied" in out["message"]
