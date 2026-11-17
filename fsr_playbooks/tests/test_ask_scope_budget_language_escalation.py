"""Ask scope follow-ups: the lookup budget is stated, the reply language is
restated where it is seen, and strong evidence on a lookup offers the full
investigation instead of starting it."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from test_openai_build_progress_forced import (
    _delta_chunk,
    _FakeStream,
    _tc,
    _usage_chunk,
)
from test_verdict_forced_on_full_surface import _TOOLS as _SURFACE
from test_verdict_forced_on_full_surface import _drain, _prose

from fsr_playbooks.llm import _loop_helpers, ask_scope, tools
from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import Message, ToolUseEvent

_TOOLS = _SURFACE + [{"type": "function", "function": {
    "name": "prior_cases", "description": "prior_cases",
    "parameters": {"type": "object", "properties": {}}}}]


def _call_round(*calls):
    return [_delta_chunk(tool_calls=[
        _tc(index=i, id=cid, name=name, args=json.dumps(args))
        for i, (cid, name, args) in enumerate(calls)]),
        _delta_chunk(finish="tool_calls"), _usage_chunk()]


def _drive(scope, rounds, results=None):
    """Run a scoped turn on a scripted model. Returns (events, dispatched,
    the messages sent on each model round)."""
    streams = [_FakeStream(r) for r in rounds]
    sent: list[list] = []

    async def _create(*_a, **kw):
        sent.append(json.loads(json.dumps(kw["messages"], default=str)))
        return streams.pop(0)

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=AsyncMock(side_effect=_create))
    p = OpenAIProvider(model="gpt-5.4-mini", base_url="http://x/v1", api_key="x",
                       client=client)
    token = ask_scope.bind_scope(scope)
    try:
        with patch("fsr_playbooks.llm.agent_loop.dispatch",
                   MagicMock(side_effect=lambda n, a, **k: tools.turn_refusal(n, a)
                             or (results or {}).get(n, {"ok": True}))) as disp, \
             patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
            events = asyncio.run(_drain(p.stream(
                system="s", messages=[Message(role="user", content="ask")],
                tools=_TOOLS, tags={})))
    finally:
        ask_scope.reset_scope(token)
    return events, disp, sent


def _user_notes(round_messages):
    return [m["content"] for m in round_messages
            if m.get("role") == "user" and isinstance(m.get("content"), str)]


# --- item 1: the budget is stated every round, and the cap says why ---------

def test_a_lookup_turn_is_told_its_budget_after_every_round():
    rounds = [_call_round((f"c{i}", "get_record", {"record": str(i)}))
              for i in range(3)] + [_prose()]
    _, _, sent = _drive("lookup", rounds)
    notes = [" ".join(_user_notes(m)) for m in sent]
    assert "[lookup budget] 1 of 6 tool calls used, 5 left" in notes[1]
    assert "[lookup budget] 2 of 6 tool calls used, 4 left" in notes[2]
    assert "[lookup budget] 3 of 6 tool calls used, 3 left" in notes[3]


def test_an_unscoped_turn_gets_no_budget_note():
    _, _, sent = _drive(None, [_call_round(("c1", "get_record", {"record": "1"})),
                               _prose()])
    assert "budget]" not in " ".join(_user_notes(sent[1])).replace("[turn budget]", "")


def test_the_cap_refusal_says_the_budget_is_spent_not_what_kind_of_tool():
    rounds = [_call_round((f"c{i}", "get_record", {"record": str(i)}))
              for i in range(7)] + [_prose()]
    _, disp, sent = _drive("lookup", rounds)
    tool_msgs = [m for m in sent[-1] if m.get("role") == "tool"]
    refused = [m for m in tool_msgs if "answer_scope" in m["content"]]
    assert refused, "the seventh call should have been refused"
    assert "6 tool calls this ask allows are spent" in refused[0]["content"]
    assert "all 6 tool calls are spent" in " ".join(_user_notes(sent[-1]))
    assert len([c for c in disp.call_args_list if c.args[0] == "get_record"]) == 6


def test_the_budget_note_is_empty_without_a_cap():
    assert ask_scope.budget_note("investigate", 4) == ""
    assert ask_scope.budget_note(None, 4) == ""


# --- item 3: the reply language is restated at the end of every round -------

def test_every_tool_round_ends_with_the_reply_language_note():
    _, _, sent = _drive(None, [_call_round(("c1", "get_record", {"record": "1"})),
                               _prose()])
    assert "[reply language]" in _user_notes(sent[1])[-1]


@pytest.mark.parametrize("directive", [
    ask_scope.WRAPUP_DIRECTIVE,
    _loop_helpers.verdict_directive(["e1"]),
    _loop_helpers.stall_directive("flail"),
    _loop_helpers.wrapup_directive([])[0],
])
def test_every_forced_end_of_turn_directive_restates_the_reply_language(directive):
    assert ask_scope.REPLY_LANGUAGE_NOTE in directive


def test_the_language_note_names_no_language():
    note = ask_scope.REPLY_LANGUAGE_NOTE.lower()
    assert not any(w in note for w in ("english", "french", "spanish", "german"))


# --- item 4: strong evidence on a lookup offers the investigation -----------

_MALICIOUS = {"ok": True, "data": {"attributes": {"last_analysis_stats": {
    "malicious": 48, "suspicious": 3, "harmless": 4}}}}
_OFFER = {"card_type": "choice", "payload": {
    "prompt": "Several intel sources call this address malicious.",
    "options": list(ask_scope.ESCALATION_OPTIONS)}}


def _cards(disp, card_type):
    return [c for c in disp.call_args_list if c.args[0] == "emit_card"
            and c.args[1].get("card_type") == card_type]


def test_a_lookup_that_finds_a_malicious_address_offers_the_investigation_and_does_not_hunt():
    rounds = [
        _call_round(("c1", "run_op", {"connector": "virustotal", "op": "query_ip"})),
        _call_round(("c2", "emit_card", _OFFER)),
        _prose(),
    ]
    events, disp, sent = _drive("lookup", rounds, results={"run_op": _MALICIOUS})
    # the offer itself is not refused by the scope
    answered = [m["content"] for m in sent[-1] if m.get("role") == "tool"]
    assert not any("answer_scope" in m for m in answered), answered
    offers = _cards(disp, "choice")
    assert len(offers) == 1
    opts = offers[0].args[1]["payload"]["options"]
    assert opts[0]["label"] == "Run the full investigation"
    # offered, not started: nothing from the hunt ran and no verdict card
    assert not [c for c in disp.call_args_list
                if c.args[0] in ("siem_search", "edr_host", "faz_search", "prior_cases")]
    assert not _cards(disp, "verdict")
    assert any(isinstance(e, ToolUseEvent) and e.name == "emit_card" for e in events)


def test_a_lookup_that_tries_to_start_the_hunt_unasked_is_refused():
    rounds = [
        _call_round(("c1", "run_op", {"connector": "virustotal", "op": "query_ip"})),
        _call_round(("c2", "prior_cases", {})),
        _call_round(("c3", "emit_card", {"card_type": "verdict", "payload": {}})),
        _prose(),
    ]
    refusal = ask_scope.answer_refusal("prior_cases", {}, ask_scope.LOOKUP)
    results = {"run_op": _MALICIOUS}
    _, _, sent = _drive("lookup", rounds, results=results)
    tool_msgs = [m["content"] for m in sent[-1] if m.get("role") == "tool"]
    assert sum("answer_scope" in m for m in tool_msgs) == 2
    assert refusal["code"] == "answer_scope"


# --- item 2: the declaration shows one example per scope, in two languages ---

def test_the_declare_prompt_gives_every_scope_an_example_in_two_languages():
    lines = ask_scope._DECLARE_SYSTEM.split("\n")
    for scope in ask_scope.SCOPES:
        i = next(n for n, ln in enumerate(lines) if ln.startswith(f"{scope}: "))
        example = next((ln for ln in lines[i + 1:i + 4] if "e.g." in ln), "")
        assert example.count("\"") >= 4 and " / " in example, (scope, example)


def test_the_escalation_offer_is_a_card_the_real_tool_accepts():
    """A choice card needs two options; the offer once had one and the tool
    refused it, so no lookup could ever escalate."""
    r = tools.dispatch("emit_card", dict(_OFFER))
    assert r["ok"] is True and r["card"]["type"] == "choice_card"
    assert [o["value"] for o in r["card"]["options"]] == ["investigate", "stop"]
    one = {"card_type": "choice", "payload": {
        "prompt": "p", "options": [dict(ask_scope.ESCALATION_OPTIONS[0])]}}
    assert tools.dispatch("emit_card", one)["code"] == "too_few_options"


def test_the_round_tail_quotes_the_analyst_so_the_language_is_matched():
    _, _, sent = _drive(None, [_call_round(("c1", "get_record", {"record": "1"})),
                               _prose()])
    assert 'The analyst wrote: "ask"' in _user_notes(sent[1])[-1]
    long = ask_scope.language_note("x" * 500 + "\\n second line")
    assert len(long) < 400 and "\\n" not in long
    assert ask_scope.language_note("") == ask_scope.REPLY_LANGUAGE_NOTE
