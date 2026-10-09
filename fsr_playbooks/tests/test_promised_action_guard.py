"""A turn must not close on a tool call it only WROTE.

The guard used to also match promises in the closing prose ("I'll proceed with
the update now -- please approve the card") with a phrase regex. That was intent
detection over wording, which this codebase does not do, so it was removed; the
seven live closes it was written for are kept below to pin that prose alone no
longer triggers anything. What remains is structural: our own call-marker
syntax copied into prose.
"""
from __future__ import annotations

import asyncio
import copy
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from test_openai_build_progress_forced import (
    _delta_chunk,
    _FakeStream,
    _tc,
    _usage_chunk,
)

from fsr_playbooks.llm._loop_helpers import PromisedActionGuard, fabricated_call
from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import Message, ToolUseEvent

HOLLOW = [
    "I'll proceed with the update now -- please approve the card.",
    "Approve the card and it'll go through.",
    "Approving the card below will make that change.",
    "**To proceed:** Review and approve the action card, and the block will execute on the FortiGate.",
    "When you're ready, approve the card and the `block_ip_new` op will run against `fortigate-firewall`.",
    "Once you approve the card, the `block_ip_new` op runs live against your FortiGate.",
    "The card is ready -- click **Deploy** to push it to FortiSOAR.",
]

# Live (build sweep): a refinement turn replayed history carrying the
# connector's `[called name(args)]` / `[tool result: ...]` markers, and the
# model answered with that transcript in prose -- no call, no card, 3 of 4 runs.
FAKE = ('[called edit_playbook({"operations": [{"op": "add_step"}]})]\n'
        '[tool result: {"ok": true, "card": {"type": "playbook_offer"}}]')


@pytest.mark.parametrize("text", HOLLOW)
def test_prose_alone_is_not_parsed_for_intent(text):
    assert PromisedActionGuard().outstanding("Some findings first.\n\n" + text) is None


def test_a_real_card_this_turn_silences_it():
    g = PromisedActionGuard()
    g.note_result("emit_card", {"card_type": "action"}, {"ok": True})
    assert g.outstanding(FAKE) is None


def test_it_fires_at_most_once():
    g = PromisedActionGuard()
    assert g.outstanding(FAKE)
    g.mark_forced()
    assert g.outstanding(FAKE) is None


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
    with patch("fsr_playbooks.llm.agent_loop.dispatch",
               MagicMock(side_effect=_dispatch)), \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="mark it completed")],
            tools=_OPENAI_TOOLS, tags={})))
    return events, sent


async def _drain(gen):
    return [ev async for ev in gen]


def test_openai_a_question_close_is_left_alone():
    _, sent = _run_openai([_text("Shall I mark it Completed?")])
    assert len(sent) == 1


def test_a_written_call_is_caught_with_its_own_directive():
    g = PromisedActionGuard()
    said = g.outstanding(FAKE)
    assert said and said.startswith("[called edit_playbook(")
    assert "wrote a tool call as text" in g.directive(said)


def test_a_written_result_alone_is_caught():
    assert fabricated_call('Done.\n[tool result: {"ok": true}]')


@pytest.mark.parametrize("text", [
    "I called the analyst's attention to step 3.",
    "The [called] label in the designer is cosmetic.",
    "See [tool results] below.",
])
def test_prose_that_merely_mentions_calls_is_not(text):
    assert fabricated_call(text) is None


def test_openai_written_call_gets_the_directive_then_the_real_call():
    events, sent = _run_openai([
        _text(FAKE),
        _call("c1", "get_record", {"uuid": "u"}),
        _text("Here it is."),
    ])
    assert [e.name for e in events if isinstance(e, ToolUseEvent)] == ["get_record"]
    assert any("wrote a tool call as text" in str(m.get("content"))
               for m in sent[1] if m.get("role") == "user")
