"""Desktop-native triage path: the driving model runs the granular tools
itself; these primitives provide the trace-session lifecycle + guidance with
NO inner model / API key.

Proves the full native chain offline: start recording → record ops the way the
MCP `run_op` tool does (`skill_trace.record_run_op`) → state reflects them →
`build_playbook_from_trace()` (no args) compiles the active trace.
"""
from __future__ import annotations

import pytest

from fsr_core.agent import skill_trace
from fsr_core.mcp_server import tools_agent as ta
from fsr_core.mcp_server.tools_compile import build_playbook_from_trace


@pytest.fixture(autouse=True)
def _clean_trace():
    skill_trace.clear_active_trace()
    yield
    skill_trace.clear_active_trace()


def test_native_session_records_and_compiles():
    started = ta.triage_session_start(
        entity={"module": "incidents", "uuid": "INC-9",
                "fields": {"name": "Beaconing host"}})
    assert started["ok"] and started["recording"] is True
    assert started["module"] == "incidents"

    # Drive the granular tools the way Claude Desktop would. run_op records via
    # skill_trace.record_run_op when a trace is active — replicate that here
    # (real connectors so the full reference DB resolves them).
    skill_trace.record_run_op(
        "virustotal", "query_ip", {"ip": "203.0.113.77"},
        {"attributes": {"network_addr": "203.0.113.77"}}, ref_prefix="data")
    skill_trace.record_run_op(
        "fortigate-firewall", "block_ip_new", {"ip_address": "203.0.113.77"},
        {"status": "blocked"})

    state = ta.triage_session_state()
    assert state["recording"] is True
    assert state["count"] == 2
    assert [c["step_name"] for c in state["calls"]]

    # build_playbook_from_trace with no args reads the active session trace.
    built = build_playbook_from_trace(trace_json="", name="Native Triage PB")
    assert built["ok"] is True, built
    assert built.get("yaml")


def test_state_when_not_recording():
    assert ta.triage_session_state() == {
        "ok": True, "recording": False, "calls": [], "count": 0}


def test_clear_stops_recording():
    ta.triage_session_start()
    assert skill_trace.get_active_trace() is not None
    out = ta.triage_session_clear()
    assert out == {"ok": True, "recording": False}
    assert skill_trace.get_active_trace() is None


def test_guidance_returns_triage_prompt():
    g = ta.triage_guidance()
    assert g["ok"] and isinstance(g["guidance"], str) and g["guidance"].strip()
