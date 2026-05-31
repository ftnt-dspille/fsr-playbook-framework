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

from fsr_core.mcp_server import tools_execution as te

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
