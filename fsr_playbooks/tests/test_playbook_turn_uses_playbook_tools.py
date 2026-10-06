"""A playbook (build) turn uses the playbook tools only.

The advertised tool list is one constant across intents (the prompt-cache
prefix), so the build slice was enforced by the prompt alone. A sweep
troubleshooting turn ran run_op to probe its fix and parked on an approval
card instead of delivering it. The turn plan's dispatch gate now refuses the
triage-only tools on a turn whose intent was STATED as build -- never on a
plan derived without an intent (the resume re-bind), which resolves to build
by default and would otherwise fence a resumed triage loop.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm.turn_plan import TurnContext, plan_turn


def _build():
    return plan_turn("build", context=TurnContext(has_open_playbook=True))


@pytest.mark.parametrize("name,args", [
    ("run_op", {"connector": "cyops_utilities", "op": "make_cyops_request"}),
    ("emit_card", {"card_type": "action", "payload": {}}),
])
def test_a_build_turn_refuses_triage_tools(name, args):
    r = _build().gate_refusal(name, args)
    assert r is not None and r["code"] == "not_a_playbook_tool"
    assert "why_did_playbook_fail" in r["error"]


@pytest.mark.parametrize("name,args", [
    ("verify_playbook", {}),
    ("why_did_playbook_fail", {}),
    ("get_op_schema", {}),
    ("run_playbook", {}),          # a run verb: both intents
    ("emit_card", {"card_type": "enhancement_offer", "payload": {}}),
])
def test_a_build_turn_keeps_the_playbook_tools(name, args):
    assert _build().gate_refusal(name, args) is None


def test_a_triage_turn_is_not_fenced():
    plan = plan_turn("triage", context=TurnContext())
    assert plan.gate_refusal("run_op", {}) is None


def test_a_plan_with_no_stated_intent_is_not_fenced():
    # resolve_intent(None) == "build"; the resume re-bind passes no intent.
    plan = plan_turn(context=TurnContext())
    assert plan.intent == "build" and plan.intent_stated is False
    assert plan.gate_refusal("run_op", {}) is None
