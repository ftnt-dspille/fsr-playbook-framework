"""Once an approval card is staged, the analyst is the next actor.

`emit_action_card`'s contract is that the turn halts until the user confirms,
edits or cancels -- the widget renders the card and waits. Nothing in the
runtime enforced that, so the agent kept dispatching tools afterwards: work
whose results no one will ever see, on a turn already handed to a human.

Measured on `contain_block_ip_direct` (calibrate run 20260815T160035Z): the
card was staged at call 14 of 26, and the eleven calls after it were threat-
intel enrichment of an IP the analyst's own message had already declared the
confirmed C2.

The stop lives in `TriageDiscipline`, which all three providers route their
dispatch through, so one guard covers Anthropic, OpenAI and the FortiAI proxy.
"""
from __future__ import annotations

from fsr_playbooks.llm._loop_helpers import TriageDiscipline

_CARD_OK = {"ok": True, "card": {"type": "action_card"}}


def _staged() -> TriageDiscipline:
    d = TriageDiscipline(authoring=False, user_text="block 1.2.3.4")
    d.note_result("emit_action_card", {}, _CARD_OK)
    return d


def test_further_tools_are_refused_after_a_card_is_staged() -> None:
    d = _staged()
    guard = d.evaluate("run_op", {"connector": "virustotal", "op": "query_ip"})
    assert guard is not None, "the agent kept acting after handing off to a human"
    assert guard.get("action_card_staged") is True


def test_the_refusal_is_a_deferral_not_a_failure() -> None:
    """`ok: false` would read as a tool error the model should retry."""
    guard = _staged().evaluate("search_module_records", {"module": "alerts"})
    assert guard["ok"] is True
    assert guard["kind"] == "guard_defer"
    assert "directive" in guard
    # It must tell the model what to do INSTEAD, or it will just try again.
    assert "verdict" in guard["directive"].lower()


def test_a_second_card_is_refused_too() -> None:
    """One gate at a time -- two cards is two things to approve at once."""
    assert _staged().evaluate("emit_action_card", {}) is not None


def test_nothing_is_gagged_before_a_card_is_staged() -> None:
    d = TriageDiscipline(authoring=False, user_text="block 1.2.3.4")
    assert d.evaluate("search_module_records", {"module": "alerts"}) is None


def test_a_failed_card_does_not_end_the_turn() -> None:
    """The whole point of a bounce is that the model gets to try again."""
    d = TriageDiscipline(authoring=False, user_text="block 1.2.3.4")
    d.note_result("emit_action_card", {},
                  {"ok": False, "code": "editable_fields_not_in_args"})
    assert d.evaluate("emit_action_card", {}) is None


def test_the_flag_is_turn_scoped() -> None:
    """A card staged last turn was already answered; a fresh guard is clean."""
    _staged()
    fresh = TriageDiscipline(authoring=False, user_text="now isolate the host")
    assert fresh.evaluate("run_op", {"connector": "x", "op": "y"}) is None


# --- the verdict is the close, not another action ---------------------------
# ka_c2_beacon (known-answer, 2/2 on deepseek): the model staged the block card,
# then called emit_card(verdict) -- and this guard deferred it. The analyst got
# "block this" with no finding. The directive above asks for a verdict, so the
# verdict itself must get through.

def test_the_verdict_card_is_not_gagged_after_a_card_is_staged() -> None:
    d = _staged()
    assert d.evaluate("emit_card", {"card_type": "verdict", "payload": {}}) is None
    assert d.evaluate("emit_verdict", {}) is None


def test_the_consolidated_action_card_stages_too() -> None:
    """`emit_card(card_type='action')` is the only name the model is offered."""
    d = TriageDiscipline(authoring=False, user_text="block 1.2.3.4")
    d.note_result("emit_card", {"card_type": "action"}, _CARD_OK)
    assert d.evaluate("run_op", {"connector": "x", "op": "y"}) is not None
    assert d.evaluate("emit_card", {"card_type": "action"}) is not None
    assert d.evaluate("emit_card", {"card_type": "verdict"}) is None


def test_a_deferred_verdict_does_not_satisfy_the_verdict_guard() -> None:
    """The deferral carries `ok: True`; counting it silenced the one guard that
    would have forced the verdict. Pin the pair together, as they run live."""
    from fsr_playbooks.llm._loop_helpers import VerdictDeliveryGuard
    g = VerdictDeliveryGuard()
    g.note_result("siem_search", {}, {"ok": True, "rows": [1]})
    deferred = {"ok": True, "kind": "guard_defer", "action_card_staged": True,
                "directive": "NOT RUN"}
    g.note_result("emit_card", {"card_type": "verdict"}, deferred)
    assert g.outstanding({"emit_card", "siem_search"}) is True
