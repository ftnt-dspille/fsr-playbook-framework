"""Phase 5 -- build_playbook_from_trace entry point (PLAN §3-5)."""
from __future__ import annotations

import json
import yaml

from fsr_playbooks.agent.skill_trace import SkillTrace
from fsr_playbooks.mcp_server import build_playbook_from_trace
from fsr_playbooks.llm.intents import BUILD_ONLY_TOOLS, tools_for_intent


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
    assert block["host"] == \
        "{{ vars.steps.Get_Ip_Report.data.attributes.network }}"
    # The wire was verified, no dangling-ref gap on host.
    assert out["verified"]["Isolate Host"]["host"] is True
    assert "host" not in out.get("gaps", {}).get("Isolate Host", [])


def test_tool_is_build_only_not_in_triage_slice():
    assert "build_playbook_from_trace" in BUILD_ONLY_TOOLS
    triage_names = {t["name"] for t in tools_for_intent("triage")}
    assert "build_playbook_from_trace" not in triage_names


def test_tool_is_registered_and_advertised_for_build():
    """The trace compiler must be in the dispatch registry, or it's never
    advertised to the model and `_guarded_dispatch` rejects it as
    intent-disallowed even under build -- the agent then silently hand-authors
    (losing trace grounding). Regression for the SAFE_TOOLS omission."""
    from fsr_playbooks.llm.tools import REGISTRY, anthropic_tools, dispatch
    assert "build_playbook_from_trace" in REGISTRY
    advertised = {t["name"] for t in anthropic_tools()}
    assert "build_playbook_from_trace" in advertised
    # Callable with no args (uses the active trace); no trace → graceful
    # empty_trace, NOT an intent-rejection or a crash.
    from fsr_playbooks.agent import skill_trace
    skill_trace.clear_active_trace()
    out = dispatch("build_playbook_from_trace", {})
    assert out["ok"] is False and out["code"] == "empty_trace"


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
    assert steps["Block Ip New"]["config"] == "cfg-uuid-123"
    # The config-less step must not borrow the other step's id; the resolver
    # supplies the "" default at compile (asserted via the source YAML here --
    # omitted means defaulted downstream).
    assert steps["Query Ip"].get("config") in (None, "")


def test_recorded_agent_is_emitted_on_connector_step():
    """An agent-routed op (agent-bound connector like fortigate) must surface
    its FortiSOAR Agent id as the connector step's `arguments.agent` alongside
    `arguments.config`. A playbook connector step for an agent-routed connector
    needs the agent binding too -- config alone isn't enough for the workflow
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
    assert steps["Get Addresses"]["agent"] == \
        "efe5dafd28b5e41cd4c37e5829ccc638"
    assert steps["Get Addresses"]["config"] == "cfg-uuid-123"
    assert steps["Query Ip"].get("agent") in (None, "")


def _conn_steps(out):
    import yaml as _y
    doc = _y.safe_load(out["yaml"])
    return doc, {s["name"]: s for s in doc["playbooks"][0]["steps"]}


def test_record_ioc_parameterized_to_records0_via_set_inputs():
    """A one-off IOC that matches a triaged-record field is parameterized to
    vars.input.records[0].<field> on a Set Inputs step (module-bound trigger),
    instead of baking the literal -- so the playbook re-runs per record."""
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
    assert steps["Query Ip"]["ip"] == \
        "{{ vars.steps.Set_Inputs.ip }}"
    assert "102.220.160.21" not in out["yaml"]
    # the gap is resolved (parameterized), not surfaced as unwired
    assert "Query Ip" not in (out.get("gaps") or {})


def test_no_module_leaves_ioc_literal_no_set_inputs():
    """Without a module the trigger is a designer-only Referenced start where
    vars.input.records[0] does not resolve -- so the IOC stays literal and no
    Set Inputs step is injected (records[0] would be a dangling reference)."""
    t = SkillTrace(record_fields={"sourceIp": "102.220.160.21"})  # no module
    t.record_run_op("virustotal", "query_ip", {"ip": "102.220.160.21"},
                    {"attributes": {}}, ref_prefix="data")
    out = build_playbook_from_trace(t.to_json(), name="No Module")
    assert out["ok"] is True
    doc, steps = _conn_steps(out)
    assert "Set Inputs" not in steps
    assert steps["Query Ip"]["ip"] == "102.220.160.21"


def test_record_fields_round_trip_json():
    t = SkillTrace(module="alerts", record_fields={"sourceIp": "1.2.3.4"})
    back = SkillTrace.from_json(t.to_json())
    assert back.module == "alerts"
    assert back.record_fields == {"sourceIp": "1.2.3.4"}
    # legacy trace (no record_fields) round-trips without the key
    legacy = SkillTrace()
    assert "record_fields" not in legacy.to_dict()
    assert SkillTrace.from_json(legacy.to_json()).record_fields is None


# --- JSON-blob record fields (#74) ----------------------------------------------
#
# Record fields like `sourcedata` carry a JSON string with nested values
# (hostName, destIpAddr).  The compiler must parse these and parameterize
# gap values found inside, using the `| from_json` Jinja filter.

def test_json_blob_field_whole_value_match():
    """A gap param whose literal matches a value nested inside a JSON-string
    record field is parameterized via `| from_json`."""
    blob = json.dumps({"incident_data": {"incidentTarget": {
        "destIpAddr": "102.220.160.21", "hostName": "smithDesktop"}}})
    t = SkillTrace(module="incidents",
                   record_fields={"destinationIp": "102.220.160.21",
                                  "sourcedata": blob})
    t.record_run_op("fortinet-fsr-soc-assistant", "call_mcp_tool",
                    {"tool": "siem_search_host",
                     "args": {"host": "smithDesktop", "window": "2h"}},
                    {"results": []}, step_name="siem_search_host")
    out = build_playbook_from_trace(t.to_json(), name="JSON Blob Match")
    assert out["ok"] is True
    doc, steps = _conn_steps(out)
    assert "Set Inputs" in steps
    si = steps["Set Inputs"]["vars"]
    # the host is extracted from the JSON blob via from_json
    assert "smithDesktop" not in out["yaml"]
    assert any("from_json" in v for v in si.values())
    # the gap is resolved
    assert "siem_search_host" not in (out.get("gaps") or {})


def test_json_blob_field_simple_field_still_works():
    """A record with both a simple field and a JSON blob field parameterizes
    the simple field normally (no from_json) and the blob field with from_json."""
    blob = json.dumps({"incident_data": {"incidentTarget": {
        "destIpAddr": "102.220.160.21", "hostName": "smithDesktop"}}})
    t = SkillTrace(module="incidents",
                   record_fields={"destinationIp": "10.0.0.5",
                                  "sourcedata": blob})
    t.record_run_op("virustotal", "query_ip", {"ip": "10.0.0.5"},
                    {"attributes": {}}, ref_prefix="data")
    t.record_run_op("fortinet-fsr-soc-assistant", "call_mcp_tool",
                    {"tool": "siem_search_host",
                     "args": {"host": "smithDesktop", "window": "2h"}},
                    {"results": []}, step_name="siem_search_host")
    out = build_playbook_from_trace(t.to_json(), name="Mixed Fields")
    assert out["ok"] is True
    doc, steps = _conn_steps(out)
    si = steps["Set Inputs"]["vars"]
    # simple field: no from_json
    ip_ref = si.get("ip", "")
    assert "from_json" not in ip_ref
    assert ip_ref == "{{ vars.input.records[0].destinationIp }}"
    # blob field: from_json
    host_ref = si.get("host", "")
    assert "from_json" in host_ref


def test_json_blob_field_not_json_stays_literal():
    """A record field that looks like JSON but isn't (malformed) should not
    break compilation -- the gap param stays literal."""
    t = SkillTrace(module="incidents",
                   record_fields={"sourcedata": "{not valid json"})
    t.record_run_op("fortinet-fsr-soc-assistant", "call_mcp_tool",
                    {"tool": "siem_search_host",
                     "args": {"host": "smithDesktop", "window": "2h"}},
                    {"results": []}, step_name="siem_search_host")
    out = build_playbook_from_trace(t.to_json(), name="Bad JSON")
    assert out["ok"] is True
    doc, steps = _conn_steps(out)
    # no Set Inputs -- the host couldn't be parameterized
    # (smithDesktop isn't in record_fields and the JSON didn't parse)
    assert "siem_search_host" in (out.get("gaps") or {})


def test_json_blob_embedded_ioc_in_query_string():
    """An IOC-shaped value inside a JSON blob can be used for embedded
    (substring) matching in a query string, with the from_json filter."""
    blob = json.dumps({"incident_data": {"incidentTarget": {
        "destIpAddr": "198.51.100.42"}}})
    t = SkillTrace(module="alerts",
                   record_fields={"sourcedata": blob})
    t.record_run_op("fortinet-fortisiem", "query_events",
                    {"query": "srcIpAddr = 198.51.100.42"},
                    {"events": []}, step_name="siem_query")
    out = build_playbook_from_trace(t.to_json(), name="Embedded JSON IOC")
    assert out["ok"] is True
    doc, steps = _conn_steps(out)
    assert "Set Inputs" in steps
    si = steps["Set Inputs"]["vars"]
    # the IOC is extracted from the JSON blob via from_json
    assert any("from_json" in v for v in si.values())
    assert "198.51.100.42" not in out["yaml"]
    # the gap is resolved
    assert "siem_query" not in (out.get("gaps") or {})


# --- containment carries its own human gate ------------------------------------
#
# The tier gate that protects containment during triage is AGENT dispatch logic;
# a compiled playbook runs without it. So the artifact needs its own gate.

def _contain_trace(enrich_output):
    t = SkillTrace()
    t.record_run_op("virustotal", "get_ip_report", {"ip": "203.0.113.77"},
                    enrich_output, ref_prefix="data")
    t.record_run_op("fortiedr", "isolate_host", {"host": "203.0.113.77"},
                    {"status": "isolated"})
    return t


def _steps_by_name(out):
    doc = yaml.safe_load(out["yaml"])
    return {s["name"]: s for s in doc["playbooks"][0]["steps"]}


def test_containment_is_fronted_by_a_confirm_stop_manual_input():
    out = build_playbook_from_trace(
        _contain_trace({"attributes": {"last_analysis_stats": {"malicious": 7}}}).to_json())
    steps = _steps_by_name(out)

    assert "Confirm Containment" in steps, "containment compiled with no human gate"
    mi = steps["Confirm Containment"]
    assert mi["type"] == "manual_input"
    routes = {o["display"]: o["next"] for o in mi["options"]}
    assert routes["Confirm"] == "Isolate Host"
    assert routes["Stop"] != "Isolate Host", "Stop must not reach containment"


def test_confirm_gate_is_inserted_even_with_no_recognized_verdict():
    """The verdict guard no-ops on an unrecognized shape -- which used to leave
    containment fully ungated. The human gate must not depend on it."""
    out = build_playbook_from_trace(
        _contain_trace({"totally": {"unrecognized": "shape"}}).to_json())
    steps = _steps_by_name(out)

    assert "Confirmed Malicious" not in steps      # verdict guard correctly no-op'd
    assert "Confirm Containment" in steps          # …but the human gate still ran
    assert steps["Confirm Containment"]["options"][0]["next"] == "Isolate Host"


def test_nothing_reaches_containment_except_through_the_confirmation():
    """Whatever pointed at containment -- including the verdict decision's
    malicious branch -- must be rewired into the confirmation."""
    out = build_playbook_from_trace(
        _contain_trace({"attributes": {"last_analysis_stats": {"malicious": 7}}}).to_json())
    steps = _steps_by_name(out)
    cont = "Isolate Host"

    for name, s in steps.items():
        if name == "Confirm Containment":
            continue
        assert s.get("next") != cont, f"{name}.next reaches containment directly"
        for cond in (s.get("conditions") or []):
            assert cond.get("next") != cont, f"{name} branch reaches containment directly"
        assert s.get("default") != cont, f"{name}.default reaches containment directly"


def test_confirm_gate_is_idempotent():
    t = _contain_trace({"attributes": {"last_analysis_stats": {"malicious": 7}}})
    out = build_playbook_from_trace(t.to_json())
    doc = yaml.safe_load(out["yaml"])
    names = [s["name"] for s in doc["playbooks"][0]["steps"]]
    assert names.count("Confirm Containment") == 1


def test_no_containment_means_no_confirmation_step():
    t = SkillTrace()
    t.record_run_op("virustotal", "get_ip_report", {"ip": "1.2.3.4"}, {"attributes": {}})
    out = build_playbook_from_trace(t.to_json())
    assert "Confirm Containment" not in _steps_by_name(out)


# --- containment is dry-runnable by construction -------------------------------
#
# useMockOutput=true is a SUBSTITUTION, not a kill switch: a step with no
# `mock_result` runs live however the run was triggered. So a trace-compiled
# containment step without one makes a nominally mocked run really contain.

def test_containment_step_carries_its_recorded_output_as_mock_result():
    out = build_playbook_from_trace(
        _contain_trace({"attributes": {"last_analysis_stats": {"malicious": 7}}}).to_json())
    cont = _steps_by_name(out)["Isolate Host"]

    mr = cont.get("mock_result")
    assert mr, "containment step has no mock_result -- a dry run would contain for real"
    assert isinstance(mr, str), "mock_result rides the wire as a JSON string"
    assert json.loads(mr) == {"status": "isolated"}, "the trace's recorded output is the mock"


def test_enrichment_steps_are_not_mocked():
    """Only state-changing steps are stamped -- a stale mocked verdict is worse
    than re-running a safe enrichment live."""
    out = build_playbook_from_trace(
        _contain_trace({"attributes": {"last_analysis_stats": {"malicious": 7}}}).to_json())
    assert not _steps_by_name(out)["Get Ip Report"].get("mock_result")


def test_unmocked_containment_is_reported_on_a_hand_authored_doc():
    from fsr_playbooks.compiler.skill_compiler import unmocked_containment_steps

    doc = {"playbooks": [{"steps": [
        {"type": "connector", "name": "Enrich", "operation": "get_ip_report"},
        {"type": "connector", "name": "Block", "operation": "block_ip_new"},
        {"type": "connector", "name": "Mocked Block", "operation": "block_ip_new",
         "mock_result": '{"status": "ok"}'},
    ]}]}
    assert unmocked_containment_steps(doc) == ["Block"]


def test_a_trace_compiled_playbook_reports_no_unmocked_containment():
    from fsr_playbooks.compiler.skill_compiler import unmocked_containment_steps

    out = build_playbook_from_trace(
        _contain_trace({"attributes": {"last_analysis_stats": {"malicious": 7}}}).to_json())
    assert unmocked_containment_steps(yaml.safe_load(out["yaml"])) == []
