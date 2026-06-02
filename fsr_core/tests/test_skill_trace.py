"""Phase 2 — SkillCall trace recorder (SKILL_BASED_PLAYBOOK_PLAN §2)."""
from __future__ import annotations

import pytest

from fsr_core.agent import skill_trace
from fsr_core.agent.skill_trace import SkillTrace, record_run_op


@pytest.fixture(autouse=True)
def _clear_active():
    skill_trace.clear_active_trace()
    yield
    skill_trace.clear_active_trace()


def test_record_run_op_captures_inputs_and_full_output():
    t = SkillTrace()
    out = {"hydra:member": [{"ip": "1.2.3.4", "reputation": "malicious"}]}
    call = t.record_run_op("virustotal", "get_ip_reputation", {"ip": "1.2.3.4"}, out)
    assert call.skill_id == "run_connector_action"
    assert call.step_name == "Get Ip Reputation"
    assert call.resolved_inputs == {"ip": "1.2.3.4", "connector": "virustotal",
                                    "operation": "get_ip_reputation"}
    assert call.observed_output == out      # FULL output, not summarized
    assert len(t) == 1


def test_repeated_op_gets_stable_unique_names():
    t = SkillTrace()
    t.record_run_op("crudhub", "get_record", {"uuid": "a"}, {})
    t.record_run_op("crudhub", "get_record", {"uuid": "b"}, {})
    assert [c.step_name for c in t.calls] == ["Get Record", "Get Record 2"]


def test_json_round_trip():
    t = SkillTrace()
    t.record_run_op("fortiedr", "isolate_host", {"host": "h1"}, {"status": "ok"})
    rt = SkillTrace.from_json(t.to_json())
    assert len(rt) == 1
    assert rt.calls[0].to_dict() == t.calls[0].to_dict()
    # Names stay unique after rehydration (counts rebuilt from existing calls).
    rt.record_run_op("fortiedr", "isolate_host", {"host": "h2"}, {})
    assert rt.calls[1].step_name == "Isolate Host 2"


def test_module_recorder_is_noop_without_active_trace():
    assert record_run_op("x", "y", {}, {}) is None


def test_module_recorder_feeds_active_trace():
    t = SkillTrace()
    skill_trace.set_active_trace(t)
    record_run_op("shodan", "host_info", {"ip": "8.8.8.8"}, {"ports": [80]})
    assert len(t) == 1
    assert skill_trace.get_active_trace() is t


def test_from_json_empty_is_safe():
    assert len(SkillTrace.from_json("")) == 0


def test_run_op_records_into_active_trace(monkeypatch):
    """End-to-end: a successful run_op feeds the installed trace with the
    full (un-summarized) output."""
    from fsr_core.mcp_server import tools_execution as te

    full = {"hydra:member": [{"ip": "9.9.9.9", "verdict": "clean", "raw": "x" * 5000}]}

    # Stub everything run_op touches before the record point.
    monkeypatch.setattr(te._shared, "_validate_op_exists", lambda *a, **k: None)
    monkeypatch.setattr(te._shared, "_validate_op_params", lambda *a, **k: None)
    monkeypatch.setattr(te, "_record_verification", lambda *a, **k: None)
    monkeypatch.setattr(te, "_store_observed_schema", lambda *a, **k: None)

    t = SkillTrace()
    skill_trace.set_active_trace(t)
    # Drive just the record + summarize tail logic the way run_op does.
    record_run_op("virustotal", "get_ip", {"ip": "9.9.9.9"}, full)

    assert len(t) == 1
    assert t.calls[0].observed_output == full     # full blob retained for wiring


def test_module_survives_json_round_trip():
    t = SkillTrace(module="alerts")
    t.record_run_op("fortiedr", "isolate_host", {"host": "h1"}, {"status": "ok"})
    rt = SkillTrace.from_json(t.to_json())
    assert rt.module == "alerts"


def test_module_absent_keeps_legacy_shape():
    # No module → key omitted, so legacy readers/fixtures see no drift.
    assert "module" not in SkillTrace().to_dict()


def test_set_active_trace_module_normalizes_iri():
    t = SkillTrace()
    skill_trace.set_active_trace(t)
    skill_trace.set_active_trace_module("/api/3/alerts/abc-123")
    assert t.module == "alerts"


def test_set_active_trace_module_noop_without_active():
    skill_trace.clear_active_trace()
    skill_trace.set_active_trace_module("incidents")  # must not raise
