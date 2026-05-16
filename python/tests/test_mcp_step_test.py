"""mcp_server.step_test — single-step variant of step_through_playbook.

Render-only path is tested offline (no live FSR). The execute path is
verified by stubbing run_op + _record_verification so we can assert the
verification side-effect without touching the live appliance.
"""
from __future__ import annotations

import textwrap

import pytest

pytest.importorskip(
    "mcp.server.fastmcp",
    reason="mcp package not installed (pip install mcp)",
)

import mcp_server  # noqa: E402
import mcp_server.tools_execution  # noqa: E402, F401
import mcp_server._shared  # noqa: E402, F401


YAML = textwrap.dedent(
    """\
    playbooks:
      - name: Demo
        steps:
          - id: trigger
            type: start
            name: Trigger
            next: fetch
          - id: fetch
            type: connector
            name: Fetch Ticket
            arguments:
              connector: jira
              operation: get_ticket_details
              params:
                issue_key: JIR-1
            next: stop
          - id: stop
            type: stop
            name: Stop
    """
)


def test_step_not_found():
    r = mcp_server.step_test(YAML, step_id="nope")
    assert r["ok"] is False
    assert "not found" in r["error"]


def test_render_only_when_execute_disabled(monkeypatch):
    # Force the live-client out of the picture so render is a no-op.
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)
    r = mcp_server.step_test(YAML, step_id="fetch", execute_safe_ops=False)
    assert r["ok"] is True
    assert r["status"] == "rendered"
    assert r["rendered_args"]["connector"] == "jira"
    assert r["verification_recorded"] is False


def test_executes_safe_op_and_records_verification(monkeypatch):
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)
    monkeypatch.setattr(
        mcp_server._shared, "_safe_op_category",
        lambda c, o: "investigation",
    )
    calls: list[tuple] = []
    monkeypatch.setattr(
        mcp_server.tools_execution, "run_op",
        lambda **kw: {"ok": True, "data": {"key": "JIR-1"},
                      "output_top_keys": ["key"]},
    )
    monkeypatch.setattr(
        mcp_server.tools_execution, "_record_verification",
        lambda c, o, s, n: calls.append((c, o, s)),
    )

    r = mcp_server.step_test(YAML, step_id="fetch")
    assert r["status"] == "executed"
    assert r["output"] == {"key": "JIR-1"}
    assert r["verification_recorded"] is True
    assert calls == [("jira", "get_ticket_details", "step_test_pass")]


def test_unsafe_op_is_skipped_not_executed(monkeypatch):
    """Op name without a safe prefix => `skipped`, no run_op call."""
    bad_yaml = YAML.replace("get_ticket_details", "delete_ticket")
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)
    monkeypatch.setattr(mcp_server._shared, "_safe_op_category", lambda c, o: "remediation")

    def _boom(**kw):
        raise AssertionError("run_op must not be called for unsafe ops")
    monkeypatch.setattr(mcp_server.tools_execution, "run_op", _boom)

    r = mcp_server.step_test(bad_yaml, step_id="fetch")
    assert r["status"] == "skipped"
    assert r["verification_recorded"] is False


def test_step_lookup_by_name_with_underscores(monkeypatch):
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)
    r = mcp_server.step_test(YAML, step_id="Fetch_Ticket", execute_safe_ops=False)
    assert r["ok"] is True
    assert r["step_id"] == "fetch"
