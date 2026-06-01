"""Phase 6 — emit_playbook_offer + reviewable-draft summarizer (PLAN §5,
contract 2.6.0). The offer card's ops_summary/draft_steps are built from the
recorded trace via the SAME deterministic compile the push uses, never
hand-written by the model."""
from __future__ import annotations

from fsr_core.agent.skill_trace import (
    SkillTrace, set_active_trace, clear_active_trace,
)
from fsr_core.compiler import skill_compiler as sc
from fsr_core.compiler import skill_verify as sv
from fsr_core.llm.intents import tools_for_intent
from fsr_core.mcp_server import emit_playbook_offer


def _trace() -> SkillTrace:
    t = SkillTrace()
    # Enrich: the IP is the alert literal (no prior step) → unverified gap.
    t.record_run_op(
        "virustotal", "get_ip_report", {"ip": "203.0.113.77"},
        {"attributes": {"network": "203.0.113.0/24"}}, ref_prefix="data",
    )
    # Block: the network comes from the enrich output → auto-wired + verified.
    t.record_run_op(
        "fortiedr", "isolate_host", {"host": "203.0.113.0/24"},
        {"status": "isolated"},
    )
    return t


def test_summarize_for_offer_labels_and_badges():
    t = _trace()
    compiled = sv.compile_and_verify(t)
    draft = sc.summarize_for_offer(t, compiled)

    assert [e["label"] for e in draft["ops_summary"]] == [
        "Get Ip Report", "Isolate Host"]
    block = draft["ops_summary"][1]
    assert block["step_type"] == "connector"
    assert block["connector"] == "fortiedr"
    assert block["operation"] == "isolate_host"
    # The wired step is verified; its label names the human source step.
    assert block["verified"] is True
    assert "Get Ip Report" in block["wiring_label"]
    # draft_steps mirrors verify badges per node.
    assert {d["node"]: d["verified"] for d in draft["draft_steps"]} == {
        "Get Ip Report": draft["ops_summary"][0]["verified"],
        "Isolate Host": True,
    }


def test_emit_playbook_offer_builds_card_from_active_trace():
    set_active_trace(_trace())
    try:
        out = emit_playbook_offer(
            id="pb-offer-1", summary="Save this triage?",
            title_suggestion="C2 Containment")
    finally:
        clear_active_trace()
    assert out["ok"] is True
    card = out["card"]
    assert card["type"] == "playbook_offer"
    assert card["id"] == "pb-offer-1"
    assert card["title_suggestion"] == "C2 Containment"
    assert card["editable_title"] is True
    assert len(card["ops_summary"]) == 2
    assert card["draft_steps"]  # branch/structure view present
    # Every entry carries the 2.6.0 enrichment fields.
    for e in card["ops_summary"]:
        assert {"skill_id", "step_type", "label", "wiring_label",
                "verified"} <= set(e)
    # The trace contains a containment op (isolate_host) → mutating, no advisory.
    assert card["has_mutating_action"] is True
    assert "advisory" not in card


def _read_only_trace() -> SkillTrace:
    t = SkillTrace()
    t.record_run_op(
        "virustotal", "get_ip_report", {"ip": "203.0.113.77"},
        {"attributes": {"reputation": -40}}, ref_prefix="data",
    )
    t.record_run_op(
        "abuseipdb", "lookup_ip", {"ip": "203.0.113.77"},
        {"abuseConfidenceScore": 90},
    )
    return t


def test_read_only_trace_offers_with_advisory_not_refused():
    # A2 (analyst decides, never refused): a purely read-only triage still
    # produces an offer card, but flags has_mutating_action=False + an advisory
    # so the analyst can choose to save an enrichment-only playbook.
    set_active_trace(_read_only_trace())
    try:
        out = emit_playbook_offer(id="ro-1", summary="Save these lookups?")
    finally:
        clear_active_trace()
    assert out["ok"] is True
    card = out["card"]
    assert card["has_mutating_action"] is False
    assert "advisory" in card and card["advisory"]
    assert len(card["ops_summary"]) == 2


def test_emit_playbook_offer_empty_trace_is_refused():
    set_active_trace(SkillTrace())
    try:
        out = emit_playbook_offer(id="x", summary="nothing to offer")
    finally:
        clear_active_trace()
    assert out["ok"] is False
    assert out["code"] == "empty_trace"


def test_emit_playbook_offer_validates_required_fields():
    set_active_trace(_trace())
    try:
        assert emit_playbook_offer(id="", summary="s")["ok"] is False
        assert emit_playbook_offer(id="x", summary="  ")["ok"] is False
    finally:
        clear_active_trace()


def test_emit_playbook_offer_available_to_triage_agent():
    names = {t["name"] for t in tools_for_intent("triage")}
    assert "emit_playbook_offer" in names
