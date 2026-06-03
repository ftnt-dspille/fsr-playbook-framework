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


def test_recorded_config_is_emitted_on_connector_step():
    """A config id resolved by run_op (recorded on the trace) must surface as
    the connector step's `arguments.config`, so an agent-bound op runs against
    the same configuration the agent used (no INTEGRATION-12 at runtime). A
    trace without a config falls back to the `""` default."""
    t = SkillTrace()
    t.record_run_op("fortigate-firewall", "block_ip_new", {"ip": "1.2.3.4"},
                    {"status": "blocked"}, config="cfg-uuid-123")
    t.record_run_op("virustotal", "query_ip", {"ip": "1.2.3.4"},
                    {"attributes": {}}, ref_prefix="data")  # no config
    out = build_playbook_from_trace(t.to_json(), name="Cfg Carry")
    assert out["ok"] is True
    doc = yaml.safe_load(out["yaml"])
    steps = {s["name"]: s for s in doc["playbooks"][0]["steps"]
             if s["type"] == "connector"}
    assert steps["Block Ip New"]["arguments"]["config"] == "cfg-uuid-123"
    # The config-less step must not borrow the other step's id; the resolver
    # supplies the "" default at compile (asserted via the source YAML here —
    # omitted means defaulted downstream).
    assert steps["Query Ip"]["arguments"].get("config") in (None, "")


def test_recorded_agent_is_emitted_on_connector_step():
    """An agent-routed op (agent-bound connector like fortigate) must surface
    its FortiSOAR Agent id as the connector step's `arguments.agent` alongside
    `arguments.config`. A playbook connector step for an agent-routed connector
    needs the agent binding too — config alone isn't enough for the workflow
    engine to reach the connector. A non-agent op carries no `agent` field."""
    t = SkillTrace()
    t.record_run_op("fortigate-firewall", "get_addresses", {"name": ""},
                    {"result": []}, config="cfg-uuid-123",
                    agent="efe5dafd28b5e41cd4c37e5829ccc638")
    t.record_run_op("virustotal", "query_ip", {"ip": "1.2.3.4"},
                    {"attributes": {}}, ref_prefix="data")  # no agent
    out = build_playbook_from_trace(t.to_json(), name="Agent Carry")
    assert out["ok"] is True
    doc = yaml.safe_load(out["yaml"])
    steps = {s["name"]: s for s in doc["playbooks"][0]["steps"]
             if s["type"] == "connector"}
    assert steps["Get Addresses"]["arguments"]["agent"] == \
        "efe5dafd28b5e41cd4c37e5829ccc638"
    assert steps["Get Addresses"]["arguments"]["config"] == "cfg-uuid-123"
    assert steps["Query Ip"]["arguments"].get("agent") in (None, "")


def _conn_steps(out):
    import yaml as _y
    doc = _y.safe_load(out["yaml"])
    return doc, {s["name"]: s for s in doc["playbooks"][0]["steps"]}


def test_record_ioc_parameterized_to_records0_via_set_inputs():
    """A one-off IOC that matches a triaged-record field is parameterized to
    vars.input.records[0].<field> on a Set Inputs step (module-bound trigger),
    instead of baking the literal — so the playbook re-runs per record."""
    t = SkillTrace(module="incidents",
                   record_fields={"sourceIp": "102.220.160.21",
                                  "name": "C2 beacon"})
    t.record_run_op("virustotal", "query_ip", {"ip": "102.220.160.21"},
                    {"attributes": {}}, ref_prefix="data")
    out = build_playbook_from_trace(t.to_json(), name="Enrich From Record")
    assert out["ok"] is True
    doc, steps = _conn_steps(out)
    # manual per-record trigger
    assert steps["Start"]["module"] == "incidents"
    assert steps["Start"]["next"] == "Set Inputs"
    # the IOC is staged off the record, not a literal
    assert steps["Set Inputs"]["type"] == "set_variable"
    assert steps["Set Inputs"]["vars"]["ip"] == \
        "{{ vars.input.records[0].sourceIp }}"
    # the connector step consumes the staged var, no literal IP
    assert steps["Query Ip"]["arguments"]["ip"] == \
        "{{ vars.steps.Set_Inputs.ip }}"
    assert "102.220.160.21" not in out["yaml"]
    # the gap is resolved (parameterized), not surfaced as unwired
    assert "Query Ip" not in (out.get("gaps") or {})


def test_no_module_leaves_ioc_literal_no_set_inputs():
    """Without a module the trigger is a designer-only Referenced start where
    vars.input.records[0] does not resolve — so the IOC stays literal and no
    Set Inputs step is injected (records[0] would be a dangling reference)."""
    t = SkillTrace(record_fields={"sourceIp": "102.220.160.21"})  # no module
    t.record_run_op("virustotal", "query_ip", {"ip": "102.220.160.21"},
                    {"attributes": {}}, ref_prefix="data")
    out = build_playbook_from_trace(t.to_json(), name="No Module")
    assert out["ok"] is True
    doc, steps = _conn_steps(out)
    assert "Set Inputs" not in steps
    assert steps["Query Ip"]["arguments"]["ip"] == "102.220.160.21"


def test_record_fields_round_trip_json():
    t = SkillTrace(module="alerts", record_fields={"sourceIp": "1.2.3.4"})
    back = SkillTrace.from_json(t.to_json())
    assert back.module == "alerts"
    assert back.record_fields == {"sourceIp": "1.2.3.4"}
    # legacy trace (no record_fields) round-trips without the key
    legacy = SkillTrace()
    assert "record_fields" not in legacy.to_dict()
    assert SkillTrace.from_json(legacy.to_json()).record_fields is None
