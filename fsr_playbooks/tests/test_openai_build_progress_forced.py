"""End-to-end: a research-only build turn is nudged back into authoring through
the ACTUAL OpenAIProvider loop -- live matrix row B3, reproduced.

B3 on .159 (connector 0.5.65 / fsr_playbooks 0.6.5): 11 research calls, then
prose, then end_turn. No draft, no verify, no offer -- the analyst gets a plan
instead of a playbook.

Unlike the delivery guards this one does NOT force a specific call and does NOT
end the turn; it appends a directive and lets the loop continue, so the model
drafts -> verifies -> offers itself. These tests pin that: the turn continues,
authoring happens, and the nudge fires at most once.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import DoneEvent, Message, ToolUseEvent

YAML = "playbooks:\n  - name: Phishing Enrichment\n"


def _delta_chunk(*, content=None, tool_calls=None, finish=None):
    delta = MagicMock(content=content, tool_calls=tool_calls)
    return MagicMock(choices=[MagicMock(delta=delta, finish_reason=finish)], usage=None)


def _usage_chunk():
    return MagicMock(choices=[], usage=MagicMock(prompt_tokens=10, completion_tokens=5))


def _tc(*, index, id=None, name=None, args=None):
    fn = MagicMock()
    fn.name = name
    fn.arguments = args
    return MagicMock(index=index, id=id, function=fn)


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        async def gen():
            for c in self._chunks:
                yield c
        return gen()


_BUILD_TOOLS = [
    {"type": "function", "function": {
        "name": n, "description": n,
        "parameters": {"type": "object", "properties": {
            "yaml_text": {"type": "string"}, "yaml": {"type": "string"},
            "id": {"type": "string"}, "summary": {"type": "string"}}}}}
    for n in ("get_step_type", "find_connector", "verify_playbook",
              "emit_playbook_offer")
]


async def _drain(gen):
    out = []
    async for ev in gen:
        out.append(ev)
    return out


def _dispatch(name, args):
    if name == "verify_playbook":
        return {"ready_to_push": True, "summary": "enriches the domain"}
    if name == "emit_playbook_offer":
        return {"ok": True, "card": {"type": "playbook_offer"}}
    return {"ok": True}


def _provider(create):
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=create)
    return OpenAIProvider(model="gpt-4.1-mini", base_url="http://x/v1",
                          api_key="x", client=client)


# Round 1: research only. Round 2: prose, no tool call -> the B3 stall.
_RESEARCH = [
    _delta_chunk(tool_calls=[_tc(index=0, id="c1", name="get_step_type", args="{}")]),
    _delta_chunk(finish="tool_calls"), _usage_chunk(),
]
_NARRATE = [
    _delta_chunk(content="Next, I will author a playbook that enriches the sender domain."),
    _delta_chunk(finish="stop"), _usage_chunk(),
]


def test_research_only_turn_is_nudged_and_then_authors():
    # After the nudge the model drafts + verifies, then offers.
    verify_round = [
        _delta_chunk(tool_calls=[_tc(index=0, id="c2", name="verify_playbook",
                                     args=json.dumps({"yaml_text": YAML}))]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    offer_round = [
        _delta_chunk(tool_calls=[_tc(index=0, id="c3", name="emit_playbook_offer",
                                     args=json.dumps({"id": "o1", "summary": "s",
                                                      "yaml": YAML}))]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    close = [_delta_chunk(content="Saved as a draft."),
             _delta_chunk(finish="stop"), _usage_chunk()]
    create = AsyncMock(side_effect=[
        _FakeStream(_RESEARCH), _FakeStream(_NARRATE),
        _FakeStream(verify_round), _FakeStream(offer_round), _FakeStream(close)])
    p = _provider(create)
    with patch("fsr_playbooks.llm.openai_provider.dispatch",
               MagicMock(side_effect=_dispatch)), \
         patch("fsr_playbooks.llm.openai_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="build a playbook")],
            tools=_BUILD_TOOLS, tags={})))

    names = [e.name for e in events if isinstance(e, ToolUseEvent)]
    # The turn did NOT end at the narration -- it went on to author and deliver.
    assert "verify_playbook" in names, "nudge did not get the model to author"
    assert "emit_playbook_offer" in names, "no offer after the nudge"
    assert isinstance(events[-1], DoneEvent)


def test_nudge_fires_at_most_once():
    # If the model narrates AGAIN after the nudge, the turn must end rather than
    # nudge forever.
    create = AsyncMock(side_effect=[
        _FakeStream(_RESEARCH), _FakeStream(_NARRATE), _FakeStream(_NARRATE)])
    p = _provider(create)
    with patch("fsr_playbooks.llm.openai_provider.dispatch",
               MagicMock(side_effect=_dispatch)), \
         patch("fsr_playbooks.llm.openai_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="build a playbook")],
            tools=_BUILD_TOOLS, tags={})))
    assert isinstance(events[-1], DoneEvent)
    # research, narrate, ONE nudged round -- then it gives up.
    assert create.await_count == 3


def test_turn_that_already_authored_is_not_nudged():
    # Research -> verify -> offer -> close. No nudge round should be inserted.
    verify_round = [
        _delta_chunk(tool_calls=[_tc(index=0, id="c2", name="verify_playbook",
                                     args=json.dumps({"yaml_text": YAML}))]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    offer_round = [
        _delta_chunk(tool_calls=[_tc(index=0, id="c3", name="emit_playbook_offer",
                                     args=json.dumps({"id": "o1", "summary": "s",
                                                      "yaml": YAML}))]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    close = [_delta_chunk(content="Done."), _delta_chunk(finish="stop"), _usage_chunk()]
    create = AsyncMock(side_effect=[
        _FakeStream(_RESEARCH), _FakeStream(verify_round),
        _FakeStream(offer_round), _FakeStream(close)])
    p = _provider(create)
    with patch("fsr_playbooks.llm.openai_provider.dispatch",
               MagicMock(side_effect=_dispatch)), \
         patch("fsr_playbooks.llm.openai_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="build a playbook")],
            tools=_BUILD_TOOLS, tags={})))
    assert isinstance(events[-1], DoneEvent)
    assert create.await_count == 4  # no extra nudged round
