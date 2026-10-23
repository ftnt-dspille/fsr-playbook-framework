"""faz_raw_query is the read-only FortiAnalyzer escape hatch, and it must stay
read-only.

The op it wraps (``json_rpc_freeform``) runs with ``confirm=True`` -- no approval
card -- so a config-changing JSON-RPC method (``set``/``add``/``delete``/...) sent
through here would write to FortiAnalyzer unapproved. The docstring always said
"read-only by intent", but nothing enforced it. These tests pin the contract:
only ``get``/``exec`` reach the op; any other method is refused with a structured
error and never runs. ``faz_search(by="raw")`` routes into the same function, so
the live axis is covered by the same guard.
"""
from __future__ import annotations

import pytest

from fsr_playbooks import execution_api
from fsr_playbooks.mcp_server import tools_triage


def _unwrap(tool):
    return getattr(tool, "fn", tool)


@pytest.fixture
def run_op_spy(monkeypatch):
    calls: list[tuple] = []

    def fake(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True, "data": []}

    monkeypatch.setattr(execution_api, "run_op", fake)
    return calls


@pytest.mark.parametrize("method", ["set", "add", "update", "delete", "clone", "move"])
def test_mutating_method_is_refused_and_never_runs(method, run_op_spy):
    out = tools_triage.faz_raw_query({"method": method, "params": [{"url": "/x"}]})
    assert out["ok"] is False
    assert out["code"] == "method_not_read_only"
    assert not run_op_spy, f"{method} must not reach run_op"


def test_missing_method_is_refused(run_op_spy):
    out = tools_triage.faz_raw_query({"params": [{"url": "/x"}]})
    assert out["ok"] is False and out["code"] == "method_not_read_only"
    assert not run_op_spy


@pytest.mark.parametrize("method", ["get", "exec", "GET", "Exec"])
def test_read_only_method_reaches_the_op(method, run_op_spy):
    out = tools_triage.faz_raw_query({"method": method, "params": [{"url": "/x"}]})
    assert out["ok"] is True
    assert len(run_op_spy) == 1


def test_raw_axis_also_refuses_a_write(run_op_spy):
    # faz_search(by="raw") parses the JSON body then delegates to faz_raw_query.
    out = _unwrap(tools_triage.faz_search)(by="raw", value='{"method": "delete"}')
    assert out["ok"] is False and out["code"] == "method_not_read_only"
    assert not run_op_spy
