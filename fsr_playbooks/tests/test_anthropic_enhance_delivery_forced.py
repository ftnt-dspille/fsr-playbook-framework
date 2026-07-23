"""Anthropic parity for the enhance-delivery guard — the same e3 failure driven
through the real AnthropicProvider.stream() with a faked streaming client.

Mirrors test_openai_enhance_delivery_forced.py. GA's default is OpenAI, but the
ship installs an `fsrpb-anthropic` (claude-haiku) fallback config, so the
Anthropic branch of the guard must be proven too — especially its distinct
forced round (`messages.create` + `tool_choice={"type":"tool",...}`, parsing
`resp.content` for the tool_use block).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
from fsr_playbooks.llm.provider import DoneEvent, Message, ToolResultEvent, ToolUseEvent


def _usage(inp=10, out=5):
    return MagicMock(input_tokens=inp, output_tokens=out,
                     cache_read_input_tokens=0, cache_creation_input_tokens=0)


def _text_block(text):
    return MagicMock(type="text", text=text)


def _tool_use_block(id, name, input):
    # `name` is reserved by the MagicMock constructor (sets the mock's repr name,
    # not an attribute), so assign it after construction or block.name comes back
    # as a mock and never matches allowed_names.
    b = MagicMock(type="tool_use", id=id, input=input)
    b.name = name
    return b


class _FakeStream:
    """Stands in for `self._client.messages.stream(...)` — an async CM that is
    itself async-iterable (text deltas) and exposes get_final_message()."""
    def __init__(self, text_deltas, final_msg):
        self._deltas = text_deltas
        self._final = final_msg

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        async def gen():
            for t in self._deltas:
                ev = MagicMock()
                ev.type = "content_block_delta"
                ev.delta = MagicMock(type="text_delta", text=t)
                yield ev
        return gen()

    async def get_final_message(self):
        return self._final


_ENHANCE_TOOLS = [
    {"name": "verify_enhancement", "description": "verify an edit",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "emit_enhancement_offer", "description": "apply a verified edit",
     "input_schema": {"type": "object", "properties": {
         "id": {"type": "string"}, "summary": {"type": "string"},
         "verified_id": {"type": "string"}}}},
]


def _fake_dispatch(name, args):
    if name == "verify_enhancement":
        return {"ready_to_push": True, "verified_id": "v1",
                "diff_summary": {"summary": "adds a manual-input gate"}}
    if name == "emit_enhancement_offer":
        return {"ok": True, "card": {"type": "enhancement_offer"}}
    return {"ok": True}


async def _drain(gen):
    out = []
    async for ev in gen:
        out.append(ev)
    return out


def _provider(streams, forced_resp):
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(side_effect=streams)
    client.messages.create = AsyncMock(return_value=forced_resp)
    return AnthropicProvider(model="claude-haiku-4-5-20251001",
                             base_url="http://x", api_key="x", client=client)


def _forced_resp(verified_id="STALE-WRONG"):
    return MagicMock(content=[_tool_use_block(
        "c_forced", "emit_enhancement_offer",
        {"id": "card1", "summary": "adds a gate", "verified_id": verified_id})])


def test_narrated_delivery_is_forced_into_a_real_offer_call():
    # Turn 1: verify_enhancement (passes). Turn 2: prose narration, end_turn, no
    # tool call — the e3 shape. Then the guard's forced tool_choice round.
    turn1 = _FakeStream([], MagicMock(
        content=[_tool_use_block("c1", "verify_enhancement", {})],
        stop_reason="tool_use", usage=_usage()))
    turn2 = _FakeStream(["The edit is verified. "],
                        MagicMock(content=[_text_block(
                            "The edit is verified. Call emit_enhancement_offer "
                            "with verified_id v1 to apply it.")],
                            stop_reason="end_turn", usage=_usage()))
    p = _provider([turn1, turn2], _forced_resp())

    disp = MagicMock(side_effect=_fake_dispatch)
    with patch("fsr_playbooks.llm.anthropic_provider.dispatch", disp), \
         patch("fsr_playbooks.llm.anthropic_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="rewire the branch")],
            tools=_ENHANCE_TOOLS, tags={})))

    offer_uses = [e for e in events
                  if isinstance(e, ToolUseEvent) and e.name == "emit_enhancement_offer"]
    assert len(offer_uses) == 1, "guard did not force the offer call"

    offer_dispatch = [c for c in disp.call_args_list
                      if c[0][0] == "emit_enhancement_offer"]
    assert len(offer_dispatch) == 1
    # The blessed handle wins over the model's stale one.
    assert offer_dispatch[0][0][1]["verified_id"] == "v1"

    assert any(isinstance(e, ToolResultEvent)
               and isinstance(e.result, dict) and e.result.get("card")
               for e in events)
    assert isinstance(events[-1], DoneEvent)


def test_no_force_when_offer_already_made():
    # Turn 1 verifies AND offers in the same turn (the healthy path). The guard
    # must stay inert — no forced round, create() never called.
    turn1 = _FakeStream([], MagicMock(
        content=[_tool_use_block("c1", "verify_enhancement", {}),
                 _tool_use_block("c2", "emit_enhancement_offer",
                                 {"id": "x", "summary": "s", "verified_id": "v1"})],
        stop_reason="tool_use", usage=_usage()))
    turn2 = _FakeStream(["Done — applied."],
                        MagicMock(content=[_text_block("Done — applied.")],
                                  stop_reason="end_turn", usage=_usage()))
    forced = _forced_resp()
    p = _provider([turn1, turn2], forced)
    with patch("fsr_playbooks.llm.anthropic_provider.dispatch",
               MagicMock(side_effect=_fake_dispatch)), \
         patch("fsr_playbooks.llm.anthropic_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="rewire")],
            tools=_ENHANCE_TOOLS, tags={})))
    # Exactly one offer (the model's own), and the forced create() never fired.
    offer_uses = [e for e in events
                  if isinstance(e, ToolUseEvent) and e.name == "emit_enhancement_offer"]
    assert len(offer_uses) == 1
    p._client.messages.create.assert_not_called()
    assert isinstance(events[-1], DoneEvent)
