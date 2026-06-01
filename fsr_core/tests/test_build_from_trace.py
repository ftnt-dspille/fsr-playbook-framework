"""Phase 5 — build_playbook_from_trace entry point (PLAN §3–5)."""
from __future__ import annotations

import yaml

from fsr_core.agent.skill_trace import SkillTrace
from fsr_core.mcp_server import build_playbook_from_trace
from fsr_core.llm.intents import BUILD_ONLY_TOOLS, tools_for_intent


def _trace_json():
    t = SkillTrace()
    t.record_run_op(
        "virustotal", "get_ip_report", {"ip": "203.0.113.77"},
        {"attributes": {"network": "203.0.113.0/24"}}, ref_prefix="data",
    )
    t.record_run_op(
        "fortiedr", "isolate_host", {"host": "203.0.113.0/24"}, {"status": "isolated"},
    )
    return t.to_json()


def test_empty_trace_returns_fallback_signal():
    out = build_playbook_from_trace(SkillTrace().to_json())
    assert out["ok"] is False
    assert out["code"] == "empty_trace"


def test_bad_json_is_handled():
    out = build_playbook_from_trace("{not json")
    assert out["ok"] is False
    assert out["code"] == "bad_trace_json"


def test_builds_yaml_with_value_matched_wire():
    out = build_playbook_from_trace(_trace_json(), name="Enrich And Block")
    assert out["ok"] is True
    doc = yaml.safe_load(out["yaml"])
    pb = doc["playbooks"][0]
    assert pb["name"] == "Enrich And Block"
    # start → enrich → block backbone present.
    names = [s["name"] for s in pb["steps"]]
    assert names[0] == "Start"
    assert "Isolate Host" in names
    block = next(s for s in pb["steps"] if s["name"] == "Isolate Host")
    assert block["arguments"]["host"] == \
        "{{ vars.steps.Get_Ip_Report.data.attributes.network }}"
    # The wire was verified, no dangling-ref gap on host.
    assert out["verified"]["Isolate Host"]["host"] is True
    assert "host" not in out.get("gaps", {}).get("Isolate Host", [])


def test_tool_is_build_only_not_in_triage_slice():
    assert "build_playbook_from_trace" in BUILD_ONLY_TOOLS
    triage_names = {t["name"] for t in tools_for_intent("triage")}
    assert "build_playbook_from_trace" not in triage_names
