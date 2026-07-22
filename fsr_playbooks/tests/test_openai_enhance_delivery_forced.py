"""End-to-end: the enhance-delivery guard forces a real offer through the ACTUAL
OpenAIProvider loop — the exact e3 failure, reproduced against a fake client.

e3 on GA (gpt-4.1-mini): the model runs `verify_enhancement` (passes, gets a
`verified_id`), then on the next round writes "Call emit_enhancement_offer with
verified_id … to apply this" as PROSE and stops — narrating the terminal action
instead of taking it. `score_enhance_delivery` graded that `verified_not_applied`
1-in-4 runs. This test drives that transcript through the real loop and asserts
the guard converts it to a deterministic tool call.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import DoneEvent, Message, ToolResultEvent, ToolUseEvent


def _delta_chunk(*, content=None, tool_calls=None, finish=None):
    delta = MagicMock(content=content, tool_calls=tool_calls)
    choice = MagicMock(delta=delta, finish_reason=finish)
    return MagicMock(choices=[choice], usage=None)


def _usage_chunk(prompt=10, completion=5):
    return MagicMock(choices=[], usage=MagicMock(prompt_tokens=prompt,
                                                 completion_tokens=completion))


def _tool_call_delta(*, index, id=None, name=None, args=None):
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


_ENHANCE_TOOLS = [
    {"type": "function", "function": {
        "name": "verify_enhancement", "description": "verify an edit",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "emit_enhancement_offer", "description": "apply a verified edit",
        "parameters": {"type": "object", "properties": {
            "id": {"type": "string"}, "summary": {"type": "string"},
            "verified_id": {"type": "string"}}}}},
]


async def _drain(gen):
    out = []
    async for ev in gen:
        out.append(ev)
    return out


def _fake_dispatch(name, args):
    if name == "verify_enhancement":
        return {"ready_to_push": True, "verified_id": "v1",
                "diff_summary": {"summary": "adds a manual-input gate"}}
    if name == "emit_enhancement_offer":
        return {"ok": True, "card": {"type": "enhancement_offer"}}
    return {"ok": True}


def _forced_response():
    """The non-streaming, tool_choice-pinned round the guard triggers. The model
    supplies a WRONG verified_id on purpose — the guard must override it."""
    tc = MagicMock(id="c_forced")
    tc.function = MagicMock(arguments=json.dumps(
        {"id": "card1", "summary": "adds a gate", "verified_id": "STALE-WRONG"}))
    msg = MagicMock(tool_calls=[tc])
    return MagicMock(choices=[MagicMock(message=msg)])


def test_narrated_delivery_is_forced_into_a_real_offer_call():
    # Turn 1: verify_enhancement (passes). Turn 2: prose narration, no tool call
    # (finish="stop") — verbatim e3. Then the guard's forced offer round.
    turn1 = [
        _delta_chunk(tool_calls=[_tool_call_delta(
            index=0, id="c1", name="verify_enhancement", args="{}")]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    turn2 = [
        _delta_chunk(content="The edit is verified and ready. Call "
                             "emit_enhancement_offer with verified_id v1 to apply it."),
        _delta_chunk(finish="stop"), _usage_chunk(),
    ]
    create = AsyncMock(side_effect=[
        _FakeStream(turn1), _FakeStream(turn2), _forced_response()])
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=create)
    p = OpenAIProvider(model="gpt-4.1-mini", base_url="http://x/v1",
                       api_key="x", client=client)

    disp = MagicMock(side_effect=_fake_dispatch)
    with patch("fsr_playbooks.llm.openai_provider.dispatch", disp), \
         patch("fsr_playbooks.llm.openai_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="rewire the branch")],
            tools=_ENHANCE_TOOLS, tags={})))

    # The offer tool was actually CALLED (not just narrated).
    offer_uses = [e for e in events
                  if isinstance(e, ToolUseEvent) and e.name == "emit_enhancement_offer"]
    assert len(offer_uses) == 1, "guard did not force the offer call"

    # And it was dispatched with the BLESSED handle, not the model's stale one.
    offer_dispatch = [c for c in disp.call_args_list
                      if c[0][0] == "emit_enhancement_offer"]
    assert len(offer_dispatch) == 1
    assert offer_dispatch[0][0][1]["verified_id"] == "v1"

    # A card result reached the stream, and the turn closed cleanly.
    assert any(isinstance(e, ToolResultEvent)
               and isinstance(e.result, dict)
               and e.result.get("card") for e in events)
    assert isinstance(events[-1], DoneEvent)


def test_forced_delivery_fires_at_most_once():
    # If the FORCED round itself somehow still didn't deliver, the guard must not
    # loop — outstanding() returns None after mark_forced(). Here the forced round
    # returns no tool_calls; the turn must still terminate.
    turn1 = [
        _delta_chunk(tool_calls=[_tool_call_delta(
            index=0, id="c1", name="verify_enhancement", args="{}")]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    turn2 = [_delta_chunk(content="narration only"),
             _delta_chunk(finish="stop"), _usage_chunk()]
    empty_forced = MagicMock(choices=[MagicMock(message=MagicMock(tool_calls=None))])
    create = AsyncMock(side_effect=[
        _FakeStream(turn1), _FakeStream(turn2), empty_forced])
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=create)
    p = OpenAIProvider(model="gpt-4.1-mini", base_url="http://x/v1",
                       api_key="x", client=client)
    with patch("fsr_playbooks.llm.openai_provider.dispatch",
               MagicMock(side_effect=_fake_dispatch)), \
         patch("fsr_playbooks.llm.openai_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="rewire")],
            tools=_ENHANCE_TOOLS, tags={})))
    # Terminates (no infinite loop) even when the forced round is empty.
    assert isinstance(events[-1], DoneEvent)
    # create called exactly 3×: turn1, turn2, ONE forced round.
    assert create.await_count == 3
