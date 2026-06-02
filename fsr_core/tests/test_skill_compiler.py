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
