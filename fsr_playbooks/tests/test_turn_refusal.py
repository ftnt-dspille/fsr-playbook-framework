"""What the model is shown and what dispatch accepts come from one predicate.

The connector hid eight tools on a read-only turn that framework dispatch still
ran if the model called them anyway, and advertised the triage-only tools on a
playbook turn that the TurnPlan then refused at dispatch -- a wasted round per
call. `turn_refusal` decides both; `advertised_for_turn` is the list side.
"""
from __future__ import annotations

from fsr_playbooks.llm import session_state
from fsr_playbooks.llm import tools as T
from fsr_playbooks.llm.intents import RUN_VERB_TOOLS, TRIAGE_ONLY_TOOLS
from fsr_playbooks.llm.session_state import SessionState
from fsr_playbooks.llm.turn_plan import TurnContext, TurnPlan


def _tools(*names, openai=False):
    if openai:
        return [{"type": "function", "function": {"name": n}} for n in names]
    return [{"name": n} for n in names]


def test_nothing_withheld_by_default():
    names = ("run_op", "push_playbook", "emit_card")
    assert T.advertised_for_turn(_tools(*names)) == _tools(*names)


def test_read_only_withholds_and_refuses_the_same_set():
    with session_state.bound(SessionState(read_only=True)):
        shown = {t["name"] for t in T.advertised_for_turn(
            _tools(*sorted(T.READ_ONLY_WITHHELD_TOOLS), "analyze_playbook"))}
        assert shown == {"analyze_playbook"}
        for name in T.READ_ONLY_WITHHELD_TOOLS:
            assert T.turn_refusal(name, {})["code"] == "read_only_turn"


def test_playbook_turn_hides_what_it_refuses():
    plan = TurnPlan(intent="build", prompt="", intent_stated=True,
                    context=TurnContext())
    blocked = sorted(TRIAGE_ONLY_TOOLS - RUN_VERB_TOOLS)
    with session_state.bound(SessionState(turn_plan=plan)):
        shown = T.advertised_for_turn(_tools(*blocked, "emit_card", openai=True))
        assert [t["function"]["name"] for t in shown] == ["emit_card"]
        assert T.turn_refusal("emit_card", {"card_type": "action"}) is not None


def test_dispatch_refuses_through_the_same_predicate():
    with session_state.bound(SessionState(read_only=True)):
        out = T.dispatch("verify_playbook", {"yaml_text": "x"})
    assert out["code"] == "read_only_turn"
