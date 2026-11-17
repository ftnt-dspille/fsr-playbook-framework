"""A lookup that finds strong evidence offers the full investigation.

The offer is a model decision, driven by one instruction in the narrow turn's
prompt (`ask_scope.escalation_directive`). These tests run a turn on a model
that does what that instruction says and nothing else, so they prove the
mechanism end to end: the instruction reaches the model, the offer it produces
is a card the real `emit_card` tool accepts, and it is offered rather than
started. Without the instruction the same model offers nothing. (Whether a real
model follows the instruction is graded live by the `effort_lookup_malicious_offer`
sweep row, on Frank.)
"""
from __future__ import annotations

import asyncio
import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

from test_ask_scope_budget_language_escalation import _TOOLS, _call_round
from test_openai_build_progress_forced import _delta_chunk, _FakeStream, _usage_chunk
from test_verdict_forced_on_full_surface import _drain

from fsr_playbooks.llm import ask_scope, tools
from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import Message

_MALICIOUS = {"ok": True, "data": {"attributes": {"last_analysis_stats": {
    "malicious": 48, "suspicious": 3, "harmless": 4}}}}
_BASE = "You are a SOC assistant."
_OPTION = re.compile(r'"([^"]+)" \(value "([^"]+)"\)')


def _text_round(text):
    return [_delta_chunk(content=text), _delta_chunk(finish="stop"), _usage_chunk()]


def _instruction_following_create(calls):
    """A model that looks the address up, then does exactly what its system
    prompt says about strong evidence: with an offer instruction it emits the
    choice card with the options the prompt names; without one it only answers.
    It reads the prompt and the tool result, never the analyst's words."""
    def _create(*_a, **kw):
        msgs = kw["messages"]
        calls.append(msgs)
        system = " ".join(m["content"] for m in msgs
                          if m.get("role") == "system" and isinstance(m["content"], str))
        tool_msgs = [m for m in msgs if m.get("role") == "tool"]
        if not tool_msgs:
            return _FakeStream(_call_round(
                ("c1", "run_op", {"connector": "virustotal", "op": "query_ip"})))
        offered = any("emit_card" in str(m.get("tool_calls", "")) for m in msgs
                      if m.get("role") == "assistant")
        found = "malicious" in tool_msgs[0]["content"]
        options = _OPTION.findall(system) if "offer the full investigation" in system else []
        if found and options and not offered:
            card = {"card_type": "choice", "payload": {
                "prompt": "Several intel sources call this address malicious.",
                "options": [{"label": lb, "value": v} for lb, v in options]}}
            return _FakeStream(_call_round(("c2", "emit_card", card)))
        return _FakeStream(_text_round("It is flagged malicious by most sources."))
    return _create


def _run(system):
    sent: list = []
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(
        create=AsyncMock(side_effect=_instruction_following_create(sent)))
    p = OpenAIProvider(model="gpt-5.4-mini", base_url="http://x/v1", api_key="x",
                       client=client)

    def _dispatch(name, args, **_k):
        return (tools.turn_refusal(name, args)
                or (_MALICIOUS if name == "run_op" else tools.dispatch(name, args)))

    token = ask_scope.bind_scope(ask_scope.LOOKUP)
    try:
        with patch("fsr_playbooks.llm.agent_loop.dispatch",
                   MagicMock(side_effect=_dispatch)) as disp, \
             patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
            asyncio.run(_drain(p.stream(
                system=system, messages=[Message(role="user", content="ask")],
                tools=_TOOLS, tags={})))
    finally:
        ask_scope.reset_scope(token)
    return disp


def _cards(disp, card_type):
    return [c for c in disp.call_args_list if c.args[0] == "emit_card"
            and c.args[1].get("card_type") == card_type]


def test_a_lookup_that_finds_malicious_evidence_offers_the_two_option_card():
    disp = _run(_BASE + ask_scope.escalation_directive())
    offers = _cards(disp, "choice")
    assert len(offers) == 1
    opts = offers[0].args[1]["payload"]["options"]
    assert opts == list(ask_scope.ESCALATION_OPTIONS)
    # the card the real tool builds from it is valid and has both options
    r = tools.dispatch("emit_card", offers[0].args[1])
    assert r["ok"] and [o["value"] for o in r["card"]["options"]] == ["investigate", "stop"]
    # offered, not started
    assert not _cards(disp, "verdict")
    assert not [c for c in disp.call_args_list
                if c.args[0] in ("siem_search", "edr_host", "faz_search", "prior_cases")]


def test_without_the_escalation_instruction_the_same_lookup_offers_nothing():
    disp = _run(_BASE)
    assert not _cards(disp, "choice")


def test_the_instruction_is_built_from_the_card_options():
    text = ask_scope.escalation_directive()
    assert tuple({"label": lb, "value": v} for lb, v in _OPTION.findall(text)) \
        == ask_scope.ESCALATION_OPTIONS
    json.dumps(text)
