"""Phase 4 — verify/repair loop over value-match wiring (PLAN §4)."""
from __future__ import annotations

from fsr_core.agent.skill_trace import SkillTrace
from fsr_core.compiler import skill_verify as sv
from fsr_core.compiler import skill_compiler as sc


def _trace_enrich_then_block():
    t = SkillTrace()
    t.record_run_op(
        "virustotal", "get_ip_report", {"ip": "203.0.113.77"},
        {"attributes": {"network": "203.0.113.0/24",
                        "last_analysis_stats": {"malicious": 9}}},
        ref_prefix="data",
    )
    t.record_run_op(
        "fortiedr", "isolate_host", {"host": "203.0.113.0/24"},
        {"status": "isolated"},
    )
    return t


def test_good_wire_verifies_against_captured_output():
    t = _trace_enrich_then_block()
    out = sv.compile_and_verify(t)
    assert out["verified"]["Isolate Host"]["host"] is True
    assert not out["repaired"]
    # The wire survives in the emitted step.
    assert out["steps"][1]["arguments"]["host"] == \
        "{{ vars.steps.Get_Ip_Report.data.attributes.network }}"
    assert not out["static_errors"], out["static_errors"]


def test_verify_wire_rejects_undefined_path():
    ctx = {"vars": {"steps": {"A": {"data": {"x": 1}}}}}
    assert sv.verify_wire("{{ vars.steps.A.data.x }}", ctx) is True
    assert sv.verify_wire("{{ vars.steps.A.data.missing }}", ctx) is False
    assert sv.verify_wire("{{ vars.steps.NoSuch.y }}", ctx) is False


def test_bad_wire_is_repaired_to_literal():
    """A wire whose path can't resolve is demoted back to the literal and
    recorded as a gap — never shipped as a dangling ref."""
    t = _trace_enrich_then_block()
    # Inject a render_fn that fails the IP wire to simulate a bad path.
    def failing_render(template, context=None, **_):
        return {"error": "Undefined"}
    out = sv.compile_and_verify(t, render_fn=failing_render)
    # host wire failed → repaired to literal, listed as a gap.
    assert out["verified"]["Isolate Host"]["host"] is False
    assert "host" in out["repaired"]["Isolate Host"]
    assert out["steps"][1]["arguments"]["host"] == "203.0.113.0/24"
    assert "host" in out["gaps"]["Isolate Host"]


def test_render_context_isolation_step_only_sees_earlier():
    """A step's wire is verified against EARLIER outputs only."""
    t = _trace_enrich_then_block()
    # Step 0 (enrich) has no prior outputs → its context is empty steps.
    ctx0 = sc.render_context(t, upto=0)
    assert ctx0["vars"]["steps"] == {}


def test_clean_trace_emits_no_static_errors():
    t = _trace_enrich_then_block()
    out = sv.compile_and_verify(t)
    assert out["static_errors"] == []


def test_live_render_fn_injection_is_used():
    t = _trace_enrich_then_block()
    calls = []
    def spy_render(template, context=None, **_):
        calls.append(template)
        return {"output": "203.0.113.0/24"}
    sv.compile_and_verify(t, render_fn=spy_render)
    assert any("vars.steps.Get_Ip_Report" in c for c in calls)
