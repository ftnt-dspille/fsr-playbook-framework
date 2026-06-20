"""Staged-action coverage — an `emit_action_card` containment the analyst was
offered but never executed must still be replayed into a trace-built playbook
(the `action_coverage` gap, CHAT_INTELLIGENCE §B4)."""
from __future__ import annotations

import yaml

from fsr_playbooks.agent import skill_trace as st
from fsr_playbooks.agent.skill_trace import SkillTrace
from fsr_playbooks.mcp_server import build_playbook_from_trace, emit_action_card


def test_record_staged_action_appends_staged_no_output_call():
    t = SkillTrace()
    call = t.record_staged_action(
        "fortigate-firewall", "block_ip_new", {"ip": "203.0.113.77"})
    assert call is not None
    assert call.staged is True
    assert call.observed_output is None
    assert call.resolved_inputs["connector"] == "fortigate-firewall"
    assert call.resolved_inputs["operation"] == "block_ip_new"
    assert len(t) == 1


def test_staged_action_is_deduped_against_same_op():
    t = SkillTrace()
    assert t.record_staged_action("fortigate-firewall", "block_ip_new",
                                  {"ip": "1.2.3.4"}) is not None
    # Re-staging the same op (re-emitted card across turns) is a no-op.
    assert t.record_staged_action("fortigate-firewall", "block_ip_new",
                                  {"ip": "1.2.3.4"}) is None
    assert len(t) == 1


def test_executed_op_wins_over_staged_duplicate():
    t = SkillTrace()
    t.record_run_op("fortigate-firewall", "block_ip_new", {"ip": "1.2.3.4"},
                    {"status": "blocked"})
    # The action later staged again must NOT add a second step — the executed
    # one (with its real output) wins.
    assert t.record_staged_action("fortigate-firewall", "block_ip_new",
                                  {"ip": "1.2.3.4"}) is None
    assert len(t) == 1
    assert t.calls[0].staged is False


def test_staged_flag_round_trips_through_json():
    t = SkillTrace()
    t.record_staged_action("fortigate-firewall", "block_ip_new", {"ip": "9.9.9.9"})
    t2 = SkillTrace.from_json(t.to_json())
    assert t2.calls[0].staged is True
    assert t2.calls[0].observed_output is None


def test_legacy_call_has_staged_false_and_omits_key():
    t = SkillTrace()
    t.record_run_op("virustotal", "get_ip_report", {"ip": "1.1.1.1"}, {"x": 1})
    assert "staged" not in t.calls[0].to_dict()
    assert t.calls[0].staged is False


def test_emit_action_card_records_into_active_trace():
    t = SkillTrace()
    st.set_active_trace(t)
    try:
        out = emit_action_card(
            id="contain-1",
            connector="fortigate-firewall",
            operation="block_ip_new",
            summary="Block the malicious source IP",
            args={"method": "Quarantine Based", "ip_addresses": "203.0.113.77", "time_to_live": "1 Hour"},
            editable_fields=["ip_addresses"],
        )
    finally:
        st.clear_active_trace()
    # The card still renders for the analyst...
    assert out["ok"] is True
    # ...AND the staged action was recorded for the trace compiler.
    assert len(t) == 1
    assert t.calls[0].staged is True
    assert t.calls[0].resolved_inputs["operation"] == "block_ip_new"


def test_emit_action_card_no_active_trace_is_safe():
    st.clear_active_trace()
    out = emit_action_card(
        id="contain-2", connector="fortigate-firewall", operation="block_ip_new",
        summary="Block IP", args={"method": "Quarantine Based", "ip_addresses": "203.0.113.77", "time_to_live": "1 Hour"}, editable_fields=["ip_addresses"],
    )
    assert out["ok"] is True  # no trace active → no crash, just no recording


def test_trace_build_replays_staged_containment_guarded():
    """End-to-end: enrichment (malicious verdict) + a STAGED containment compile
    into a playbook whose containment step is present and gated behind the
    verdict decision."""
    t = SkillTrace()
    t.record_run_op(
        "virustotal", "get_ip_report", {"ip": "203.0.113.77"},
        {"attributes": {"last_analysis_stats": {"malicious": 7}}},
        ref_prefix="data",
    )
    t.record_staged_action(
        "fortigate-firewall", "block_ip_new", {"ip": "203.0.113.77"})

    out = build_playbook_from_trace(t.to_json(), name="Enrich And Contain")
    assert out["ok"] is True
    doc = yaml.safe_load(out["yaml"])
    pb = doc["playbooks"][0]
    names = [s["name"] for s in pb["steps"]]
    # The staged containment is present as a real connector step...
    block = next(s for s in pb["steps"] if s["name"] == "Block Ip New")
    assert block["arguments"]["operation"] == "block_ip_new"
    # ...gated behind the synthesized malicious-verdict decision (safe-by-default).
    assert "Assess Verdict" in names
    assert "Confirmed Malicious" in names
    dec = next(s for s in pb["steps"] if s["name"] == "Confirmed Malicious")
    assert dec["conditions"][0]["next"] == "Block Ip New"
