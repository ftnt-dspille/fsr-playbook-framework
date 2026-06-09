"""Phase 3 — trace→YAML compiler with value-match wiring (PLAN §3)."""
from __future__ import annotations

import yaml

from fsr_core.agent.skill_trace import SkillTrace
from fsr_core.compiler import skill_compiler as sc
from fsr_core.compiler.parser import parse_yaml


def _trace_enrich_then_block():
    """Enrich an IP (VirusTotal, payload under `.data`), then block the
    host the enrichment surfaced (crudhub-style, no `.data` wrapper)."""
    t = SkillTrace()
    t.record_run_op(
        "virustotal", "get_ip_report", {"ip": "203.0.113.77"},
        {"attributes": {"network": "203.0.113.0/24",
                        "last_analysis_stats": {"malicious": 9}}},
        ref_prefix="data",
    )
    t.record_run_op(
        "fortiedr", "isolate_host",
        {"host": "203.0.113.0/24"},          # equals VT's .data.attributes.network
        {"status": "isolated"},
    )
    return t


def test_value_match_wires_downstream_literal_to_prior_output():
    t = _trace_enrich_then_block()
    out = sc.compile_trace(t)
    block = out["steps"][1]
    host = block["arguments"]["host"]
    assert host == "{{ vars.steps.Get_Ip_Report.data.attributes.network }}", host


def test_first_occurrence_left_as_literal():
    t = _trace_enrich_then_block()
    out = sc.compile_trace(t)
    enrich = out["steps"][0]
    # The IP is a one-off triage value with no earlier producer → literal.
    assert enrich["arguments"]["ip"] == "203.0.113.77"
    assert "Get_Ip_Report" not in out["wiring"]  # nothing wired in step 1


def test_embedded_ioc_in_query_string_is_wired():
    """A SIEM hunt embeds the IOC in a query string (`destIpAddr = <ip>`); the
    IP came from a prior op's output, so it should wire the embedded occurrence
    (not bake the IOC in as a literal) → the playbook is re-runnable."""
    t = SkillTrace()
    t.record_run_op("fortinet-fortisiem", "get_incidents", {},
                    [{"incidentId": "55", "indicator": "185.220.101.47"}])
    t.record_run_op("fortinet-fortisiem", "search_events",
                    {"attribute": "destIpAddr = 185.220.101.47"}, {})
    out = sc.compile_trace(t)
    attr = out["steps"][1]["arguments"]["attribute"]
    assert attr == "destIpAddr = {{ vars.steps.Get_Incidents[0].indicator }}", attr


def test_embedded_match_respects_token_boundary():
    """A partial IOC must NOT wire: 185.220.101.47 inside 185.220.101.470."""
    t = SkillTrace()
    t.record_run_op("c", "first", {}, {"ip": "185.220.101.47"})
    t.record_run_op("c", "second", {"q": "host 185.220.101.470 seen"}, {})
    out = sc.compile_trace(t)
    assert out["steps"][1]["arguments"]["q"] == "host 185.220.101.470 seen"


def test_embedded_skips_plain_words():
    """An unstructured word (no digit/separator) is too coincidental to embed —
    `Germany` appearing in both a prior output and a later literal is not wired."""
    t = SkillTrace()
    t.record_run_op("c", "first", {}, {"country": "Germany"})
    t.record_run_op("c", "second", {"note": "actor based in Germany region"}, {})
    out = sc.compile_trace(t)
    assert out["steps"][1]["arguments"]["note"] == "actor based in Germany region"


def test_whole_value_match_preferred_over_embedded():
    """When the whole param equals a prior output value, emit a pure ref, not an
    embedded substitution."""
    t = SkillTrace()
    t.record_run_op("c", "first", {}, {"net": "203.0.113.0/24"})
    t.record_run_op("c", "second", {"cidr": "203.0.113.0/24"}, {})
    out = sc.compile_trace(t)
    assert out["steps"][1]["arguments"]["cidr"] == "{{ vars.steps.First.net }}"


def test_bidirectional_hunt_wires_every_occurrence():
    """`srcIpAddr = X OR destIpAddr = X` must wire BOTH X's, or the playbook is
    still half-hardcoded."""
    t = SkillTrace()
    t.record_run_op("fortinet-fortisiem", "get_incidents", {},
                    [{"indicator": "185.220.101.47"}])
    t.record_run_op(
        "fortinet-fortisiem", "search_events",
        {"attribute": "srcIpAddr = 185.220.101.47 OR destIpAddr = 185.220.101.47"},
        {})
    out = sc.compile_trace(t)
    attr = out["steps"][1]["arguments"]["attribute"]
    ref = "{{ vars.steps.Get_Incidents[0].indicator }}"
    assert attr == f"srcIpAddr = {ref} OR destIpAddr = {ref}", attr


def test_record_field_parameterizes_embedded_ioc():
    """A hunt's first op embeds the alert's IOC in a query string with no prior
    producer; it should parameterize to the trigger record (re-runnable), not
    bake the IOC in as a literal."""
    steps = [{"type": "connector", "name": "Search Events",
              "arguments": {"connector": "fortinet-fortisiem",
                            "operation": "search_events",
                            "attribute": "srcIpAddr = 185.220.101.47"}}]
    gaps = {"Search Events": ["attribute"]}
    record_vars, new_steps, first = sc.wire_record_inputs(
        steps, gaps, {"sourceIp": "185.220.101.47"}, "Search Events")
    # A Set Inputs step is prepended and the trigger now points at it.
    assert first == "Set Inputs"
    assert new_steps[0]["name"] == "Set Inputs"
    (var, ref), = record_vars.items()
    assert ref == "{{ vars.input.records[0].sourceIp }}"
    attr = steps[0]["arguments"]["attribute"]
    assert attr == "srcIpAddr = {{ vars.steps.Set_Inputs." + var + " }}", attr
    assert gaps == {}  # the param was resolved, not left a gap


def _enrich_then_contain(count=14, verdict_bool=None, contain_op="block_ip_new"):
    t = SkillTrace()
    out = {"attributes": {"last_analysis_stats": {"malicious": count}}}
    if verdict_bool is not None:
        out = {"knownMalicious": verdict_bool}
    t.record_run_op("virustotal", "query_ip", {"ip": "9.9.9.9"}, out, ref_prefix="data")
    t.record_run_op("fortigate-firewall", contain_op,
                    {"ip_addresses": "9.9.9.9"}, {"status": "ok"})
    return t


def test_containment_guard_inserts_decision_and_set_variable():
    """enrich(malicious count) → block compiles to a guarded branch: a
    set_variable extracts the verdict and a decision only blocks when malicious."""
    c = sc.compile_trace(_enrich_then_contain(count=14))
    sc.insert_containment_guard(c, _enrich_then_contain(count=14))
    by_type = [(s["type"], s["name"]) for s in c["steps"]]
    assert ("set_variable", "Assess Verdict") in by_type
    assert ("decision", "Confirmed Malicious") in by_type
    dec = next(s for s in c["steps"] if s["type"] == "decision")
    assert dec["conditions"][0]["next"] == "Block Ip New"      # true → contain
    assert dec["default"] == "Containment Skipped"             # false → skip
    assert "| int) > 0" in dec["conditions"][0]["when"]
    # the enrichment now flows into the guard, not straight to the block
    enrich = next(s for s in c["steps"] if s["name"] == "Query Ip")
    assert enrich["next"] == "Assess Verdict"


def test_containment_guard_bool_verdict_uses_truthy_condition():
    c = sc.compile_trace(_enrich_then_contain(verdict_bool=True, contain_op="isolate_endpoint"))
    sc.insert_containment_guard(c, _enrich_then_contain(verdict_bool=True, contain_op="isolate_endpoint"))
    dec = next(s for s in c["steps"] if s["type"] == "decision")
    assert dec["conditions"][0]["when"] == "{{ vars.steps.Assess_Verdict.malicious_verdict }}"


def test_no_guard_without_verdict_signal():
    """No recognized verdict in the enrichment → leave the chain untouched (no
    guess), so we never synthesize a meaningless decision."""
    t = SkillTrace()
    t.record_run_op("shodan", "host_information", {"ip": "9.9.9.9"},
                    {"org": "Acme", "ports": [443]}, ref_prefix="")
    t.record_run_op("fortigate-firewall", "block_ip_new", {"ip_addresses": "9.9.9.9"}, {})
    c = sc.compile_trace(t)
    sc.insert_containment_guard(c, t)
    assert not any(s["type"] == "decision" for s in c["steps"])


def test_no_guard_without_containment():
    t = SkillTrace()
    t.record_run_op("virustotal", "query_ip", {"ip": "9.9.9.9"},
                    {"attributes": {"last_analysis_stats": {"malicious": 14}}}, ref_prefix="data")
    c = sc.compile_trace(t)
    sc.insert_containment_guard(c, t)
    assert not any(s["type"] == "decision" for s in c["steps"])


def test_trivial_values_are_not_wired():
    t = SkillTrace()
    t.record_run_op("c", "first", {"x": "seed_value"}, {"port": 443, "ok": True})
    t.record_run_op("c", "second", {"port": 443, "enabled": True}, {})
    out = sc.compile_trace(t)
    # 443 / True coincide but are trivial → no false-positive wire.
    assert "second" not in [k for k in out["wiring"]]
    assert "Second" not in out["wiring"]


def test_steps_chain_in_trace_order():
    t = _trace_enrich_then_block()
    out = sc.compile_trace(t)
    assert out["steps"][0]["next"] == "Isolate Host"
    assert "next" not in out["steps"][1]   # last step
    assert out["first_step"] == "Get Ip Report"


def test_bracket_quoting_for_non_identifier_keys():
    t = SkillTrace()
    t.record_run_op("crudhub", "find", {"q": "x"},
                    {"hydra:member": [{"@id": "/api/3/hosts/abc-123-uuid"}]})
    t.record_run_op("fortiedr", "block", {"target": "/api/3/hosts/abc-123-uuid"}, {})
    out = sc.compile_trace(t)
    ref = out["steps"][1]["arguments"]["target"]
    assert ref == "{{ vars.steps.Find['hydra:member'][0]['@id'] }}", ref


def test_compiled_playbook_parses_clean():
    t = _trace_enrich_then_block()
    out = sc.compile_trace(t)
    doc = {
        "collection": "00 - FSR Studio",
        "playbooks": [{
            "name": "Enrich And Block",
            "trigger": "start",
            "steps": [{"type": "start", "name": "Start",
                       "next": out["first_step"]}] + out["steps"],
        }],
    }
    _, errors = parse_yaml(yaml.safe_dump(doc, sort_keys=False))
    hard = [e for e in errors if getattr(e, "severity", "error") != "warning"]
    assert not hard, f"compiled trace failed to parse: {hard}"


def test_render_context_mirrors_runtime_prefix():
    t = _trace_enrich_then_block()
    ctx = sc.render_context(t)
    # VT payload nested under .data (ref_prefix), matching its wired ref.
    assert ctx["vars"]["steps"]["Get_Ip_Report"]["data"]["attributes"]["network"] \
        == "203.0.113.0/24"
    # crudhub-style step has no .data wrapper.
    assert "data" not in ctx["vars"]["steps"]["Isolate_Host"]


def test_gaps_lists_unwired_wirable_params():
    t = SkillTrace()
    # A wirable string with no producer → gap.
    t.record_run_op("c", "only", {"ticket": "INC-0001-unmatched"}, {})
    out = sc.compile_trace(t)
    assert out["gaps"].get("Only") == ["ticket"]


def test_assemble_binds_module_to_start_trigger():
    t = _trace_enrich_then_block()
    out = sc.compile_trace(t)
    doc = sc.assemble_playbook(out, name="Triage PB", module="alerts")
    start = doc["playbooks"][0]["steps"][0]
    assert start["type"] == "start"
    assert start["module"] == "alerts"  # → cybersponse.action, not Referenced


def test_assemble_without_module_leaves_bare_start():
    t = _trace_enrich_then_block()
    out = sc.compile_trace(t)
    doc = sc.assemble_playbook(out, name="Triage PB")
    start = doc["playbooks"][0]["steps"][0]
    assert "module" not in start


def test_assembled_playbook_ships_active():
    """A playbook compiled from a triage session imports enabled (is_active →
    isActive=true), so the analyst doesn't have to toggle it on before it runs."""
    t = _trace_enrich_then_block()
    out = sc.compile_trace(t)
    doc = sc.assemble_playbook(out, name="Triage PB", module="alerts")
    assert doc["playbooks"][0]["is_active"] is True
