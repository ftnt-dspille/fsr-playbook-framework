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


def test_base_prompt_is_the_unlayered_intent_prompt():
    # A host that stacks its own prompt layers (grounding, personas) starts
    # from base_prompt; prompt = base_prompt + prior/constraints layers.
    from fsr_playbooks.llm.intents import load_intent_prompt
    for intent in ("triage", "build"):
        plan = plan_turn(intent)
        assert plan.base_prompt == load_intent_prompt(intent), intent
        assert plan.prompt.startswith(plan.base_prompt), intent
        assert len(plan.prompt) > len(plan.base_prompt), intent


def test_registered_intent_prompt_loader_wins():
    # A host that owns an intent's prompt (the connector owns triage)
    # registers a loader; plan_turn then serves the host's text as the base.
    from fsr_playbooks.llm import intents

    intents.register_intent_prompt("triage", lambda: "HOST TRIAGE PROMPT")
    try:
        assert intents.load_intent_prompt("triage") == "HOST TRIAGE PROMPT"
        plan = plan_turn("triage")
        assert plan.base_prompt == "HOST TRIAGE PROMPT"
        assert plan.prompt.startswith("HOST TRIAGE PROMPT")
        # A failing/empty loader falls back to the vendored copy.
        intents.register_intent_prompt("triage", lambda: "")
        assert intents.load_intent_prompt("triage") not in ("", None)
    finally:
        intents._PROMPT_LOADERS.pop("triage", None)


def test_disposition_prompt_states_focus_per_prior():
    """Phase 3: with the full surface advertised, focus comes from the stated
    disposition, not tool absence. Each prior names its posture, what the
    out-of-posture surface is FOR, and that approval gating is unchanged."""
    build = plan_turn("build").prompt
    assert "Disposition: you are authoring a playbook" in build
    assert "GROUND your steps" in build
    assert "approval card" in build
    triage = plan_turn("triage").prompt
    assert "Disposition: you are working a live record" in triage
    assert "OFFERING to bottle" in triage


def test_intent_is_prior_not_slice():
    # build prior still advertises the triage frontier and vice versa.
    # The card family is reached through the emit_card union (the per-card
    # names are CONSOLIDATED_AWAY since the dispatch gate landed).
    build_names = {t["name"] for t in plan_turn("build").tools}
    assert {"emit_card", "run_op"} <= build_names
    triage_names = {t["name"] for t in plan_turn("triage").tools}
    assert {"validate_yaml", "push_playbook", "emit_card"} <= triage_names


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


def test_budget_note_helper_soft_window_only():
    """budget_note (the live-loop injection) warns ONLY in the soft window:
    silent with headroom, silent at/after exhaustion (the forced wrap-up
    round owns the cliff)."""
    from fsr_playbooks.llm._loop_helpers import budget_note
    assert budget_note(1, 16) == ""
    assert "3 tool calls left" in budget_note(13, 16)
    assert "1 tool call left" in budget_note(15, 16)
    assert budget_note(16, 16) == ""
    assert budget_note(20, 16) == ""


def test_providers_inject_budget_note():
    """Every live provider loop carries the injection (the drift risk is a
    provider missing it and its users hitting the cliff unwarned)."""
    import pathlib

    import fsr_playbooks
    base = pathlib.Path(fsr_playbooks.__file__).parent / "llm"
    for prov in ("anthropic_provider.py", "openai_provider.py",
                 "fortiai_proxy_provider.py"):
        assert "budget_note" in (base / prov).read_text(), prov


def test_emit_card_top_level_fields_folded_into_payload():
    """Models regularly flatten emit_card's payload to top-level kwargs; the
    dispatch normalizer folds them back so the card renders on the FIRST
    call instead of costing a bad_payload self-repair round-trip."""
    out = dispatch("emit_card", {
        "card_type": "choice", "id": "c1",
        "prompt": "Which one?", "options": [
            {"label": "A", "value": "a"}, {"label": "B", "value": "b"}],
    })
    assert isinstance(out, dict) and out.get("code") != "bad_payload", out
    # An explicit dict payload is untouched, and a missing card_type still
    # errors -- the normalizer only repairs the misplaced-fields shape.
    bad = dispatch("emit_card", {"id": "x", "summary": "no card_type"})
    assert (bad or {}).get("ok") is not True and (
        bad.get("error") is not None or bad.get("code"))
