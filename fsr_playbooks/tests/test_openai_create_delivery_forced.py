"""End-to-end: the create-delivery guard forces a real playbook offer through
the ACTUAL OpenAIProvider loop -- the live widget failure, reproduced.

Observed on box .159 (connector 0.5.64, gpt-4.1-mini): a build turn ran
`get_step_type` / `find_connector` / `find_operation`, drafted YAML, passed
`verify_playbook`, then closed with "Next, I will author a playbook that
triggers on a phishing alert ..." and ended. No `emit_playbook_offer`, so the
chat showed prose and the analyst had no card to accept -- nothing to click
"Save as Playbook" on.

This drives that transcript through the real loop and asserts the guard converts
it into a deterministic tool call carrying the VERIFIED bytes.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import DoneEvent, Message, ToolResultEvent, ToolUseEvent

VERIFIED_YAML = "playbooks:\n  - name: Phishing Alert - Domain Enrichment\n"


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


_BUILD_TOOLS = [
    {"type": "function", "function": {
        "name": "verify_playbook", "description": "pre-submit gate",
        "parameters": {"type": "object", "properties": {
            "yaml_text": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "emit_playbook_offer", "description": "offer to save",
        "parameters": {"type": "object", "properties": {
            "id": {"type": "string"}, "summary": {"type": "string"},
            "yaml": {"type": "string"}}}}},
]


async def _drain(gen):
    out = []
    async for ev in gen:
        out.append(ev)
    return out


def _fake_dispatch(name, args):
    if name == "verify_playbook":
        return {"ready_to_push": True, "summary": "enriches the sender domain"}
    if name == "emit_playbook_offer":
        return {"ok": True, "card": {"type": "playbook_offer"}}
    return {"ok": True}


def _forced_response():
    """The tool_choice-pinned round the guard triggers. The model supplies WRONG
    yaml on purpose -- only verified bytes may reach the card."""
    tc = MagicMock(id="c_forced")
    tc.function = MagicMock(arguments=json.dumps(
        {"id": "offer1", "summary": "enriches sender domain",
         "yaml": "playbooks:\n  - name: HALLUCINATED\n"}))
    msg = MagicMock(tool_calls=[tc])
    return MagicMock(choices=[MagicMock(message=msg)])


def _narrated_turns():
    """Turn 1: verify_playbook passes. Turn 2: prose promising to author."""
    turn1 = [
        _delta_chunk(tool_calls=[_tool_call_delta(
            index=0, id="c1", name="verify_playbook",
            args=json.dumps({"yaml_text": VERIFIED_YAML}))]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    turn2 = [
        _delta_chunk(content="Next, I will author a playbook that triggers on a "
                             "phishing alert and enriches the sender domain."),
        _delta_chunk(finish="stop"), _usage_chunk(),
    ]
    return turn1, turn2


def _provider(create):
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=create)
    return OpenAIProvider(model="gpt-4.1-mini", base_url="http://x/v1",
                          api_key="x", client=client)


def test_narrated_build_is_forced_into_a_real_offer_call():
    turn1, turn2 = _narrated_turns()
    create = AsyncMock(side_effect=[
        _FakeStream(turn1), _FakeStream(turn2), _forced_response()])
    p = _provider(create)

    disp = MagicMock(side_effect=_fake_dispatch)
    with patch("fsr_playbooks.llm.openai_provider.dispatch", disp), \
         patch("fsr_playbooks.llm.openai_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s",
            messages=[Message(role="user", content="build a phishing playbook")],
            tools=_BUILD_TOOLS, tags={})))

    # The offer tool was actually CALLED, not narrated.
    offer_uses = [e for e in events
                  if isinstance(e, ToolUseEvent) and e.name == "emit_playbook_offer"]
    assert len(offer_uses) == 1, "guard did not force the offer call"

    # And it carries the VERIFIED bytes, not the model's hallucinated YAML.
    offer_dispatch = [c for c in disp.call_args_list
                      if c[0][0] == "emit_playbook_offer"]
    assert len(offer_dispatch) == 1
    assert offer_dispatch[0][0][1]["yaml"] == VERIFIED_YAML

    # A card reached the stream and the turn closed cleanly.
    assert any(isinstance(e, ToolResultEvent)
               and isinstance(e.result, dict)
               and e.result.get("card") for e in events)
    assert isinstance(events[-1], DoneEvent)


def test_forced_create_delivery_fires_at_most_once():
    # If the forced round itself delivers nothing, the guard must not loop.
    turn1, turn2 = _narrated_turns()
    empty_forced = MagicMock(choices=[MagicMock(message=MagicMock(tool_calls=None))])
    create = AsyncMock(side_effect=[
        _FakeStream(turn1), _FakeStream(turn2), empty_forced])
    p = _provider(create)
    with patch("fsr_playbooks.llm.openai_provider.dispatch",
               MagicMock(side_effect=_fake_dispatch)), \
         patch("fsr_playbooks.llm.openai_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="build one")],
            tools=_BUILD_TOOLS, tags={})))
    assert isinstance(events[-1], DoneEvent)
    # turn1, turn2, ONE forced round.
    assert create.await_count == 3


def test_offer_already_delivered_is_not_forced():
    # The happy path (also seen live): the model calls the offer itself. The
    # guard must stay out of the way -- no second, duplicate card.
    turn1 = [
        _delta_chunk(tool_calls=[_tool_call_delta(
            index=0, id="c1", name="verify_playbook",
            args=json.dumps({"yaml_text": VERIFIED_YAML}))]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    turn2 = [
        _delta_chunk(tool_calls=[_tool_call_delta(
            index=0, id="c2", name="emit_playbook_offer",
            args=json.dumps({"id": "o1", "summary": "s", "yaml": VERIFIED_YAML}))]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    turn3 = [_delta_chunk(content="Saved as a draft playbook."),
             _delta_chunk(finish="stop"), _usage_chunk()]
    create = AsyncMock(side_effect=[
        _FakeStream(turn1), _FakeStream(turn2), _FakeStream(turn3)])
    p = _provider(create)
    with patch("fsr_playbooks.llm.openai_provider.dispatch",
               MagicMock(side_effect=_fake_dispatch)), \
         patch("fsr_playbooks.llm.openai_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="build one")],
            tools=_BUILD_TOOLS, tags={})))
    offer_uses = [e for e in events
                  if isinstance(e, ToolUseEvent) and e.name == "emit_playbook_offer"]
    assert len(offer_uses) == 1, "guard forced a duplicate offer"
    # No forced round: exactly the three modelled turns.
    assert create.await_count == 3
