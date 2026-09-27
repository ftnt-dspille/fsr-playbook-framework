"""A turn must not close on a promise it did not keep.

Live on Frank (chat-sweep A/B, 362 turns): "I'll proceed with the update now --
please approve the card" and "Once you approve the card, block_ip_new runs
live against your FortiGate", each closing a turn that made NO call. Nothing
ran and no card existed; the analyst was told to approve something that was
not there. The seven sentences below are those closes, verbatim.
"""
from __future__ import annotations

import asyncio
import copy
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from test_anthropic_enhance_delivery_forced import _FakeStream as _AnthropicStream
from test_anthropic_enhance_delivery_forced import _text_block, _tool_use_block, _usage
from test_openai_build_progress_forced import (
    _delta_chunk,
    _FakeStream,
    _tc,
    _usage_chunk,
)

from fsr_playbooks.llm._loop_helpers import PromisedActionGuard, promised_action
from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import DoneEvent, Message, ToolUseEvent

HOLLOW = [
    "I'll proceed with the update now -- please approve the card.",
    "Approve the card and it'll go through.",
    "Approving the card below will make that change.",
    "**To proceed:** Review and approve the action card, and the block will execute on the FortiGate.",
    "When you're ready, approve the card and the `block_ip_new` op will run against `fortigate-firewall`.",
    "Once you approve the card, the `block_ip_new` op runs live against your FortiGate.",
    "The card is ready -- click **Deploy** to push it to FortiSOAR.",
]
LEGITIMATE = [
    "Would you like me to proceed with marking it Completed?",
    "Shall I block the IP on the FortiGate now?",
    "I made no changes to the record.",
    "The task is assigned to Priya Raman and is due 2026-10-03.",
    "Which option do you want: (A) mark it Completed anyway, or (B) leave it open?",
    "I can't edit incidents from here -- open INC-2231 and set its status there.",
    "Nothing was blocked: the FortiGate connector is not configured.",
]


@pytest.mark.parametrize("text", HOLLOW)
def test_the_live_hollow_closes_are_caught(text):
    assert promised_action("Some findings first.\n\n" + text)


@pytest.mark.parametrize("text", LEGITIMATE)
def test_questions_and_plain_answers_are_not(text):
    assert promised_action(text) is None


def test_a_real_card_or_approval_this_turn_silences_it():
    g = PromisedActionGuard()
    g.note_result("emit_card", {"card_type": "action"}, {"ok": True})
    assert g.outstanding(HOLLOW[0]) is None
    g = PromisedActionGuard()
    g.note_result("update_record", {}, {"ok": True, "pending_approval": True,
                                        "approval_id": "a1"})
    assert g.outstanding(HOLLOW[0]) is None


def test_a_refused_card_does_not_count_as_delivered():
    g = PromisedActionGuard()
    g.note_result("emit_card", {"card_type": "action"}, {"ok": False, "code": "bad_payload"})
    assert g.outstanding(HOLLOW[0])


def test_it_fires_at_most_once():
    g = PromisedActionGuard()
    assert g.outstanding(HOLLOW[0])
    g.mark_forced()
    assert g.outstanding(HOLLOW[0]) is None


# --- through the real loops -------------------------------------------------
_NAMES = ("get_record", "update_record", "emit_card")
_OPENAI_TOOLS = [{"type": "function", "function": {
    "name": n, "description": n,
    "parameters": {"type": "object", "properties": {}}}} for n in _NAMES]
_ANTHROPIC_TOOLS = [{"name": n, "description": n,
                     "input_schema": {"type": "object", "properties": {}}}
                    for n in _NAMES]


def _dispatch(name, args):
    if name == "update_record":
        return {"ok": True, "pending_approval": True, "approval_id": "a1"}
    return {"ok": True, "record": {"name": "t"}}


def _call(cid, name, args):
    return [_delta_chunk(tool_calls=[_tc(index=0, id=cid, name=name,
                                         args=json.dumps(args))]),
            _delta_chunk(finish="tool_calls"), _usage_chunk()]


def _text(t):
    return [_delta_chunk(content=t), _delta_chunk(finish="stop"), _usage_chunk()]


def _run_openai(rounds):
    sent: list = []
    queue = [_FakeStream(r) for r in rounds]

    def _create(*_a, **kw):
        sent.append(copy.deepcopy(kw["messages"]))
        return queue.pop(0)

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=AsyncMock(side_effect=_create))
    p = OpenAIProvider(model="gpt-5.4-mini", base_url="http://x/v1", api_key="x",
                       client=client)
    with patch("fsr_playbooks.llm.openai_provider.dispatch",
               MagicMock(side_effect=_dispatch)), \
         patch("fsr_playbooks.llm.openai_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="mark it completed")],
            tools=_OPENAI_TOOLS, tags={})))
    return events, sent


async def _drain(gen):
    return [ev async for ev in gen]


def _directives(sent):
    return [m for m in sent[-1] if m.get("role") == "user"
            and "made no call" in str(m.get("content"))]


def test_openai_hollow_close_gets_one_directive_then_the_call():
    events, sent = _run_openai([
        _call("c1", "get_record", {"uuid": "u"}),
        _text("I'll proceed with the update now -- please approve the card."),
        _call("c2", "update_record", {"uuid": "u", "status": "Completed"}),
        _text("Approval requested."),
    ])
    assert [e.name for e in events if isinstance(e, ToolUseEvent)] == [
        "get_record", "update_record"]
    assert len(_directives(sent)) == 1
    assert "please approve the card" in _directives(sent)[0]["content"]


def test_openai_ignored_directive_ends_the_turn_not_a_loop():
    events, sent = _run_openai([
        _text("I'll proceed with the update now -- please approve the card."),
        _text("I'll proceed with the update now -- please approve the card."),
    ])
    assert len(sent) == 2 and isinstance(events[-1], DoneEvent)


def test_openai_a_question_close_is_left_alone():
    _, sent = _run_openai([_text("Shall I mark it Completed?")])
    assert len(sent) == 1


def test_anthropic_hollow_close_gets_the_directive():
    def turn(blocks, stop):
        return _AnthropicStream([], MagicMock(content=blocks, stop_reason=stop,
                                              usage=_usage()))
    streams = [
        turn([_text_block("I'll proceed with the update now -- please approve the card.")],
             "end_turn"),
        turn([_tool_use_block("c2", "update_record", {"uuid": "u"})], "tool_use"),
        turn([_text_block("Approval requested.")], "end_turn"),
    ]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(side_effect=streams)
    client.messages.create = AsyncMock()
    p = AnthropicProvider(model="claude-haiku-4-5-20251001", base_url="http://x",
                          api_key="x", client=client)
    with patch("fsr_playbooks.llm.anthropic_provider.dispatch",
               MagicMock(side_effect=_dispatch)), \
         patch("fsr_playbooks.llm.anthropic_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="mark it completed")],
            tools=_ANTHROPIC_TOOLS, tags={})))
    assert "update_record" in [e.name for e in events if isinstance(e, ToolUseEvent)]
