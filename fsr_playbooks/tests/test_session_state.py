"""SessionState: the turn's host-known facts as one object.

The field setters (set_grounded_yaml, set_read_only_turn, ...) are views onto
it. Their tokens must behave like the separate ContextVars they replaced:
each restores only its own field, in any order -- a host resetting in the order
it bound (first-in, first-out) must not leave a field set after the turn.
"""
from __future__ import annotations

from fsr_playbooks.llm import session_state
from fsr_playbooks.llm.session_state import SessionState
from fsr_playbooks.llm.tools import (
    _change_affordance_present,
    _is_read_only_turn,
    reset_change_affordance,
    reset_read_only_turn,
    set_change_affordance,
    set_read_only_turn,
)
from fsr_playbooks.llm.turn_plan import active_turn_plan, reset_turn_plan, set_turn_plan
from fsr_playbooks.mcp_server._shared import (
    get_grounded_yaml,
    get_playbook_scope,
    reset_grounded_yaml,
    reset_playbook_scope,
    set_grounded_yaml,
    set_playbook_scope,
)


def test_defaults_fail_open():
    assert session_state.current() == SessionState()
    assert _change_affordance_present() is True
    assert _is_read_only_turn() is False


def test_tokens_reset_in_bind_order_leave_nothing_behind():
    t1 = set_grounded_yaml("playbooks: []")
    t2 = set_playbook_scope("modify")
    t3 = set_read_only_turn(True)
    t4 = set_change_affordance(False)
    # first-in, first-out -- the order the connector resets in
    for t, reset in ((t1, reset_grounded_yaml), (t2, reset_playbook_scope),
                     (t3, reset_read_only_turn), (t4, reset_change_affordance)):
        reset(t)
    assert session_state.current() == SessionState()


def test_each_token_restores_only_its_field():
    t1 = set_grounded_yaml("a")
    t2 = set_grounded_yaml("b")
    t3 = set_playbook_scope("create_new")
    reset_grounded_yaml(t1)            # out of order
    assert get_grounded_yaml() is None
    assert get_playbook_scope() == "create_new"
    reset_playbook_scope(t3)
    reset_grounded_yaml(t2)            # restores what t2 saw: "a"
    assert get_grounded_yaml() == "a"
    session_state.bind(SessionState())


def test_bound_runs_the_turn_with_exactly_that_state():
    plan = object()
    with session_state.bound(SessionState(grounded_yaml="x", read_only=True,
                                          turn_plan=plan, playbook_scope="modify")):
        assert get_grounded_yaml() == "x"
        assert _is_read_only_turn() is True
        assert active_turn_plan() is plan
        assert get_playbook_scope() == "modify"
    assert session_state.current() == SessionState()


def test_none_and_foreign_tokens_are_harmless():
    reset_turn_plan(None)
    reset_grounded_yaml(object())
    tok = set_turn_plan(None)
    reset_turn_plan(tok)
    assert session_state.current() == SessionState()
