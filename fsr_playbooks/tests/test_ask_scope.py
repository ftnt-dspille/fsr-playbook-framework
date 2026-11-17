"""Ask scope: the effort of a turn matches the size of the ask."""
from __future__ import annotations

import asyncio

import pytest
from test_verdict_forced_on_full_surface import (
    _delta_chunk,
    _hunt_round,
    _prose,
    _run,
    _usage_chunk,
)

from fsr_playbooks.llm import ask_scope, tools
from fsr_playbooks.llm.provider import TextEvent


class _Declaring:
    def __init__(self, said):
        self.said = said
        self.seen = None

    async def stream(self, **kw):
        self.seen = kw
        yield TextEvent(text=self.said)


class _Broken:
    async def stream(self, **_kw):
        raise RuntimeError("gateway down")
        yield  # pragma: no cover


def _json(scope, reason="r"):
    return f'{{"scope": "{scope}", "reason": "{reason}"}}'


# Every typed ask is declared by the model, whatever its keywords say: a
# reputation question holds "malicious" and is still a lookup.
_DECLARED = [
    ("Is the source address of this alert malicious?", _json("lookup", "one reputation check"), "lookup"),
    ("Is 1.2.3.4 known bad?", _json("lookup"), "lookup"),
    ("Has this host talked to anything suspicious today?", _json("lookup"), "lookup"),
    ("What does VirusTotal say about the source address?", _json("lookup"), "lookup"),
    ("Who owns this host?", _json("lookup"), "lookup"),
    ("What is this alert's name", _json("answer"), "answer"),
    ("triage this", _json("investigate"), "investigate"),
    ("block the address", _json("act"), "act"),
    ("build a playbook that tags these", _json("build"), "build"),
    ("what's the story here", "Investigate.", "investigate"),
]


@pytest.mark.parametrize("text,said,expected", _DECLARED, ids=[d[0][:40] for d in _DECLARED])
def test_the_model_declares_the_scope_of_every_typed_ask(text, said, expected):
    got, how, _ = asyncio.run(ask_scope.resolve_scope(_Declaring(said), text))
    assert (got, how) == (expected, "declared")


def test_the_declaration_carries_a_reason_and_sees_the_record():
    p = _Declaring(_json("lookup", "one reputation check"))
    got, _how, reason = asyncio.run(ask_scope.resolve_scope(
        p, "Is it bad?", record="alerts: Burst of requests"))
    assert reason == "one reputation check"
    assert "Burst of requests" in p.seen["messages"][0].content
    assert p.seen["tools"] == []


@pytest.mark.parametrize("text", ["", "   "])
def test_no_typed_ask_is_unscoped_without_calling_the_model(text):
    assert asyncio.run(ask_scope.resolve_scope(_Broken(), text)) == (None, "default", "")


def test_a_quick_action_chip_is_unscoped_without_calling_the_model():
    assert asyncio.run(ask_scope.resolve_scope(
        _Broken(), "what is this", quick_action="explain")) == (None, "default", "")


@pytest.mark.parametrize("text", ["triage this", "what is this alert's name",
                                  "¿Cuál es el nombre de esta alerta?"])
def test_a_failed_declaration_leaves_the_turn_unscoped_whatever_the_words(text):
    # No keyword fallback: the words are never read outside the model.
    assert asyncio.run(ask_scope.resolve_scope(_Broken(), text)) == (None, "default", "")


def test_the_declare_prompt_allows_any_language():
    p = _Declaring(_json("answer"))
    asyncio.run(ask_scope.resolve_scope(p, "¿Cuál es el nombre de esta alerta?"))
    assert "any language" in p.seen["system"]


def test_the_scope_module_reads_no_words():
    import inspect
    src = inspect.getsource(ask_scope)
    assert "classify_scope" not in src
    assert "_RE =" not in src and "re.compile" not in src


def test_an_unreadable_declaration_is_unscoped():
    assert asyncio.run(ask_scope.resolve_scope(_Declaring("no idea"), "the host thing?"))[0] is None


# --- enforcement -------------------------------------------------------------

_WITHHELD = [("siem_search", {}), ("edr_host", {}), ("faz_search", {}), ("prior_cases", {}),
             ("update_record", {}), ("run_playbook", {}),
             ("emit_card", {"card_type": "verdict"}), ("emit_card", {"card_type": "action"}),
             ("emit_card", {"card_type": "playbook_offer"})]
_KEPT = [("get_record", {}), ("search_module_records", {}), ("find", {}), ("run_op", {}),
         ("emit_card", {"card_type": "capability_gap"})]


@pytest.mark.parametrize("name,args", _WITHHELD, ids=[f"{n}:{a.get('card_type','')}" for n, a in _WITHHELD])
def test_answer_scope_refuses_the_hunt_and_the_deliverables(name, args):
    r = ask_scope.answer_refusal(name, args)
    assert r and r["code"] == "answer_scope"
    token = ask_scope.bind_scope("answer")
    try:
        assert tools.turn_refusal(name, args)["code"] == "answer_scope"
    finally:
        ask_scope.reset_scope(token)
    assert (tools.turn_refusal(name, args) or {}).get("code") != "answer_scope"


@pytest.mark.parametrize("name,args", _KEPT, ids=[f"{n}:{a.get('card_type','')}" for n, a in _KEPT])
def test_answer_scope_keeps_the_lookups(name, args):
    assert ask_scope.answer_refusal(name, args) is None


_LOOKUP_KEPT = [("siem_search", {}), ("edr_host", {}), ("faz_search", {}), ("run_op", {}),
                ("get_record", {}), ("emit_card", {"card_type": "choice"}),
                ("emit_card", {"card_type": "ioc"})]
_LOOKUP_WITHHELD = [("prior_cases", {}), ("update_record", {}), ("run_playbook", {}),
                    ("emit_card", {"card_type": "verdict"}),
                    ("emit_card", {"card_type": "action"})]


@pytest.mark.parametrize("name,args", _LOOKUP_KEPT, ids=[f"{n}:{a.get('card_type','')}" for n, a in _LOOKUP_KEPT])
def test_lookup_keeps_the_log_and_endpoint_lookups(name, args):
    assert ask_scope.answer_refusal(name, args, ask_scope.LOOKUP) is None


@pytest.mark.parametrize("name,args", _LOOKUP_WITHHELD, ids=[f"{n}:{a.get('card_type','')}" for n, a in _LOOKUP_WITHHELD])
def test_lookup_withholds_the_sweep_the_writes_and_the_verdict(name, args):
    assert ask_scope.answer_refusal(name, args, ask_scope.LOOKUP)["code"] == "answer_scope"
    token = ask_scope.bind_scope("lookup")
    try:
        assert tools.turn_refusal(name, args)["code"] == "answer_scope"
    finally:
        ask_scope.reset_scope(token)


def test_the_caps_are_three_and_six():
    assert (ask_scope.max_tool_calls("answer"), ask_scope.max_tool_calls("lookup"),
            ask_scope.max_tool_calls("investigate")) == (3, 6, None)


def test_the_hunt_is_not_advertised_on_an_answer_turn():
    surface = [{"name": n, "description": n, "input_schema": {}}
               for n in ("get_record", "siem_search", "edr_host", "prior_cases", "run_op")]
    token = ask_scope.bind_scope("answer")
    try:
        names = [t["name"] for t in tools.advertised_for_turn(surface)]
    finally:
        ask_scope.reset_scope(token)
    assert names == ["get_record", "run_op"]


# --- the loop ----------------------------------------------------------------

def _verdicts(disp):
    return [c for c in disp.call_args_list
            if c.args[0] == "emit_card" and c.args[1].get("card_type") == "verdict"]


def _scoped(scope, rounds):
    token = ask_scope.bind_scope(scope)
    try:
        return _run(rounds)
    finally:
        ask_scope.reset_scope(token)


def test_an_unscoped_turn_still_ends_on_a_verdict():
    _, disp = _scoped(None, [_hunt_round(), _prose()])
    assert _verdicts(disp)


def test_an_answer_turn_that_answers_is_not_forced_into_a_verdict():
    events, disp = _scoped("answer", [_hunt_round(), _prose()])
    assert not _verdicts(disp)
    assert any(isinstance(e, TextEvent) and "C2 beacon" in e.text for e in events)


def test_a_lookup_turn_is_not_forced_into_a_verdict_and_ends_on_text():
    events, disp = _scoped("lookup", [_hunt_round(), _prose()])
    assert not _verdicts(disp)
    assert any(isinstance(e, TextEvent) and "C2 beacon" in e.text for e in events)


def test_a_lookup_turn_past_its_cap_is_refused_and_answers():
    import json

    from test_verdict_forced_on_full_surface import _tc
    rounds = [[_delta_chunk(tool_calls=[_tc(index=0, id=f"c{i}", name="get_record",
                                            args=json.dumps({"record": str(i)}))]),
               _delta_chunk(finish="tool_calls"), _usage_chunk()] for i in range(8)]
    _, disp = _scoped("lookup", rounds + [_prose()])
    # the loop's own cap: calls past 6 never reach dispatch
    assert len([c for c in disp.call_args_list if c.args[0] == "get_record"]) <= 6


def test_an_answer_turn_that_ends_without_text_gets_one_answer_round():
    empty = [_delta_chunk(finish="stop"), _usage_chunk()]
    wrapup = _prose()
    events, disp = _scoped("answer", [_hunt_round(), empty, wrapup])
    assert not _verdicts(disp)
    assert any(isinstance(e, TextEvent) and "C2 beacon" in e.text for e in events)
