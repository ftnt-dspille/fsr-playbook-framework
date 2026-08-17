"""TurnPlan (redesign Phase 2): one resolution point, dispatch-level gating.

The invariants that matter:
  * plan_turn advertises the FULL consolidated surface -- intent never
    subtracts tools; it only changes the stated prior in the prompt.
  * tier_policy mirrors TOOL_TIERS for every advertised tool.
  * the prompt carries the context prior, the stated constraints (budget,
    approval-tier contract), and the never-dead-end capability_gap rule.
  * the affordance gate refuses open-playbook writes at DISPATCH when no
    playbook is open, fail-closed with a capability_gap pointer -- and is
    inert when no plan is installed (host opt-in, zero default change).
"""
from __future__ import annotations

from fsr_playbooks.llm.tools import TOOL_TIERS, anthropic_tools, dispatch
from fsr_playbooks.llm.turn_plan import (
    TurnBudget,
    TurnContext,
    active_turn_plan,
    plan_turn,
    reset_turn_plan,
    set_turn_plan,
)


def test_full_surface_advertised_in_both_intents():
    full = {t["name"] for t in anthropic_tools()}
    for intent in ("triage", "build"):
        plan = plan_turn(intent)
        assert {t["name"] for t in plan.tools} == full, intent


def test_tier_policy_mirrors_tool_tiers():
    plan = plan_turn("triage")
    for t in plan.tools:
        assert plan.tier_policy[t["name"]] == TOOL_TIERS.get(t["name"], 0)


def test_prompt_carries_prior_constraints_and_gap_rule():
    ctx = TurnContext(page="alert record #37326", has_trace=True)
    plan = plan_turn("triage", context=ctx)
    p = plan.prompt
    assert "a prior, not a cage" in p
    assert "alert record #37326" in p
    assert "build_playbook_from_trace" in p           # trace affordance stated
    assert "capability_gap" in p                       # never-dead-end rule
    assert f"at most {plan.budget.max_tool_turns} tool calls" in p
    assert "Approval tier" in p


def test_intent_is_prior_not_slice():
    # build prior still advertises the triage frontier and vice versa
    build_names = {t["name"] for t in plan_turn("build").tools}
    assert {"emit_action_card", "run_op"} <= build_names
    triage_names = {t["name"] for t in plan_turn("triage").tools}
    assert {"validate_yaml", "push_playbook", "emit_playbook_offer"} <= triage_names


def test_low_signal_message_still_gated():
    plan = plan_turn("triage", message="hi")
    assert "Low-signal input" in plan.prompt
    assert "Low-signal input" not in plan_turn("triage", message="block 1.2.3.4").prompt


def test_budget_note_progression():
    b = TurnBudget(max_tool_turns=5, soft_close_remaining=2)
    assert b.note(0) == ""
    assert "2 tool calls left" in b.note(3)
    assert "1 tool call left" in b.note(4)
    assert "Tool budget exhausted" in b.note(5)
    assert b.remaining(99) == 0


def test_gate_refuses_open_playbook_frontier_without_playbook():
    plan = plan_turn("build", context=TurnContext(has_open_playbook=False))
    for call in (
        ("emit_patch_proposal", {}),
        ("emit_enhancement_offer", {}),
        ("verify_enhancement", {}),
        ("emit_card", {"card_type": "patch_proposal"}),
        ("emit_card", {"card_type": "enhancement_offer"}),
    ):
        r = plan.gate_refusal(*call)
        assert r is not None and r["code"] == "not_afforded", call
        assert "capability_gap" in r["error"], call


def test_gate_affords_with_open_playbook_and_other_tools():
    plan = plan_turn("build", context=TurnContext(has_open_playbook=True))
    assert plan.gate_refusal("emit_patch_proposal", {}) is None
    assert plan.gate_refusal("emit_card", {"card_type": "patch_proposal"}) is None
    no_pb = plan_turn("triage")
    assert no_pb.gate_refusal("run_op", {}) is None
    assert no_pb.gate_refusal("emit_card", {"card_type": "capability_gap"}) is None
    assert no_pb.gate_refusal("emit_action_card", {}) is None


def test_dispatch_consults_installed_plan_and_only_then():
    # No plan installed: gate inert -- validation error, not not_afforded.
    out = dispatch("emit_card", {"card_type": "patch_proposal"})
    assert (out or {}).get("code") != "not_afforded"

    plan = plan_turn("build")  # has_open_playbook defaults False
    token = set_turn_plan(plan)
    try:
        assert active_turn_plan() is plan
        gated = dispatch("emit_card", {"card_type": "patch_proposal"})
        assert gated["code"] == "not_afforded"
        # resume path (_internal) bypasses the affordance gate like other
        # turn-scoped gates -- an approved action must never re-refuse.
        resumed = dispatch(
            "emit_card", {"card_type": "patch_proposal"}, _internal=True)
        assert (resumed or {}).get("code") != "not_afforded"
    finally:
        reset_turn_plan(token)
    assert active_turn_plan() is None
